#!/usr/bin/env python3
"""Publish the saved xhigh experiment separately from historical suite rankings."""
import json
import statistics
import subprocess
import sys
from pathlib import Path

from run_qwen_family_xhigh import LABELS, NAMES, OUT, ROOT, SUITE, TASKS, execution_scope, scheduled_slots, prefix, save, sha
from qwen_family_dashboard import write_dashboard

RECORD = ROOT / 'benchmarks/runs/qwen-family-full-xhigh-macos-20261020.json'
MAXIMA = [12, 10, 7, 12, 6, 7, 8]


def summarize(rows, task_keys=TASKS, rounds=(1, 2, 3)):
    rows = [r for r in rows if r['task'] in task_keys and r['round'] in rounds]
    by_slot = {(r['round'], r['task']): r for r in rows}
    assert len(by_slot) == len(rows), 'Duplicate measured slots'
    totals = []
    for round_ in rounds:
        scores = [by_slot.get((round_, t), {}).get('semantic_score') for t in task_keys]
        totals.append(sum(scores) if all(s is not None for s in scores) else None)
    per_task = {}
    for task in task_keys:
        rr = [r for r in rows if r['task'] == task]
        scores = [r.get('semantic_score') for r in rr]
        metrics = {}
        for key in ['ttft_s', 'first_answer_s', 'total_s', 'reasoning_tokens_retokenized', 'answer_tokens_retokenized']:
            values = [r[key] for r in rr if r.get(key) is not None and r['finish_reason'] == 'stop']
            metrics['mean_' + key] = statistics.mean(values) if values else None
        good = [r for r in rr if r.get('generation_tokens') and r.get('generation_tokens_per_s') and r['finish_reason'] == 'stop']
        metrics['weighted_generation_tokens_per_s'] = sum(r['generation_tokens'] for r in good) / sum(r['generation_tokens'] / r['generation_tokens_per_s'] for r in good) if good else None
        pp = [r['prompt_tokens_per_s'] for r in rr if r.get('prompt_tokens_per_s') and r['finish_reason'] == 'stop']
        metrics['mean_prompt_tokens_per_s'] = statistics.mean(pp) if pp else None
        per_task[task] = {'scores': scores, 'mean_score': statistics.mean(scores) if len(scores) == len(rounds) and all(s is not None for s in scores) else None, **metrics}
    good = [r for r in rows if r.get('generation_tokens') and r.get('generation_tokens_per_s') and r['finish_reason'] == 'stop']
    return {'pass_totals': totals, 'mean_score': statistics.mean(totals) if all(t is not None for t in totals) else None,
            'score_range': [min(totals), max(totals)] if all(t is not None for t in totals) else None,
            'completed_answers': sum(r['finish_reason'] == 'stop' and r.get('has_answer') for r in rows),
            'graded_answers': sum(r.get('semantic_score') is not None for r in rows),
            'weighted_generation_tokens_per_s': sum(r['generation_tokens'] for r in good) / sum(r['generation_tokens'] / r['generation_tokens_per_s'] for r in good) if good else None,
            'tasks': per_task}


def fmt(value, places=2):
    return '-' if value is None else f'{value:.{places}f}'


def main():
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    assert branch == 'bench/qwen-family-full-xhigh-20261020', 'Refuse to publish on an unexpected branch'
    protocol = json.loads((OUT / 'protocol.json').read_text())
    scope = execution_scope()
    focused = bool(scope.get('paused_tasks'))
    comparison_tasks = scope['tasks'] if focused else TASKS
    comparison_rounds = scope.get('comparison_rounds', [1, 2]) if focused else [1, 2, 3]
    comparison_max = sum(MAXIMA[TASKS.index(t)] for t in comparison_tasks)
    models = []
    for label, name in zip(LABELS, NAMES):
        rows = []
        for round_ in [1, 2, 3]:
            for task in TASKS:
                path = prefix(label, round_, task).with_suffix('.result.json')
                if not path.exists():
                    continue
                r = json.loads(path.read_text())
                fields = ['model', 'round', 'task', 'seed', 'finish_reason', 'ttft_s', 'first_answer_s', 'total_s',
                          'generation_tokens', 'generation_tokens_per_s', 'prompt_tokens', 'prompt_tokens_per_s',
                          'reasoning_tokens_retokenized', 'answer_tokens_retokenized', 'peak_mlx_memory_gb',
                          'prompt_sha256', 'rendered_sha256', 'machine_before', 'machine_after', 'preparation_status']
                row = {k: r.get(k) for k in fields}
                row.update(context_tokens=r.get('context_tokens', 65536),
                           request_wall_timeout_s=r.get('request_wall_timeout_s', 3600))
                row.update(source_artifact=str(path.relative_to(ROOT)), source_sha256=sha(path.read_bytes()),
                           has_answer=bool(r['answer'].strip()), semantic_score=None)
                grade_path = path.with_suffix('.grade.json')
                if grade_path.exists():
                    g = json.loads(grade_path.read_text())
                    assert g['source_sha256'] == sha(path.read_bytes()), 'Judgment source mismatch'
                    meta, grade = g['semantic_judge'], g['semantic_grade']
                    assert meta['judge_protocol'] == 'source-aware-v2'
                    assert meta['task_prompt_sha256'] == row['prompt_sha256']
                    score = grade.get('score')
                    if score is not None:
                        assert meta['judge_model'] == 'gpt-5.6-luna' and meta['judge_effort'] == 'xhigh'
                        assert grade['max_score'] == MAXIMA[TASKS.index(task)] and 0 <= score <= grade['max_score']
                    row.update(semantic_score=score, semantic_max=grade['max_score'],
                               grade_artifact=str(grade_path.relative_to(ROOT)), grade_sha256=sha(grade_path.read_bytes()),
                               judge_usage=meta.get('usage'), judge_elapsed_s=meta.get('elapsed_s'))
                if row['finish_reason'] != 'stop' or not row['has_answer']:
                    row['semantic_score'] = None
                rows.append(row)
        runtime_path = OUT / f'{label}-runtime.json'
        runtime = json.loads(runtime_path.read_text()) if runtime_path.exists() else None
        if runtime and 'identity' in runtime:
            runtime['identity'] = {k: v for k, v in runtime['identity'].items() if k != 'path'}
            runtime['command'] = ['<local-model-path>' if v.startswith(str(Path.home() / 'models')) else '<llama-server>' if v == runtime['command'][0] else v for v in runtime['command']]
        memory = [json.loads(p.read_text())['peak_rss_kib'] for p in OUT.glob(f'{label}-pass*-memory.summary.json')]
        mlx_memory = [r['peak_mlx_memory_gb'] for r in rows if r.get('peak_mlx_memory_gb') is not None]
        models.append({'label': label, 'name': name, 'runtime': runtime, 'records': rows,
                       'peak_process_rss_gib': max(memory) / 1024**2 if memory else None,
                       'peak_mlx_memory_gb': max(mlx_memory) if mlx_memory else None,
                       'summary': summarize(rows),
                       'comparison_summary': summarize(rows, comparison_tasks, comparison_rounds)})
    active_slots = set(scheduled_slots())
    active = [r for m in models for r in m['records'] if (r['model'], r['round'], r['task']) in active_slots]
    complete = (len(active) == len(active_slots) and all(r['finish_reason'] == 'stop' and r['has_answer'] and r['semantic_score'] is not None for r in active))
    status = f'round{max(comparison_rounds)}_complete_heavy_tasks_paused' if complete and focused else 'complete' if complete else 'finished_with_incomplete_results'
    state = json.loads((OUT / 'state.json').read_text())
    state.update(status=status, scope=scope,
                 completed_answers=sum(m['summary']['completed_answers'] for m in models),
                 graded_answers=sum(m['summary']['graded_answers'] for m in models),
                 publication_status='writing')
    save(OUT / 'state.json', state)
    record = {'experiment_id': 'qwen-family-full-xhigh-macos-20261020', 'status': status,
              'date': '2026-10-20', 'hardware': 'Apple M1 Max 64GB, macOS Metal', 'suite': json.loads(SUITE.read_text()),
              'protocol': protocol, 'models': models,
              'execution_scope': scope,
              'comparison': {'tasks': comparison_tasks, 'rounds': comparison_rounds, 'score_max': comparison_max},
              'comparison_policy': 'Rank within this thinking-on variant only. Original suite 1.1 compression has /no_think, so these /62 totals do not join historical combined ranking.',
              'memory_policy': 'MLX peak is backend-reported decimal GB; process RSS is GiB and does not include every Metal allocation. These are separate measurements, not interchangeable model footprints.',
              'source_artifact': str((OUT / 'state.json').relative_to(ROOT)),
              'failures': json.loads((OUT / 'state.json').read_text()).get('errors', [])}
    save(RECORD, record)
    save(OUT / 'comparison.json', record)
    lead = (f'Apache and Finance are paused. The comparison below uses the five selected tasks in rounds {", ".join(map(str, comparison_rounds))}, out of 40 per pass. Original heavy-task attempts remain in the saved history. ' if focused else 'Three scheduled passes per model. ') + 'Explicit thinking on/xhigh. Compression omits only the original /no_think directive. Context increased from 64K to 128K after first-round context failures; the one-hour wall limit remains. Results retain their actual context setting. This experiment is separate from historical suite rankings. Missing or incomplete results display as a dash.'
    lines = ['# Five-model xhigh comparison - five-task results' if focused else '# Five-model full-suite xhigh comparison', '', lead, '',
             '| Model | ' + ' | '.join(f'Pass {n} /{comparison_max}' for n in comparison_rounds) + f' | Mean /{comparison_max} | Generation tok/s |',
             '|---|' + '---:|' * (len(comparison_rounds) + 2)]
    for m in models:
        s = m['comparison_summary']
        lines.append('| ' + m['name'] + ' | ' + ' | '.join(fmt(t, 0) for t in s['pass_totals']) + f" | {fmt(s['mean_score'])} | {fmt(s['weighted_generation_tokens_per_s'])} |")
    lines += ['', 'Generation throughput includes thinking and answer tokens. GGUF/MLX formats, quantization and native templates differ. First-answer latency is measured separately from TTFT. Raw answers and reasoning remain in the local results directory.', '',
              '| Model | Task | Mean score | TTFT s | First answer s | Thinking tokens | Generation tok/s | PP tok/s |',
              '|---|---|---:|---:|---:|---:|---:|---:|']
    for m in models:
        for task in comparison_tasks:
            maximum = MAXIMA[TASKS.index(task)]
            s = m['comparison_summary']['tasks'][task]
            lines.append(f"| {m['name']} | {task} | {fmt(s['mean_score'])}/{maximum} | {fmt(s['mean_ttft_s'])} | {fmt(s['mean_first_answer_s'])} | {fmt(s['mean_reasoning_tokens_retokenized'], 0)} | {fmt(s['weighted_generation_tokens_per_s'])} | {fmt(s['mean_prompt_tokens_per_s'])} |")
    report_text = '\n'.join(lines) + '\n'
    (OUT / 'comparison.md').write_text(report_text)
    leaderboard = ROOT / 'leaderboards/data/leaderboard-64gb.json'
    data = json.loads(leaderboard.read_text())
    experiments = data.setdefault('comparisons', [])
    experiments[:] = [x for x in experiments if x.get('experiment_id') != record['experiment_id']]
    experiments.append({'experiment_id': record['experiment_id'], 'suite': 'qwen-family-full-xhigh@1.0',
                        'status': record['status'], 'source': str(RECORD.relative_to(ROOT)),
                        'comparison': record['comparison'],
                        'ranking_scope': 'Within this thinking-on experiment only',
                        'models': [{'name': m['name'], **m['comparison_summary']} for m in models]})
    save(leaderboard, data)
    write_dashboard()
    subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)
    subprocess.run([str(ROOT / '.venv/bin/python'), '-m', 'unittest', 'discover', '-s', 'tests'], cwd=ROOT, check=True)
    files = [str(RECORD.relative_to(ROOT)), 'leaderboards/data/leaderboard-64gb.json',
             'qwen-family-xhigh-results.html', 'scripts/qwen_family_dashboard.py',
             'benchmarks/suites/qwen-family-full-xhigh-v1.json', 'scripts/run_qwen_family_xhigh.py',
             'scripts/publish_qwen_family_xhigh.py']
    subprocess.run(['git', 'add', '--', *files], cwd=ROOT, check=True)
    diff = subprocess.run(['git', 'diff', '--cached', '--quiet', '--', *files], cwd=ROOT)
    if diff.returncode == 1:
        subprocess.run(['git', 'commit', '--only', '-m', 'Add five-model full-suite xhigh comparison', '--', *files], cwd=ROOT, check=True)
        branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
        assert branch == 'bench/qwen-family-full-xhigh-20261020', 'Refuse to push an unexpected branch'
        if '--local-only' not in sys.argv:
            subprocess.run(['git', 'push', '-u', 'origin', branch], cwd=ROOT, check=True)
    publication_status = 'local_complete' if '--local-only' in sys.argv else 'published'
    save(OUT / 'publication.json', {'status': publication_status, 'complete': complete,
                                   'record': str(RECORD.relative_to(ROOT)),
                                   'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()})
    state['publication_status'] = publication_status
    save(OUT / 'state.json', state)
    print('PUBLISHED', record['status'], str(RECORD), flush=True)


if __name__ == '__main__':
    if '--self-test' in sys.argv:
        sample = [{'round': n, 'task': t, 'semantic_score': m, 'finish_reason': 'stop', 'has_answer': True}
                  for n in [1, 2, 3] for t, m in zip(TASKS, MAXIMA)]
        assert summarize(sample)['pass_totals'] == [62, 62, 62]
        assert summarize(sample)['mean_score'] == 62
        assert summarize(sample, TASKS[2:], [1, 2])['pass_totals'] == [40, 40]
        assert summarize(sample, TASKS[2:], [1, 2, 3])['pass_totals'] == [40, 40, 40]
        sample[0]['semantic_score'] = None
        assert summarize(sample)['pass_totals'][0] is None and summarize(sample)['mean_score'] is None
        print('Publication self-checks passed: totals and missing scores.')
    else:
        main()
