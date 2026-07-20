import importlib.util
import json
from pathlib import Path

import pytest


WORKER_PATH = Path(__file__).parents[1] / "scripts" / "campaign_worker.py"
spec = importlib.util.spec_from_file_location("campaign_worker", WORKER_PATH)
worker = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(worker)


def manifest(tmp_path, filename="model-Q4_K_M.gguf"):
    candidate = tmp_path / "candidates" / filename
    candidate.parent.mkdir()
    return {"campaign_id": "nightly-test", "candidates": [{"id": "candidate-a", "file": str(candidate)}]}


def write_manifest(tmp_path, data):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    return path


def test_manifest_validation_accepts_q4_under_candidate_root(tmp_path):
    data = manifest(tmp_path)
    validated = worker.validate_manifest(data, tmp_path / "candidates")
    assert validated["candidates"][0]["id"] == "candidate-a"


@pytest.mark.parametrize("filename", ["model-Q3_K_M.gguf", "model-IQ3.gguf"])
def test_manifest_validation_rejects_q3_or_lower(tmp_path, filename):
    with pytest.raises(ValueError, match="Q4"):
        worker.validate_manifest(manifest(tmp_path, filename), tmp_path / "candidates")


def test_manifest_validation_rejects_unsafe_directory(tmp_path):
    data = manifest(tmp_path)
    data["candidates"][0]["file"] = str(tmp_path / "outside" / "model-Q4.gguf")
    with pytest.raises(ValueError, match="candidate root"):
        worker.validate_manifest(data, tmp_path / "candidates")


def test_atomic_state_is_valid_json(tmp_path):
    state = tmp_path / "state" / "campaign.json"
    worker.atomic_write_json(state, {"campaign_id": "x", "value": 1})
    assert json.loads(state.read_text()) == {"campaign_id": "x", "value": 1}
    assert not list(state.parent.glob("*.tmp"))


def test_dry_run_is_inert_and_records_full_skipped_lifecycle(tmp_path, monkeypatch):
    state, lock = tmp_path / "state.json", tmp_path / "campaign.lock"
    path = write_manifest(tmp_path, manifest(tmp_path))
    calls = []
    monkeypatch.setattr(worker.subprocess, "run", lambda *a, **k: calls.append(a))
    result = worker.run_campaign(path, state, lock, execute=False, dry_run=True, no_telegram=False, candidate_root=tmp_path / "candidates")
    candidate = result["candidates"][0]
    assert calls == []
    assert candidate["terminal"] == "skipped"
    assert set(candidate["phases"]) >= {"preflight", "downloading", "64k_gate", "throughput_short", "throughput_medium", "quality", "restored", "terminal"}
    assert json.loads(state.read_text())["candidates"][0]["terminal"] == "skipped"


def test_exclusive_lock_has_diagnostic(tmp_path):
    lock = tmp_path / "campaign.lock"
    with worker.CampaignLock(lock, "x", "test"):
        with pytest.raises(worker.LockBusy):
            with worker.CampaignLock(lock, "y", "test"):
                pass
        diagnostic = json.loads(lock.read_text())
        assert diagnostic["campaign_id"] == "x"
        assert diagnostic["pid"] > 0


def test_status_is_read_only(tmp_path):
    state = tmp_path / "state.json"
    worker.atomic_write_json(state, {"campaign_id": "x", "status": "running"})
    before = state.read_bytes()
    assert worker.read_status(state) == {"campaign_id": "x", "status": "running"}
    assert state.read_bytes() == before


def test_resume_does_not_redo_terminal_work(tmp_path):
    state, lock = tmp_path / "state.json", tmp_path / "campaign.lock"
    path = write_manifest(tmp_path, manifest(tmp_path))
    worker.run_campaign(path, state, lock, execute=False, dry_run=True, no_telegram=True, candidate_root=tmp_path / "candidates")
    before = state.read_bytes()
    result = worker.run_campaign(path, state, lock, execute=False, dry_run=True, no_telegram=True, resume=True, candidate_root=tmp_path / "candidates")
    assert state.read_bytes() == before
    assert result["candidates"][0]["terminal"] == "skipped"


def test_cancel_sets_durable_requested_flag(tmp_path):
    state = tmp_path / "state.json"
    worker.atomic_write_json(state, {"campaign_id": "x", "candidates": []})
    result = worker.request_cancel(state)
    assert result["cancel_requested"] is True
    assert json.loads(state.read_text())["cancel_requested"] is True


def test_mlx_iq4_and_commands_are_validated_safely(tmp_path):
    root = tmp_path / "candidates"
    data = {"campaign_id": "mlx", "lane": "main64", "retain_top_n": 4,
            "candidates": [{"id": "mlx", "backend": "mlx", "model_dir": str(root / "mlx")},
                           {"id": "iq4", "backend": "llama", "file": str(root / "x-IQ4_XS.gguf")} ]}
    assert worker.validate_manifest(data, root)["candidates"][0]["backend"] == "mlx"
    data["candidates"][0]["commands"] = {"quality": ["/usr/bin/true"]}
    with pytest.raises(ValueError, match="forbidden"):
        worker.validate_manifest(data, root)


def test_runbook_command_shapes_and_dynamic_protected_window(tmp_path):
    c = {"id": "m", "backend": "mlx", "model_dir": str(tmp_path / "m")}
    paths = worker.result_paths(c)
    assert worker.server_command(c)[:2] == ["mlx_lm.server", "--model"]
    assert "65536" in worker.benchmark_command("64k_gate", "served", c, paths)
    assert "256" in worker.benchmark_command("throughput_short", "served", c, paths)
    assert "2048" in worker.benchmark_command("throughput_medium", "served", c, paths)
    assert worker.protected(lambda: type("T", (), {"minute": 12})())
    assert not worker.protected(lambda: type("T", (), {"minute": 11})())


def test_launch_records_immediate_durable_job_metadata(tmp_path, monkeypatch):
    data = manifest(tmp_path); data["candidates"][0]["backend"] = "llama"
    path = write_manifest(tmp_path, data)
    class P: pid = 4321
    monkeypatch.setattr(worker.subprocess, "Popen", lambda *a, **kw: P())
    out = worker.launch(path, tmp_path / "state.json", tmp_path / "lock", execute=False, dry_run=True,
                        no_telegram=True, allow_protected_window=False, candidate_root=tmp_path / "candidates")
    assert out["pid"] == 4321
    assert json.loads((tmp_path / "state.json").read_text())["job"]["pid"] == 4321


def test_resume_rejects_changed_manifest_hash(tmp_path):
    data = manifest(tmp_path); data["candidates"][0]["backend"] = "llama"
    path = write_manifest(tmp_path, data); state = tmp_path / "state"; lock = tmp_path / "lock"
    worker.run_campaign(path, state, lock, execute=False, dry_run=True, no_telegram=True, candidate_root=tmp_path / "candidates")
    data["retain_top_n"] = 3; path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="manifest hash"):
        worker.run_campaign(path, state, lock, execute=False, dry_run=True, no_telegram=True, resume=True, candidate_root=tmp_path / "candidates")
