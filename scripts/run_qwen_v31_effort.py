#!/usr/bin/env python3
"""Compare four thinking settings on four frozen Qwen tasks."""
import fcntl, hashlib, html, inspect, json, subprocess, time
from pathlib import Path
import run_qwen_family_xhigh as bench

ROOT=bench.ROOT
OUT=ROOT/'results/qwen-v31-effort-20261114'
BASE=ROOT/'results/qwen-v31-20261114/baseline-xhigh'
PAGE=ROOT/'qwen-v31-effort-results.html'
LABEL='unsloth-v31-q4xl'
TASKS=['access','compression','family_backup_note','two_section_backup_checklist','family_text_lines']
LEVELS=['off','low','medium','xhigh']
MAXIMA={'access':7,'compression':12,'family_backup_note':6,'two_section_backup_checklist':7,'family_text_lines':8}
ORIGINAL_REQUEST=bench.gguf_request
ORIGINAL_POPEN=subprocess.Popen

def result_path(level, n, task):
    directory=BASE if level=='xhigh' else OUT/level
    return directory/f'{LABEL}-pass{n}-{task}.result.json'

def render():
    rows=[]; finished=0
    for level in LEVELS:
        for n in (1,2,3):
            for task in TASKS:
                path=result_path(level,n,task); row={}; score='-'; status='Queued'
                if path.exists():
                    finished+=1; row=json.loads(path.read_text()); status='Completed' if row.get('finish_reason')=='stop' and row.get('answer','').strip() else 'Failed'
                    grade=path.with_suffix('.grade.json')
                    if grade.exists() and status=='Completed':
                        g=json.loads(grade.read_text()); meta=g.get('semantic_judge',{}); v=g.get('semantic_grade',{})
                        if g.get('source_sha256')==hashlib.sha256(path.read_bytes()).hexdigest() and meta.get('judge_protocol')=='source-aware-v2' and meta.get('judge_model')=='gpt-5.6-luna' and meta.get('judge_effort')=='xhigh' and v.get('max_score')==MAXIMA[task] and type(v.get('score')) is int:
                            score=f"{v['score']}/{MAXIMA[task]}";status='Graded'
                cells=[level,str(n),task,status,score,str(round(row['total_s'],1)) if row.get('total_s') is not None else '-',str(round(row['first_answer_s'],1)) if row.get('first_answer_s') is not None else '-',str(row.get('reasoning_tokens_retokenized','-')),str(round(row['generation_tokens_per_s'],2)) if row.get('generation_tokens_per_s') is not None else '-']
                rows.append('<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in cells)+'</tr>')
    body=''.join(rows)
    page=f'''<!doctype html><html><head><meta charset="utf-8"><title>Qwen v3.1 thinking effort</title><style>body{{font:15px system-ui;background:#10151d;color:#edf3fa;margin:2em}}table{{border-collapse:collapse}}td,th{{border:1px solid #556;padding:7px;text-align:left}}.stamp{{float:right}}</style></head><body><div class="stamp">Updated {html.escape(time.strftime('%Y-%m-%d %H:%M:%S %Z'))}</div><h1>Qwen v3.1 thinking effort</h1><p>{finished}/60 attempts saved; {60-finished}/60 remaining. Compression is being tested at off, low, and medium; the existing xhigh passes are reused. Times include prompt processing; tok/s includes reasoning and answer.</p><table><tr><th>Effort</th><th>Pass</th><th>Task</th><th>Status</th><th>Score</th><th>Elapsed s</th><th>Answer starts s</th><th>Thinking tokens</th><th>Generation tok/s</th></tr>{body}</table></body></html>'''
    temp=PAGE.with_suffix('.tmp');temp.write_text(page);temp.replace(PAGE)

def judge(path):
    r=json.loads(path.read_text())
    if r.get('finish_reason')=='stop' and r.get('answer','').strip() and not path.with_suffix('.grade.json').exists():
        with path.with_suffix('.judge.log').open('a') as log:
            try: subprocess.run([str(bench.PYTHON),str(bench.SCRIPT),'judge','--result',str(path)],stdout=log,stderr=subprocess.STDOUT,timeout=900,check=True)
            except (OSError,subprocess.SubprocessError) as exc: log.write(repr(exc)+'\n')
    render()

def setup_level(level):
    folder=OUT/level;folder.mkdir(parents=True,exist_ok=True)
    for task in TASKS:
        (folder/f'{task}.prompt.txt').write_bytes((BASE/f'{task}.prompt.txt').read_bytes())
    (folder/f'{LABEL}-download.json').write_bytes((BASE/f'{LABEL}-download.json').read_bytes())
    bench.OUT=folder
    src=inspect.getsource(ORIGINAL_REQUEST).replace("'reasoning_effort': 'xhigh'",f"'reasoning_effort': '{level}'").replace("'enable_thinking': True",f"'enable_thinking': {level != 'off'}").replace("'xhigh' in rendered.lower() and rendered.rstrip().endswith('<think>')",("not rendered.rstrip().endswith('<think>')" if level=='off' else "rendered.rstrip().endswith('<think>')"))
    assert f"'reasoning_effort': '{level}'" in src
    exec(compile(src,'<effort request>','exec'),bench.__dict__)
    request=bench.gguf_request
    def run_request(label,n,task,prompt,warmup=False):
        result=request(label,n,task,prompt,warmup)
        if not warmup:
            render();judge(result_path(level,n,task))
        return result
    bench.gguf_request=run_request
    def run_server(command,*args,**kwargs):
        command=list(command)
        if '--reasoning-effort' in command:
            command[command.index('--reasoning-effort')+1]=level
            command[command.index('--reasoning')+1]='off' if level=='off' else 'on'
        return ORIGINAL_POPEN(command,*args,**kwargs)
    subprocess.Popen=run_server

def main():
    OUT.mkdir(parents=True,exist_ok=True);render()
    with (ROOT/'benchy-state/campaign.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        for level in LEVELS[:3]:
            setup_level(level)
            for n in (1,2,3):
                bench.save(OUT/'state.json',{'status':'running','level':level,'round':n,'task':'compression','updated_at':time.time()})
                if not result_path(level,n,'compression').exists():
                    bench.gguf_round(LABEL,n,task_names=['compression'])
                for task in ['compression']:
                    path=result_path(level,n,task)
                    if path.exists(): judge(path)
        bench.save(OUT/'state.json',{'status':'finished','updated_at':time.time()});render()

if __name__=='__main__':
    try: main()
    except Exception as exc:
        bench.save(OUT/'state.json',{'status':'failed','error':repr(exc),'updated_at':time.time()});render();raise
