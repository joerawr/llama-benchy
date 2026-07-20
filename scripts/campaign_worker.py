#!/usr/bin/env python3
"""Durable, serial benchmark campaign worker.

Manifests describe models, never shell commands.  The only executable shapes in
this module are the reviewed runbook commands, so a campaign cannot turn a
benchmark worker into a general command runner.
"""
from __future__ import annotations
import argparse, fcntl, hashlib, json, os, re, signal, subprocess, sys, tempfile, time, urllib.request
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / "benchy-state" / "campaign-state.json"
DEFAULT_LOCK = ROOT / "benchy-state" / "campaign.lock"
DEFAULT_CANDIDATE_ROOT = Path("/Users/jrogers/models/_nightly-candidates")
PHASES = ("downloading", "64k_gate", "throughput_short", "throughput_medium", "quality")
PROTECTED_MINUTES = range(12, 26)
APACHE_CREDIBLE_MIN = 0.60


def now() -> str: return datetime.now(timezone.utc).isoformat()
def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); fd, tmp = tempfile.mkstemp(prefix=".campaign-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2, sort_keys=True); f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path); dfd = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
def load_json(path: Path) -> dict[str, Any]: return json.loads(path.read_text(encoding="utf-8"))
def persist(path: Path, state: dict[str, Any]) -> None: state["updated_at"] = now(); atomic_write_json(path, state)
def read_status(path: Path) -> dict[str, Any]: return load_json(path)
def manifest_hash(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
def inside(path: Path, root: Path) -> bool:
    try: path.relative_to(root); return True
    except ValueError: return False
def is_safe_quant(name: str) -> bool:
    u = name.upper()
    return not bool(re.search(r"(?:^|[-_.])(?:IQ[0-3]|Q[0-3]|UD[-_]?Q[0-3])(?:[-_.]|$)", u)) and bool(re.search(r"(?:^|[-_.])(?:IQ4|IQ5|IQ6|IQ8|Q[4-8])(?:[-_.A-Z0-9]|$)", u))

def validate_manifest(data: dict[str, Any], candidate_root: Path = DEFAULT_CANDIDATE_ROOT) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("campaign_id"), str) or not data["campaign_id"]: raise ValueError("manifest requires campaign_id")
    if data.get("lane", "main64") != "main64": raise ValueError("campaign lane must be main64")
    if not isinstance(data.get("retain_top_n", 4), int) or data.get("retain_top_n", 4) < 1: raise ValueError("retain_top_n must be positive")
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates: raise ValueError("manifest requires non-empty candidates")
    root = candidate_root.expanduser().resolve(); ids: set[str] = set()
    for c in candidates:
        if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", c["id"]): raise ValueError("each candidate requires safe id")
        if c["id"] in ids: raise ValueError("duplicate candidate id")
        ids.add(c["id"])
        if "commands" in c: raise ValueError("manifest commands are forbidden")
        # Legacy GGUF manifests omitted backend; preserve that safe spelling as llama.
        backend = c.setdefault("backend", "llama")
        key = "model_dir" if backend == "mlx" else "file" if backend == "llama" else None
        if not key: raise ValueError("backend must be mlx or llama")
        raw = c.get(key)
        if not isinstance(raw, str) or not Path(raw).is_absolute(): raise ValueError(f"{key} must be an absolute path")
        target = Path(raw).expanduser().resolve()
        if not inside(target, root): raise ValueError(f"candidate path must be under candidate root {root}")
        if backend == "llama":
            if target.suffix.lower() != ".gguf" or not is_safe_quant(target.name): raise ValueError("candidate must be Q4-or-higher GGUF (IQ4 accepted)")
            if c.get("mmproj"):
                p = Path(c["mmproj"])
                if not p.is_absolute() or not inside(p.expanduser().resolve(), root): raise ValueError("mmproj must be an absolute scratch path")
        if c.get("repo_id") is not None and (not isinstance(c["repo_id"], str) or not c["repo_id"]): raise ValueError("repo_id must be a non-empty string")
    return data

class LockBusy(RuntimeError): pass
class CampaignLock(AbstractContextManager["CampaignLock"]):
    def __init__(self, path: Path, campaign_id: str, command: str): self.path,self.campaign_id,self.command,self.handle=path,campaign_id,command,None
    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True); self.handle=self.path.open("a+", encoding="utf-8")
        try: fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.close(); self.handle=None; raise LockBusy("campaign lock held")
        self.handle.seek(0); self.handle.truncate(); json.dump({"campaign_id":self.campaign_id,"pid":os.getpid(),"started_at":now(),"command":self.command},self.handle); self.handle.flush(); os.fsync(self.handle.fileno()); return self
    def __exit__(self,*_:Any):
        if self.handle: fcntl.flock(self.handle.fileno(),fcntl.LOCK_UN); self.handle.close()

def phase_record(c: dict[str,Any], phase: str, status: str, **extra: Any) -> None:
    c.setdefault("phases",{}).setdefault(phase,{}).update({"status":status,"updated_at":now(),**extra})
def candidate_path(c:dict[str,Any])->Path: return Path(c["model_dir"] if c["backend"]=="mlx" else c["file"])
def result_paths(c:dict[str,Any])->dict[str,str]:
    label=c["id"]; return {"64k_gate":str(ROOT/f"results/{label}-64k-gate.json"),"throughput_short":str(ROOT/f"results/{label}-short.json"),"throughput_medium":str(ROOT/f"results/{label}-medium.json"),"quality":str(ROOT/f"results/pinchbench-lite-{label}.json"),"ifeval":str(ROOT/f"results/ifeval-lite-{label}.json"),"compression":str(ROOT/f"results/long-compression-{label}.json")}
def new_state(manifest:dict[str,Any])->dict[str,Any]:
    return {"campaign_id":manifest["campaign_id"],"manifest_hash":manifest_hash(manifest),"lane":manifest.get("lane","main64"),"retain_top_n":manifest.get("retain_top_n",4),"status":"queued","started_at":now(),"updated_at":now(),"cancel_requested":False,"logs":{"worker":str(ROOT/"benchy-state/campaign-worker.log"),"server":str(ROOT/"benchy-state/current-server.log")},"candidates":[{"id":c["id"],"backend":c["backend"],"path":str(candidate_path(c)),"terminal":None,"phases":{},"results":result_paths(c),"notification":{"state":"pending"}} for c in manifest["candidates"]]}

class Controller:
    """Production subprocess seam; tests replace it without touching services."""
    def run(self, command:list[str], *, log_path:Path, timeout:int=1800)->dict[str,Any]:
        log_path.parent.mkdir(parents=True,exist_ok=True)
        with log_path.open("ab") as out:
            try: p=subprocess.run(command,cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,timeout=timeout,check=False,text=False)
            except subprocess.TimeoutExpired as e: return {"returncode":124,"error":f"timeout after {timeout}s"}
        return {"returncode":p.returncode,"log_path":str(log_path),"command":command}
    def spawn(self, command:list[str], log_path:Path)->subprocess.Popen[Any]:
        log_path.parent.mkdir(parents=True,exist_ok=True); f=log_path.open("ab"); return subprocess.Popen(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    def ready(self, timeout:int=180)->str:
        deadline=time.time()+timeout
        while time.time()<deadline:
            try:
                with urllib.request.urlopen("http://127.0.0.1:18081/v1/models",timeout=2) as r:
                    if r.status==200:
                        body=json.loads(r.read()); return body.get("data",[{"id":"unknown"}])[0]["id"]
            except Exception: time.sleep(1)
        raise TimeoutError("trial server 18081 did not become ready")
    def stop_group(self,pid:int)->None:
        try: os.killpg(pid,signal.SIGTERM)
        except ProcessLookupError: pass
    def telegram(self,message:str)->dict[str,Any]: return self.run([str(ROOT/"ops/telegram-report.sh"),message],log_path=ROOT/"benchy-state/campaign-telegram.log",timeout=60)

def project(command:list[str], log:Path, controller:Controller, timeout:int=1800)->dict[str,Any]: return controller.run(command,log_path=log,timeout=timeout)
def current(action:str, controller:Controller, log:Path)->dict[str,Any]: return project([sys.executable,str(ROOT/"scripts/current_server.py"),action],log,controller,900)
def server_command(c:dict[str,Any])->list[str]:
    path=str(candidate_path(c))
    if c["backend"]=="mlx": return ["mlx_lm.server","--model",path,"--host","127.0.0.1","--port","18081","--temp","0","--max-tokens","4096","--chat-template-args",'{"enable_thinking": false}']
    cmd=["llama-server","-m",path,"--host","127.0.0.1","--port","18081","-c","65536","-np","1","-ngl","99","--reasoning","off","--reasoning-budget","0","-lv","4"]
    if c.get("mmproj"): cmd += ["--mmproj",c["mmproj"]]
    return cmd
def benchmark_command(phase:str, model:str, c:dict[str,Any], paths:dict[str,str])->list[str]:
    base=[sys.executable,"-m","llama_benchy","--base-url","http://127.0.0.1:18081/v1","--model",model]
    if phase=="64k_gate": return base+["--pp","65536","--tg","1","--depth","0","--runs","1","--latency-mode","none","--no-warmup","--skip-coherence","--no-adapt-prompt","--save-result",paths[phase],"--format","json"]
    if phase=="throughput_short": return base+["--pp","256","--tg","32","--depth","0","--runs","1","--latency-mode","none","--no-warmup","--skip-coherence","--no-adapt-prompt","--save-result",paths[phase],"--format","json"]
    if phase=="throughput_medium": return base+["--pp","512","2048","--tg","128","--depth","0","4096","--runs","3","--latency-mode","generation","--no-cache","--save-result",paths[phase],"--format","json"]
    return [sys.executable,str(ROOT/"scripts/pinchbench_lite.py"),"--base-url","http://127.0.0.1:18081/v1","--model",model,"--label",c["id"],"--task","task_csv_finance_report","--task","task_log_apache_error_summary","--task","task_access_log_anomaly","--runs","3","--timeout","900","--out",paths["quality"]]
def download_command(c:dict[str,Any])->list[str]|None:
    p=candidate_path(c)
    if p.exists(): return None
    if not c.get("repo_id"): raise FileNotFoundError(f"missing candidate and no repo_id: {p}")
    # exact repo/file, never a shell or arbitrary manifest command
    return ["hf","download",c["repo_id"],c.get("repo_file",p.name),"--local-dir",str(p.parent if c["backend"]=="llama" else p)]
def apache_weak(path:str)->bool:
    try:
        data=load_json(Path(path)); text=json.dumps(data).lower()
        # Runner output has evolved; absence of a numeric score is conservative weak.
        scores=re.findall(r'"(?:score|quality_score)"\s*:\s*([0-9.]+)',text)
        return len(scores)>=2 and sum(float(x)<APACHE_CREDIBLE_MIN for x in scores[:2])>=2
    except Exception: return False
def quality_score(c:dict[str,Any])->tuple[float,float,float]:
    score=0.0
    try:
        data=load_json(Path(c["results"]["quality"])); vals=re.findall(r'"(?:score|quality_score)"\s*:\s*([0-9.]+)',json.dumps(data)); score=sum(map(float,vals))/len(vals) if vals else 0.0
    except Exception: pass
    fit=1.0 if c["phases"].get("64k_gate",{}).get("status")=="completed" else 0.0
    speed=0.0
    try:
        data=load_json(Path(c["results"]["throughput_short"])); vals=re.findall(r'"tg_throughput"\s*:\s*\{[^}]*"mean"\s*:\s*([0-9.]+)',json.dumps(data)); speed=float(vals[0]) if vals else 0.0
    except Exception: pass
    return score,fit,speed

def protected(now_fn=datetime.now)->bool: return now_fn().minute in PROTECTED_MINUTES
def restore(cstate:dict[str,Any], state:dict[str,Any], state_path:Path, controller:Controller, log:Path)->None:
    phase_record(cstate,"restored","running"); persist(state_path,state)
    a=current("start",controller,log); b=current("smoke",controller,log)
    phase_record(cstate,"restored","completed" if not a["returncode"] and not b["returncode"] else "failed",commands=[a.get("command"),b.get("command")],result={"start":a,"smoke":b}); persist(state_path,state)
def notify_candidate(c:dict[str,Any], state:dict[str,Any], state_path:Path, controller:Controller, no_telegram:bool)->None:
    n=c["notification"]
    if n.get("state") in {"sent","skipped"}: return
    if no_telegram: c["notification"]={"state":"skipped","updated_at":now()}; persist(state_path,state); return
    result=controller.telegram(f"campaign candidate {c['id']} {c['terminal']}")
    c["notification"]={"state":"sent" if result.get("returncode")==0 else "failed","attempted_at":now(),"result":result}; persist(state_path,state)

def run_campaign(manifest_path:Path,state_path:Path=DEFAULT_STATE,lock_path:Path=DEFAULT_LOCK,*,execute:bool,dry_run:bool,no_telegram:bool,resume:bool=False,allow_protected_window:bool=False,controller:Controller|None=None,candidate_root:Path=DEFAULT_CANDIDATE_ROOT,now_fn=datetime.now)->dict[str,Any]:
    manifest=validate_manifest(load_json(manifest_path),candidate_root); h=manifest_hash(manifest); controller=controller or Controller()
    with CampaignLock(lock_path,manifest["campaign_id"],"worker"):
        if resume and state_path.exists():
            state=load_json(state_path)
            if state.get("campaign_id")!=manifest["campaign_id"] or state.get("manifest_hash")!=h: raise ValueError("resume manifest hash mismatch (changed or reordered candidates)")
            if all(c.get("terminal") for c in state.get("candidates", [])):
                return state
            for c in state["candidates"]:
                for p,r in c.get("phases",{}).items():
                    if r.get("status")=="running": phase_record(c,p,"failed",error="interrupted previous worker",retriable=True)
        else: state=new_state(manifest)
        state["status"]="running"; persist(state_path,state)
        for definition,c in zip(manifest["candidates"],state["candidates"]):
            if c.get("terminal") and c["terminal"]!="failed": continue
            # failed candidates are safely retried on resume after their failed phase is marked retriable.
            if c.get("terminal")=="failed" and resume: c["terminal"]=None
            log=ROOT/f"benchy-state/campaign-{c['id']}.log"; c["log_path"]=str(log); trial=None
            phase_record(c, "preflight", "skipped" if (dry_run or not execute) else "completed", result="inert" if (dry_run or not execute) else "manifest_validated")
            persist(state_path, state)
            try:
                if execute and not dry_run and protected(now_fn) and not allow_protected_window: raise RuntimeError("protected window :12-:25; refusing to start disruptive trial")
                if state.get("cancel_requested"): raise InterruptedError("cancel requested")
                phase_record(c,"downloading","running"); persist(state_path,state)
                if dry_run or not execute:
                    cmd=None; r={"returncode":0,"command":None,"result":"dry_run" if dry_run else "not_executed"}
                else:
                    cmd=download_command(definition)
                    r={"returncode":0,"command":None,"result":"preexisting"} if cmd is None else project(cmd,log,controller,3600)
                if r["returncode"]: raise RuntimeError("download failed")
                phase_record(c,"downloading","completed",command=cmd,result=r); persist(state_path,state)
                if execute and not dry_run:
                    status=current("status",controller,log)
                    c["managed_server_before"] = status
                    stop=current("stop",controller,log)
                    if stop["returncode"]: raise RuntimeError("could not stop current server")
                    trial=controller.spawn(server_command(definition),log); c["trial_server"]={"pid":trial.pid,"port":18081,"command":server_command(definition),"log_path":str(log)}; persist(state_path,state); model=controller.ready()
                else: model="dry-run"
                for phase in PHASES[1:]:
                    if state.get("cancel_requested"): raise InterruptedError("cancel requested")
                    if c["phases"].get(phase,{}).get("status")=="completed": continue
                    cmd=benchmark_command(phase,model,definition,c["results"]); phase_record(c,phase,"running",command=cmd,log_path=str(log),result_path=c["results"].get(phase)); persist(state_path,state)
                    r={"returncode":0,"result":"dry_run"} if (dry_run or not execute) else project(cmd,log,controller,3600)
                    if r["returncode"]: raise RuntimeError(f"{phase} failed")
                    phase_record(c,phase,"completed",command=cmd,result=r); persist(state_path,state)
                    if phase=="quality" and apache_weak(c["results"]["quality"]): c["early_stop"]="two weak Apache runs"; break
                c["terminal"]="skipped" if (dry_run or not execute) else "tested"
            except InterruptedError as exc: c["terminal"]="skipped"; c["error"]=str(exc)
            except KeyboardInterrupt:
                state["cancel_requested"] = True; c["terminal"]="skipped"; c["error"]="worker interrupted"
            except Exception as exc: c["terminal"]="failed"; c["error"]=str(exc)
            finally:
                if trial: controller.stop_group(trial.pid)
                # Restoration is intentionally allowed even inside protected window.
                if execute and not dry_run: restore(c,state,state_path,controller,log)
                else: phase_record(c,"restored","skipped",result="dry_run" if dry_run else "not_executed"); persist(state_path,state)
                phase_record(c,"terminal","completed",result=c["terminal"]); persist(state_path,state) # durable before telegram
                notify_candidate(c,state,state_path,controller,no_telegram or not execute)
        rank_and_cleanup(state,state_path,candidate_root); state["status"]="cancelled" if state.get("cancel_requested") else "completed"; state["completed_at"]=now(); persist(state_path,state); return state

def rank_and_cleanup(state:dict[str,Any],state_path:Path,root:Path)->None:
    eligible=[c for c in state["candidates"] if c.get("terminal")=="tested" and all(Path(x).exists() for x in (c["results"]["64k_gate"],c["results"]["quality"]))]
    ranked=sorted(eligible,key=quality_score,reverse=True); keep={c["id"] for c in ranked[:state["retain_top_n"]]}; state["ranking"]=[{"id":c["id"],"rank":i+1,"metric":quality_score(c)} for i,c in enumerate(ranked)]
    root=root.expanduser().resolve()
    for c in state["candidates"]:
        if c["id"] in keep: c["cleanup"]={"decision":"retained"}; continue
        p=Path(c["path"]).resolve(); target=p if p.is_dir() else p.parent
        if c.get("terminal") in {"tested","failed","skipped"} and c.get("terminal") and c.get("results") and inside(target,root) and c["id"] not in keep:
            # Failed/skipped candidates need terminal evidence; only delete a directory after a report/result exists.
            evidence=any(Path(x).exists() for x in c["results"].values())
            if evidence and target.exists():
                import shutil; shutil.rmtree(target); c["cleanup"]={"decision":"deleted","path":str(target)}
            else: c["cleanup"]={"decision":"not_deleted_no_result_evidence"}
    persist(state_path,state)

def request_cancel(state_path:Path,lock_path:Path=DEFAULT_LOCK)->dict[str,Any]:
    state=load_json(state_path)
    with CampaignLock(lock_path,state.get("campaign_id","unknown"),"cancel"):
        state=load_json(state_path)
        if state.get("status") in {"completed","cancelled"}: return state
        state["cancel_requested"]=True; persist(state_path,state); return state

def launch(manifest_path:Path,state_path:Path,lock_path:Path,*,execute:bool,dry_run:bool,no_telegram:bool,allow_protected_window:bool,candidate_root:Path=DEFAULT_CANDIDATE_ROOT)->dict[str,Any]:
    manifest=validate_manifest(load_json(manifest_path),candidate_root); state=new_state(manifest); log=Path(state["logs"]["worker"]); log.parent.mkdir(parents=True,exist_ok=True); persist(state_path,state)
    cmd=["uv","run","python",str(Path(__file__).resolve()),"worker","--manifest",str(manifest_path),"--state",str(state_path),"--lock-file",str(lock_path)] + (["--execute"] if execute else [])+(["--dry-run"] if dry_run else [])+(["--no-telegram"] if no_telegram else [])+(["--allow-protected-window"] if allow_protected_window else [])
    with log.open("ab") as f: proc=subprocess.Popen(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    state["job"]={"pid":proc.pid,"command":cmd,"log_path":str(log),"launched_at":now()}; persist(state_path,state)
    return {"campaign_id":manifest["campaign_id"],"pid":proc.pid,"state_path":str(state_path),"log_path":str(log)}
def main()->None:
    p=argparse.ArgumentParser(); p.add_argument("command",choices=("launch","start","worker","resume","status","cancel","notify")); p.add_argument("--manifest",type=Path); p.add_argument("--state",type=Path,default=DEFAULT_STATE); p.add_argument("--lock-file",type=Path,default=DEFAULT_LOCK); p.add_argument("--execute",action="store_true"); p.add_argument("--dry-run",action="store_true"); p.add_argument("--no-telegram",action="store_true"); p.add_argument("--allow-protected-window",action="store_true"); p.add_argument("--foreground",action="store_true"); a=p.parse_args()
    if a.command=="status": print(json.dumps(read_status(a.state),indent=2)); return
    if a.command=="cancel": print(json.dumps(request_cancel(a.state,a.lock_file),indent=2)); return
    if not a.manifest: p.error("--manifest is required")
    if a.command in {"launch","start"} and not a.foreground: out=launch(a.manifest,a.state,a.lock_file,execute=a.execute,dry_run=a.dry_run,no_telegram=a.no_telegram,allow_protected_window=a.allow_protected_window)
    else: out=run_campaign(a.manifest,a.state,a.lock_file,execute=a.execute,dry_run=a.dry_run,no_telegram=a.no_telegram,resume=a.command in {"resume", "worker"},allow_protected_window=a.allow_protected_window)
    print(json.dumps(out,indent=2))
if __name__=="__main__": main()
