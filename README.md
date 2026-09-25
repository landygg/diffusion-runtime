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

## Promoting an image (`stable`) and keeping one (`keep-*`)

`build` publishes every new image automatically, but `latest` only guarantees that it builds and passes the **CPU** smoke test. GPU-only problems (out of memory, drivers, CUDA kernels, a render that changes) can't be caught there. So production templates should use **`stable`**, which only moves when the maintainer promotes an image after validating it on a real GPU:

1. Find the new image's immutable tag (e.g. `0.37.2-cu130-r1a2b3c4d`) in the `build` run summary (*Pin by digest*).
2. Deploy that exact tag on RunPod (or a local GPU) and run a real generation.
3. If it works, run the `promote` workflow with that tag. It re-points `stable` and `stable-<variant>` to the same image, with no rebuild or re-upload:
   ```bash
   gh workflow run promote -R landygg/diffusion-runtime -f tag=0.37.2-cu130-r1a2b3c4d
   ```
   Or use *Actions → promote → Run workflow*.

If a new image fails on the GPU, don't promote it; `stable` stays on the previous one. To roll back, promote an older immutable tag again. Until the first promotion `stable` doesn't exist yet; use `latest` or a digest meanwhile.

**Keeping an image:** the `retention` workflow keeps the 5 newest immutable images per variant and deletes older ones. To keep a specific image forever (e.g. the exact stack a project was produced with), promote it to a channel named `keep-<name>` instead of `stable`:

```bash
gh workflow run promote -R landygg/diffusion-runtime -f tag=0.37.2-cu130-r1a2b3c4d -f channel=keep-episode01
```

Tags starting with `latest`, `stable`, `keep-` or `buildcache-` are never deleted (`retention.json`).

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
| `COMFY_CORS_ORIGIN` | RunPod: `https://<pod>-<port>.proxy.runpod.net`; else off | Value for `--enable-cors-header` (`*` = any origin, `off` = disabled) |
| `COMFY_KEEPALIVE_ON_CRASH` | RunPod: `1`; else `0` | `1` keeps the container alive if ComfyUI exits, for debugging |
| `PUBLIC_KEY` | — | Starts sshd with key-only root login (host keys persist in `/workspace/.ssh-host-keys`) |

Extra ComfyUI flags can also go in `/workspace/comfyui_args.txt` (created on first start, read at every start), so they change without redeploying.

### RunPod template

| Setting | Value |
|---|---|
| Container image | `ghcr.io/landygg/diffusion-runtime:stable` (or a digest) |
| Expose HTTP ports | `8188` |
| Expose TCP ports | `22` (only if you use `PUBLIC_KEY`) |
| Volume mount path | `/workspace` (Network Volume recommended) |
| Environment | `PUBLIC_KEY` (optional); `COMFY_EXTRA_ARGS` (optional) |

Behind RunPod's proxy, ComfyUI rejects API and websocket calls with 403 unless CORS is enabled (the proxy's host and origin differ). The image enables it automatically for the pod's own proxy origin.

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
3. Validate each new image on a real GPU and promote it (see *Promoting an image*).
4. Run the `retention` workflow as a dry run to review what it would delete.
