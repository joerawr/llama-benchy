#!/usr/bin/env python3
"""One hosted stock-Qwen xhigh baseline for each paused heavy task."""
import argparse
import json
import signal
import subprocess
import time
from pathlib import Path

import requests
from tokenizers import Tokenizer

from openrouter_benchmark_campaign import openrouter_api_key
from run_qwen_family_xhigh import OUT, PYTHON, ROOT, SCRIPT, SUITE, save, sha, tasks

DIRECTORY = OUT / 'openrouter-baseline'
MODEL = 'qwen/qwen3.8-27b'
PROVIDER = 'near-ai/fp8'
MAX_TOKENS = 65536
SYSTEM = ('Reasoning effort is set to xhigh. Please think carefully through the task, '
          'validate key assumptions, consider plausible alternatives, and prioritize '
          'correctness, consistency, and clarity in the final answer.')


def apply_event(row, event, elapsed):
    if event.get('error'):
        raise RuntimeError(str(event['error']))
    for key in ['id', 'provider', 'model', 'usage']:
        if event.get(key) is not None:
            row[key] = event[key]
    for choice in event.get('choices', []):
        delta = choice.get('delta') or {}
        thinking = delta.get('reasoning') or delta.get('reasoning_content') or ''.join(
            item.get('text', '') for item in delta.get('reasoning_details', [])
            if item.get('type') == 'reasoning.text')
        answer = delta.get('content') or ''
        if thinking or answer:
            if row['ttft_s'] is None:
                row['ttft_s'] = elapsed
        if answer and row['first_answer_s'] is None:
            row['first_answer_s'] = elapsed
        row['reasoning'] += thinking
        row['answer'] += answer
        if choice.get('finish_reason') is not None:
            row['finish_reason'] = choice['finish_reason']


def deadline(signum, frame):
    raise TimeoutError('One-hour request wall limit')


def dashboard():
    from qwen_family_dashboard import write_dashboard
    write_dashboard()


def request_payload(task):
    return {'model': MODEL, 'messages': [{'role': 'system', 'content': SYSTEM},
                                           {'role': 'user', 'content': task.prompt}],
               'stream': True, 'stream_options': {'include_usage': True},
               'reasoning': {'effort': 'xhigh', 'exclude': False},
               'provider': {'only': [PROVIDER], 'allow_fallbacks': False, 'require_parameters': True},
               'max_tokens': MAX_TOKENS, 'temperature': 1.0, 'top_p': .95, 'top_k': 20,
               'seed': 20261020}


def run(task_name, tokenizer):
    task = tasks()[task_name]
    assert sha(task.prompt.encode()) == json.loads(SUITE.read_text())['tasks'][task_name]['prompt_sha256']
    path = DIRECTORY / f'qwen38-{task_name}.result.json'
    if path.exists():
        return path
    request = request_payload(task)
    save(DIRECTORY / f'{task_name}.request.json', request)
    row = {'task': task_name, 'model': MODEL, 'provider_requested': PROVIDER,
           'prompt_sha256': sha(task.prompt.encode()), 'reasoning_effort': 'xhigh',
           'max_tokens': MAX_TOKENS, 'context_tokens': 262144, 'wall_limit_s': 3600,
           'sampling_note': 'Near AI exposes temperature/top_p/top_k/seed; neutral min_p and penalty controls are not exposed.',
           'started_at': time.time(), 'answer': '', 'reasoning': '', 'ttft_s': None,
           'first_answer_s': None, 'finish_reason': None,
           'timing_note': 'Network and hosted inference; not comparable to local tok/s.'}
    live = {'task': task_name, 'status': 'running', 'started_at': row['started_at'],
            'provider_requested': PROVIDER, 'max_tokens': MAX_TOKENS}
    save(DIRECTORY / 'live.json', live)
    dashboard()
    started = time.monotonic()
    heartbeat = started
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(3600)
    try:
        with requests.post('https://openrouter.ai/api/v1/chat/completions',
                           headers={'Authorization': 'Bearer ' + openrouter_api_key(),
                                    'X-OpenRouter-Title': 'Qwen family heavy-task baseline'},
                           json=request, stream=True, timeout=(30, 300)) as response:
            if response.status_code != 200:
                raise RuntimeError(f'HTTP {response.status_code}: {response.text[:2000]}')
            with (DIRECTORY / f'{task_name}.events.jsonl').open('w') as events:
                for line in response.iter_lines(chunk_size=1, decode_unicode=True):
                    if not line or not line.startswith('data:'):
                        continue
                    payload = line[5:].strip()
                    if payload == '[DONE]':
                        break
                    event = json.loads(payload)
                    events.write(json.dumps(event) + '\n')
                    events.flush()
                    apply_event(row, event, time.monotonic() - started)
                    if time.monotonic() - heartbeat >= 15:
                        live.update(elapsed_s=time.monotonic() - started,
                                    reasoning_characters=len(row['reasoning']),
                                    answer_characters=len(row['answer']),
                                    ttft_s=row['ttft_s'], first_answer_s=row['first_answer_s'])
                        save(DIRECTORY / 'live.json', live)
                        dashboard()
                        print('GENERATING', task_name, round(live['elapsed_s']),
                              len(row['reasoning']), len(row['answer']), flush=True)
                        heartbeat = time.monotonic()
        if row['finish_reason'] != 'stop' or not row['answer'].strip():
            row['error'] = 'Incomplete delivered answer'
    except Exception as exc:
        row.update(error=repr(exc), finish_reason='error')
    finally:
        signal.alarm(0)
    row['total_s'] = time.monotonic() - started
    usage = row.get('usage') or {}
    row['reasoning_tokens_provider'] = (usage.get('completion_tokens_details') or {}).get('reasoning_tokens')
    row['prompt_tokens'] = usage.get('prompt_tokens')
    row['generation_tokens'] = usage.get('completion_tokens')
    row['cost_usd'] = usage.get('cost')
    for field in ['reasoning', 'answer']:
        text = row[field]
        row[field + '_tokens_retokenized'] = len(tokenizer.encode(text, add_special_tokens=False).ids) if text else 0
        (DIRECTORY / f'{task_name}.{field}.txt').write_text(text)
    save(path, row)
    save(DIRECTORY / 'live.json', {'task': task_name, 'status': 'finished', 'finished_at': time.time()})
    dashboard()
    print('FINISHED', task_name, row['finish_reason'], round(row['total_s']),
          'thinking', row['reasoning_tokens_provider'], 'total', row['generation_tokens'], flush=True)
    return path


def self_check():
    request = request_payload(tasks()['finance'])
    assert request['provider']['only'] == ['near-ai/fp8'] and not request['provider']['allow_fallbacks']
    assert request['max_tokens'] == 65536 and request['reasoning']['effort'] == 'xhigh'
    assert not {'min_p', 'presence_penalty', 'frequency_penalty', 'repetition_penalty'} & request.keys()
    row = {'answer': '', 'reasoning': '', 'ttft_s': None, 'first_answer_s': None}
    apply_event(row, {'choices': [{'delta': {'reasoning': 'abc', 'reasoning_details': [
        {'type': 'reasoning.text', 'text': 'abc'}]}}]}, 1)
    apply_event(row, {'choices': [{'delta': {'content': 'done'}, 'finish_reason': 'stop'}],
                      'usage': {'completion_tokens_details': {'reasoning_tokens': 3}}}, 2)
    assert row['reasoning'] == 'abc' and row['answer'] == 'done'
    assert row['ttft_s'] == 1 and row['first_answer_s'] == 2 and row['finish_reason'] == 'stop'
    apply_event(row, {'choices': [{'delta': {'reasoning_details': [
        {'type': 'reasoning.text', 'text': 'd'}]}}]}, 3)
    assert row['reasoning'] == 'abcd'
    try:
        apply_event(row, {'error': {'message': 'failed'}}, 4)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Stream errors must be preserved')
    print('Self-check passed')


def summarize():
    records = []
    fields = ['task', 'model', 'provider_requested', 'provider', 'id', 'prompt_sha256', 'reasoning_effort', 'sampling_note',
              'max_tokens', 'context_tokens', 'wall_limit_s', 'started_at', 'finish_reason',
              'ttft_s', 'first_answer_s', 'total_s', 'prompt_tokens', 'generation_tokens',
              'reasoning_tokens_provider', 'reasoning_tokens_retokenized', 'answer_tokens_retokenized', 'cost_usd']
    for task in ['apache', 'finance']:
        path = DIRECTORY / f'qwen38-{task}.result.json'
        if not path.exists():
            continue
        raw = json.loads(path.read_text())
        row = {field: raw.get(field) for field in fields}
        row['evidence'] = str(path.relative_to(ROOT))
        grade_path = path.with_suffix('.grade.json')
        if grade_path.exists():
            grade = json.loads(grade_path.read_text())
            assert grade['source_sha256'] == sha(path.read_bytes())
            meta = grade['semantic_judge']
            if grade['semantic_grade'].get('score') is not None:
                assert (meta.get('judge_model'), meta.get('judge_effort'), meta.get('judge_protocol')) == (
                    'gpt-5.6-luna', 'xhigh', 'source-aware-v2')
                row['semantic_grade'] = grade['semantic_grade']
            else:
                row['grading_status'] = 'incomplete'
                row['grading_error'] = grade['semantic_grade'].get('error')
        records.append(row)
    record = {'experiment_id': 'qwen38-openrouter-heavy-xhigh-20261020',
              'status': 'complete' if len(records) == 2 else 'in_progress', 'planned_requests': 2,
              'suite': 'qwen-family-full-xhigh@1.0', 'tasks': ['apache', 'finance'],
              'purpose': 'Hosted stock-Qwen completion and quality baseline; excluded from local speed rankings.',
              'limits': ['Apache completed on DeepInfra BF16; Finance moved to Near AI FP8 for speed. Interrupted Finance evidence is retained separately.',
                         'Provider context is 262K; generation caps are 128K DeepInfra and 64K Near AI. Local campaign context was 64K or 128K.',
                         'Identical task and xhigh system prompts; provider internal template and kernels are not observable.',
                         'Network and hosted timings do not measure Mac inference speed.'],
              'records': records}
    save(ROOT / 'benchmarks/runs/qwen38-openrouter-heavy-xhigh-20261020.json', record)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--summarize', action='store_true')
    parser.add_argument('--follow', action='store_true', help='Collect an already-running campaign without sending requests')
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return
    if args.summarize:
        summarize()
        return
    if args.follow:
        until = time.monotonic() + 3 * 3600
        while time.monotonic() < until:
            summarize()
            if (DIRECTORY / 'live.json').exists() and json.loads((DIRECTORY / 'live.json').read_text()).get('status') == 'complete':
                dashboard()
                return
            time.sleep(15)
        raise TimeoutError('Baseline collector exceeded three hours')
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    tokenizer = Tokenizer.from_file(str(Path.home() /
                                        'models/mlx-community/Qwen3.8-27B-8bit/tokenizer.json'))
    for task in ['apache', 'finance']:
        path = run(task, tokenizer)
        row = json.loads(path.read_text())
        if row['finish_reason'] == 'stop' and row['answer'].strip() and not path.with_suffix('.grade.json').exists():
            with path.with_suffix('.judge.log').open('a') as log:
                try:
                    subprocess.run([str(PYTHON), str(SCRIPT), 'judge', '--result', str(path)],
                                   stdout=log, stderr=subprocess.STDOUT, timeout=900, check=True)
                except (OSError, subprocess.SubprocessError) as exc:
                    log.write(repr(exc) + '\n')
        dashboard()
        summarize()
    save(DIRECTORY / 'live.json', {'status': 'complete', 'finished_at': time.time()})
    dashboard()


if __name__ == '__main__':
    main()
