#!/usr/bin/env python3
"""Five-model, three-round macOS campaign; each inference and judgment is durable."""
from __future__ import annotations

import argparse
import dataclasses
import fcntl
import hashlib
import importlib.metadata
import json
import os
import signal
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/qwen-family-full-xhigh-20261020'
SUITE = ROOT / 'benchmarks/suites/qwen-family-full-xhigh-v1.json'
PYTHON = ROOT / '.venv/bin/python'
MLX_PYTHON = ROOT / 'results/runtimes/swift15-mlx-5bit/.venv/bin/python'
SERVER = ROOT / 'results/runtimes/llama.cpp-latest-20261019/build-metal/bin/llama-server'
SCRIPT = Path(__file__).resolve()
BASE = 'http://127.0.0.1:18081'
TIMEOUT = 3600
CONTEXT = 131072
LABELS = ['qwen38-mlx8', 'dirk-q8xl', 'turbo735-q8', 'twin709-ultra-q8', 'swift15-mlx5']
NAMES = ['Qwen3.8 27B MLX 8-bit', 'Dirk Qwen3.8 27B Q8_K_XL', 'DavidAU TURBO 735 Q8_0',
         'DavidAU TWIN TURBO ULTRA Q8_0', 'Swift 1.5 MLX 5-bit']
LOCAL = {'qwen38-mlx8': 'mlx-community/Qwen3.8-27B-8bit', 'swift15-mlx5': 'ukisai/Swift-1.5-5bit-MLX'}
REVISIONS = {'qwen38-mlx8': '815b83c0df8ffd1d1b5244cf75fd6ef14fca9ef9',
             'swift15-mlx5': '79bf5dd3f3fde79409bd32b29ecf5fc557fd2ca1'}
TASKS = ['finance', 'apache', 'access', 'compression', 'family_backup_note',
         'two_section_backup_checklist', 'family_text_lines']
XHIGH = 'Reasoning effort is set to xhigh.'


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prefix(label, round_, task):
    return OUT / f'{label}-pass{round_}-{task}'


def execution_scope():
    path = OUT / 'control.json'
    control = json.loads(path.read_text()) if path.exists() else {'rounds': [1, 2, 3], 'tasks': TASKS}
    assert control['rounds'] and set(control['rounds']) <= {1, 2, 3}
    assert control['tasks'] and set(control['tasks']) <= set(TASKS)
    return control


def scheduled_slots():
    control = execution_scope()
    return [(label, round_, task) for round_ in control['rounds'] for label in LABELS for task in control['tasks']]


def tasks():
    sys.path.insert(0, str(ROOT / 'scripts'))
    sys.path.insert(0, str(ROOT))
    from codex_gap_campaign import build_tasks
    result = build_tasks()
    original = result['compression']
    assert original.prompt.startswith('/no_think\n\n')
    result['compression'] = dataclasses.replace(original, prompt=original.prompt[len('/no_think\n\n'):])
    return result


def freeze():
    current = tasks()
    sys.path.insert(0, str(ROOT / 'scripts'))
    from codex_gap_campaign import build_tasks
    original = build_tasks()
    manifest = {'suite_id': 'qwen-family-full-xhigh', 'version': '1.0', 'source_suite': '1.1',
                'difference': 'Remove only the leading /no_think directive from compression; thinking on and xhigh for every task. Original checklist unchanged.',
                'score_max': 62, 'passes': 3, 'seeds': [20261020, 20261021, 20261022],
                'tasks': {k: {'task_id': v.task_id, 'source_prompt_sha256': sha(original[k].prompt.encode()),
                              'prompt_sha256': sha(v.prompt.encode())} for k, v in current.items()}}
    if SUITE.exists():
        assert json.loads(SUITE.read_text()) == manifest, 'Frozen suite changed'
    else:
        save(SUITE, manifest)
    for k, v in current.items():
        (OUT / f'{k}.prompt.txt').write_text(v.prompt)
    protocol_path = OUT / 'protocol.json'
    previous_protocol = OUT / 'protocol-initial-64k.json'
    if protocol_path.exists() and not previous_protocol.exists():
        previous_protocol.write_bytes(protocol_path.read_bytes())
    save(protocol_path, {
        'suite': manifest, 'order_per_round': LABELS, 'context_tokens': CONTEXT,
        'completion_cap': None, 'request_wall_timeout_s': TIMEOUT, 'mtp': False,
        'execution_scope': execution_scope(),
        'sampling': {'temperature': 1.0, 'top_p': .95, 'top_k': 20, 'min_p': 0,
                     'presence_penalty': 0, 'repeat_penalty': 1.0},
        'kv': 'Native unquantized: BF16 MLX attention; f16/f16 GGUF attention.',
        'prefill': '512 MLX; batch512/microbatch512 GGUF',
        'cache_reuse': False, 'warmup': 'One short 8-token request per model load, excluded from measured answers.',
        'grader': 'gpt-5.6-luna xhigh; source-aware-v2; delivered answers only',
        'limits': ['Models use their native templates, with explicit xhigh overrides; template differences are part of the package comparison.',
                   'GGUF and MLX, and their quantization formats, differ; throughput is not an isolated weight-quality comparison.',
                   'Recovery increased context from 64K to 128K; earlier completed and timed-out attempts are retained with their original execution settings. The one-hour wall limit remains.',
                   'Download/archive activity may overlap measurements; preparation status is captured with each request.'],
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'runner_sha256': sha(SCRIPT.read_bytes())})


def split_reasoning(raw):
    thought, marker, answer = raw.partition('</think>')
    return (thought.removeprefix('<think>'), answer) if marker else (raw, '')


def machine():
    return {'power': subprocess.check_output(['pmset', '-g', 'batt'], text=True),
            'swap': subprocess.check_output(['sysctl', 'vm.swapusage'], text=True)}


def preparation_status():
    try:
        return json.loads((OUT / 'preparation.json').read_text())['status']
    except (OSError, ValueError):
        return 'unknown'


def alarm(signum, frame):
    raise TimeoutError(f'Request exceeded {TIMEOUT}s wall limit')


def mlx_worker(label, round_):
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.models.cache import make_prompt_cache
    from mlx_lm.sample_utils import make_sampler
    model_path = Path.home() / 'models' / LOCAL[label]
    override = {'language_model_only': True} if label == 'qwen38-mlx8' else {}
    model, tokenizer = load(str(model_path), model_config=override)
    version = {n: importlib.metadata.version(n) for n in ['mlx', 'mlx-metal', 'mlx-lm', 'transformers', 'tokenizers']}
    runtime = {'versions': version, 'model_class': type(model).__module__ + '.' + type(model).__name__,
               'config_override': override, 'model_revision': REVISIONS[label],
               'context_tokens': CONTEXT, 'request_wall_timeout_s': TIMEOUT,
               'template_sha256': sha(tokenizer.chat_template.encode()), 'device': mx.device_info()}
    save(OUT / f'{label}-runtime.json', runtime)
    save(OUT / f'{label}-pass{round_}-runtime.json', runtime)
    warm = tokenizer.apply_chat_template([{'role': 'user', 'content': 'Reply READY.'}], tokenize=False,
                                         add_generation_prompt=True, enable_thinking=True, reasoning_effort='xhigh')
    for _ in stream_generate(model, tokenizer, warm, max_tokens=8, prefill_step_size=512):
        pass
    signal.signal(signal.SIGALRM, alarm)
    for task in execution_scope()['tasks']:
        p = prefix(label, round_, task)
        if p.with_suffix('.result.json').exists():
            continue
        prompt = (OUT / f'{task}.prompt.txt').read_text()
        rendered = tokenizer.apply_chat_template([{'role': 'user', 'content': prompt}], tokenize=False,
                                                 add_generation_prompt=True, enable_thinking=True, reasoning_effort='xhigh')
        assert XHIGH in rendered and rendered.endswith('<think>\n'), 'xhigh thinking was not rendered'
        p.with_suffix('.rendered.txt').write_text(rendered)
        mx.synchronize(); mx.clear_cache(); mx.reset_peak_memory(); mx.random.seed(20261019 + round_)
        row = {'model': label, 'round': round_, 'task': task, 'seed': 20261019 + round_,
               'context_tokens': CONTEXT, 'request_wall_timeout_s': TIMEOUT,
               'answer': '', 'reasoning': '', 'raw_text': '', 'finish_reason': None,
               'ttft_s': None, 'first_answer_s': None, 'prompt_sha256': sha(prompt.encode()),
               'rendered_sha256': sha(rendered.encode()), 'machine_before': machine(),
               'preparation_status': preparation_status()}
        cache = make_prompt_cache(model)
        started = time.monotonic(); heartbeat = started
        print('START', label, round_, task, flush=True)
        save(OUT / 'live.json', {'model': label, 'round': round_, 'task': task, 'started_at': time.time()})
        signal.alarm(TIMEOUT)
        try:
            with p.with_suffix('.events.jsonl').open('w') as events:
                for response in stream_generate(model, tokenizer, rendered, max_tokens=-1,
                        sampler=make_sampler(temp=1.0, top_p=.95, top_k=20, min_p=0),
                        prompt_cache=cache, prefill_step_size=512):
                    elapsed = time.monotonic() - started
                    row['raw_text'] += response.text
                    row['reasoning'], row['answer'] = split_reasoning(row['raw_text'])
                    if response.text and row['ttft_s'] is None:
                        row['ttft_s'] = elapsed
                    if row['answer'].strip() and row['first_answer_s'] is None:
                        row['first_answer_s'] = elapsed
                    row.update(generation_tokens=response.generation_tokens,
                               generation_tokens_per_s=response.generation_tps,
                               prompt_tokens=response.prompt_tokens, prompt_tokens_per_s=response.prompt_tps,
                               peak_mlx_memory_gb=response.peak_memory, finish_reason=response.finish_reason)
                    events.write(json.dumps({'elapsed_s': elapsed, 'token': response.token, 'text': response.text,
                                              'generation_tokens': response.generation_tokens}) + '\n')
                    if response.prompt_tokens + response.generation_tokens > CONTEXT:
                        raise RuntimeError('Declared 128K context exceeded')
                    if time.monotonic() - heartbeat >= 30:
                        events.flush()
                        save(OUT / 'live.json', {k: row.get(k) for k in ['model', 'round', 'task', 'generation_tokens', 'ttft_s', 'first_answer_s']} | {'elapsed_s': elapsed})
                        print('GENERATING', label, round_, task, round(elapsed), response.generation_tokens, flush=True)
                        heartbeat = time.monotonic()
            assert row['finish_reason'] == 'stop' and row['answer'].strip(), 'Incomplete delivered answer'
        except Exception as exc:
            row.update(error=repr(exc), finish_reason='error')
        finally:
            signal.alarm(0)
        row.update(total_s=time.monotonic() - started, machine_after=machine())
        for field in ['answer', 'reasoning']:
            p.with_suffix(f'.{field}.txt').write_text(row[field])
            row[field + '_tokens_retokenized'] = len(tokenizer.encode(row[field], add_special_tokens=False)) if row[field] else 0
        save(p.with_suffix('.result.json'), row)
        print('FINISHED', label, round_, task, row['finish_reason'], round(row['total_s'], 1), flush=True)


def api(path, payload=None, timeout=60):
    import requests
    r = requests.get(BASE + path, timeout=timeout) if payload is None else requests.post(BASE + path, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def gguf_request(label, round_, task, prompt, warmup=False):
    import requests
    p = prefix(label, round_, task)
    kwargs = {'enable_thinking': True, 'reasoning_effort': 'xhigh'}
    payload = {'model': label, 'messages': [{'role': 'user', 'content': prompt}],
               'chat_template_kwargs': kwargs, 'reasoning_effort': 'xhigh',
               'stream': True, 'stream_options': {'include_usage': True},
               'max_tokens': 8 if warmup else -1, 'cache_prompt': False,
               'temperature': 1.0, 'top_p': .95, 'top_k': 20, 'min_p': 0,
               'presence_penalty': 0, 'repeat_penalty': 1.0, 'seed': 20261019 + round_,
               'timings_per_token': True, 'return_progress': True}
    rendered = api('/apply-template', {'messages': payload['messages'], 'chat_template_kwargs': kwargs})['prompt']
    assert 'xhigh' in rendered.lower() and rendered.rstrip().endswith('<think>'), 'Native template did not enable xhigh thinking'
    if not warmup:
        p.with_suffix('.rendered.txt').write_text(rendered)
        save(p.with_suffix('.request.json'), payload)
    row = {'model': label, 'round': round_, 'task': task, 'seed': 20261019 + round_,
           'context_tokens': CONTEXT, 'request_wall_timeout_s': TIMEOUT,
           'answer': '', 'reasoning': '', 'finish_reason': None, 'ttft_s': None,
           'first_answer_s': None, 'prompt_sha256': sha(prompt.encode()),
           'rendered_sha256': sha(rendered.encode()), 'machine_before': machine(),
           'preparation_status': preparation_status()}
    started = time.monotonic(); heartbeat = started
    signal.signal(signal.SIGALRM, alarm); signal.alarm(TIMEOUT)
    try:
        with p.with_suffix('.events.jsonl').open('w') as events, requests.post(BASE + '/v1/chat/completions',
                json=payload, stream=True, timeout=(30, TIMEOUT)) as response:
            response.raise_for_status()
            for line in response.iter_lines(chunk_size=1):
                if not line or not line.startswith(b'data: '):
                    continue
                elapsed = time.monotonic() - started
                if line == b'data: [DONE]':
                    break
                event = json.loads(line[6:])
                events.write(json.dumps({'elapsed_s': elapsed, 'event': event}) + '\n'); events.flush()
                if event.get('error'):
                    raise RuntimeError(str(event['error']))
                for choice in event.get('choices', []):
                    delta = choice.get('delta', {})
                    text = delta.get('content') or ''
                    thought = delta.get('reasoning_content') or delta.get('reasoning') or ''
                    row['answer'] += text; row['reasoning'] += thought
                    if (text or thought) and row['ttft_s'] is None:
                        row['ttft_s'] = elapsed
                    if row['answer'].strip() and row['first_answer_s'] is None:
                        row['first_answer_s'] = elapsed
                    if choice.get('finish_reason'):
                        row['finish_reason'] = choice['finish_reason']
                    if delta.get('tool_calls'):
                        raise RuntimeError('Unexpected tool call in tool-free suite')
                if event.get('timings'):
                    row['timings'] = event['timings']
                if event.get('usage'):
                    row['usage'] = event['usage']
                if time.monotonic() - heartbeat >= 30:
                    save(OUT / 'live.json', {k: row.get(k) for k in ['model', 'round', 'task', 'ttft_s', 'first_answer_s']} | {'elapsed_s': elapsed, 'timings': row.get('timings')})
                    print('GENERATING', label, round_, task, round(elapsed), flush=True)
                    heartbeat = time.monotonic()
            if not warmup:
                assert row['finish_reason'] == 'stop' and row['answer'].strip(), 'Incomplete delivered answer'
    except Exception as exc:
        row.update(error=repr(exc), finish_reason='error')
    finally:
        signal.alarm(0)
    row.update(total_s=time.monotonic() - started, machine_after=machine())
    for field in ['answer', 'reasoning']:
        p.with_suffix(f'.{field}.txt').write_text(row[field])
        try:
            row[field + '_tokens_retokenized'] = len(api('/tokenize', {'content': row[field], 'add_special': False})['tokens']) if row[field] else 0
        except Exception as exc:
            row[field + '_tokens_retokenized'] = None
            row['tokenization_error'] = repr(exc)
    timing = row.get('timings', {})
    row.update(generation_tokens=timing.get('predicted_n'), generation_tokens_per_s=timing.get('predicted_per_second'),
               prompt_tokens=timing.get('prompt_n'), prompt_tokens_per_s=timing.get('prompt_per_second'))
    if not warmup:
        save(p.with_suffix('.result.json'), row)
        print('FINISHED', label, round_, task, row['finish_reason'], round(row['total_s'], 1), flush=True)
    return row


def stop(proc):
    if proc is not None and proc.poll() is None:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait()


def monitor(proc, path, done):
    peak = 0
    with path.open('w') as log:
        while not done.wait(5):
            try:
                rss = int(subprocess.check_output(['ps', '-o', 'rss=', '-p', str(proc.pid)], text=True).strip())
                peak = max(peak, rss)
                log.write(json.dumps({'time': time.time(), 'rss_kib': rss, 'peak_rss_kib': peak, **machine()}) + '\n'); log.flush()
            except (subprocess.CalledProcessError, ValueError):
                break
    save(path.with_suffix('.summary.json'), {'peak_rss_kib': peak})


def gguf_round(label, round_, task_names=None):
    identity = json.loads((OUT / f'{label}-download.json').read_text())
    assert identity['status'] == 'ready' and Path(identity['path']).stat().st_size == identity['bytes']
    command = [str(SERVER), '-m', identity['path'], '--alias', label, '--host', '127.0.0.1', '--port', '18081',
               '-c', str(CONTEXT), '-np', '1', '-b', '512', '-ub', '512', '-t', '4', '-ngl', '99',
               '--jinja', '--reasoning', 'on', '--reasoning-effort', 'xhigh', '--reasoning-budget', '-1',
               '--reasoning-format', 'deepseek', '--cache-type-k', 'f16', '--cache-type-v', 'f16',
               '--spec-type', 'none', '--no-context-shift']
    runtime = {'command': command, 'identity': identity,
               'version': subprocess.check_output([str(SERVER), '--version'], stderr=subprocess.STDOUT, text=True)}
    save(OUT / f'{label}-runtime.json', runtime)
    save(OUT / f'{label}-pass{round_}-runtime.json', runtime)
    proc = None; done = threading.Event(); sampler = None
    with (OUT / f'{label}-pass{round_}-server.log').open('w') as log:
        try:
            proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            sampler = threading.Thread(target=monitor, args=(proc, OUT / f'{label}-pass{round_}-memory.jsonl', done))
            sampler.start()
            for _ in range(600):
                if proc.poll() is not None:
                    raise RuntimeError(f'Server exited {proc.returncode}')
                try:
                    if api('/health', timeout=2).get('status') == 'ok':
                        break
                except Exception:
                    pass
                time.sleep(1)
            else:
                raise TimeoutError('Server failed to load in 600s')
            gguf_request(label, round_, 'warmup', 'Reply READY.', warmup=True)
            for task in task_names if task_names is not None else execution_scope()['tasks']:
                if not prefix(label, round_, task).with_suffix('.result.json').exists():
                    gguf_request(label, round_, task, (OUT / f'{task}.prompt.txt').read_text())
        finally:
            stop(proc); done.set()
            if sampler:
                sampler.join(timeout=10)


def judge_file(path):
    sys.path.insert(0, str(ROOT))
    from grader.semantic_judge import judge_result
    row = json.loads(path.read_text())
    task = tasks()[row['task']]
    diagnostic = task.grader(row['answer'])
    grade, metadata = judge_result(row['answer'], diagnostic, task.task_id, task_prompt=task.prompt,
                                    finish_reason=row['finish_reason'])
    save(path.with_suffix('.grade.json'), {'semantic_grade': grade, 'semantic_judge': metadata,
                                          'diagnostic_grade': diagnostic, 'source_sha256': sha(path.read_bytes())})


def judge_loop(done):
    attempted = set()
    while True:
        pending = [p for p in sorted(OUT.glob('*-pass*-*.result.json'))
                   if not p.with_suffix('.grade.json').exists() and p not in attempted]
        for p in pending:
            attempted.add(p)
            with p.with_suffix('.judge.log').open('a') as log:
                try:
                    subprocess.run([str(PYTHON), str(SCRIPT), 'judge', '--result', str(p)], stdout=log,
                                   stderr=subprocess.STDOUT, timeout=900, check=True)
                except (subprocess.SubprocessError, OSError) as exc:
                    log.write(repr(exc) + '\n')
        if done.is_set():
            remaining = [p for p in OUT.glob('*-pass*-*.result.json')
                         if not p.with_suffix('.grade.json').exists() and p not in attempted]
            if not remaining:
                break
        done.wait(10)


def run():
    freeze()
    scope = execution_scope()
    prior = json.loads((OUT / 'state.json').read_text()) if (OUT / 'state.json').exists() else {}
    state = {'status': 'running', 'started_at': time.time(), 'planned_answers': 105, 'model_order': LABELS,
             'context_tokens': CONTEXT, 'request_wall_timeout_s': TIMEOUT,
             'rounds': 3, 'thinking': 'on, xhigh', 'errors': []}
    state.update(scope=scope, active_target_answers=len(scheduled_slots()))
    if prior:
        state.update(started_at=prior.get('started_at', time.time()), resumed_at=time.time())
    with (ROOT / 'benchy-state/campaign.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        done = threading.Event()
        judge = threading.Thread(target=judge_loop, args=(done,)); judge.start()
        try:
            for round_ in scope['rounds']:
                for label in LABELS:
                    if all(prefix(label, round_, t).with_suffix('.result.json').exists() for t in scope['tasks']):
                        continue
                    state.update(current_model=label, current_round=round_)
                    save(OUT / 'state.json', state)
                    proc = None; sampled = None; monitor_done = threading.Event()
                    try:
                        if label in LOCAL:
                            env = os.environ | {'MLX_GDN_PACKED': '1', 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'}
                            with (OUT / f'{label}-pass{round_}.log').open('a') as log:
                                proc = subprocess.Popen([str(MLX_PYTHON), '-u', str(SCRIPT), 'mlx', '--model', label, '--round', str(round_)], env=env, stdout=log, stderr=subprocess.STDOUT)
                                sampled = threading.Thread(target=monitor, args=(proc, OUT / f'{label}-pass{round_}-memory.jsonl', monitor_done)); sampled.start()
                                result = proc.wait(timeout=7 * TIMEOUT + 900)
                                if result:
                                    raise RuntimeError(f'MLX worker exited {result}')
                        else:
                            while not (OUT / f'{label}-download.json').exists() or json.loads((OUT / f'{label}-download.json').read_text()).get('status') != 'ready':
                                if preparation_status() == 'error':
                                    raise RuntimeError('Model preparation failed; see preparation.json')
                                state['waiting_for_download'] = label; save(OUT / 'state.json', state)
                                time.sleep(10)
                            state.pop('waiting_for_download', None)
                            gguf_round(label, round_)
                    except Exception as exc:
                        state['errors'].append({'model': label, 'round': round_, 'error': repr(exc)})
                        print('MODEL ERROR', label, round_, repr(exc), flush=True)
                    finally:
                        stop(proc); monitor_done.set()
                        if sampled:
                            sampled.join(timeout=10)
                    state['saved_answers'] = len(list(OUT.glob('*-pass*-*.result.json')))
                    save(OUT / 'state.json', state)
            state.update(status='grading', current_model=None, current_round=None)
        finally:
            done.set(); judge.join()
            state['saved_answers'] = len(list(OUT.glob('*-pass*-*.result.json')))
            active = [prefix(label, round_, task).with_suffix('.result.json') for label, round_, task in scheduled_slots()]
            state['active_saved_answers'] = sum(path.exists() for path in active)
            state['status'] = 'scope_finished' if all(path.exists() for path in active) and not state['errors'] else 'finished_with_incomplete_results'
            state['finished_at'] = time.time(); save(OUT / 'state.json', state)
            subprocess.run([str(PYTHON), str(ROOT / 'scripts/publish_qwen_family_xhigh.py')], check=True)


def self_test():
    assert split_reasoning('thought</think>\nanswer') == ('thought', '\nanswer')
    assert split_reasoning('unfinished') == ('unfinished', '')
    current = tasks()
    assert list(current) == TASKS and '/no_think' not in current['compression'].prompt[:30]
    assert current['two_section_backup_checklist'].prompt == (ROOT / 'benchmarks/suites/checklist-v1.1.txt').read_text()
    assert len(LABELS) * len(TASKS) * 3 == 105
    scope = execution_scope()
    assert len(scheduled_slots()) == len(LABELS) * len(scope['rounds']) * len(scope['tasks'])
    assert all(sha(t.prompt.encode()) == json.loads(SUITE.read_text())['tasks'][k]['prompt_sha256'] for k, t in current.items())
    print('Campaign self-checks passed: frozen task hashes, unchanged checklist, thinking split, 105 slots.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['freeze', 'run', 'mlx', 'judge', 'self-test'])
    parser.add_argument('--model', choices=LABELS)
    parser.add_argument('--round', type=int, choices=[1, 2, 3])
    parser.add_argument('--result', type=Path)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.mode == 'freeze':
        freeze()
    elif args.mode == 'run':
        run()
    elif args.mode == 'mlx':
        mlx_worker(args.model, args.round)
    elif args.mode == 'judge':
        judge_file(args.result)
    else:
        self_test()
