#!/usr/bin/env python3
"""One sequential Cerebras FP16 pass of the five non-heavy tasks."""
import argparse
import json
import subprocess
import time
from pathlib import Path

from tokenizers import Tokenizer

import run_qwen_openrouter_baseline as hosted
from qwen_family_dashboard import MAXIMA, hosted_result, hosted_speed
from run_qwen_family_xhigh import OUT, PYTHON, ROOT, SCRIPT, save, sha, tasks

DIRECTORY = OUT / 'cerebras-five-task'
TASKS = ['access', 'compression', 'family_backup_note', 'two_section_backup_checklist', 'family_text_lines']


def configure():
    hosted.DIRECTORY = DIRECTORY
    hosted.PROVIDER = 'cerebras/fp16'
    hosted.MAX_TOKENS = 32768
    hosted.CONTEXT = 65536
    hosted.SAMPLING_NOTE = 'Cerebras FP16: temperature 1, top_p .95, seed 20261020; top_k is not exposed.'


def summarize():
    records = []
    for task in TASKS:
        row, score, status = hosted_result(OUT, task, results_subdir='cerebras-five-task')
        if not row:
            continue
        fields = ['task', 'model', 'provider_requested', 'provider', 'id', 'prompt_sha256', 'reasoning_effort',
                  'max_tokens', 'context_tokens', 'wall_limit_s', 'sampling_note', 'started_at',
                  'finish_reason', 'ttft_s', 'first_answer_s', 'total_s', 'prompt_tokens',
                  'generation_tokens', 'reasoning_tokens_provider', 'reasoning_tokens_retokenized',
                  'answer_tokens_retokenized', 'cost_usd']
        record = {field: row.get(field) for field in fields}
        path = DIRECTORY / f'qwen38-{task}.result.json'
        record.update(semantic_score=score, semantic_max=MAXIMA[task], status=status,
                      observed_generation_tokens_per_s=hosted_speed(row),
                      evidence=str(path.relative_to(ROOT)), source_sha256=sha(path.read_bytes()))
        if score is not None:
            grade_path = path.with_suffix('.grade.json')
            record.update(grade_evidence=str(grade_path.relative_to(ROOT)), grade_sha256=sha(grade_path.read_bytes()))
        billing_path = path.with_suffix('.generation.json')
        if billing_path.exists():
            billing = json.loads(billing_path.read_text()).get('data', {})
            assert billing.get('id') == row.get('id')
            record.update(billing_total_cost_usd=billing.get('total_cost'),
                          cached_prompt_tokens=billing.get('native_tokens_cached'),
                          billing_evidence=str(billing_path.relative_to(ROOT)))
        records.append(record)
    costs = [r['cost_usd'] for r in records]
    scores = [r['semantic_score'] for r in records]
    save(ROOT / 'benchmarks/runs/qwen38-cerebras-five-task-xhigh-20261020.json', {
        'experiment_id': 'qwen38-cerebras-five-task-xhigh-20261020',
        'suite': 'qwen-family-full-xhigh@1.0', 'provider': 'cerebras/fp16',
        'judge': {'model': 'gpt-5.6-luna', 'effort': 'xhigh', 'protocol': 'source-aware-v2'},
        'task_order': TASKS, 'planned_requests': 5, 'passes': 1,
        'status': 'complete' if len(records) == 5 else 'in_progress',
        'score_max': 40, 'score': sum(scores) if len(scores) == 5 and all(s is not None for s in scores) else None,
        'cost_usd': sum(costs) if len(costs) == 5 and all(c is not None for c in costs) else None,
        'limitations': ['One sequential pass, xhigh, 64K context and 32K maximum generated tokens.',
                        'Hosted timings and costs include provider behavior; local runtime results remain separate.',
                        'Top-k is not exposed; prompts match the thinking-on variant, including compression.'],
        'records': records})


def run():
    configure()
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    state = {'status': 'running', 'task_order': TASKS, 'started_at': time.time()}
    save(DIRECTORY / 'state.json', state)
    hosted.dashboard()
    tokenizer = Tokenizer.from_file(str(Path.home() / 'models/mlx-community/Qwen3.8-27B-8bit/tokenizer.json'))
    paths = []
    for task in TASKS:
        state['current_task'] = task
        save(DIRECTORY / 'state.json', state)
        paths.append(hosted.run(task, tokenizer))
        summarize()
    state.update(status='grading', current_task=None)
    save(DIRECTORY / 'state.json', state)
    for path in paths:
        row = json.loads(path.read_text())
        if row['finish_reason'] == 'stop' and row['answer'].strip() and not path.with_suffix('.grade.json').exists():
            with path.with_suffix('.judge.log').open('a') as log:
                try:
                    subprocess.run([str(PYTHON), str(SCRIPT), 'judge', '--result', str(path)],
                                   stdout=log, stderr=subprocess.STDOUT, timeout=900, check=True)
                except (OSError, subprocess.SubprocessError) as exc:
                    log.write(repr(exc) + '\n')
        summarize()
        hosted.dashboard()
    state.update(status='complete', finished_at=time.time())
    save(DIRECTORY / 'state.json', state)
    save(DIRECTORY / 'live.json', {'status': 'complete', 'finished_at': time.time()})
    hosted.dashboard()
    print('Cerebras five-task pass complete', flush=True)


def self_check():
    configure()
    assert len(TASKS) == 5 and not set(TASKS) & {'finance', 'apache'}
    frozen = json.loads(hosted.SUITE.read_text())
    tokenizer = Tokenizer.from_file(str(Path.home() / 'models/mlx-community/Qwen3.8-27B-8bit/tokenizer.json'))
    for task in TASKS:
        prompt = tasks()[task].prompt
        assert sha(prompt.encode()) == frozen['tasks'][task]['prompt_sha256']
        request = hosted.request_payload(tasks()[task], hosted.MAX_TOKENS)
        assert request['provider']['only'] == ['cerebras/fp16']
        assert request['max_tokens'] == 32768 and request['seed'] == 20261020
        assert request['reasoning']['effort'] == 'xhigh' and 'top_k' not in request
        assert len(tokenizer.encode(prompt, add_special_tokens=False).ids) + 32768 + 128 < 65536
    print('Cerebras checks passed: five tasks only, exact prompts, xhigh, seed, supported controls and context fit.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    self_check() if args.self_check else run()
