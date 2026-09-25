"""Install custom nodes pinned in nodes.lock.yaml into a ComfyUI custom_nodes dir.

Runs inside the image build, after ComfyUI's requirements (so PyYAML exists).
Every node is fetched at an exact commit and its requirements are installed
under the torch constraints file, so a node can never replace the pinned torch.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

SHA = re.compile(r"^[0-9a-f]{40}$")
CONSTRAINTS = "/opt/constraints.txt"


def run(*cmd: str, cwd: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def install(node: dict, target_root: Path) -> None:
    name, repo, commit = node["name"], node["repo"], node["commit"]
    if not SHA.match(commit):
        sys.exit(f"{name}: commit must be a full 40-char SHA, got {commit!r}")

    dest = target_root / name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    run("git", "init", "-q", cwd=dest)
    run("git", "fetch", "-q", "--depth", "1", repo, commit, cwd=dest)
    run("git", "checkout", "-q", "FETCH_HEAD", cwd=dest)
    shutil.rmtree(dest / ".git")

    req = dest / "requirements.txt"
    if req.exists() and not node.get("skip_requirements", False):
        run("uv", "pip", "install", "-c", CONSTRAINTS, "-r", str(req))
    if extra := node.get("pip"):
        run("uv", "pip", "install", "-c", CONSTRAINTS, *extra)
    if node.get("run_install_py") and (dest / "install.py").exists():
        run(sys.executable, "install.py", cwd=dest)


def main() -> None:
    lock_path, target = Path(sys.argv[1]), Path(sys.argv[2])
    nodes = (yaml.safe_load(lock_path.read_text()) or {}).get("nodes") or []
    target.mkdir(parents=True, exist_ok=True)
    for node in nodes:
        install(node, target)
    print(f"installed {len(nodes)} custom node(s)")


if __name__ == "__main__":
    main()
