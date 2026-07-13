#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any
from urllib import request
from urllib.error import URLError


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
RUNTIME_DIR = ROOT / ".runtime"
LOG_DIR = RUNTIME_DIR / "logs"
SUPERVISOR_PID = RUNTIME_DIR / "supervisor.pid"
STATE_FILE = RUNTIME_DIR / "state.json"

BACKEND_URL = "http://127.0.0.1:8000/api/health"
FRONTEND_PORT = "4400"
FRONTEND_URL = f"http://127.0.0.1:{FRONTEND_PORT}/"


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 炒股 Agent 本地服务控制脚本")
    parser.add_argument("command", choices=["start", "stop", "restart", "status", "health", "supervise"])
    args = parser.parse_args()

    if args.command == "start":
        return start()
    if args.command == "stop":
        return stop()
    if args.command == "restart":
        stop()
        return start()
    if args.command == "status":
        return status()
    if args.command == "health":
        return health(print_json=True)
    if args.command == "supervise":
        return supervise()
    return 1


def start() -> int:
    ensure_runtime()
    if supervisor_running():
        print("本地服务监控已在运行。")
        return status()

    missing = missing_dependencies()
    if missing:
        for item in missing:
            print(item)
        return 1

    log_path = LOG_DIR / "supervisor.log"
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "supervise"],
            cwd=str(ROOT),
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

    for _ in range(40):
        if supervisor_running():
            break
        if process.poll() is not None:
            print("启动失败，请查看 .runtime/logs/supervisor.log")
            return 1
        time.sleep(0.25)

    print("本地服务已启动，监控会自动重启异常退出的前后端。")
    return status()


def stop() -> int:
    pid = read_pid(SUPERVISOR_PID)
    if not pid:
        print("本地服务未运行。")
        return 0

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        cleanup_pid()
        print("本地服务未运行。")
        return 0

    for _ in range(50):
        if not process_exists(pid):
            cleanup_pid()
            print("本地服务已停止。")
            return 0
        time.sleep(0.2)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    cleanup_pid()
    print("本地服务已强制停止。")
    return 0


def status() -> int:
    state = read_state()
    checks = check_services()
    print(f"监控进程：{'运行中' if supervisor_running() else '未运行'}")
    print(f"前端 {FRONTEND_PORT}：{checks['frontend']['status']} - {checks['frontend']['message']}")
    print(f"后端 8000：{checks['backend']['status']} - {checks['backend']['message']}")
    if state:
        print(f"最近心跳：{state.get('updated_at', '未知')}")
        print(f"后端重启次数：{state.get('backend_restarts', 0)}")
        print(f"前端重启次数：{state.get('frontend_restarts', 0)}")
    print(f"访问地址：http://127.0.0.1:{FRONTEND_PORT}/")
    return 0 if checks["frontend"]["ok"] and checks["backend"]["ok"] else 1


def health(print_json: bool = False) -> int:
    checks = check_services()
    if print_json:
        print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0 if checks["frontend"]["ok"] and checks["backend"]["ok"] else 1


def supervise() -> int:
    ensure_runtime()
    SUPERVISOR_PID.write_text(str(os.getpid()), encoding="utf-8")
    children: dict[str, subprocess.Popen[bytes] | None] = {"backend": None, "frontend": None}
    restart_counts = {"backend": 0, "frontend": 0}
    failures = {"backend": 0, "frontend": 0}
    stopping = False

    def handle_stop(_signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    try:
        children["backend"] = launch_backend()
        children["frontend"] = launch_frontend()
        restart_counts["backend"] += 1
        restart_counts["frontend"] += 1
        started_at = time.time()

        while not stopping:
            time.sleep(5)
            for name in ("backend", "frontend"):
                child = children[name]
                if child is None or child.poll() is not None:
                    children[name] = relaunch(name, children.get(name))
                    restart_counts[name] += 1
                    failures[name] = 0
                    continue

                if time.time() - started_at < 12:
                    continue

                ok = check_one(name)["ok"]
                failures[name] = 0 if ok else failures[name] + 1
                if failures[name] >= 3:
                    children[name] = relaunch(name, children.get(name))
                    restart_counts[name] += 1
                    failures[name] = 0

            write_state(restart_counts)
    finally:
        for child in children.values():
            terminate_child(child)
        cleanup_pid()
    return 0


def launch_backend() -> subprocess.Popen[bytes]:
    python_path = BACKEND_DIR / ".venv" / "bin" / "python"
    return launch(
        "backend",
        [str(python_path), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        BACKEND_DIR,
    )


def launch_frontend() -> subprocess.Popen[bytes]:
    return launch("frontend", ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", FRONTEND_PORT], FRONTEND_DIR)


def launch(name: str, command: list[str], cwd: Path) -> subprocess.Popen[bytes]:
    ensure_runtime()
    log_path = LOG_DIR / f"{name}.log"
    log = log_path.open("ab")
    return subprocess.Popen(command, cwd=str(cwd), stdout=log, stderr=log, start_new_session=True)


def relaunch(name: str, child: subprocess.Popen[bytes] | None) -> subprocess.Popen[bytes]:
    terminate_child(child)
    time.sleep(1)
    return launch_backend() if name == "backend" else launch_frontend()


def terminate_child(child: subprocess.Popen[bytes] | None) -> None:
    if child is None or child.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(child.pid), signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(30):
        if child.poll() is not None:
            return
        time.sleep(0.2)
    try:
        os.killpg(os.getpgid(child.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass


def check_services() -> dict[str, dict[str, Any]]:
    return {"frontend": check_one("frontend"), "backend": check_one("backend")}


def check_one(name: str) -> dict[str, Any]:
    url = FRONTEND_URL if name == "frontend" else BACKEND_URL
    try:
        with request.urlopen(url, timeout=4) as response:
            body = response.read().decode("utf-8", errors="ignore")
            if name == "backend":
                data = json.loads(body)
                message = f"service={data.get('service')}, opend={data.get('opend')}, ai={data.get('ai', {}).get('configured')}"
            else:
                message = f"HTTP {response.status}"
            return {"ok": True, "status": "正常", "message": message}
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "status": "异常", "message": str(exc)[:160]}


def missing_dependencies() -> list[str]:
    missing: list[str] = []
    if not (BACKEND_DIR / ".venv" / "bin" / "python").exists():
        missing.append("缺少后端虚拟环境：请先在 backend/ 下创建 .venv 并安装 requirements.txt")
    if not (FRONTEND_DIR / "node_modules").exists():
        missing.append("缺少前端依赖：请先在 frontend/ 下运行 npm install")
    return missing


def ensure_runtime() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def supervisor_running() -> bool:
    pid = read_pid(SUPERVISOR_PID)
    return bool(pid and process_exists(pid))


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def cleanup_pid() -> None:
    try:
        SUPERVISOR_PID.unlink()
    except FileNotFoundError:
        pass


def write_state(restart_counts: dict[str, int]) -> None:
    ensure_runtime()
    STATE_FILE.write_text(
        json.dumps(
            {
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "backend_restarts": restart_counts["backend"],
                "frontend_restarts": restart_counts["frontend"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def read_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


if __name__ == "__main__":
    raise SystemExit(main())
