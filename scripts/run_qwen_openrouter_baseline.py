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
PROVIDER = 'modelrun/fp4'
MAX_TOKENS = 235929
CONTEXT = 262144
SAMPLING_NOTE = 'ModelRun FP4 exposes temperature/top_p; top_k and seed are not exposed. Quantization differs from the local MLX 8-bit baseline.'
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


def request_payload(task, max_tokens=MAX_TOKENS):
    request = {'model': MODEL, 'messages': [{'role': 'system', 'content': SYSTEM},
                                           {'role': 'user', 'content': task.prompt}],
               'stream': True, 'stream_options': {'include_usage': True},
               'reasoning': {'effort': 'xhigh', 'exclude': False},
               'provider': {'only': [PROVIDER], 'allow_fallbacks': False, 'require_parameters': True},
               'max_tokens': max_tokens, 'temperature': 1.0, 'top_p': .95}
    if PROVIDER == 'cerebras/fp16':
        request['seed'] = 20261020
    return request


def run(task_name, tokenizer):
    task = tasks()[task_name]
    assert sha(task.prompt.encode()) == json.loads(SUITE.read_text())['tasks'][task_name]['prompt_sha256']
    path = DIRECTORY / f'qwen38-{task_name}.result.json'
    if path.exists():
        return path
    max_tokens = 131072 if task_name == 'apache' else MAX_TOKENS
    request = request_payload(task, max_tokens)
    save(DIRECTORY / f'{task_name}.request.json', request)
    row = {'task': task_name, 'model': MODEL, 'provider_requested': PROVIDER,
           'prompt_sha256': sha(task.prompt.encode()), 'reasoning_effort': 'xhigh',
           'max_tokens': max_tokens, 'context_tokens': CONTEXT, 'wall_limit_s': 3600,
           'sampling_note': SAMPLING_NOTE,
           'started_at': time.time(), 'answer': '', 'reasoning': '', 'ttft_s': None,
           'first_answer_s': None, 'finish_reason': None,
           'timing_note': 'Network and hosted inference; not comparable to local tok/s.'}
    live = {'task': task_name, 'status': 'running', 'started_at': row['started_at'],
            'provider_requested': PROVIDER, 'max_tokens': max_tokens}
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
            response.encoding = 'utf-8'
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
    assert request['provider']['only'] == ['modelrun/fp4'] and not request['provider']['allow_fallbacks']
    assert request['max_tokens'] == 235929 and request['reasoning']['effort'] == 'xhigh'
    apache = request_payload(tasks()['apache'], 131072)
    assert apache['max_tokens'] == 131072 and apache['messages'][-1]['content'] == tasks()['apache'].prompt
    assert not {'top_k', 'seed', 'min_p', 'presence_penalty', 'frequency_penalty', 'repetition_penalty'} & request.keys()
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
    fields = ['task', 'model', 'provider_requested', 'provider', 'id', 'prompt_sha256', 'reasoning_effort', 'sampling_note',
              'max_tokens', 'context_tokens', 'wall_limit_s', 'started_at', 'finish_reason',
              'ttft_s', 'first_answer_s', 'total_s', 'prompt_tokens', 'generation_tokens',
              'reasoning_tokens_provider', 'reasoning_tokens_retokenized', 'answer_tokens_retokenized', 'cost_usd']
    def collect(path):
        raw = json.loads(path.read_text())
        row = {field: raw.get(field) for field in fields}
        row['evidence'] = str(path.relative_to(ROOT))
        billing_path = path.with_suffix('.generation.json')
        if billing_path.exists():
            billing = json.loads(billing_path.read_text()).get('data', {})
            assert billing.get('id') == raw.get('id'), 'Billing metadata does not match this request'
            row['billing_total_cost_usd'] = billing.get('total_cost')
            row['provider_generation_time_ms'] = billing.get('generation_time')
            row['cached_prompt_tokens'] = billing.get('native_tokens_cached')
            row['billing_evidence'] = str(billing_path.relative_to(ROOT))
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
        return row
    records = [collect(path) for task in ['apache', 'finance']
               if (path := DIRECTORY / f'qwen38-{task}.result.json').exists()]
    previous = [collect(path) for path in sorted(DIRECTORY.glob('*/qwen38-*.result.json'))]
    record = {'experiment_id': 'qwen38-openrouter-heavy-xhigh-20261020',
              'status': 'complete' if len(records) == 2 else 'in_progress',
              'planned_requests': 3 if (DIRECTORY / 'deepinfra-bf16-apache-128k').exists() else 2,
              'suite': 'qwen-family-full-xhigh@1.0', 'tasks': ['apache', 'finance'],
              'purpose': 'Hosted stock-Qwen completion and quality baseline; excluded from local speed rankings.',
              'limits': ['Apache compares ModelRun FP4 against the preserved DeepInfra BF16 result, both with 128K output caps. Finance uses ModelRun FP4 after Near AI FP8 exhausted its 64K output cap.',
                         'Provider context is 262K; the Finance ModelRun output cap is 235929. ModelRun does not expose top_k or seed.',
                         'Identical task and xhigh system prompts; provider internal template and kernels are not observable.',
                         'Network and hosted timings do not measure Mac inference speed.'],
              'records': records, 'previous_attempts': previous}
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
