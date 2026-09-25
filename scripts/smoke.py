"""In-image smoke test. Runs on CPU, so it works on GPU-less CI runners and on a Mac.

1. torch and ComfyUI-Manager import.
2. ComfyUI boots with --cpu --enable-manager and every custom node imports (no "IMPORT FAILED").
3. /object_info exposes every class_type listed in required_nodes.txt.
4. get-model / sync-models are on PATH and models.lock.yaml is valid (offline).
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

COMFY = Path(os.environ.get("COMFY_HOME", "/opt/ComfyUI"))
REQUIRED = Path("/opt/comfy/required_nodes.txt")
PORT = 8199
BOOT_TIMEOUT_S = 300


def fail(msg: str) -> None:
    print(f"SMOKE FAIL: {msg}", flush=True)
    sys.exit(1)


def check_imports() -> None:
    import torch

    print(f"torch {torch.__version__} (cuda {torch.version.cuda})")
    sys.path.insert(0, str(COMFY))  # the manager imports ComfyUI's `comfy` package
    try:
        import comfyui_manager  # noqa: F401  # from manager_requirements.txt
    except ImportError as e:
        fail(f"comfyui_manager not importable: {e}")
    print("comfyui_manager ok")


def check_model_tools() -> None:
    for cmd in (["get-model", "--help"], ["sync-models", "--help"], [sys.executable, "/opt/comfy/models.py", "check"]):
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            fail(f"{' '.join(cmd)} failed: {r.stderr or r.stdout}")
    print("model tools ok")


def object_info() -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/object_info", timeout=10) as r:
        return json.load(r)


def main() -> None:
    check_imports()
    check_model_tools()
    required = [
        line.strip()
        for line in REQUIRED.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    log_path = Path("/tmp/smoke-comfy.log")
    with log_path.open("w") as log:
        proc = subprocess.Popen(
            [sys.executable, str(COMFY / "main.py"), "--cpu", "--listen", "127.0.0.1",
             "--port", str(PORT), "--disable-auto-launch", "--enable-manager"],
            cwd=COMFY, stdout=log, stderr=subprocess.STDOUT,
        )
    try:
        deadline = time.monotonic() + BOOT_TIMEOUT_S
        info = None
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            try:
                info = object_info()
                break
            except OSError:
                time.sleep(2)
        output = log_path.read_text()
        print(output[-4000:])
        if info is None:
            fail("ComfyUI did not come up (see log above)")
        if "IMPORT FAILED" in output:
            fail("a custom node failed to import")
        missing = [n for n in required if n not in info]
        if missing:
            fail(f"missing node types: {missing}")
        print(f"SMOKE OK: {len(info)} node types, all {len(required)} required present")
    finally:
        proc.terminate()
        proc.wait(timeout=30)


if __name__ == "__main__":
    main()
