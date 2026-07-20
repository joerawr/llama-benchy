#!/usr/bin/env python3
import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "benchy-state" / "serving-current.json"
DEFAULT_PID = ROOT / "benchy-state" / "current-server.pid"
DEFAULT_LOG = ROOT / "benchy-state" / "current-server.log"


def load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = ["label", "backend", "path", "served", "host", "health_host", "port", "ctx"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"{path} missing required keys: {', '.join(missing)}")
    return data


def is_pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_pid(pid_path: Path) -> int | None:
    try:
        text = pid_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def health_url(config: dict[str, Any], path: str = "/v1/models") -> str:
    return f"http://{config['health_host']}:{config['port']}{path}"


def wait_for_health(config: dict[str, Any], timeout_s: int) -> None:
    deadline = time.time() + timeout_s
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url(config), timeout=2) as response:
                if 200 <= response.status < 300:
                    return
                last_error = f"HTTP {response.status}"
        except Exception as exc:  # noqa: BLE001 - report any readiness failure
            last_error = str(exc)
        time.sleep(1)
    raise TimeoutError(f"server did not become healthy: {last_error}")


def build_command(config: dict[str, Any]) -> list[str]:
    backend = config.get("backend", "llama")
    model_path = Path(config["path"]).expanduser()
    if not model_path.exists():
        raise FileNotFoundError(str(model_path))

    if backend == "llama":
        cmd = [
            "llama-server",
            "-m",
            str(model_path),
            "--host",
            str(config["host"]),
            "--port",
            str(config["port"]),
            "-c",
            str(config["ctx"]),
            "-np",
            str(config.get("n_parallel", 1)),
            "-ngl",
            str(config.get("gpu_layers", 99)),
            "--reasoning",
            str(config.get("reasoning", "off")),
            "--reasoning-budget",
            str(config.get("reasoning_budget", 0)),
        ]
    elif backend == "mlx":
        cmd = [
            "mlx_lm.server",
            "--model",
            str(model_path),
            "--host",
            str(config["host"]),
            "--port",
            str(config["port"]),
        ]
    else:
        raise ValueError(f"unsupported backend: {backend}")

    cmd.extend(str(arg) for arg in config.get("extra_args", []))
    return cmd


def start(config_path: Path, pid_path: Path, log_path: Path, timeout_s: int) -> int:
    config = load_config(config_path)
    existing_pid = read_pid(pid_path)
    if existing_pid and is_pid_running(existing_pid):
        print(f"{config['label']} already running with pid {existing_pid}")
        return 0

    pid_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_command(config)
    with log_path.open("ab") as log_file:
        log_file.write(f"\n=== starting {config['label']} at {time.ctime()} ===\n".encode())
        log_file.write((" ".join(cmd) + "\n").encode())
        log_file.flush()
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    pid_path.write_text(str(proc.pid), encoding="utf-8")
    try:
        wait_for_health(config, timeout_s)
    except Exception:
        stop(pid_path, timeout_s=30)
        raise
    print(f"started {config['label']} pid={proc.pid} url=http://{config['health_host']}:{config['port']}/v1")
    return 0


def stop(pid_path: Path, timeout_s: int) -> int:
    pid = read_pid(pid_path)
    if not pid:
        print("no current-server pid file")
        return 0
    if not is_pid_running(pid):
        pid_path.unlink(missing_ok=True)
        print(f"pid {pid} is not running")
        return 0

    for sig, wait_s in [(signal.SIGINT, timeout_s), (signal.SIGTERM, 15), (signal.SIGKILL, 5)]:
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            break
        except PermissionError:
            os.kill(pid, sig)
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if not is_pid_running(pid):
                pid_path.unlink(missing_ok=True)
                print(f"stopped pid {pid}")
                return 0
            time.sleep(0.5)

    if is_pid_running(pid):
        print(f"failed to stop pid {pid}", file=sys.stderr)
        return 1
    pid_path.unlink(missing_ok=True)
    print(f"stopped pid {pid}")
    return 0


def status(config_path: Path, pid_path: Path) -> int:
    config = load_config(config_path)
    pid = read_pid(pid_path)
    running = bool(pid and is_pid_running(pid))
    healthy = False
    if running:
        try:
            with urllib.request.urlopen(health_url(config), timeout=2) as response:
                healthy = 200 <= response.status < 300
        except Exception:
            healthy = False
    print(
        json.dumps(
            {
                "label": config["label"],
                "served": config["served"],
                "pid": pid,
                "running": running,
                "healthy": healthy,
                "base_url": f"http://{config['health_host']}:{config['port']}/v1",
            },
            indent=2,
        )
    )
    return 0 if running and healthy else 1


def smoke(config_path: Path) -> int:
    config = load_config(config_path)
    payload = {
        "model": config["served"],
        "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
        "temperature": 0,
        "max_tokens": 8,
        "stream": False,
    }
    request = urllib.request.Request(
        health_url(config, "/v1/chat/completions"),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    content = body["choices"][0]["message"].get("content", "").strip()
    print(content)
    return 0 if "ok" in content.lower() else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["start", "stop", "status", "smoke"])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--pid-file", type=Path, default=DEFAULT_PID)
    parser.add_argument("--log-file", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    if args.command == "start":
        raise SystemExit(start(args.config, args.pid_file, args.log_file, args.timeout))
    if args.command == "stop":
        raise SystemExit(stop(args.pid_file, args.timeout))
    if args.command == "status":
        raise SystemExit(status(args.config, args.pid_file))
    if args.command == "smoke":
        raise SystemExit(smoke(args.config))


if __name__ == "__main__":
    main()
