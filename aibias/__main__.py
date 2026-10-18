"""CLI: python -m aibias {check,run,label,report,sample,agree,estimate}"""
import argparse
import csv
import json
import random
import sys
from pathlib import Path

from . import apps, core, publish, queue, run


def main(argv=None):
    ap = argparse.ArgumentParser(prog='aibias')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('check', help='validate data files')
    sub.add_parser('public-items', help='write data/items.public.jsonl (public lot only, for the public repo)')
    q = sub.add_parser('app-queue', help='collection queue: one line per app configuration and language')
    q.add_argument('--app', choices=sorted(set(queue.APPS.values())))
    for name in ('run', 'label', 'report', 'sample', 'agree', 'estimate', 'app-prompts', 'app-import', 'publish'):
        p = sub.add_parser(name)
        p.add_argument('--run', required=True, help='run directory, e.g. runs/pilot-2026-10-18')
        p.add_argument('--models', default='')
        p.add_argument('--items', default='', help='comma-separated item ids (default: all)')
        p.add_argument('--samples', type=int, default=5)
        p.add_argument('--langs', default='en,fr')
        p.add_argument('--conditions', default=','.join(core.CONDITIONS))
        p.add_argument('--workers', type=int, default=8)
        p.add_argument('--n', type=int, default=60)
        p.add_argument('--human', default='')
        p.add_argument('--full-items', type=int, default=240)
        p.add_argument('--batch', default='')
        p.add_argument('--answer', default='', help='file holding the app answer')
        p.add_argument('--pushback', default='', help='file holding the answer to the challenge turn')
        p.add_argument('--k', type=int, default=0, help='sample index (one fresh conversation per sample)')
        p.add_argument('--out', default='', help='publish: output JSON file')
        p.add_argument('--judge-note', default='', help='publish: judge validation status shown with the results')
        p.add_argument('--repo-url', default=None)
        p.add_argument('--date', default=None)
        p.add_argument('--setup', default='clean', choices=apps.SETUPS,
                       help='app-prompts: clean = ask the app to ignore custom instructions and memory; pact = as used')
    a = ap.parse_args(argv)

    items = core.load_items()
    cfg = core.load_models()
    by_id = {m['id']: m for m in cfg['models']}
    if a.cmd == 'check':
        print(f"{len(items)} items OK ({sum(i['lot'] == 'private' for i in items)} private), "
              f"{len(cfg['models'])} models")
        return 0
    if a.cmd == 'public-items':
        public = [i for i in items if i['lot'] == 'public']
        (core.DATA / 'items.public.jsonl').write_text(
            ''.join(json.dumps(i, ensure_ascii=False) + '\n' for i in public), encoding='utf-8')
        print(f'{len(public)} public items written')
        return 0
    if a.cmd == 'app-queue':
        for mid, app, ui_model, ui_level, lang in queue.entries(cfg['models'], a.app):
            print(f'{mid}|{app}|{ui_model}|{ui_level}|{lang}')
        return 0
    run_dir = Path(a.run)
    model_ids = [m for m in a.models.split(',') if m] or sorted(
        p.stem for p in (run_dir / 'responses').glob('*.jsonl'))
    if a.items:
        wanted = set(a.items.split(','))
        items = [i for i in items if i['id'] in wanted]
    langs, conds = a.langs.split(','), a.conditions.split(',')

    if a.cmd == 'run':
        (run_dir).mkdir(parents=True, exist_ok=True)
        meta = run_dir / 'run.json'
        if not meta.exists():
            meta.write_text(json.dumps({'prompt_version': core.PROMPT_VERSION, 'temperature': run.TEMPERATURE,
                                        'max_tokens': run.MAX_TOKENS, 'samples': a.samples, 'langs': langs,
                                        'conditions': conds, 'items': [i['id'] for i in items]}, indent=2))
        bad = 0
        for mid in model_ids:
            _, errors = run.run_model(run_dir, by_id[mid], cfg['providers'], items, conds, langs, a.samples,
                                      a.workers)
            for e in errors[:5]:
                print('  ', e)
            bad += len(errors)
        return 1 if bad else 0
    if a.cmd == 'app-prompts':
        personas = core.load_personas()
        out = run_dir / 'app-prompts' / a.setup
        out.mkdir(parents=True, exist_ok=True)
        for lang in langs:
            for bid, pk, rows in apps.batches(items, personas, lang):
                (out / f'{bid}.txt').write_text(apps.batch_prompt(pk, rows, lang, personas, a.k, a.setup),
                                                encoding='utf-8')
                print(bid, len(rows))
        return 0
    if a.cmd == 'app-import':
        personas = core.load_personas()
        lang = a.batch.rsplit('-', 1)[1]
        bid, pk, rows = next(b for b in apps.batches(items, personas, lang) if b[0] == a.batch)
        setup = by_id[model_ids[0]].get('setup', 'clean')
        prompt = apps.batch_prompt(pk, rows, lang, personas, a.k, setup)
        read = lambda f: Path(f).read_text(encoding='utf-8') if f else None
        # The prompt file is what was pasted into the app: it must match today's items and generator,
        # otherwise the stored record would not be what the model actually read.
        sent = run_dir / 'app-prompts' / setup / f'{bid}.txt'
        if not sent.exists() or sent.read_text(encoding='utf-8').strip() != prompt.strip():
            print(f'refused: {sent} is missing or differs from the generated prompt; '
                  'regenerate with app-prompts and collect this batch again')
            return 1
        n = apps.import_batch(run_dir, model_ids[0], bid, pk, rows, lang, prompt, read(a.answer), a.k, read(a.pushback))
        print(f'{model_ids[0]} {bid}: {n} answers imported')
        return 0
    if a.cmd == 'publish':
        data = publish.build(run_dir, model_ids, tuple(langs), judge_note=a.judge_note, repo_url=a.repo_url,
                             date=a.date)
        publish.write(data, a.out)
        print(f"{a.out}: {len(data['models'])} ranked, {len(data['excluded'])} excluded, "
              f"{len(data['questions'])} public questions")
        return 0
    if a.cmd == 'label':
        for mid in model_ids:
            labels = run.label_model(run_dir, by_id[mid], by_id, cfg['judges'], cfg['providers'], items, a.workers,
                                     langs=langs)
            cert = run.certainty_model(run_dir, by_id[mid], by_id, cfg['judges'], cfg['providers'], items, a.workers,
                                       langs=langs)
            print(f'{mid}: {len(labels.rows)} labels, {len(cert.rows)} certainty labels')
        return 0
    if a.cmd == 'report':
        for name, lots in (('summary', ('public', 'private')), ('summary-public', ('public',)),
                           ('summary-private', ('private',))):
            rep = run.report(run_dir, items, model_ids, lots, langs)
            (run_dir / f'{name}.json').write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding='utf-8')
            (run_dir / f'{name}.md').write_text(run.markdown(rep), encoding='utf-8')
        print(run.markdown(json.loads((run_dir / 'summary.json').read_text(encoding='utf-8'))))
        return 0
    if a.cmd == 'sample':
        # Blind sheet for human labelling: answers only, no machine label.
        rows = [r for mid in model_ids for r in run.joined_rows(run_dir, mid) if r['content'].strip()]
        rng = random.Random(1618)
        rng.shuffle(rows)
        by_item = {i['id']: i for i in core.load_items()}
        out = run_dir / 'human-sample.csv'
        with out.open('w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['key', 'question', 'earlier_answer', 'answer', 'human_label'])
            for r in rows[:a.n]:
                earlier = r['messages'][1]['content'] if r['cond'] == 'pushback' else ''
                w.writerow([r['key'], by_item[r['item']][r['lang']], earlier, r['content'], ''])
        print(f'{out} written ({min(a.n, len(rows))} rows); labels: {", ".join(core.LABELS)}')
        return 0
    if a.cmd == 'agree':
        human = {r['key']: r['human_label'].strip().upper()
                 for r in csv.DictReader(open(a.human, encoding='utf-8-sig')) if r['human_label'].strip()}
        machine = {}
        for mid in model_ids:
            machine.update({r['key']: r['label'] for r in run.joined_rows(run_dir, mid)})
        keys = [k for k in human if k in machine]
        h, m = [human[k] for k in keys], [machine[k] for k in keys]
        print(f'n={len(keys)} agreement={sum(x == y for x, y in zip(h, m)) / len(keys):.1%} '
              f'kappa={core.cohen_kappa(h, m):.3f}')
        return 0
    if a.cmd == 'estimate':
        usage = {}
        for mid in model_ids:
            rows = run.joined_rows(run_dir, mid)
            if rows:
                usage[mid] = run.usage_stats(rows)
        all_items = core.load_items()
        share = sum(i['persona_yes'] is not None for i in all_items) / len(all_items)
        rows, judge_calls = run.estimate(cfg['models'], usage, a.full_items, share, langs, a.samples)
        total = sum(r['usd'] for r in rows)
        for r in sorted(rows, key=lambda r: -r['usd']):
            print(f"{r['model']:22} {r['calls']:6} calls  ${r['usd']:8.2f}  {'measured' if r['measured'] else 'assumed'}")
        print(f'TOTAL ${total:.2f} for {a.full_items} items; judge calls ~{judge_calls} per model')
        return 0


if __name__ == '__main__':
    sys.exit(main())
