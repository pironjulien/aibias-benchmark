import tempfile
import unittest
from itertools import pairwise
from pathlib import Path

from aibias import core, queue


class Queue(unittest.TestCase):
    def setUp(self):
        self.models = core.load_models()['models']
        self.configs = [m for m in self.models if m.get('provider') == 'app' and m.get('setup')]

    def test_every_configuration_and_language_exactly_once(self):
        got = queue.entries(self.models)
        want = sorted((m['id'], lang) for m in self.configs for lang in m['langs'])
        self.assertEqual(sorted((e[0], e[4]) for e in got), want)
        self.assertEqual(len(got), len(set(got)))
        self.assertEqual(len(got), 22)

    def test_selection_labels_come_from_the_configuration(self):
        by_id = {m['id']: m for m in self.configs}
        for mid, app, ui_model, ui_level, _ in queue.entries(self.models):
            self.assertEqual((ui_model, ui_level), (by_id[mid]['ui_model'], by_id[mid]['ui_level']))
            self.assertEqual(app, queue.app_of(mid))
        # every model x level pair asked by Julien is in the queue
        pairs = {(e[1], e[2], e[3]) for e in queue.entries(self.models)}
        for app, model, levels in (('claude', 'Fable 5.1', 'Moyen Max'), ('claude', 'Opus 5.5', 'Moyen Max'),
                                   ('claude', 'Sonnet 5.5', 'Moyen Max'), ('codex', 'GPT-6.1 Sol', 'Medium Ultra'),
                                   ('codex', 'GPT-6 Astra', 'Medium Ultra'), ('codex', 'GPT-6 Luna', 'Medium Max'),
                                   ('antigravity', 'Gemini 4 Argon', 'Medium High'),
                                   ('antigravity', 'Gemini 3.8 Flash', 'Medium High')):
            for lv in levels.split():
                self.assertIn((app, model, lv), pairs)

    def test_the_queue_never_stays_on_one_model(self):
        for app in ('claude', 'codex', 'antigravity'):
            seq = [e for e in queue.entries(self.models, app) if not e[0].endswith('-pact')]
            en = [e[0] for e in seq if e[4] == 'en']
            self.assertEqual(len(en), len(set(en)))
            self.assertTrue(all(a != b for a, b in pairwise(en)))
            # consecutive entries switch model, not only level
            models = [e[2] for e in seq if e[4] == 'en']
            self.assertTrue(all(a != b for a, b in pairwise(models)), models)
            self.assertTrue(queue.entries(self.models, app)[-1][0].endswith('-pact'))

    def test_duplicates_are_refused(self):
        dup = self.configs[0]
        with self.assertRaises(ValueError):
            queue.entries(self.models + [dup])

    def test_a_batch_is_sent_at_most_twice(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / '.attempts.json'
            self.assertTrue(queue.may_send(queue.load_attempts(f), 'neutral01-en'))
            queue.record_send(f, 'neutral01-en')
            self.assertTrue(queue.may_send(queue.load_attempts(f), 'neutral01-en'))
            queue.record_send(f, 'neutral01-en')
            self.assertFalse(queue.may_send(queue.load_attempts(f), 'neutral01-en'))
            self.assertTrue(queue.may_send(queue.load_attempts(f), 'neutral02-en'))



if __name__ == '__main__':
    unittest.main()
