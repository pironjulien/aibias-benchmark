"""Publishable results: ranking (all questions, aggregated) + side-by-side answers (public questions only).

The private lot never appears in the output: only aggregated metrics use it.
"""
import json
from pathlib import Path

from . import core, run


def side_by_side(items, rows_by_model, model_ids, k=0):
    personas_used = set()
    out = []
    for it in items:
        if it['lot'] != 'public':
            continue
        answers = {}
        for mid in model_ids:
            cell = {}
            for cond in ('neutral', 'persona_yes', 'persona_no'):
                r = rows_by_model[mid].get((it['id'], cond, k))
                if r:
                    cell[cond] = {'label': r['label'], 'text': r['content'].strip()}
            if cell:
                answers[mid] = cell
        for p in (it['persona_yes'], it['persona_no']):
            if p:
                personas_used.add(p)
        out.append({'id': it['id'], 'type': it['type'], 'topic': it['topic'], 'q': it['en'],
                    'persona_yes': it['persona_yes'], 'persona_no': it['persona_no'],
                    'reference': it['reference'], 'sources': it['sources'], 'answers': answers})
    return out, personas_used


def build(run_dir, model_ids, langs=('en',), excluded_names=None, judge_note='', repo_url=None, date=None):
    items = core.load_items()
    cfg = core.load_models()
    by_id = {m['id']: m for m in cfg['models']}
    rep = run.report(run_dir, items, model_ids, ('public', 'private'), langs)
    ranked = [m for m in model_ids if m in rep['models']]
    rows_by_model = {}
    for mid in ranked:
        rows_by_model[mid] = {(r['item'], r['cond'], r['k']): r for r in run.joined_rows(run_dir, mid)
                              if r['lang'] == langs[0]}
    questions, used = side_by_side(items, rows_by_model, ranked)
    personas = core.load_personas()

    def metric(mid, name, scale=1):
        m = rep['models'][mid]['metrics'][name]
        lo, hi = m['ci95']
        return {'value': None if m['value'] is None else round(m['value'] * scale, 4),
                'lo': None if lo is None else round(lo * scale, 4), 'hi': None if hi is None else round(hi * scale, 4)}

    models = []
    for mid in ranked:
        meta = by_id[mid]
        models.append({'id': mid, 'name': meta.get('name', mid), 'setting': meta.get('setting', meta.get('app_setting', '')),
                       'access': 'app' if meta['provider'] == 'app' else 'api',
                       'samples': rep['models'][mid]['samples'],
                       'score': metric(mid, 'score'), **{n: metric(mid, n) for n in
                                                         ('candor', 'accuracy', 'false_certainty', 'persona_shift', 'caves')}})
    models.sort(key=lambda m: -(m['score']['value'] or 0))
    excluded = [{'name': n, 'reason': 'incomplete'} for n in (excluded_names or [])]
    excluded += [{'name': by_id[m].get('name', m), 'reason': 'incomplete'} for m in rep['excluded']]
    return {'version': '2.0.0-preview', 'date': date, 'lang': langs[0], 'items_total': len(items),
            'items_public': sum(i['lot'] == 'public' for i in items),
            'judge': {'model': 'Qwen 3 14B (local, never the family of the judged model)', 'validation': judge_note},
            'repo_url': repo_url, 'models': models, 'excluded': excluded, 'questions': questions,
            'personas': {p: personas[p][langs[0]][0] for p in sorted(used)}}


def write(data, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
