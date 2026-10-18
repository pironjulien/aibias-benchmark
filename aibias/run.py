"""Network side: API client, resumable runner, judge, reports, cost estimate."""
import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import core

SECRETS = Path(os.environ.get('AIBIAS_SECRETS', Path.home() / '.aibias' / 'api-keys'))
TEMPERATURE = 0.618
MAX_TOKENS = 4096


class ApiError(Exception):
    pass


def chat(provider, api_model, messages, temperature=TEMPERATURE, max_tokens=MAX_TOKENS, retries=6, extra=None):
    key = (SECRETS / provider['key_file']).read_text(encoding='utf-8').strip() if provider.get('key_file') else 'none'
    body = json.dumps({'model': api_model, 'messages': messages, 'temperature': temperature,
                       'max_tokens': max_tokens, **(extra or {})}).encode()
    req = urllib.request.Request(provider['base_url'].rstrip('/') + '/chat/completions', data=body,
                                 headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
    for attempt in range(retries):
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode('utf-8', 'replace')
            if e.code not in (408, 409, 425, 429, 500, 502, 503, 504) or attempt == retries - 1:
                raise ApiError(f'HTTP {e.code}: {detail}') from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == retries - 1:
                raise ApiError(str(e)) from None
        time.sleep(1.618 ** attempt + random.random())
    if 'choices' not in data:
        raise ApiError(f'no choices: {str(data)[:300]}')
    ch = data['choices'][0]
    msg = ch.get('message') or {}
    return {'content': msg.get('content') or '', 'finish': ch.get('finish_reason'),
            'reasoning_chars': len(msg.get('reasoning_content') or msg.get('reasoning') or ''),
            'usage': data.get('usage', {}), 'served_model': data.get('model'),
            'latency_s': round(time.time() - t0, 2)}


class Store:
    """Append-only JSONL per model; a key present means the call is done."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.rows = {}
        if self.path.exists():
            for line in self.path.read_text(encoding='utf-8').splitlines():
                if line.strip():
                    r = json.loads(line)
                    self.rows[r['key']] = r

    def add(self, row):
        with self.lock:
            with self.path.open('a', encoding='utf-8') as f:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
            self.rows[row['key']] = row


def plan(items, conditions, langs, samples):
    jobs = []
    for it in items:
        for cond in conditions:
            if cond.startswith('persona') and it['persona_yes'] is None:
                continue
            for lang in langs:
                for k in range(samples):
                    jobs.append((it, cond, lang, k))
    return jobs


def run_model(run_dir, model, providers, items, conditions, langs, samples, workers=8, call=chat, log=print):
    personas = core.load_personas()
    store = Store(Path(run_dir) / 'responses' / f"{model['id']}.jsonl")
    errors = []

    def one(job):
        it, cond, lang, k = job
        key = core.job_key(model['id'], it['id'], cond, lang, k)
        if key in store.rows:
            return
        prev = None
        if cond == 'pushback':
            prev = store.rows.get(core.job_key(model['id'], it['id'], 'neutral', lang, k))
            if not prev or not prev['content']:
                return
        msgs = core.messages_for(it, cond, lang, k, personas, prev and prev['content'])
        try:
            res = call(providers[model['provider']], model['api_model'], msgs)
        except ApiError as e:
            errors.append(f"{it['id']}/{cond}/{lang}/{k}: {e}")
            return
        store.add({'key': key, 'model': model['id'], 'api_model': model['api_model'], 'item': it['id'],
                   'cond': cond, 'lang': lang, 'k': k, 'prompt_version': core.PROMPT_VERSION,
                   'temperature': TEMPERATURE, 'messages': msgs, **res,
                   'at': datetime.now(timezone.utc).isoformat(timespec='seconds')})

    first = [c for c in conditions if c != 'pushback']
    for phase in (first, ['pushback'] if 'pushback' in conditions else []):
        jobs = plan(items, phase, langs, samples)
        with ThreadPoolExecutor(workers) as ex:
            list(ex.map(one, jobs))
    log(f"{model['id']}: {len(store.rows)} answers, {len(errors)} errors")
    return store, errors


def pick_judge(model, models_by_id, judges):
    for j in judges:
        if models_by_id[j]['family'] != model['family']:
            return models_by_id[j]
    raise ValueError(f"no judge outside family {model['family']}")


def label_model(run_dir, model, models_by_id, judges, providers, items, workers=8, call=chat, langs=core.LANGS):
    store = Store(Path(run_dir) / 'responses' / f"{model['id']}.jsonl")
    labels = Store(Path(run_dir) / 'labels' / f"{model['id']}.jsonl")
    judge = pick_judge(model, models_by_id, judges)
    by_id = {it['id']: it for it in items}

    def one(row):
        if row['key'] in labels.rows or row['item'] not in by_id or row['lang'] not in langs:
            return
        if not row['content'].strip():
            labels.add({'key': row['key'], 'label': 'EMPTY', 'by': 'script'})
            return
        if row['cond'] != 'pushback':
            lab = core.script_label(row['content'])
            if lab:
                labels.add({'key': row['key'], 'label': lab, 'by': 'script'})
                return
        q = by_id[row['item']][row['lang']]
        earlier = row['messages'][1]['content'] if row['cond'] == 'pushback' else None
        prompt = core.judge_prompt(q, row['content'], earlier)
        try:
            res = call(providers[judge['provider']], judge['api_model'],
                       [{'role': 'user', 'content': prompt}], temperature=0, max_tokens=2048,
                       extra=judge.get('judge_params'))
        except ApiError:
            return
        lab = core.parse_judge(res['content'])
        labels.add({'key': row['key'], 'label': lab or 'UNPARSED', 'by': judge['id'],
                    'judge_raw': res['content'][:80], 'judge_usage': res['usage']})

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, list(store.rows.values())))
    return labels


def joined_rows(run_dir, model_id):
    store = Store(Path(run_dir) / 'responses' / f'{model_id}.jsonl')
    labels = Store(Path(run_dir) / 'labels' / f'{model_id}.jsonl')
    cert = Store(Path(run_dir) / 'certainty' / f'{model_id}.jsonl')
    out = []
    for r in store.rows.values():
        row = {**r, 'label': labels.rows.get(r['key'], {}).get('label')}
        if r['key'] in cert.rows:
            row['certainty'] = cert.rows[r['key']]['certainty']
        out.append(row)
    return out


def certainty_model(run_dir, model, models_by_id, judges, providers, items, workers=8, call=chat, langs=core.LANGS):
    """Second judging pass, open questions only: is a YES/NO stated as settled or as a probability?"""
    rows = joined_rows(run_dir, model['id'])
    cert = Store(Path(run_dir) / 'certainty' / f"{model['id']}.jsonl")
    judge = pick_judge(model, models_by_id, judges)
    by_id = {it['id']: it for it in items}

    def one(row):
        it = by_id.get(row['item'])
        if (row['key'] in cert.rows or it is None or it['type'] != 'open' or row['cond'] != 'neutral'
                or row['lang'] not in langs or row['label'] not in core.STANCES):
            return
        try:
            res = call(providers[judge['provider']], judge['api_model'],
                       [{'role': 'user', 'content': core.certainty_prompt(it[row['lang']], row['content'])}],
                       temperature=0, max_tokens=2048, extra=judge.get('judge_params'))
        except ApiError:
            return
        cert.add({'key': row['key'], 'certainty': core.parse_certainty(res['content']) or 'UNPARSED',
                  'by': judge['id']})

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, rows))
    return cert


def usage_stats(rows):
    n = len(rows) or 1
    pin = sum((r['usage'].get('prompt_tokens') or 0) for r in rows) / n
    pout = sum((r['usage'].get('completion_tokens') or 0) for r in rows) / n
    return {'calls': len(rows), 'avg_in': round(pin), 'avg_out': round(pout)}


def completeness(items, rows, langs):
    """(complete, missing count). Expected: every item x condition x language x sample index seen for this model;
    a row counts only once it has a label (EMPTY = the model returned nothing: an answer, not a gap)."""
    ks = sorted({r['k'] for r in rows}) or [0]
    want = {(it['id'], c, lang, k) for it in items for c in core.CONDITIONS for lang in langs for k in ks
            if not (c.startswith('persona') and it['persona_yes'] is None)}
    open_ids = {it['id'] for it in items if it['type'] == 'open'}
    have = {(r['item'], r['cond'], r['lang'], r['k']) for r in rows if r['label'] in core.LABELS + ('EMPTY',)
            and not (r['item'] in open_ids and r['cond'] == 'neutral' and r['label'] in core.STANCES
                     and r.get('certainty') not in ('CERTAIN', 'PROBABLE'))}
    missing = len(want - have)
    return missing == 0, missing


def report(run_dir, items, model_ids, lots=('public', 'private'), langs=core.LANGS):
    """Completeness rule: an incomplete model never enters a ranking; it is listed under `excluded`."""
    chosen = [it for it in items if it['lot'] in lots]
    out = {'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
           'prompt_version': core.PROMPT_VERSION, 'temperature': TEMPERATURE,
           'items': len(chosen), 'lots': list(lots), 'langs': list(langs), 'models': {}, 'excluded': {}}
    for mid in model_ids:
        rows = [r for r in joined_rows(run_dir, mid) if r['lang'] in langs]
        ok, missing = completeness(chosen, rows, langs)
        if not ok:
            out['excluded'][mid] = f'incomplete: {missing} answers missing or unlabelled'
            continue
        labels = [r['label'] for r in rows]
        out['models'][mid] = {
            'metrics': core.summarize(chosen, rows),
            'samples': len({r['k'] for r in rows}),
            'served_models': sorted({r['served_model'] for r in rows if r.get('served_model')}),
            'usage': usage_stats(rows),
            'labels': {lab: labels.count(lab) for lab in sorted(set(labels), key=str)},
        }
    return out


def markdown(rep):
    names = [('score', 'Score /100', 1), ('candor', 'Franchise', 100), ('accuracy', 'Exactitude', 100),
             ('false_certainty', 'Fausse assurance', 100), ('persona_shift', 'Complaisance', 100),
             ('caves', 'Cède', 100), ('lang_gap', 'Écart FR/EN', 100)]
    head = '| Modèle | ' + ' | '.join(n for _, n, _ in names) + ' |'
    lines = [head, '|' + '---|' * (len(names) + 1)]

    def fmt(m, f):
        v, (lo, hi) = m['value'], m['ci95']
        return '–' if v is None else f'{v * f:.0f} [{lo * f:.0f}–{hi * f:.0f}]'

    ranked = sorted(rep['models'].items(), key=lambda kv: -(kv[1]['metrics']['score']['value'] or 0))
    for mid, m in ranked:
        lines.append(f'| {mid} | ' + ' | '.join(fmt(m['metrics'][k], f) for k, _, f in names) + ' |')
    return '\n'.join(lines) + '\n'


def estimate(models, usage_by_model, n_items, persona_share, langs, samples, judge_share=0.35):
    """Cost in USD of a full run. Unmeasured models get the median measured token counts."""
    per_item = samples * len(langs) * (2 + 2 * persona_share)   # neutral + pushback + 2 personas
    calls = n_items * per_item
    measured = sorted(usage_by_model.values(), key=lambda u: u['avg_out'])
    default = measured[len(measured) // 2] if measured else {'avg_in': 120, 'avg_out': 900}
    rows = []
    for m in models:
        u = usage_by_model.get(m['id'], default)
        # pushback calls carry the first answer, roughly doubling the prompt for a quarter of calls
        cost = calls * (u['avg_in'] * 1.25 * m['in'] + u['avg_out'] * m['out']) / 1e6
        rows.append({'model': m['id'], 'calls': round(calls), 'usd': round(cost, 2),
                     'measured': m['id'] in usage_by_model})
    return rows, round(calls * judge_share)
