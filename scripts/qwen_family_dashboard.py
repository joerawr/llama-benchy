#!/usr/bin/env python3
"""Live HTML snapshot of the five-model campaign, independent of inference."""
import argparse
import hashlib
import html
import json
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from run_qwen_family_xhigh import LABELS, NAMES, OUT, ROOT, TASKS

DOCUMENT = ROOT / 'qwen-family-xhigh-results.html'
TOTAL = len(LABELS) * len(TASKS) * 3
TASK_NAMES = dict(zip(TASKS, ['Finance', 'Apache', 'Access anomaly', 'Compression',
                             'Family note', 'Checklist', 'Text lines']))
MAXIMA = dict(zip(TASKS, [12, 10, 7, 12, 6, 7, 8]))


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def snapshot(directory=OUT):
    state = read_json(directory / 'state.json')
    live = read_json(directory / 'live.json')
    control = read_json(directory / 'control.json') or {'rounds': [1, 2, 3], 'tasks': TASKS}
    selected = {(label, n, task) for label in LABELS for n in control['rounds'] for task in control['tasks']}
    slots = []
    last_result = None
    for label, name in zip(LABELS, NAMES):
        for round_ in [1, 2, 3]:
            for task in TASKS:
                p = directory / f'{label}-pass{round_}-{task}.result.json'
                raw = p.read_bytes() if p.exists() else None
                r = json.loads(raw) if raw else {}
                grade = read_json(p.with_suffix('.grade.json'))
                g, meta = grade.get('semantic_grade', {}), grade.get('semantic_judge', {})
                score = g.get('score')
                valid_grade = (raw is not None and grade.get('source_sha256') == hashlib.sha256(raw).hexdigest()
                               and meta.get('judge_protocol') == 'source-aware-v2'
                               and meta.get('judge_model') == 'gpt-5.6-luna' and meta.get('judge_effort') == 'xhigh'
                               and type(score) is int and g.get('max_score') == MAXIMA[task]
                               and 0 <= score <= MAXIMA[task])
                delivered = bool(r.get('answer', '').strip()) and r.get('finish_reason') == 'stop'
                in_scope = (label, round_, task) in selected
                active = (in_scope and not raw and live.get('model') == label and live.get('round') == round_
                          and live.get('task') == task and state.get('current_model') == label
                          and state.get('current_round') == round_ and state.get('status') == 'running')
                status = ('Failed' if raw and not delivered else 'Graded' if delivered and valid_grade
                          else 'Grade failed' if delivered and grade else 'Awaiting grade' if delivered
                          else 'Running' if active else 'Deferred' if round_ in control.get('deferred_rounds', [])
                          else 'Paused' if task in control.get('paused_tasks', [])
                          else 'Deferred' if not in_scope else 'Queued')
                reason = r.get('error', '') if status == 'Failed' else g.get('error', '') if status == 'Grade failed' else ''
                if '3600' in reason or 'timed out' in reason.lower():
                    reason = 'One-hour time limit'
                elif 'context exceeded' in reason.lower():
                    reason = str(r.get('context_tokens', 65536) // 1024) + 'K context full'
                elif status == 'Failed' and 'Incomplete delivered answer' in reason:
                    n = (r.get('prompt_tokens') or 0) + (r.get('generation_tokens') or 0)
                    reason = '64K context full' if n >= 65534 and r.get('context_tokens', 65536) == 65536 else 'Incomplete output'
                reason = reason.replace(str(ROOT), '.').replace(str(Path.home()), '~')
                if raw:
                    last_result = max(last_result or 0, p.stat().st_mtime)
                slots.append({'model': label, 'name': name, 'round': round_, 'task': task,
                              'status': status, 'reason': reason, 'score': score if delivered and valid_grade else None,
                              'record': r, 'finished': bool(raw), 'delivered': delivered, 'active': active, 'in_scope': in_scope})
    finished = sum(s['finished'] for s in slots)
    live_matches = any(s['active'] for s in slots)
    started = live.get('started_at')
    if live_matches and started is None and live.get('elapsed_s') is not None:
        started = (directory / 'live.json').stat().st_mtime - live['elapsed_s']
    return {'directory': directory, 'slots': slots, 'state': state, 'live': live, 'control': control, 'started': started if live_matches else None,
            'finished': finished, 'remaining': TOTAL - finished,
            'active_total': len(selected), 'active_finished': sum(s['finished'] and s['in_scope'] for s in slots),
            'active_remaining': sum(not s['finished'] and s['in_scope'] for s in slots),
            'paused': sum(s['status'] == 'Paused' for s in slots), 'deferred': sum(s['status'] == 'Deferred' for s in slots),
            'delivered': sum(s['delivered'] for s in slots),
            'failed': sum(s['finished'] and not s['delivered'] for s in slots),
            'graded': sum(s['score'] is not None for s in slots),
            'grading': sum(s['delivered'] and s['score'] is None for s in slots),
            'last_result': last_result}


def stamp(value):
    if value is None:
        return '-'
    return datetime.fromtimestamp(value, ZoneInfo('America/Los_Angeles')).strftime('%b %d, %Y  %I:%M:%S %p %Z')


def number(value, places=2):
    return '-' if value is None else f'{value:,.{places}f}'


def duration(value):
    if value is None:
        return '-'
    value = round(value)
    return f'{value // 3600:d}:{value // 60 % 60:02d}:{value % 60:02d}' if value >= 3600 else f'{value // 60:d}:{value % 60:02d}'


def hosted_section(directory):
    directory = directory / 'openrouter-baseline'
    if not directory.exists():
        return ''
    live = read_json(directory / 'live.json')
    rows, finished = [], 0
    for task in ['apache', 'finance']:
        path = directory / f'qwen38-{task}.result.json'
        row = read_json(path)
        grade = read_json(path.with_suffix('.grade.json'))
        semantic, judge = grade.get('semantic_grade', {}), grade.get('semantic_judge', {})
        score = semantic.get('score')
        valid = (path.exists() and grade.get('source_sha256') == hashlib.sha256(path.read_bytes()).hexdigest()
                 and judge.get('judge_protocol') == 'source-aware-v2' and judge.get('judge_effort') == 'xhigh'
                 and judge.get('judge_model') == 'gpt-5.6-luna' and type(score) is int
                 and semantic.get('max_score') == MAXIMA[task] and 0 <= score <= MAXIMA[task])
        delivered = row.get('finish_reason') == 'stop' and bool(row.get('answer', '').strip())
        finished += bool(row)
        status = ('Graded' if delivered and valid else 'Grade failed' if delivered and grade else 'Awaiting grade' if delivered else 'Failed' if row
                  else 'Running' if live.get('status') == 'running' and live.get('task') == task else 'Queued')
        running = status == 'Running'
        timing = live if running else row
        elapsed = time.time() - live['started_at'] if running else row.get('total_s')
        cells = [TASK_NAMES[task], status, f'{score}/{MAXIMA[task]}' if delivered and valid else '-',
                 number(row.get('reasoning_tokens_provider'), 0), number(row.get('reasoning_tokens_retokenized'), 0),
                 number(row.get('generation_tokens'), 0), number(timing.get('ttft_s')),
                 number(timing.get('first_answer_s')), duration(elapsed), number(row.get('cost_usd'), 4),
                 row.get('provider_requested', live.get('provider_requested', '-') if running else '-'),
                 row.get('finish_reason', '-')]
        rows.append('<tr>' + ''.join('<td>' + html.escape(c) + '</td>' for c in cells) + '</tr>')
    headers = ['Task', 'Status', 'Score', 'Thinking (provider)', 'Thinking (retokenized)', 'Generated total',
               'TTFT s', 'Answer starts s', 'Elapsed', 'Cost USD', 'Provider', 'Finish']
    return ('<section class="progress"><h2>Hosted stock Qwen3.8-27B baseline</h2><p>' + str(finished) +
            '/2 tests saved; ' + str(2 - finished) + '/2 remaining. OpenRouter: Apache / DeepInfra BF16; '
            'Finance / Near AI FP8. Xhigh; same task prompts, temperature/top_p/top_k and seed 20261020. '
            '262K provider context; generation caps: DeepInfra 128K, Near AI 64K. Near AI does not expose the neutral '
            'penalty/min_p controls. One-hour wall limit. Interrupted DeepInfra Finance evidence is preserved. '
            'Hosted timings include network and server behavior and are excluded from local speed comparisons. '
            'Provider counts are reported separately from local-tokenizer estimates; a dash means unavailable.</p>'
            '<div class="wrap"><table><thead><tr>' + ''.join('<th>' + h + '</th>' for h in headers) +
            '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div></section>')


def cross_check_section(directory):
    directory = directory / 'heavy-cross-checks-128k'
    state = read_json(directory / 'state.json')
    if not state:
        return ''
    data = snapshot(directory)
    slots = [next(s for s in data['slots'] if (s['model'], s['task'], s['round']) ==
                  (item['model'], item['task'], 1)) for item in state['plan']]
    rows = []
    for slot in slots:
        r = slot['record']
        status = slot['status']
        if not r and state.get('status') == 'waiting_openrouter':
            status = 'Waiting for OpenRouter'
        error = next((x['error'] for x in state.get('errors', []) if x['model'] == slot['model'] and x['task'] == slot['task']), '')
        if not r and error:
            status = 'Failed'
        current = state.get('current_model') == slot['model'] and state.get('status') == 'running'
        if current and not r:
            status = 'Running' if slot['active'] else 'Loading / starting request'
        live = data['live'] if current and data['live'].get('model') == slot['model'] else {}
        score = '-' if slot['score'] is None else f"{slot['score']}/{MAXIMA[slot['task']]}"
        cells = [slot['name'], TASK_NAMES[slot['task']], status, score,
                 number(r.get('ttft_s', live.get('ttft_s'))), number(r.get('first_answer_s', live.get('first_answer_s'))),
                 number(r.get('reasoning_tokens_retokenized'), 0), number(r.get('generation_tokens_per_s')),
                 duration(time.time() - state['started_at'] if current else r.get('total_s')),
                 slot['reason'] or error]
        rows.append('<tr>' + ''.join('<td>' + html.escape(c) + '</td>' for c in cells) + '</tr>')
    finished = sum(s['finished'] for s in slots)
    headers = ['Model', 'Task', 'Status', 'Score', 'TTFT s', 'Answer starts s', 'Thinking tokens',
               'Generation tok/s', 'Elapsed', 'Detail']
    return ('<section class="progress"><h2>Local 128K follow-up checks</h2><p>' + str(finished) +
            '/2 tests saved; ' + str(2 - finished) + '/2 remaining. Starts after both OpenRouter attempts finish. '
            'One attempt each: TWIN TURBO Finance, then TURBO735 Apache. Thinking on/xhigh; 128K context; '
            'one-hour wall limit per request. Earlier attempts are preserved above and in their original records.</p>'
            '<div class="wrap"><table><thead><tr>' + ''.join('<th>' + h + '</th>' for h in headers) +
            '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div></section>')


def render(data, now=None):
    now = time.time() if now is None else now
    e = html.escape
    active = next((s for s in data['slots'] if s['active']), None)
    state = data['state']
    if active:
        current = f"{active['name']} / pass {active['round']} / {TASK_NAMES[active['task']]}"
    elif data['active_remaining'] == 0:
        current = 'Inference finished' + ('; grading remains' if data['grading'] else '')
    elif state.get('status') == 'running':
        current = 'Loading or moving to the next test: ' + dict(zip(LABELS, NAMES)).get(state.get('current_model'), '')
    else:
        current = state.get('status', 'Waiting for campaign').replace('_', ' ')
    summaries = []
    focused = bool(data['control'].get('paused_tasks'))
    for label, name in zip(LABELS, NAMES):
        ss = [s for s in data['slots'] if s['model'] == label]
        passes = []
        for round_ in [1, 2, 3]:
            rr = [s for s in ss if s['round'] == round_]
            if round_ in data['control'].get('deferred_rounds', []):
                passes.append(f'Pass {round_}: deferred')
                continue
            if focused:
                rr = [s for s in rr if s['task'] in data['control']['tasks']]
            scores = [s['score'] for s in rr]
            maximum = sum(MAXIMA[s['task']] for s in rr)
            text = f'{sum(scores)}/{maximum}' if all(s is not None for s in scores) else 'incomplete' if all(s['finished'] for s in rr) else f"{sum(s['finished'] for s in rr)}/{len(rr)} finished"
            passes.append(f'Pass {round_}: {text}')
        active_ss = [s for s in ss if s['in_scope']]
        summaries.append('<article><h2>' + e(name) + '</h2><b>' + str(sum(s['finished'] for s in active_ss)) + '/' + str(len(active_ss)) + ' active-scope tests finished</b><p>' + e(' | '.join(passes)) + '</p></article>')
    rows = []
    for s in data['slots']:
        r = s['record']
        score = '-' if s['score'] is None else f"{s['score']}/{MAXIMA[s['task']]}"
        context = str(r.get('context_tokens', 65536) // 1024) + 'K' if r else '-'
        cls = 'failed' if s['status'] in ['Failed', 'Grade failed'] else 'running' if s['active'] else 'graded' if s['score'] is not None else 'queued'
        cells = [s['name'], str(s['round']), TASK_NAMES[s['task']], s['status'], score,
                 number(r.get('ttft_s')), number(r.get('first_answer_s')),
                 number(r.get('reasoning_tokens_retokenized'), 0), number(r.get('generation_tokens_per_s')),
                 number(r.get('prompt_tokens_per_s')), duration(r.get('total_s')), context, s['reason']]
        rows.append('<tr class="' + cls + '" data-model="' + e(s['model']) + '" data-status="' + e(s['status']) + '">' +
                    ''.join('<td>' + e(c) + '</td>' for c in cells) + '</tr>')
    headers = ['Model', 'Pass', 'Task', 'Status', 'Score', 'TTFT s', 'Answer starts s',
               'Thinking tokens', 'Generation tok/s', 'Prompt tok/s', 'Elapsed', 'Context', 'Detail']
    model_options = ''.join('<option value="' + e(label) + '">' + e(name) + '</option>' for label, name in zip(LABELS, NAMES))
    status_options = ''.join('<option>' + status + '</option>' for status in ['Running', 'Queued', 'Graded', 'Failed', 'Awaiting grade', 'Grade failed', 'Paused', 'Deferred'])
    elapsed = duration(max(0, now - data['started'])) if data['started'] is not None else '-'
    live_note = f"Current test elapsed: {elapsed}."
    if active and data['live'].get('generation_tokens') is not None:
        live_note += ' Generated tokens: ' + number(data['live']['generation_tokens'], 0) + '.'
    scope_note = ('Round two: Access anomaly, Compression, Family note, Checklist, Text lines. Apache and Finance paused; round three deferred. Pass scores below use these five tasks, out of 40.' if focused else 'Full campaign: five models, seven tasks, three passes.')
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Five-model xhigh test progress</title><style>
:root{color-scheme:dark;--bg:#10151d;--panel:#192230;--line:#334155;--muted:#aebdd0;--text:#edf3fa;--blue:#83c8ff;--green:#91e2bc;--red:#ffacac}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,sans-serif}main{max-width:1800px;margin:auto;padding:28px}header{display:flex;justify-content:space-between;align-items:flex-start;gap:24px}h1{font-size:26px;margin:0}h2{font-size:15px;margin:0 0 8px}p{margin:7px 0;color:var(--muted)}.stamp{text-align:right;white-space:nowrap;color:var(--muted);font-size:13px}.stamp time{display:block;color:var(--text)}.progress{margin:22px 0;background:var(--panel);padding:20px;border:1px solid var(--line);border-radius:12px}.counter{font-size:24px;font-weight:700}.counts{display:flex;gap:28px;flex-wrap:wrap;margin:12px 0}.counts b{color:var(--text)}progress{width:100%;height:12px;accent-color:var(--blue)}.current{margin-top:14px;color:var(--blue)}.models{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin:18px 0}article{padding:15px;background:var(--panel);border:1px solid var(--line);border-radius:10px}article p{font-size:12px}.controls{display:flex;gap:16px;align-items:center;margin:20px 0}select,button{background:var(--panel);color:var(--text);border:1px solid var(--line);padding:8px;border-radius:6px}.wrap{overflow:auto;max-height:70vh;border:1px solid var(--line);border-radius:9px}table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:13px}th,td{padding:10px 12px;text-align:right;border-bottom:1px solid var(--line)}th{position:sticky;top:0;background:#233044;z-index:1}th:nth-child(-n+4),td:nth-child(-n+4),td:last-child{text-align:left}td:last-child{white-space:normal;min-width:160px;max-width:350px}.failed td:nth-child(4){color:var(--red)}.graded td:nth-child(4){color:var(--green)}.running{background:#19334c}.queued{color:var(--muted)}.notes{font-size:13px;margin-top:20px}a{color:var(--blue)}@media(max-width:700px){main{padding:14px}header{display:block}.stamp{text-align:left;margin-top:12px}.counter{font-size:21px}}
</style></head><body><main><header><div><h1>Five-model xhigh comparison</h1><p>M1 Max 64GB &middot; 5 models &times; 7 tasks &times; 3 passes</p></div>
<div class="stamp">Last updated<time>''' + e(stamp(now)) + '</time>Last test saved: ' + e(stamp(data['last_result'])) + '''</div></header>
<section class="progress"><div class="counter">''' + str(data['active_finished']) + ' / ' + str(data['active_total']) + ' active-scope tests finished &nbsp;&middot;&nbsp; ' + str(data['active_remaining']) + ' / ' + str(data['active_total']) + ''' remaining</div><p>''' + e(scope_note) + '''</p>
<progress value="''' + str(data['active_finished']) + '" max="' + str(data['active_total']) + '"></progress><div class="counts"><span><b>' + str(data['finished']) + '/' + str(TOTAL) + '</b> historical attempts saved</span><span><b>' + str(data['failed']) + '</b> failed / incomplete</span><span><b>' + str(data['graded']) + '</b> graded</span><span><b>' + str(data['grading']) + '</b> awaiting a valid grade</span><span><b>' + str(data['paused']) + '</b> paused</span><span><b>' + str(data['deferred']) + '''</b> deferred</span></div>
<div class="current">''' + e(current) + '</div><p>' + e(live_note) + '''</p></section>
<div class="models">''' + ''.join(summaries) + '</div>' + hosted_section(data.get('directory', OUT)) + cross_check_section(data.get('directory', OUT)) + '''<div class="controls"><label>Model <select id="model"><option value="">All models</option>''' + model_options + '''</select></label><label>Status <select id="status"><option value="">All statuses</option>''' + status_options + '''</select></label><button onclick="location.reload()">Refresh results</button></div>
<div class="wrap"><table><thead><tr>''' + ''.join('<th>' + e(h) + '</th>' for h in headers) + '</tr></thead><tbody>' + ''.join(rows) + '''</tbody></table></div>
<div class="notes"><p>Refresh this document for the latest snapshot. The file updates within a few seconds of each saved result or grade, and refreshes its timestamp every 15 seconds while the campaign is running. Refreshing this page does not contact or interrupt the model.</p>
<p>Failed tests count as finished attempts. A dash is missing quality evidence, not a score of zero. A pass total appears only when every task in its stated scope has a valid grade. Scores use Luna xhigh, source-aware-v2; hidden reasoning is not graded or displayed.</p>
<p>Thinking is explicitly on/xhigh; one-hour wall limit per request. Initial tests used 64K; remaining tests use 128K. Compression removes the original /no_think directive, and checklist wording is unchanged. GGUF and MLX throughput includes backend and quantization differences. This document is separate from the primary benchmark document.</p>
<p>TTFT is the first generated text; answer start excludes time spent thinking. Generation speed includes thinking and answer tokens. Thinking tokens are separately retokenized. Elapsed is wall time, including prefill.</p></div></main>
<script>function filter(){const m=document.getElementById('model').value,s=document.getElementById('status').value;document.querySelectorAll('tbody tr[data-model]').forEach(r=>{r.hidden=(m&&r.dataset.model!==m)||(s&&r.dataset.status!==s)})}document.getElementById('model').onchange=filter;document.getElementById('status').onchange=filter;</script></body></html>'''


def write_dashboard(directory=OUT, target=DOCUMENT):
    data = snapshot(directory)
    document = render(data)
    with tempfile.NamedTemporaryFile(mode='w', dir=target.parent, prefix=target.name + '.', suffix='.tmp', delete=False) as temp:
        temp.write(document)
        name = temp.name
    Path(name).replace(target)
    return data


def signature():
    paths = list(OUT.glob('*.result.json')) + list(OUT.glob('*.result.grade.json'))
    paths += [OUT / name for name in ['state.json', 'live.json', 'protocol.json', 'control.json', 'publication.json']]
    paths += list((OUT / 'openrouter-baseline').glob('*.json'))
    paths += list((OUT / 'heavy-cross-checks-128k').glob('*.json'))
    return [(p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(paths) if p.exists()]


def watch():
    previous = None
    last_write = 0
    while True:
        state = read_json(OUT / 'state.json')
        if state.get('publication_status') == 'published':
            return
        current = signature()
        if state.get('publication_status') != 'writing' and (current != previous or time.monotonic() - last_write >= 15):
            data = write_dashboard()
            print(stamp(time.time()), data['finished'], '/', TOTAL, 'finished;', data['failed'], 'failed;', data['graded'], 'graded', flush=True)
            previous, last_write = current, time.monotonic()
        time.sleep(2)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split('?', 1)[0] not in ['/', '/' + DOCUMENT.name]:
            self.send_error(404)
            return
        content = DOCUMENT.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format_, *args):
        pass


def self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        result = p / 'qwen38-mlx8-pass1-finance.result.json'
        result.write_text(json.dumps({'finish_reason': 'stop', 'answer': 'HIDDEN ANSWER', 'reasoning': 'HIDDEN REASONING'}))
        failure = p / 'dirk-q8xl-pass1-apache.result.json'
        failure.write_text(json.dumps({'finish_reason': 'error', 'error': '<script>bad</script>'}))
        data = snapshot(p)
        assert data['finished'] == 2 and data['remaining'] == 103 and data['failed'] == 1 and data['grading'] == 1
        document = render(data)
        assert document.count('<tr class=') == TOTAL
        assert 'HIDDEN ANSWER' not in document and 'HIDDEN REASONING' not in document
        assert '<script>bad</script>' not in document and '&lt;script&gt;bad&lt;/script&gt;' in document
        grade = {'source_sha256': hashlib.sha256(result.read_bytes()).hexdigest(),
                 'semantic_grade': {'score': 0, 'max_score': 12},
                 'semantic_judge': {'judge_protocol': 'source-aware-v2', 'judge_model': 'gpt-5.6-luna', 'judge_effort': 'xhigh'}}
        result.with_suffix('.grade.json').write_text(json.dumps(grade))
        assert snapshot(p)['graded'] == 1
        grade['source_sha256'] = 'stale'
        result.with_suffix('.grade.json').write_text(json.dumps(grade))
        assert snapshot(p)['graded'] == 0
        (p / 'control.json').write_text(json.dumps({'rounds': [2], 'tasks': TASKS[2:], 'paused_tasks': TASKS[:2], 'deferred_rounds': [3]}))
        narrowed = snapshot(p)
        assert narrowed['active_total'] == 25 and narrowed['active_remaining'] == 25
        assert next(s for s in narrowed['slots'] if s['model'] == LABELS[0] and s['round'] == 2 and s['task'] == 'finance')['status'] == 'Paused'
        assert all(s['status'] == 'Deferred' for s in narrowed['slots'] if s['round'] == 3)
        hosted = p / 'openrouter-baseline'
        hosted.mkdir()
        hosted_result = hosted / 'qwen38-apache.result.json'
        hosted_result.write_text(json.dumps({'finish_reason': 'stop', 'answer': 'HOSTED SECRET ANSWER',
                                             'reasoning': 'HOSTED SECRET REASONING',
                                             'reasoning_tokens_retokenized': 123, 'provider': '<script>provider</script>'}))
        hosted_grade = {'source_sha256': hashlib.sha256(hosted_result.read_bytes()).hexdigest(),
                        'semantic_grade': {'score': 8, 'max_score': 10}, 'semantic_judge': grade['semantic_judge']}
        hosted_result.with_suffix('.grade.json').write_text(json.dumps(hosted_grade))
        document = render(snapshot(p))
        assert '1/2 tests saved; 1/2 remaining' in document and '8/10' in hosted_section(p)
        assert 'HOSTED SECRET' not in document and '<script>provider</script>' not in document
        hosted_grade['source_sha256'] = 'stale'
        hosted_result.with_suffix('.grade.json').write_text(json.dumps(hosted_grade))
        assert '8/10' not in hosted_section(p)
        cross = p / 'heavy-cross-checks-128k'
        cross.mkdir()
        (cross / 'state.json').write_text(json.dumps({'status': 'waiting_openrouter',
            'plan': [{'model': 'twin709-ultra-q8', 'task': 'finance'}, {'model': 'turbo735-q8', 'task': 'apache'}]}))
        section = cross_check_section(p)
        assert section.count('Waiting for OpenRouter') == 2 and '0/2 tests saved; 2/2 remaining' in section
        assert section.index('TWIN TURBO') < section.index('TURBO 735')
        from concurrent.futures import ThreadPoolExecutor
        target = p / 'dashboard.html'
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: write_dashboard(p, target), range(8)))
        assert target.read_text().count('<tr class=') == TOTAL and not list(p.glob('*.tmp'))
    print('Dashboard checks passed: 105 slots, remaining/failure counts, zero and stale grades, escaped output, no answer/reasoning leakage.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.serve:
        write_dashboard()
        server = ThreadingHTTPServer(('127.0.0.1', 18083), Handler)
        threading.Thread(target=watch, daemon=True).start()
        print('Dashboard: http://127.0.0.1:18083/', flush=True)
        server.serve_forever()
    else:
        data = write_dashboard()
        print(str(DOCUMENT), data['finished'], '/', TOTAL, 'finished')
