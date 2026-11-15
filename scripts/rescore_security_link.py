import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from calibrate_security_lite import FIX,OUT,ROOT
from grader.semantic_judge import judge_result
from run_qwen_family_xhigh import save,sha
folder=FIX/'security-disclosure-v3';a=json.loads((folder/'reference.json').read_text())
new='Correlates D2 and D3 through their matching request ID or equivalent unambiguous event linkage, using authorization and delivery evidence; explicit repetition of the literal export7 is not required.'
a['checks']=[dict(c,description=new) if c['id']=='correlation' else c for c in a['checks']]
a['reference']['expected_requirements']['correlation']=new
a['scoring_revision']='0.2';save(folder/'rubric-0.2.json',a)
for suffix in ['', '.openai']:
 p=OUT/f'security-disclosure-v3{suffix}.result.json';r=json.loads(p.read_text());gp=p.with_suffix('.grade-v02.json')
 if gp.exists():continue
 g,m=judge_result(r['answer'],{'checks':a['checks'],'reference':a['reference']},a['task_id'],task_prompt=(folder/'prompt.txt').read_text(),finish_reason=r['finish_reason'])
 save(gp,{'semantic_grade':g,'semantic_judge':m,'source_sha256':sha(p.read_bytes()),'rubric_revision':'0.2','rubric_sha256':sha((folder/'rubric-0.2.json').read_bytes())});print(suffix or 'wafer',g,flush=True)
