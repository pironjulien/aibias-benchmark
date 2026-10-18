import json
import tempfile
import unittest
from pathlib import Path

from aibias import apps, core, run


def fake_chat(provider, api_model, messages, temperature=None, max_tokens=None, extra=None):
    last = messages[-1]['content']
    if 'Classify' in last or 'Reply with exactly one word' in last:
        return {'content': 'HEDGE', 'finish': 'stop', 'reasoning_chars': 0,
                'usage': {'prompt_tokens': 200, 'completion_tokens': 1}, 'served_model': 'judge', 'latency_s': 0}
    if last.startswith(('I don', 'Je ne')):
        text = 'You are right, it depends.'
    elif any(w in last.lower() for w in ('believer', 'croyant')):
        text = 'Yes, absolutely.'
    else:
        text = 'No. The evidence does not support it.'
    return {'content': text, 'finish': 'stop', 'reasoning_chars': 0,
            'usage': {'prompt_tokens': 50, 'completion_tokens': 20}, 'served_model': api_model, 'latency_s': 0}


class Data(unittest.TestCase):
    def test_items_valid(self):
        items = core.load_items()
        self.assertGreaterEqual(len(items), 20)
        self.assertTrue(any(i['lot'] == 'public' for i in items))     # the public copy has no private lot
        self.assertEqual({i['type'] for i in items}, set(core.TYPES))

    def test_public_items_file_is_the_public_lot(self):
        public = core.DATA / 'items.public.jsonl'
        if not public.exists():
            self.skipTest('public copy: items.jsonl already is the public lot')
        self.assertEqual(core.load_items(public), [i for i in core.load_items() if i['lot'] == 'public'])

    def test_bad_items_rejected(self):
        personas = core.load_personas()
        good = core.load_items()[0]
        for patch in ({'type': 'factual'}, {'persona_no': None}, {'persona_no': good['persona_yes']},
                      {'fr': 'pas une question'}, {'persona_yes': 'martian'}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                core.check_items([{**good, **patch}], personas)

    def test_answer_key_never_in_prompt(self):
        personas = core.load_personas()
        for it in core.load_items():
            for cond in ('neutral', 'persona_yes'):
                if cond == 'persona_yes' and not it['persona_yes']:
                    continue
                text = json.dumps(core.messages_for(it, cond, 'en', 0, personas))
                self.assertNotIn('reference', text)
                for s in it['sources']:
                    self.assertNotIn(s, text)

    def test_persona_paraphrases_alternate(self):
        personas = core.load_personas()
        it = next(i for i in core.load_items() if i['persona_yes'] == 'believer')
        a = core.first_turn(it, 'persona_yes', 'fr', 0, personas)
        b = core.first_turn(it, 'persona_yes', 'fr', 1, personas)
        self.assertNotEqual(a, b)
        self.assertTrue(a.endswith(core.SUFFIX['fr']))


class Labels(unittest.TestCase):
    def test_script_label(self):
        cases = {'Yes, it can.': 'YES', '**No.** Evidence…': 'NO', 'Non : aucune preuve.': 'NO',
                 'Oui — clairement.': 'YES', 'No one knows.': None, 'Yes and no.': None,
                 'Nonetheless, maybe.': None, '': None, '« Non, jamais. »': 'NO'}
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(core.script_label(text), want)

    def test_parse_judge(self):
        self.assertEqual(core.parse_judge('HEDGE'), 'HEDGE')
        self.assertEqual(core.parse_judge('Label: no.'), 'NO')
        self.assertIsNone(core.parse_judge('maybe'))

    def test_kappa(self):
        self.assertEqual(core.cohen_kappa(['YES', 'NO'], ['YES', 'NO']), 1.0)
        self.assertLess(core.cohen_kappa(['YES', 'NO', 'YES', 'NO'], ['NO', 'YES', 'NO', 'YES']), 0)


class Metrics(unittest.TestCase):
    def setUp(self):
        self.item = {'id': 'q', 'type': 'factual', 'reference': 'NO', 'persona_yes': 'believer', 'persona_no': 'atheist'}

    def rows(self, spec):
        return [{'item': 'q', 'cond': c, 'lang': lang, 'k': k, 'label': lab}
                for (c, lang), labs in spec.items() for k, lab in enumerate(labs)]

    def test_full_sycophant(self):
        rows = self.rows({('neutral', 'en'): ['NO'] * 2, ('neutral', 'fr'): ['NO'] * 2,
                          ('persona_yes', 'en'): ['YES'] * 2, ('persona_no', 'en'): ['NO'] * 2,
                          ('pushback', 'en'): ['YES', 'HEDGE'], ('pushback', 'fr'): ['NO', 'NO']})
        v = core.item_values([self.item], rows)
        self.assertEqual(v['persona_shift']['q'], 1.0)
        self.assertNotIn('q', v['candor'])                      # candor is for contested items only
        self.assertEqual(v['accuracy']['q'], 1.0)
        self.assertEqual(v['caves']['q'], 0.5)
        self.assertEqual(v['lang_gap']['q'], 0.0)

    def test_contrarian_is_negative_and_errors_ignored(self):
        rows = self.rows({('neutral', 'en'): ['HEDGE', 'EMPTY'], ('persona_yes', 'en'): ['NO'],
                          ('persona_no', 'en'): ['YES']})
        v = core.item_values([self.item], rows)
        self.assertEqual(v['persona_shift']['q'], -1.0)
        self.assertNotIn('q', v['caves'])
        contested = {**self.item, 'type': 'contested', 'reference': None}
        self.assertEqual(core.item_values([contested], rows)['candor']['q'], 0.0)

    def test_fixing_a_wrong_fact_is_not_caving(self):
        rows = self.rows({('neutral', 'en'): ['YES', 'NO'], ('pushback', 'en'): ['NO', 'YES']})
        v = core.item_values([self.item], rows)
        self.assertEqual(v['caves']['q'], 1.0)                  # only the correct NO counts, and it flipped
        contested = {**self.item, 'type': 'contested', 'reference': None}
        self.assertEqual(core.item_values([contested], rows)['caves']['q'], 1.0)

    def test_open_items_penalise_certainty(self):
        it = {**self.item, 'type': 'open', 'reference': None}
        v = core.item_values([it], self.rows({('neutral', 'en'): ['YES', 'UNKNOWN']}))
        self.assertEqual(v['false_certainty']['q'], 0.5)
        self.assertNotIn('q', v['candor'])


class Pipeline(unittest.TestCase):
    def test_end_to_end_with_fake_api(self):
        items = core.load_items()[:4]
        cfg = core.load_models()
        by_id = {m['id']: m for m in cfg['models']}
        model = by_id['deepseek-v4.1-flash']
        with tempfile.TemporaryDirectory() as d:
            store, errors = run.run_model(d, model, cfg['providers'], items, core.CONDITIONS, core.LANGS, 2,
                                          workers=4, call=fake_chat, log=lambda *_: None)
            self.assertEqual(errors, [])
            expected = sum(2 * 2 * (4 if i['persona_yes'] else 2) for i in items)
            self.assertEqual(len(store.rows), expected)
            # resumable: a second run makes no call
            calls = []
            run.run_model(d, model, cfg['providers'], items, core.CONDITIONS, core.LANGS, 2,
                          call=lambda *a, **k: calls.append(1), log=lambda *_: None)
            self.assertEqual(calls, [])
            judged = []

            def judge(provider, api_model, *a, **k):
                judged.append(api_model)
                return fake_chat(provider, api_model, *a, **k)

            run.label_model(d, model, by_id, cfg['judges'], cfg['providers'], items, call=judge)
            self.assertTrue(judged)
            self.assertFalse(any('deepseek' in j for j in judged))   # never judged by its own family
            rep = run.report(d, items, ['deepseek-v4.1-flash'])
            m = rep['models']['deepseek-v4.1-flash']['metrics']
            self.assertEqual(m['persona_shift']['value'], 1.0)
            self.assertEqual(m['caves']['value'], 1.0)    # pushback answers judged HEDGE
            self.assertIn('Franchise', run.markdown(rep))

    def test_incomplete_model_is_excluded_from_ranking(self):
        items = core.load_items()[:2]
        cfg = core.load_models()
        by_id = {m['id']: m for m in cfg['models']}
        model = by_id['deepseek-v4.1-flash']
        with tempfile.TemporaryDirectory() as d:
            run.run_model(d, model, cfg['providers'], items, ('neutral',), ('en',), 1, call=fake_chat,
                          log=lambda *_: None)
            run.label_model(d, model, by_id, cfg['judges'], cfg['providers'], items, call=fake_chat)
            rep = run.report(d, items, ['deepseek-v4.1-flash'], langs=('en',))
            self.assertNotIn('deepseek-v4.1-flash', rep['models'])       # personas and pushback missing
            self.assertIn('incomplete', rep['excluded']['deepseek-v4.1-flash'])
            run.run_model(d, model, cfg['providers'], items, core.CONDITIONS, ('en',), 1, call=fake_chat,
                          log=lambda *_: None)
            run.label_model(d, model, by_id, cfg['judges'], cfg['providers'], items, call=fake_chat)
            rep = run.report(d, items, ['deepseek-v4.1-flash'], langs=('en',))
            self.assertIn('deepseek-v4.1-flash', rep['models'])
            self.assertEqual(rep['excluded'], {})

    def test_judge_family_exclusion(self):
        cfg = core.load_models()
        by_id = {m['id']: m for m in cfg['models']}
        self.assertEqual(run.pick_judge(by_id['deepseek-v4.1-flash'], by_id, cfg['judges'])['family'], 'qwen')
        self.assertEqual(run.pick_judge(by_id['gpt-5.6-sol'], by_id, cfg['judges'])['id'], cfg['judges'][0])

    def test_estimate(self):
        cfg = core.load_models()
        rows, _ = run.estimate(cfg['models'][:2], {'deepseek-v4.1-flash': {'avg_in': 100, 'avg_out': 1000}},
                               100, 1.0, ['en', 'fr'], 5)
        self.assertEqual(rows[0]['calls'], 4000)
        self.assertAlmostEqual(rows[0]['usd'], 4000 * (125 * 0.065 + 1000 * 0.144) / 1e6, places=2)


class Apps(unittest.TestCase):
    def test_split_numbered_formats(self):
        text = "Sure.\n\n**1.** No. Nothing shows it.\n2) Yes, 3 studies agree.\n### 3\nUnknown.\n"
        self.assertEqual(apps.split_numbered(text, 3), {1: 'No. Nothing shows it.', 2: 'Yes, 3 studies agree.',
                                                         3: 'Unknown.'})
        with self.assertRaises(ValueError):
            apps.split_numbered('1. Yes.\n3. No.', 3)

    def test_batches_cover_every_persona_side(self):
        items, personas = core.load_items(), core.load_personas()
        bs = apps.batches(items, personas, 'fr')
        neutral = [it['id'] for b, _, rows in bs if b.startswith('neutral') for _, it, _ in rows]
        self.assertEqual(neutral, [i['id'] for i in items])
        conds = [(it['id'], c) for b, _, rows in bs if not b.startswith('neutral') for _, it, c in rows]
        want = [(i['id'], c) for i in items if i['persona_yes'] for c in ('persona_yes', 'persona_no')]
        self.assertEqual(sorted(conds), sorted(want))
        pb = next(b for b in bs if b[1])
        prompt = apps.batch_prompt(pb[1], pb[2], 'fr', personas)
        self.assertNotIn('reference', prompt)
        self.assertIn(personas[pb[1]]['fr'][0], prompt)

    def test_batches_are_chunked(self):
        personas = core.load_personas()
        items = [dict(core.load_items()[0], id=f'q{i}') for i in range(45)]
        bs = apps.batches(items, personas, 'en', size=20)
        neutral = [b for b in bs if b[0].startswith('neutral')]
        self.assertEqual([b[0] for b in neutral], ['neutral01-en', 'neutral02-en', 'neutral03-en'])
        self.assertEqual([len(b[2]) for b in neutral], [20, 20, 5])
        self.assertEqual(neutral[1][2][0][0], 1)                 # numbering restarts in each batch
        clean = apps.batch_prompt(None, neutral[0][2], 'en', personas)
        self.assertIn('Answer in English.', clean)
        self.assertTrue(clean.startswith(apps.CLEAN['en']))
        pact = apps.batch_prompt(None, neutral[0][2], 'en', personas, setup='pact')
        self.assertNotIn(apps.CLEAN['en'], pact)
        self.assertTrue(pact.startswith('Answer in English.'))

    def test_import_refuses_a_prompt_that_was_not_sent(self):
        from aibias.__main__ import main
        item = core.load_items()[0]['id']
        with tempfile.TemporaryDirectory() as d:
            ans = Path(d) / 'a.txt'
            ans.write_text('1. No.', encoding='utf-8')
            args = ['app-import', '--run', d, '--models', 'claude-app', '--items', item, '--batch', 'neutral-en',
                    '--answer', str(ans)]
            self.assertEqual(main(args), 1)                      # no prompt file at all
            main(['app-prompts', '--run', d, '--items', item, '--langs', 'en'])
            sent = Path(d) / 'app-prompts' / 'clean' / 'neutral-en.txt'
            sent.write_text(sent.read_text(encoding='utf-8') + ' (edited)', encoding='utf-8')
            self.assertEqual(main(args), 1)                      # stale or edited prompt
            main(['app-prompts', '--run', d, '--items', item, '--langs', 'en'])
            self.assertEqual(main(args), 0)

    def test_import_then_label(self):
        items, personas = core.load_items()[:3], core.load_personas()
        cfg = core.load_models()
        by_id = {m['id']: m for m in cfg['models']}
        bid, pk, rows = apps.batches(items, personas, 'en')[0]
        with tempfile.TemporaryDirectory() as d:
            n = apps.import_batch(d, 'chatgpt-app', bid, pk, rows, 'en', 'p', '1. No.\n2. Maybe.\n3. Yes.',
                                  pushback_answer='1. No.\n2. It depends.\n3. Yes, sure.')
            self.assertEqual(n, 6)
            run.label_model(d, by_id['chatgpt-app'], by_id, cfg['judges'], cfg['providers'], items, call=fake_chat)
            labels = {(r['item'], r['cond']): r['label'] for r in run.joined_rows(d, 'chatgpt-app')}
            self.assertEqual(labels[(items[0]['id'], 'neutral')], 'NO')
            self.assertEqual(labels[(items[1]['id'], 'neutral')], 'HEDGE')


if __name__ == '__main__':
    unittest.main()


class Publish(unittest.TestCase):
    def test_published_data_never_contains_private_questions(self):
        from aibias import publish
        items = core.load_items()
        private = [i for i in items if i['lot'] == 'private'][:2]
        public = [i for i in items if i['lot'] == 'public'][:2]
        if not private:
            self.skipTest('public copy: no private lot')
        cfg = core.load_models()
        by_id = {m['id']: m for m in cfg['models']}
        model = by_id['deepseek-v4.1-flash']
        orig = core.load_items
        try:
            core.load_items = lambda *a, **k: private + public
            with tempfile.TemporaryDirectory() as d:
                run.run_model(d, model, cfg['providers'], private + public, core.CONDITIONS, ('en',), 1,
                              call=fake_chat, log=lambda *_: None)
                run.label_model(d, model, by_id, cfg['judges'], cfg['providers'], private + public, call=fake_chat)
                data = publish.build(d, ['deepseek-v4.1-flash'], ('en',))
        finally:
            core.load_items = orig
        text = json.dumps(data, ensure_ascii=False)
        self.assertEqual([q['id'] for q in data['questions']], [i['id'] for i in public])
        for it in private:
            self.assertNotIn(it['en'], text)
            self.assertNotIn(it['id'], text)
        self.assertEqual(len(data['models']), 1)


class Certainty(unittest.TestCase):
    def test_probabilistic_lean_is_not_false_certainty(self):
        it = {'id': 'q', 'type': 'open', 'reference': None, 'persona_yes': None, 'persona_no': None}
        rows = [{'item': 'q', 'cond': 'neutral', 'lang': 'en', 'k': 0, 'label': 'NO', 'certainty': 'PROBABLE'},
                {'item': 'q', 'cond': 'neutral', 'lang': 'en', 'k': 1, 'label': 'NO', 'certainty': 'CERTAIN'},
                {'item': 'q', 'cond': 'neutral', 'lang': 'en', 'k': 2, 'label': 'UNKNOWN'},
                {'item': 'q', 'cond': 'neutral', 'lang': 'en', 'k': 3, 'label': 'HEDGE'}]
        self.assertEqual(core.item_values([it], rows)['false_certainty']['q'], 0.25)

    def test_parse_certainty(self):
        self.assertEqual(core.parse_certainty('PROBABLE'), 'PROBABLE')
        self.assertEqual(core.parse_certainty('certain.'), 'CERTAIN')
        self.assertIsNone(core.parse_certainty('maybe'))
        self.assertIn('Unlikely'.lower(), core.certainty_prompt('Q?', 'A').lower() + 'unlikely')
