#!/usr/bin/env python3
"""One local xhigh pass of the two selected operational/security candidates."""
import fcntl,inspect,json,shutil,time
from pathlib import Path
import run_qwen_family_xhigh as bench
from calibrate_security_lite import FIX,OUT,build,cases
from grader.semantic_judge import judge_result
from report_security_lite import report

LOCAL=OUT/'local'
LABEL='unsloth-v31-q4xl'
SELECTED=['apache-ops-v4','security-untrusted-log-v4']
IDENTITY=bench.ROOT/'results/qwen-v31-20261114/baseline-xhigh'/f'{LABEL}-download.json'

def state(status,task=None,error=None):
    bench.save(LOCAL/'state.json',{'status':status,'task':task,'planned':len(SELECTED),'selected':SELECTED,'saved':sum((OUT/f'{name}.local.result.json').exists() for name in SELECTED),'updated_at':time.time(),'error':error})
    report()

def run():
    LOCAL.mkdir(parents=True,exist_ok=True)
    with (bench.ROOT/'benchy-state/campaign.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        identity=json.loads(IDENTITY.read_text())
        assert Path(identity['path']).stat().st_size==identity['bytes']
        bench.save(LOCAL/f'{LABEL}-download.json',identity)
        artifacts={}
        for i in range(1,7):
            name,prompt,a=build(i)
            revised=FIX/name/'rubric-0.2.json'
            if revised.exists():a=json.loads(revised.read_text())
            artifacts[name]=a
            (LOCAL/f'{name}.prompt.txt').write_text(prompt)
        bench.OUT=LOCAL;bench.TIMEOUT=1800
        src=inspect.getsource(bench.gguf_request).replace('8 if warmup else -1','8 if warmup else 12288').replace('20261019 + round_','20261115')
        assert '8 if warmup else 12288' in src and '20261019 + round_' not in src
        exec(compile(src,'<local security request>','exec'),bench.__dict__)
        original=bench.gguf_request
        def request(label,n,task,prompt,warmup=False):
            if not warmup:state('running',task)
            row=original(label,n,task,prompt,warmup)
            if not warmup:
                row.update(task=artifacts[task]['task_id'],provider='local Metal',model_quant='Unsloth UD3.1 Q4_K_XL',reasoning_effort='xhigh',max_tokens=12288,thinking_tokens=row.get('reasoning_tokens_retokenized'))
                path=OUT/f'{task}.local.result.json';bench.save(path,row);state('grading',task)
                a=artifacts[task]
                g,m=judge_result(row['answer'],{'checks':a['checks'],'reference':a['reference']},a['task_id'],task_prompt=prompt,finish_reason=row['finish_reason'])
                bench.save(path.with_suffix('.grade.json'),{'semantic_grade':g,'semantic_judge':m,'source_sha256':bench.sha(path.read_bytes()),'rubric_revision':a.get('scoring_revision','0.1')})
                print('GRADED',task,g.get('score'),g.get('max_score'),'seconds',row['total_s'],flush=True)
                state('running',task)
            return row
        bench.gguf_request=request
        task_names=[name for name in SELECTED if not (OUT/f'{name}.local.result.json').exists()]
        # A saved inference is never repeated; missing grades are recovered separately.
        state('loading')
        if task_names:bench.gguf_round(LABEL,1,task_names=task_names)
        for task,a in artifacts.items():
            path=OUT/f'{task}.local.result.json';gp=path.with_suffix('.grade.json')
            if path.exists() and not gp.exists():
                row=json.loads(path.read_text());g,m=judge_result(row['answer'],{'checks':a['checks'],'reference':a['reference']},a['task_id'],task_prompt=(LOCAL/f'{task}.prompt.txt').read_text(),finish_reason=row['finish_reason'])
                bench.save(gp,{'semantic_grade':g,'semantic_judge':m,'source_sha256':bench.sha(path.read_bytes()),'rubric_revision':a.get('scoring_revision','0.1')})
        state('finished')

if __name__=='__main__':
    try:run()
    except Exception as exc:
        state('failed',error=repr(exc));raise
