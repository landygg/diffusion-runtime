#!/opt/venv/bin/python
"""Download Hugging Face models onto the volume ($COMFY_DATA_DIR/models/<folder>/).

Installed in the image as three commands (argv[0] picks the subcommand):

  get-model <ref> [folder]    one model; ref = Hub URL, org/repo[@rev]/path, or a
                              file name listed in models.lock.yaml. folder is a
                              ComfyUI model folder (created if missing), inferred
                              from the path when omitted (".../text_encoders/x").
  sync-models [group ...]     every model in models.lock.yaml (or only those groups)
  models.py check             validate models.lock.yaml offline (used by smoke.py)

Downloads go through huggingface_hub (hf_xet when the repo supports it), are
staged on the volume so an interrupted download resumes, and are moved into
place only after size and sha256 match. Gated models: set HF_TOKEN on the pod
or run `hf auth login` once (HF_HOME defaults to the volume, so it persists).
"""

import argparse
import fcntl
import hashlib
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

DATA = Path(os.environ.get("COMFY_DATA_DIR", "/workspace"))
MODELS = DATA / "models"
STAGING = DATA / ".cache" / "models-staging"
MANIFEST = Path(os.environ.get("COMFY_MODELS_MANIFEST", "/opt/comfy/models.lock.yaml"))
LOCK = Path("/tmp/models-download.lock")

# Before importing huggingface_hub: keep its cache and token on the volume, and
# drop progress bars when the output goes to the pod log instead of a terminal.
os.environ.setdefault("HF_HOME", str(DATA / ".cache" / "huggingface"))
if not sys.stdout.isatty():
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

# ComfyUI's folder_paths names (plus legacy aliases it still maps).
FOLDERS = {
    "audio_encoders", "checkpoints", "clip", "clip_vision", "configs", "controlnet",
    "diffusers", "diffusion_models", "embeddings", "gligen", "hypernetworks",
    "latent_upscale_models", "loras", "model_patches", "photomaker", "style_models",
    "t2i_adapter", "text_encoders", "unet", "upscale_models", "vae", "vae_approx",
}
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
HUB_HOSTS = {"huggingface.co", "www.huggingface.co", "hf.co"}


def log(msg: str) -> None:
    print(f"[models] {msg}", flush=True)


@dataclass
class Model:
    repo: str
    revision: str
    file: str
    folder: str
    sha256: str | None = None
    size: int | None = None
    name: str | None = None
    group: str | None = None

    @property
    def dest(self) -> Path:
        base = Path(self.folder) if Path(self.folder).is_absolute() else MODELS / self.folder
        return base / (self.name or Path(self.file).name)


# --- manifest -------------------------------------------------------------------

def load_manifest(path: Path = MANIFEST) -> list[Model]:
    import yaml

    if not path.exists():
        return []
    entries = (yaml.safe_load(path.read_text()) or {}).get("models") or []
    return [Model(**e) for e in entries]


def check_manifest(models: list[Model]) -> list[str]:
    errors, seen = [], {}
    for m in models:
        where = f"{m.repo}:{m.file}"
        if not (isinstance(m.revision, str) and SHA1.match(m.revision)):
            errors.append(f"{where}: revision must be a full 40-char commit SHA (quote it if all digits)")
        if not (isinstance(m.sha256, str) and SHA256.match(m.sha256)):
            errors.append(f"{where}: sha256 must be 64 hex chars (quote it if all digits)")
        if not isinstance(m.size, int) or m.size <= 0:
            errors.append(f"{where}: size must be a positive integer")
        if Path(m.folder or "").parts[:1] not in [(f,) for f in FOLDERS]:
            errors.append(f"{where}: folder must be a ComfyUI model folder (or a subfolder of one), "
                          f"got {m.folder!r}")
        if not m.group:
            errors.append(f"{where}: group is required")
        if (prev := seen.setdefault(m.dest, where)) != where:
            errors.append(f"{where}: same destination as {prev} ({m.dest})")
    return errors


# --- references -----------------------------------------------------------------

def parse_ref(ref: str) -> tuple[str, str, str]:
    """Return (repo, revision, path) from a Hub URL or `org/repo[@rev]/path`."""
    if "://" in ref:
        url = urlparse(ref)
        parts = [unquote(p) for p in url.path.strip("/").split("/")]
        if url.hostname not in HUB_HOSTS or len(parts) < 5 or parts[2] not in ("resolve", "blob"):
            sys.exit(f"not a Hugging Face file URL: {ref}\n"
                     "expected https://huggingface.co/<org>/<repo>/resolve/<revision>/<path>")
        return f"{parts[0]}/{parts[1]}", parts[3], "/".join(parts[4:])
    parts = ref.strip("/").split("/")
    if len(parts) < 3:
        sys.exit(f"cannot parse {ref!r}: use a Hub URL, org/repo[@revision]/path/to/file, "
                 "or a file name from models.lock.yaml")
    repo_name, _, revision = parts[1].partition("@")
    return f"{parts[0]}/{repo_name}", revision or "main", "/".join(parts[2:])


def infer_folder(path: str) -> str | None:
    for part in reversed(Path(path).parent.parts):
        if part in FOLDERS:
            return part
    return None


def resolve(ref: str, folder: str | None) -> Model:
    if "/" not in ref:  # bare file name: look it up in the manifest
        matches = [m for m in load_manifest() if Path(m.file).name == ref or m.name == ref]
        if not matches:
            sys.exit(f"{ref!r} is not in {MANIFEST}; pass its Hub URL or org/repo/path instead")
        m = matches[0]
        if folder:
            m.folder = folder
        return m

    from huggingface_hub import HfApi

    repo, revision, path = parse_ref(ref)
    folder = folder or infer_folder(path)
    if not folder:
        sys.exit(f"cannot infer the model folder from {path!r}; pass it as the second argument "
                 f"(e.g. get-model {ref} loras)")
    api = HfApi()
    with hub_errors(repo):
        commit = api.model_info(repo, revision=revision).sha
        info = api.get_paths_info(repo, [path], revision=commit)
    if not info or not hasattr(info[0], "size"):
        sys.exit(f"{path} not found in {repo}@{revision}")
    lfs = getattr(info[0], "lfs", None)
    return Model(repo=repo, revision=commit, file=path, folder=folder,
                 sha256=lfs.sha256 if lfs else None, size=info[0].size)


class hub_errors:
    """Turn Hub HTTP errors into one readable line instead of a traceback."""

    def __init__(self, repo: str):
        self.repo = repo

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        from huggingface_hub.errors import (
            GatedRepoError,
            HfHubHTTPError,
            RepositoryNotFoundError,
        )

        if exc is None:
            return False
        if isinstance(exc, GatedRepoError):
            sys.exit(f"{self.repo} is gated: accept its license on huggingface.co, then set "
                     "HF_TOKEN or run `hf auth login`")
        if isinstance(exc, RepositoryNotFoundError):
            sys.exit(f"{self.repo}: repository not found (or private; set HF_TOKEN)")
        if isinstance(exc, HfHubHTTPError):
            sys.exit(f"{self.repo}: {exc}")
        return False


# --- download -------------------------------------------------------------------

def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(16 << 20):
            h.update(chunk)
    return h.hexdigest()


def human(n: int | None) -> str:
    if n is None:
        return "? bytes"
    return f"{n / (1 << 30):.2f} GiB" if n >= 1 << 30 else f"{n / (1 << 20):.1f} MiB"


def present(m: Model, verify: bool) -> bool:
    dest = m.dest
    if not dest.exists():
        return False
    if m.size is not None and dest.stat().st_size != m.size:
        log(f"{dest}: size differs from the lock, downloading again")
        return False
    if verify and m.sha256 and sha256_of(dest) != m.sha256:
        log(f"{dest}: sha256 differs from the lock, downloading again")
        return False
    return True


def download(m: Model) -> None:
    from huggingface_hub import hf_hub_download

    dest = m.dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = STAGING / m.repo.replace("/", "--")
    log(f"downloading {m.repo}@{m.revision[:8]}/{m.file} ({human(m.size)}) -> {dest}")
    with hub_errors(m.repo):
        staged = Path(hf_hub_download(m.repo, m.file, revision=m.revision, local_dir=stage_dir))

    size = staged.stat().st_size
    if m.size is not None and size != m.size:
        staged.unlink()
        sys.exit(f"{m.file}: got {size} bytes, expected {m.size}")
    log(f"verifying sha256 of {staged.name}")
    digest = sha256_of(staged)
    if m.sha256 and digest != m.sha256:
        staged.unlink()
        sys.exit(f"{m.file}: sha256 {digest} does not match {m.sha256}")
    m.sha256, m.size = digest, size
    shutil.move(staged, dest)  # a rename when staging and dest share the volume
    # Drop hf's resume metadata for this file, or a later --force would skip the download.
    (stage_dir / ".cache" / "huggingface" / "download" / f"{m.file}.metadata").unlink(missing_ok=True)
    log(f"ok {dest}")


def locked():
    """Serialize downloads inside the container (a startup sync vs. a manual get-model)."""
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    fd = LOCK.open("w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("another download is running, waiting for it to finish")
        fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


# --- commands -------------------------------------------------------------------

def cmd_get(args: argparse.Namespace) -> None:
    m = resolve(args.ref, args.folder)
    with locked():
        if not args.force and present(m, verify=False):
            log(f"already present: {m.dest} (use --force to download again)")
        else:
            download(m)
    print(
        "\nTo pin it for every new pod, add this to models.lock.yaml in the repo:\n"
        f"  - group: {m.group or '<group>'}\n"
        f"    repo: {m.repo}\n"
        f"    revision: {m.revision}\n"
        f"    file: {m.file}\n"
        f"    folder: {m.folder}\n"
        f"    sha256: {m.sha256 or '<run again with --force to compute>'}\n"
        f"    size: {m.size}"
    )


def cmd_sync(args: argparse.Namespace) -> None:
    models = load_manifest()
    if errors := check_manifest(models):  # e.g. an unquoted all-digit sha256 parsed as an int
        sys.exit(f"{MANIFEST} is invalid, nothing downloaded:\n  " + "\n  ".join(errors))
    groups = set(args.groups) - {"all"}
    if unknown := groups - {m.group for m in models}:
        sys.exit(f"unknown group(s): {', '.join(sorted(unknown))}")
    todo = [m for m in models if not groups or m.group in groups]
    failed = []
    with locked():
        for m in todo:
            if present(m, verify=args.verify):
                log(f"present {m.dest}")
                continue
            try:
                download(m)
            except SystemExit as e:  # keep going: one bad model shouldn't block the rest
                log(f"FAILED {e}")
                failed.append(m.file)
    log(f"{len(todo) - len(failed)}/{len(todo)} model(s) ready in {MODELS}")
    if failed:
        sys.exit(1)


def cmd_check(_: argparse.Namespace) -> None:
    models = load_manifest()
    if errors := check_manifest(models):
        sys.exit("models.lock.yaml:\n  " + "\n  ".join(errors))
    print(f"models.lock.yaml ok: {len(models)} model(s)")


def get_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("ref", help="Hub URL, org/repo[@revision]/path, or a file name from the lock")
    p.add_argument("folder", nargs="?", help="ComfyUI model folder or absolute path (default: inferred)")
    p.add_argument("--force", action="store_true", help="download again even if present")
    p.set_defaults(func=cmd_get)


def sync_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("groups", nargs="*", help="only these groups (default: all)")
    p.add_argument("--verify", action="store_true", help="re-hash files already present")
    p.set_defaults(func=cmd_sync)


def main() -> None:
    fmt = argparse.RawDescriptionHelpFormatter
    name = Path(sys.argv[0]).name
    if name in ("get-model", "sync-models"):
        parser = argparse.ArgumentParser(prog=name, description=__doc__, formatter_class=fmt)
        (get_args if name == "get-model" else sync_args)(parser)
    else:
        parser = argparse.ArgumentParser(prog="models.py", description=__doc__, formatter_class=fmt)
        sub = parser.add_subparsers(dest="cmd", required=True)
        get_args(sub.add_parser("get", help="download one model"))
        sync_args(sub.add_parser("sync", help="download every model in models.lock.yaml"))
        sub.add_parser("check", help="validate models.lock.yaml").set_defaults(func=cmd_check)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
