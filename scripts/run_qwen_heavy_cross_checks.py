#!/usr/bin/env python3
"""Two local xhigh checks, queued after the hosted stock-Qwen baseline."""
import argparse
import fcntl
import json
import subprocess
import tempfile
import time
from pathlib import Path

import run_qwen_family_xhigh as bench
from qwen_family_dashboard import write_dashboard

PARENT = bench.OUT
OUT = PARENT / 'heavy-cross-checks-128k'
PLAN = [('twin709-ultra-q8', 'finance'), ('turbo735-q8', 'apache')]


def hosted_done(directory):
    for task in ['apache', 'finance']:
        path = directory / f'qwen38-{task}.result.json'
        try:
            if json.loads(path.read_text()).get('finish_reason') is None:
                return False
        except (OSError, ValueError):
            return False
    return True


def summarize():
    fields = ['model', 'task', 'seed', 'context_tokens', 'request_wall_timeout_s', 'finish_reason',
              'prompt_sha256', 'rendered_sha256', 'ttft_s', 'first_answer_s', 'reasoning_tokens_retokenized',
              'answer_tokens_retokenized', 'generation_tokens', 'generation_tokens_per_s',
              'prompt_tokens', 'prompt_tokens_per_s', 'total_s']
    records = []
    for label, task in PLAN:
        path = OUT / f'{label}-pass1-{task}.result.json'
        if not path.exists():
            continue
        raw = json.loads(path.read_text())
        row = {field: raw.get(field) for field in fields}
        row['evidence'] = str(path.relative_to(bench.ROOT))
        grade_path = path.with_suffix('.grade.json')
        if grade_path.exists():
            grade = json.loads(grade_path.read_text())
            assert grade['source_sha256'] == bench.sha(path.read_bytes())
            meta = grade['semantic_judge']
            assert (meta['judge_model'], meta['judge_effort'], meta['judge_protocol']) == (
                'gpt-5.6-luna', 'xhigh', 'source-aware-v2')
            row['semantic_grade'] = grade['semantic_grade']
        records.append(row)
    bench.save(bench.ROOT / 'benchmarks/runs/qwen-heavy-cross-checks-128k-20261020.json', {
        'experiment_id': 'qwen-heavy-cross-checks-128k-20261020',
        'suite': 'qwen-family-full-xhigh@1.0', 'planned_requests': 2,
        'status': 'complete' if len(records) == 2 else 'in_progress',
        'thinking': 'on, xhigh', 'context_tokens': 131072, 'wall_limit_s': 3600,
        'order': [{'model': label, 'task': task} for label, task in PLAN],
        'limits': ['One new attempt per model/task; earlier attempts remain in the original campaign.'],
        'records': records})


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    with (bench.ROOT / 'benchy-state/campaign.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = {'status': 'waiting_openrouter', 'created_at': time.time(),
                 'plan': [{'model': label, 'task': task} for label, task in PLAN], 'errors': []}
        bench.save(OUT / 'state.json', state)
        summarize()
        write_dashboard()
        print('QUEUED: waiting for both hosted attempts to finish', flush=True)
        while not hosted_done(PARENT / 'openrouter-baseline'):
            time.sleep(15)
        print('Hosted attempts finished; starting local checks', flush=True)
        frozen = json.loads(bench.SUITE.read_text())
        for label, task in PLAN:
            prompt = (PARENT / f'{task}.prompt.txt').read_bytes()
            assert bench.sha(prompt) == frozen['tasks'][task]['prompt_sha256']
            (OUT / f'{task}.prompt.txt').write_bytes(prompt)
            (OUT / f'{label}-download.json').write_bytes((PARENT / f'{label}-download.json').read_bytes())
        bench.OUT = OUT
        for label, task in PLAN:
            path = OUT / f'{label}-pass1-{task}.result.json'
            state.update(status='running', current_model=label, current_task=task, current_round=1, started_at=time.time())
            bench.save(OUT / 'state.json', state)
            write_dashboard()
            try:
                if not path.exists():
                    bench.gguf_round(label, 1, task_names=[task])
                row = json.loads(path.read_text())
                summarize()
                state['status'] = 'grading'
                bench.save(OUT / 'state.json', state)
                write_dashboard()
                if row['finish_reason'] == 'stop' and row['answer'].strip() and not path.with_suffix('.grade.json').exists():
                    with path.with_suffix('.judge.log').open('a') as log:
                        subprocess.run([str(bench.PYTHON), str(bench.SCRIPT), 'judge', '--result', str(path)],
                                       stdout=log, stderr=subprocess.STDOUT, timeout=900, check=True)
            except Exception as exc:
                state['errors'].append({'model': label, 'task': task, 'error': repr(exc)})
                print('ERROR', label, task, repr(exc), flush=True)
            summarize()
            write_dashboard()
        state.update(status='complete_with_errors' if state['errors'] else 'complete',
                     current_model=None, current_task=None, finished_at=time.time())
        bench.save(OUT / 'state.json', state)
        write_dashboard()
        print('Local checks complete', flush=True)


def self_check():
    assert PLAN == [('twin709-ultra-q8', 'finance'), ('turbo735-q8', 'apache')]
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        assert not hosted_done(directory)
        (directory / 'qwen38-apache.result.json').write_text('{"finish_reason":"error"}')
        assert not hosted_done(directory)
        (directory / 'qwen38-finance.result.json').write_text('{"finish_reason":null}')
        assert not hosted_done(directory)
        (directory / 'qwen38-finance.result.json').write_text('{"finish_reason":"stop"}')
        assert hosted_done(directory)
    assert bench.CONTEXT == 131072 and bench.TIMEOUT == 3600
    print('Cross-checks passed: exact order, both hosted results required, 128K and one-hour limits.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    self_check() if args.self_check else run()
