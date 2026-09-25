# diffusion-runtime

[Español](README_ES.md)

**Unofficial Docker runtime for [ComfyUI](https://github.com/Comfy-Org/ComfyUI).** Not affiliated with or endorsed by Comfy Org or NVIDIA; "ComfyUI" is a trademark of Comfy Org, Inc.

A ComfyUI Docker image (no models) that rebuilds itself whenever ComfyUI tags a
new release or the recipe in this repo changes. Built for RunPod and for local
GPUs with the NVIDIA Container Toolkit.

## What is inside / outside

| Image | Volume (`$COMFY_DATA_DIR`, default `/workspace`) |
|---|---|
| ComfyUI (pinned tag), torch + CUDA (wheels), ffmpeg, ComfyUI-Manager (`manager_requirements.txt`), custom nodes from `nodes.lock.yaml` (currently empty: Wan 2.2 and Z-Image use core nodes) | `models/`, `input/`, `output/`, `user/` (workflows, settings), `temp/`, `custom_nodes/` (opt-in) |

## Tags

`<comfyui>-<variant>-r<hash>` immutable · `<comfyui>` · `latest` (automatic) · `stable` (manual, **promote** workflow).
Variants in `variants.json`: `cu130` (torch 2.14, driver ≥ 580, default) and `cu128` (torch 2.11, compatibility).

## Usage

```bash
# RunPod: Container Image = ghcr.io/landygg/diffusion-runtime:stable, port 8188/http, Network Volume at /workspace
docker run --gpus all -p 8188:8188 -v "$PWD/data:/workspace" \
  -e COMFY_EXTRA_ARGS="--lowvram" ghcr.io/landygg/diffusion-runtime:stable
```

For reproducible pipelines, pin by digest (`ghcr.io/landygg/diffusion-runtime@sha256:…`) rather than by a moving tag.

| Variable | Default | Effect |
|---|---|---|
| `COMFY_DATA_DIR` | `/workspace` | Volume root |
| `COMFY_PORT` | `8188` | Port |
| `COMFY_EXTRA_ARGS` | — | Extra flags (`--lowvram`, `--highvram`, …) |
| `COMFY_ENABLE_MANAGER` | `0` | `1` adds `--enable-manager` |
| `COMFY_ALLOW_VOLUME_NODES` | `0` | `1` also loads `custom_nodes/` from the volume (not reproducible) |

## Policy files (everything is defined in the repo)

| File | Controls | Enforced by |
|---|---|---|
| `nodes.lock.yaml` | Custom nodes, pinned by SHA | build (`install_nodes.py`) |
| `required_nodes.txt` | Node types downstream workflows need; the build fails if one is missing | smoke test (`smoke.py`) |
| `variants.json` | CUDA / torch / Python variants | build (matrix) |
| `renovate.json` | Which dependencies update automatically, and how | Renovate (weekly PRs) |
| `retention.json` | How many images to keep in GHCR | `retention` workflow (weekly) |

## Adding or updating a custom node

Add an entry to `nodes.lock.yaml` (`repo`, `ref: main`, `commit` = `git ls-remote <repo> HEAD`) and its `class_type` values to `required_nodes.txt`, then open a PR. Once merged, the recipe hash changes and a new image is built. From then on Renovate proposes the SHA bumps. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Local build and smoke test (Mac)

With Apple's `container` app (or Docker, same flags):

```bash
container builder start --cpus 8 --memory 16g
container build --platform linux/amd64 -t runtime:dev .
container run --rm --platform linux/amd64 --memory 8g --entrypoint python runtime:dev /opt/comfy/smoke.py
```

The smoke test boots ComfyUI on CPU and checks that `torch` and `comfyui_manager` import, that no node reports `IMPORT FAILED`, and that `/object_info` exposes everything in `required_nodes.txt`.

## License

MIT for this repository. The images aggregate third-party software under its own licenses (ComfyUI GPL-3.0, NVIDIA EULA, …): see [licenses/NOTICE.md](licenses/NOTICE.md).

## Maintainer setup

1. After the first build: *Packages → diffusion-runtime → Package settings → Change visibility* → public (GitHub has no API for this).
2. Install the [Renovate GitHub App](https://github.com/apps/renovate), then add it as a bypass actor (via PR only) on the `main: review` ruleset. Branch protection and Actions settings are managed by the maintainer outside this repo.
3. Validate a new image on a real GPU, then run the `promote` workflow with its immutable tag to move `stable`.
4. Run the `retention` workflow as a dry run to review what it would delete.
