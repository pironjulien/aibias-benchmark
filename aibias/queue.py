"""Collection queue for the app track: every app configuration x language exactly once.

The queue is built from data/models.json, never typed by hand: each entry names the model and the level the
collector must select in the app before sending anything. Order: languages in turn, and inside a language the
configurations alternate between models and levels; the '-pact' bonus runs come last.
"""
import json
from pathlib import Path

from . import core

APPS = {'claude-': 'claude', 'codex-': 'codex', 'agy-': 'antigravity'}
MAX_SENDS = 2          # a batch is sent to the same app configuration at most twice


def app_of(model_id):
    return next((app for prefix, app in APPS.items() if model_id.startswith(prefix)), None)


def entries(models, app=None):
    """[(model_id, app, ui_model, ui_level, lang)], unique, in collection order."""
    configs = [m for m in models if m.get('provider') == 'app' and m.get('setup') and app_of(m['id'])
               and (app is None or app_of(m['id']) == app)]
    out = []
    for setup in ('clean', 'pact'):
        group = [m for m in configs if m['setup'] == setup]
        for lang in core.LANGS:
            # alternate levels first, then models: Opus Moyen, Sonnet Moyen, Fable Moyen, Opus Max, ...
            levels = sorted({m['ui_level'] for m in group if lang in m['langs']}, key=lambda lv: lv.lower())
            for lv in levels:
                for m in group:
                    if lang in m['langs'] and m['ui_level'] == lv:
                        out.append((m['id'], app_of(m['id']), m['ui_model'], m['ui_level'], lang))
    if len(set(out)) != len(out) or len({(e[0], e[4]) for e in out}) != len(out):
        raise ValueError('duplicate entry in the collection queue')
    return out


def expect(ui_model, ui_level):
    """Label the app shows for the selected model and level (checked before every batch)."""
    return f'{ui_model} {ui_level}'


def load_attempts(path):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def may_send(attempts, lot):
    return attempts.get(lot, 0) < MAX_SENDS


def record_send(path, lot):
    """Counts a send before it happens, so a crash cannot hide it."""
    path = Path(path)
    attempts = load_attempts(path)
    attempts[lot] = attempts.get(lot, 0) + 1
    path.write_text(json.dumps(attempts, indent=1, sort_keys=True), encoding='utf-8')
    return attempts[lot]
