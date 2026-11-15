#!/usr/bin/env python3
"""Frozen lite-task prototypes and explicitly routed hosted calibration."""
import argparse,csv,hashlib,html,json,math,re,statistics,sys,time
from collections import Counter
from datetime import datetime
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from grader.semantic_judge import judge_result
from openrouter_benchmark_campaign import openrouter_api_key
from run_qwen_openrouter_baseline import apply_event,SYSTEM
from run_qwen_family_xhigh import save,sha
ASSETS=ROOT/'benchmarks-files/pinchbench/assets'
FIX=ROOT/'benchmarks/suites/heavy-lite-calibration-20261115'
OUT=ROOT/'results/heavy-lite-calibration-20261115'

def apache_category(line):
 if '[notice]' in line:return 'notice'
 if '[client ' not in line:return 'server_error'
 if 'Directory index forbidden' in line:return 'directory_index'
 if 'File does not exist' in line:return 'missing_file'
 if 'script not found' in line:return 'missing_script'
 if 'Invalid method' in line:return 'invalid_method'
 return 'other_client'

def build(kind,version):
 folder=FIX/f'v{version}';folder.mkdir(parents=True,exist_ok=True)
 checks=[]
 def check(key,description):checks.append({'id':key,'description':description})
 if kind=='apache':
  source=ASSETS/'logs/apache_error.log';lines=source.read_text().splitlines();size={1:120,2:80,3:80}[version]
  chosen={0,len(lines)-1}
  for pattern in ['awstats','openwebmail','cmd.exe','root.exe','%c0','%252e','graceful restart','createBean','resuming normal operations']:
   matches=[i for i,x in enumerate(lines) if pattern.lower() in x.lower()]
   if matches:chosen.add(matches[0])
  groups={k:[i for i,x in enumerate(lines) if apache_category(x)==k] for k in sorted({apache_category(x) for x in lines})}
  for k,indices in groups.items():
   for j in range(8):chosen.add(indices[min(len(indices)-1,j*(len(indices)-1)//7)])
  for j in range(1000):
   if len(chosen)>=size:break
   chosen.add((j*617)%1000)
  indices=sorted(chosen); selected=[lines[i] for i in indices];counts=Counter(apache_category(x) for x in selected)
  ips=[re.search(r'\[client ([^\]]+)\]',x).group(1) for x in selected if '[client ' in x]
  timestamps=[datetime.strptime(x[1:x.index(']')],'%a %b %d %H:%M:%S %Y') for x in selected]
  ref={'entries':len(selected),'error':sum('[error]' in x for x in selected),'notice':sum('[notice]' in x for x in selected),'date_start':str(min(timestamps)),'date_end':str(max(timestamps)),'client_entries':len(ips),'unique_client_ips':len(set(ips)),'client_categories':{k:counts.get(k,0) for k in ['directory_index','missing_file','missing_script','invalid_method','other_client']},'top_client_ips':Counter(ips).most_common(3),'source_line_indices_zero_based':indices}
  data='\n'.join(selected)+'\n';name='apache_lite.log'
  prompt='''Analyze this Apache error-log excerpt using only its evidence. No tools are available. Return Markdown with three headings: Counts, Findings, Actions. Keep the answer within 650 words. Count each nonempty log line once, including repeated identical lines; a client entry contains [client IP]. Do not infer successful compromise from a failed probe.
Counts: exact total entries, error/notice totals, earliest/latest timestamps, client-entry count, unique client-IP count. Classify every client entry into exactly one category: Directory index forbidden, File does not exist, script not found, Invalid method, or other (in that precedence); give category counts.
Findings: separate server startup/configuration faults from client errors; describe worm/traversal and scanner evidence with IP/path examples. State what the log cannot prove.
Actions: exactly three prioritized actions covering connector configuration, directory-index noise, and hostile probes; tie each to evidence.
<APACHE_ERROR_LOG>\n'''+data+'</APACHE_ERROR_LOG>'
  check('overview','Exact total, error and notice counts agree with reference.')
  check('date_range','Correct earliest and latest timestamps (equivalent date formats accepted).')
  check('client_totals','Correct client-entry total and unique client-IP count.')
  check('categories','All five mutually exclusive client-category counts match reference, including zero counts.')
  check('server_faults','Correctly identifies JK/createBean configuration faults and distinguishes them from client probes; startup notices are not attacks.')
  check('worm_traversal','Identifies cmd.exe/root.exe worm-style probing and encoded traversal with at least one matching IP/path example from the excerpt.')
  check('scanner','Identifies awstats and openwebmail/FrontPage scanning with matching source IP/path evidence.')
  check('actions','Exactly three prioritized actionable recommendations address JK connector config, directory-index noise, and hostile probes, each grounded in evidence.')
  check('uncertainty','Explicitly says failed probes do not establish successful compromise, and adds no unsupported claims.')
  check('format','Uses the requested three report sections and stays within 650 words; equivalent headings accepted.')
 else:
  source=ASSETS/'csvs/apple_stock_2014.csv';allrows=list(csv.reader(source.read_text().splitlines()));size={1:30,2:30,3:40}[version];selected=allrows[31:31+size] if version==3 else allrows[1:1+size]
  from pinchbench_lite import finance_reference
  from datetime import date
  pairs=[(date.fromisoformat(d),float(p)) for d,p in selected];ref=finance_reference(pairs)
  returns=[pairs[i][1]/pairs[i-1][1]-1 for i in range(1,len(pairs))]
  ref.update(daily_mean=statistics.mean(returns),daily_sample_std=statistics.stdev(returns),return_over_annual_vol=ref['total_return']/ref['annualized_vol'])
  data='Date,AdjustedClose\n'+'\n'.join(','.join(x) for x in selected)+'\n';name='finance_lite.csv'
  prompt='''Analyze only the supplied adjusted-close CSV. No tools are available. Return Markdown with three headings: Summary, Metrics, Risks. Keep the answer within 650 words. This is a short sample, not a full year; do not invent missing periods or external causes.
Report row count and first/last dates and prices; total return; high/low with dates; single best/worst close-to-close daily percentage return with dates; mean daily return, sample standard deviation and annualized volatility; longest up/down streak lengths and start/end dates; maximum drawdown with peak/trough dates; total-return/annualized-volatility ratio; a brief cautious interpretation.
Definitions: r[t]=P[t]/P[t-1]-1, N-1 daily returns; sample SD uses divisor (number of returns-1); annualized volatility=sample SD*sqrt(252). Total return=last/first-1. Drawdown=P[t]/highest preceding-or-current price-1; report the most negative value. A streak counts consecutive positive/negative daily changes, zeros break it; dates span the prior close through the last change. Use earliest occurrence for ties. Round percentages to two decimals, prices to two decimals, ratios to two decimals. The ratio is not an annualized Sharpe ratio.
<CSV>\n'''+data+'</CSV>'
  check('sample','Correct row count and first/last dates and adjusted prices (price tolerance 0.02).')
  check('return','Correct total sample return within 0.05 percentage points.')
  check('extrema','Correct high/low prices and dates (price tolerance 0.02).')
  check('daily_extremes','Correct single best/worst daily percentage returns and their ending dates within 0.05 percentage points.')
  check('daily_stats','Mean daily return and sample SD both within 0.05 percentage points of reference.')
  check('annual_vol','Annualized volatility within 0.15 percentage points of reference using sqrt(252).')
  check('streaks','Correct longest up/down streak lengths and start/end dates using the defined change-count convention.')
  check('drawdown','Correct maximum drawdown within 0.05 percentage points and correct peak/trough dates.')
  check('ratio','Correct total-return/annualized-volatility ratio within 0.02; does not mislabel it an annualized Sharpe ratio.')
  check('interpretation','Requested three sections, at most 650 words, cautious evidence-based interpretation recognizing the short sample; no invented external explanations.')
 if version in (2,3):
  if kind=='apache':
   prompt="""Analyze the Apache log excerpt below. No tools are available. Return a concise Markdown report, at most 400 words, with headings Counts, Findings, Actions.
Counts: total entries, errors, notices, and first/last timestamps. Each nonempty line is one entry; repeated identical lines still count separately.
Findings: distinguish server startup/configuration errors from client errors. Identify worm/traversal probes and scanner activity with matching source-IP/path evidence. State whether this log proves successful compromise.
Actions: exactly three prioritized actions, covering JK connector configuration, directory-index noise, and hostile probes, tied to the evidence.
<APACHE_ERROR_LOG>\n"""+data+'</APACHE_ERROR_LOG>'
   checks=[c for c in checks if c['id'] not in ['client_totals','categories']]
   checks[-1]['description']='Uses the requested three report sections and stays within 400 words; equivalent headings accepted.'
   if version==3:
    summary={k:v for k,v in ref.items() if k not in ['source_line_indices_zero_based']}
    prompt="""You are the on-call analyst. A deterministic parser has already computed the authoritative summary below from this exact log excerpt. Use its counts and timestamps as given; the task is diagnosis and response prioritization, and does not require recounting log lines. No tools are available.
Return Markdown within 400 words under Findings and Actions. Distinguish startup/configuration faults from client errors and routine notices; identify worm/traversal and scanner activity using matching source-IP/path evidence. State what failed probes do and do not prove. Give exactly three prioritized actions addressing JK configuration, directory-index noise and hostile probes, tied to the evidence.
<PARSER_SUMMARY>\n"""+json.dumps(summary,indent=2)+'\n</PARSER_SUMMARY>\n<APACHE_ERROR_LOG>\n'+data+'</APACHE_ERROR_LOG>'
    checks=[c for c in checks if c['id'] not in ['overview','date_range']]
    checks[-1]['description']='Uses Findings and Actions sections, at most 400 words, and does not contradict the supplied authoritative counts.'

  else:
   prompt="""Analyze only this adjusted-close price sample. No tools are available. Return a concise Markdown report, at most 400 words, under Summary, Metrics, Risks.
Report row count and first/last dates and prices, total return, high/low with dates, the single best/worst daily percentage move with dates, and maximum drawdown with peak/trough dates. Briefly explain the trend and the main limitation of this short sample. Ground all statements in the data.
Definitions: daily move=P[t]/P[t-1]-1, assigned to the later date; total return=last/first-1; drawdown=P[t]/highest preceding-or-current price-1. Maximum drawdown is the most negative drawdown. Use earliest occurrence for ties. Round percentages to two decimals and prices to two decimals. Do not invent external causes or imply the short sample establishes a full-year trend.
<CSV>\n"""+data+'</CSV>'
   checks=[c for c in checks if c['id'] in ['sample','return','extrema','daily_extremes','drawdown','interpretation']]
   checks[-1]['description']='Requested three sections, at most 400 words, cautious evidence-based interpretation recognizing the short sample; no invented external explanations.'
 ref.pop('source_line_indices_zero_based',None) if kind!='apache' else None
 artifact={'task_id':f'{kind}_lite@0.{version}','source':str(source.relative_to(ROOT)),'source_sha256':sha(source.read_bytes()),'data_file':name,'prompt_sha256':sha(prompt.encode()),'reference':ref,'checks':checks,'selection':'Deterministic stratified excerpt' if kind=='apache' else f'Consecutive trading rows 31 through {30+size}' if version==3 else f'First {size} consecutive trading days'}
 for path,text in [(folder/name,data),(folder/f'{kind}.prompt.txt',prompt),(folder/f'{kind}.json',json.dumps(artifact,indent=2)+'\n')]:
  if path.exists():assert path.read_text()==text,'Frozen version changed'
  else:path.write_text(text)
 assert kind!='apache' or sum(ref['client_categories'].values())==ref['client_entries']
 return prompt,artifact

def run(kind,version,prompt=None,artifact=None,stem=None):
 OUT.mkdir(parents=True,exist_ok=True)
 if prompt is None:prompt,artifact=build(kind,version)
 stem=stem or f'{kind}-v{version}'
 path=OUT/f'{stem}.result.json'
 if not path.exists():
  endpoint=requests.get('https://openrouter.ai/api/v1/models/qwen/qwen3.8-27b/endpoints',timeout=30).json()
  provider=next(e for e in endpoint['data']['endpoints'] if e['tag']=='wafer/fp8');save(OUT/'endpoint.json',provider)
  prior=sum(json.loads(p.read_text()).get('cost_usd') or 0 for p in OUT.glob('*.result.json'))
  upper=12288*float(provider['pricing']['completion'])+len(prompt.encode())*float(provider['pricing']['prompt'])
  assert prior+upper<2,'Calibration safety budget $2 exceeded'
  body={'model':'qwen/qwen3.8-27b','messages':[{'role':'system','content':SYSTEM},{'role':'user','content':prompt}],'provider':{'only':['wafer/fp8'],'allow_fallbacks':False,'require_parameters':True},'reasoning':{'effort':'xhigh','exclude':False},'temperature':1,'top_p':.95,'top_k':20,'min_p':0,'seed':20261115,'max_tokens':12288,'stream':True,'stream_options':{'include_usage':True}}
  save(OUT/f'{stem}.request.json',body)
  row={'task':artifact['task_id'],'prompt_sha256':artifact['prompt_sha256'],'started_at':time.time(),'answer':'','reasoning':'','ttft_s':None,'first_answer_s':None,'finish_reason':None};start=time.monotonic()
  try:
   with requests.post('https://openrouter.ai/api/v1/chat/completions',headers={'Authorization':'Bearer '+openrouter_api_key()},json=body,stream=True,timeout=(30,120)) as resp:
    resp.encoding='utf-8';resp.raise_for_status()
    with path.with_suffix('.events.jsonl').open('w') as log:
     for line in resp.iter_lines(chunk_size=1,decode_unicode=True):
      if time.monotonic()-start>900:raise TimeoutError('15-minute hosted calibration limit')
      if not line or not line.startswith('data:'):continue
      payload=line[5:].strip()
      if payload=='[DONE]':break
      event=json.loads(payload);log.write(json.dumps(event)+'\n');apply_event(row,event,time.monotonic()-start)
  except Exception as ex:row.update(error=repr(ex),finish_reason='error')
  usage=row.get('usage') or {};row.update(total_s=time.monotonic()-start,cost_usd=usage.get('cost'),prompt_tokens=usage.get('prompt_tokens'),generation_tokens=usage.get('completion_tokens'),thinking_tokens=(usage.get('completion_tokens_details') or {}).get('reasoning_tokens'));save(path,row)
  print('INFERENCE',kind,version,{k:row.get(k) for k in ['provider','finish_reason','total_s','generation_tokens','thinking_tokens','cost_usd']},flush=True)
 row=json.loads(path.read_text());grade=path.with_suffix('.grade.json')
 if not grade.exists():
  g,meta=judge_result(row['answer'],{'checks':artifact['checks'],'reference':artifact['reference']},artifact['task_id'],task_prompt=prompt,finish_reason=row.get('finish_reason'))
  save(grade,{'semantic_grade':g,'semantic_judge':meta,'source_sha256':sha(path.read_bytes())})
 g=json.loads(grade.read_text())['semantic_grade']; print('GRADE',kind,version,json.dumps(g),flush=True)

def report():
 records=[];rows=[]
 for kind in ('apache','finance'):
  for version in (1,2,3):
   path=OUT/f'{kind}-v{version}.result.json'
   if not path.exists():continue
   r=json.loads(path.read_text());gp=path.with_suffix('.grade.json');g=json.loads(gp.read_text()) if gp.exists() else {}
   valid=g.get('source_sha256')==sha(path.read_bytes()) and g.get('semantic_judge',{}).get('judge_protocol')=='source-aware-v2'
   grade=g.get('semantic_grade',{}) if valid else {}
   record={k:r.get(k) for k in ['task','model','provider','id','started_at','finish_reason','total_s','ttft_s','first_answer_s','prompt_tokens','generation_tokens','thinking_tokens','cost_usd','prompt_sha256']}
   record.update(kind=kind,version=version,semantic_score=grade.get('score'),semantic_max=grade.get('max_score'),source_artifact=str(path.relative_to(ROOT)),source_sha256=sha(path.read_bytes()),fixture=str((FIX/f'v{version}'/f'{kind}.json').relative_to(ROOT)))
   if valid:record.update(grade_artifact=str(gp.relative_to(ROOT)),grade_sha256=sha(gp.read_bytes()))
   if r.get('generation_tokens') is not None:
    record['local_projection_s_at_8tps']=r['generation_tokens']/8+(r.get('prompt_tokens') or 0)/90
    record['local_projection_s_at_10tps']=r['generation_tokens']/10+(r.get('prompt_tokens') or 0)/100
   records.append(record)
   cells=[kind,str(version),r.get('finish_reason','-'),f"{grade['score']}/{grade['max_score']}" if grade.get('score') is not None else 'Incomplete',str(round(r['total_s'],2)),str(r.get('generation_tokens','-')),str(r.get('thinking_tokens','-')),f"${r.get('cost_usd') or 0:.5f}"]
   rows.append('<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in cells)+'</tr>')
 cost=sum(r.get('cost_usd') or 0 for r in records)
 save(ROOT/'benchmarks/runs/heavy-lite-calibration-20261115.json',{'experiment_id':'heavy-lite-calibration-20261115','purpose':'Prototype design calibration, not a model ranking','model':'qwen/qwen3.8-27b','provider':'wafer/fp8','thinking':'xhigh','max_output_tokens':12288,'safety_budget_usd':2,'user_budget_usd':20,'cost_usd':cost,'judge':{'model':'gpt-5.6-luna','effort':'xhigh','protocol':'source-aware-v2'},'selected_candidates':{'apache':'apache_lite@0.3','finance':'finance_lite@0.2'},'limitations':['One hosted inference per prototype; local 30-minute completion remains unverified.','Incomplete output is null quality, never zero.','Apache v3 uses supplied parser counts; Finance v2 omits volatility, streaks and risk-adjusted ratios.','Local runtime projections use total generated tokens and estimated prefill; they are not measurements.','Luna grading uses the local Codex judge, separate from OpenRouter charges.'],'records':records})
 page='<html><head><meta charset="utf-8"><title>Heavy lite calibration</title><style>body{font:15px system-ui;margin:2em}td,th{padding:9px;border:1px solid #aaa}table{border-collapse:collapse}</style></head><body><h1>Heavy lite benchmark calibration</h1><p>Wafer FP8 Qwen3.8-27B, xhigh. One hosted request per version. Output limit 12,288 total tokens; incomplete attempts are ungraded. Total OpenRouter cost: $'+f'{cost:.5f}'+'</p><p>Selected candidates: Apache v3 (80 raw lines plus parser counts, operational analysis); Finance v2 (30 daily prices, focused arithmetic). Local completion under 30 minutes is projected, not yet measured.</p><table><tr><th>Task</th><th>Version</th><th>Finish</th><th>Score</th><th>Hosted seconds</th><th>Total output tokens</th><th>Thinking tokens (provider)</th><th>Cost</th></tr>'+''.join(rows)+'</table></body></html>'
 (ROOT/'heavy-lite-calibration-results.html').write_text(page)
 print('TOTAL OPENROUTER COST',round(cost,6))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('kind',choices=['apache','finance']);p.add_argument('version',type=int,choices=[1,2,3]);p.add_argument('--build-only',action='store_true');a=p.parse_args()
 if a.build_only:build(a.kind,a.version)
 else:run(a.kind,a.version)
