import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from aibias import core, queue

ROOT = Path(__file__).resolve().parent.parent


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
            self.assertTrue(all(a != b for a, b in zip(en, en[1:])))
            # consecutive entries switch model, not only level
            models = [e[2] for e in seq if e[4] == 'en']
            self.assertTrue(all(a != b for a, b in zip(models, models[1:])), models)
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


def _bash():
    # On Windows, Git Bash: the first `bash` on PATH is often WSL's (System32), which cannot read Windows paths.
    if os.name == 'nt':
        git = shutil.which('git')
        if git:
            candidate = Path(git).resolve().parents[1] / 'bin' / 'bash.exe'
            if candidate.exists():
                return str(candidate)
        return r'C:\Program Files\Git\bin\bash.exe'
    return shutil.which('bash') or '/bin/bash'


BASH = _bash()


@unittest.skipUnless(Path(BASH).exists(), 'bash not available')
@unittest.skipUnless((ROOT / 'tools' / 'run_queue.sh').exists(), 'app-collection tools are local only')
class RunQueueScript(unittest.TestCase):
    def run_queue(self, app, fake_exit=0):
        with tempfile.TemporaryDirectory() as d:
            calls = Path(d) / 'calls.jsonl'
            fake = Path(d) / 'fake.py'
            fake.write_text(
                'import json,sys\n'
                f'open(r"{calls}","a",encoding="utf-8").write(json.dumps(sys.argv[1:])+chr(10))\n'
                f'sys.exit({fake_exit})\n', encoding='utf-8')
            env = {**os.environ, 'AIBIAS_ROOT': ROOT.as_posix(), 'COLLECT': f'python -B {fake.as_posix()}'}
            r = subprocess.run([BASH, (ROOT / 'tools' / 'run_queue.sh').as_posix(), app, '123', '1'], env=env,
                               capture_output=True, encoding='utf-8')
            lines = calls.read_text(encoding='utf-8').splitlines() if calls.exists() else []
            return r.returncode, [json.loads(x) for x in lines]

    def test_script_runs_each_configuration_once_with_its_selection(self):
        code, calls = self.run_queue('claude')
        self.assertEqual(code, 0)
        got = []
        for args in calls:
            a = dict(zip(args[::2], args[1::2]))
            got.append((a['--model'], a['--select-model'], a['--select-level'], a['--lang']))
        want = [(e[0], e[2], e[3], e[4]) for e in queue.entries(core.load_models()['models'], 'claude')]
        self.assertEqual(got, want)
        self.assertEqual(len(got), len(set(got)))

    def test_script_stops_on_arret(self):
        code, calls = self.run_queue('codex', fake_exit=2)
        self.assertEqual(code, 2)
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
