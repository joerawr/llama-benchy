#!/usr/bin/env python3
"""Publish preserved calibration evidence without raw model text."""
import html,json,sys
from pathlib import Path
from run_qwen_family_xhigh import ROOT,save,sha
from calibrate_security_lite import FIX,OUT,cases

def report():
 review_path=OUT/'refusal-review.json';reviews=json.loads(review_path.read_text()) if review_path.exists() else {}
 records=[];rows=[]
 for case in cases():
  name=case[0]
  for suffix,model in [('', 'Qwen3.8-27B / Wafer FP8'),('.openai','GPT-6.1 Sol / Codex')]:
   path=OUT/f'{name}{suffix}.result.json'
   if not path.exists():continue
   r=json.loads(path.read_text());gp=path.with_suffix('.grade.json')
   revised=path.with_suffix('.grade-v02.json')
   if revised.exists():gp=revised
   g=json.loads(gp.read_text()) if gp.exists() else {}
   a=json.loads((FIX/name/'reference.json').read_text());meta=g.get('semantic_judge',{});q=g.get('semantic_grade',{})
   valid=(g.get('source_sha256')==sha(path.read_bytes()) and meta.get('judge_protocol')=='source-aware-v2' and meta.get('judge_model')=='gpt-5.6-luna' and meta.get('judge_effort')=='xhigh' and type(q.get('score')) is int and q.get('max_score')==len(a['checks']) and 0<=q['score']<=len(a['checks']) and r.get('finish_reason')=='stop')
   record={k:r.get(k) for k in ['model','provider','task','total_s','first_answer_s','ttft_s','finish_reason','generation_tokens','thinking_tokens','cost_usd','prompt_sha256','tool_used','usage']}
   record['grading_revision']=g.get('rubric_revision','0.1')
   if revised.exists():
    original=path.with_suffix('.grade.json');record.update(original_grade_source=str(original.relative_to(ROOT)),original_grade_sha256=sha(original.read_bytes()),original_quality_score=json.loads(original.read_text())['semantic_grade'].get('score'))
   record.update(display_model=model,case=name,quality_score=q.get('score') if valid else None,quality_max=len(a['checks']),failed_checks=q.get('substantive_failures',[]) if valid else [],refusal=reviews.get(path.name,{'classification':'pending_review'}) if reviews.get(path.name,{}).get('source_sha256')==sha(path.read_bytes()) else {'classification':'pending_review'},source=str(path.relative_to(ROOT)),source_sha256=sha(path.read_bytes()),fixture=str((FIX/name/'reference.json').relative_to(ROOT)))
   if gp.exists():record.update(grade_source=str(gp.relative_to(ROOT)),grade_sha256=sha(gp.read_bytes()))
   if r.get('generation_tokens'):record['local_generation_minutes_at_8_to_10_tps']=[r['generation_tokens']/600,r['generation_tokens']/480]
   records.append(record)
   quality=f"{q['score']}/{len(a['checks'])}" if valid else '-'
   cells=[name,model,quality,record['refusal']['classification'],str(round(r.get('total_s',0),1)),str(r.get('generation_tokens') or '-'),f"${r['cost_usd']:.5f}" if r.get('cost_usd') is not None else 'Separate Codex usage']
   rows.append('<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in cells)+'</tr>')
 cost=sum(r.get('cost_usd') or 0 for r in records)
 summary={'experiment_id':'security-lite-calibration-20261115','date':'2026-11-15','purpose':'Prototype operational Apache and defensive cybersecurity triage; measure observed refusals without presuming them.','judge':{'model':'gpt-5.6-luna','effort':'xhigh','protocol':'source-aware-v2'},'hosted_cost_usd':cost,'requested_additional_variants':6,'hosted_provider':'wafer/fp8','hosted_model':'qwen/qwen3.8-27b','openai_model':'gpt-6.1-sol','reasoning_effort':'xhigh','records':records,'limitations':['One inference per prototype/model. No Claude run and no local model run.','Both receive the same frozen benchmark prompt; CLI and API wrappers differ.','Qwen is hosted FP8, not the local UD3.1 Q4 model; local generation projections exclude prefill.','Qwen output cap is 12288 tokens; OpenAI has a 15-minute wall limit and no explicit output cap.','Directory-trust technical launch errors were archived, retried and excluded from refusal counts.','Refusal labels are manual reviews of delivered answers, separate from canonical semantic scores.','No synthetic log depicts a real private system; benchmark actions are defensive.']}
 save(ROOT/'benchmarks/runs/security-lite-calibration-20261115.json',summary)
 page='<html><head><meta charset="utf-8"><title>Apache and security calibration</title><style>body{font:15px system-ui;margin:2em}td,th{padding:9px;border:1px solid #aaa}table{border-collapse:collapse}</style></head><body><h1>Apache and defensive security calibration</h1><p>Six additional prototypes; xhigh. One run per task/model. Technical failures and incomplete outputs are not refusals. Canonical Luna xhigh source-aware-v2 grading.</p><p>OpenRouter spend: $'+f'{cost:.5f}'+'; OpenAI uses separate Codex access. API and CLI elapsed times include different overhead and are not local speed measurements.</p><table><tr><th>Case</th><th>Model</th><th>Score</th><th>Refusal review</th><th>Elapsed s</th><th>Qwen output tokens</th><th>OpenRouter cost</th></tr>'+''.join(rows)+'</table><p>These are prototype results, not a stable model ranking. Hosted Qwen differs from the downloaded local quant. Local completion remains unmeasured. No Claude inference was run.</p></body></html>'
 (ROOT/'security-lite-calibration-results.html').write_text(page)
 print('Records',len(records),'OpenRouter cost',round(cost,6))
if __name__=='__main__':report()
