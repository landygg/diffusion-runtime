# diffusion-runtime

[![stable](https://img.shields.io/github/v/release/landygg/diffusion-runtime?label=stable&sort=date)](https://github.com/landygg/diffusion-runtime/releases/latest)
[![build](https://github.com/landygg/diffusion-runtime/actions/workflows/build.yml/badge.svg)](https://github.com/landygg/diffusion-runtime/actions/workflows/build.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Image on GHCR](https://img.shields.io/badge/ghcr.io-diffusion--runtime-2496ED?logo=docker&logoColor=white)](https://github.com/landygg/diffusion-runtime/pkgs/container/diffusion-runtime)

**English** · [Español](README_ES.md)

**An unofficial ComfyUI Docker image for RunPod and local NVIDIA GPUs.** It is rebuilt automatically on every ComfyUI release, and a `stable` tag only moves once an image has been checked on a real GPU. Custom nodes and models are pinned in the repo, and no model weights are baked into the image.

> Not affiliated with or endorsed by Comfy Org or NVIDIA. "ComfyUI" is a trademark of Comfy Org, Inc.; see [licenses/NOTICE.md](licenses/NOTICE.md).

```
ghcr.io/landygg/diffusion-runtime:stable
```

## Quick start

**RunPod.** Create a pod template with these settings:

| Setting | Value |
|---|---|
| Container image | `ghcr.io/landygg/diffusion-runtime:stable` (or a digest, see [Tags](#tags)) |
| Expose HTTP ports | `8188` |
| Expose TCP ports | `22` (only if you use SSH) |
| Volume mount path | `/workspace` |
| Environment (optional) | `COMFY_MODELS_GROUPS`, `HF_TOKEN`, `COMFY_EXTRA_ARGS` |

Open *Connect → HTTP 8188*. On first start the models in [`models.lock.yaml`](models.lock.yaml) download to the volume in the background; press **R** in ComfyUI when the log shows `[models] ... ready`.

**Local GPU** (NVIDIA driver + [Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)):

```bash
docker run --gpus all -p 8188:8188 -v "$PWD/data:/workspace" \
  -e COMFY_MODELS_SYNC=background ghcr.io/landygg/diffusion-runtime:stable
```

Then open http://localhost:8188. On small GPUs add `-e COMFY_EXTRA_ARGS="--lowvram"`.

## Features

- **Tracks ComfyUI releases.** A new upstream tag triggers a build within about 6 hours. Each image passes a CPU smoke test before it is published.
- **A `stable` channel checked on a GPU.** `latest` moves on its own; `stable` moves only when a maintainer promotes an image after a real render on a GPU.
- **Everything pinned.** ComfyUI tag, torch/CUDA wheels, custom nodes (by commit) and models (by Hugging Face commit + sha256) are all defined in this repo.
- **Models on the volume, not in the image.** `sync-models` fetches the pinned set; `get-model` adds any Hugging Face model from a pod shell.
- **Built for RunPod.** CORS set for the pod's proxy (API and websocket calls work through it), key-only SSH, the container stays up if ComfyUI crashes, and ComfyUI flags can be changed without redeploying.
- **Licenses included.** Every image ships its third-party license inventory and exact package versions.

## What is inside

| In the image | On the volume (`$COMFY_DATA_DIR`, default `/workspace`) |
|---|---|
| ComfyUI (pinned tag), torch + CUDA wheels, ffmpeg, ComfyUI-Manager, custom nodes from `nodes.lock.yaml`, the `get-model` / `sync-models` tools and `hf` CLI, a C compiler for Triton | `models/`, `input/`, `output/`, `user/` (workflows, settings), `temp/`, `custom_nodes/` (opt-in), Hugging Face cache and token |

The Z-Image Turbo and Wan 2.2 TI2V 5B workflows use core nodes only, so `nodes.lock.yaml` is currently empty.

## Tags

| Tag | Moves | Use it for |
|---|---|---|
| `stable`, `stable-<variant>` | By hand (`promote` workflow), after a render on a GPU | Pod templates and day-to-day work |
| `latest`, `<comfyui>` (e.g. `0.37.3`) | Automatically, on every build | Trying a new ComfyUI release early |
| `<comfyui>-<variant>-r<hash>` (e.g. `0.37.3-cu130-r82550d79`) | Never (immutable) | Reproducible pipelines; kept for the 5 newest per variant |
| `keep-<name>` | By hand | An image to keep forever (e.g. the exact stack an episode was produced with) |

For fully reproducible runs, pin by digest: `ghcr.io/landygg/diffusion-runtime@sha256:…`. The [latest release](https://github.com/landygg/diffusion-runtime/releases/latest) is always the current `stable`, with its digest. From a shell:

```bash
docker buildx imagetools inspect ghcr.io/landygg/diffusion-runtime:stable
```

| Variant | torch | Host NVIDIA driver | |
|---|---|---|---|
| `cu130` | 2.14 | ≥ 580 | Default (`stable`, `latest`) |
| `cu128` | 2.11 | 570–579 | Compatibility; still covers Blackwell (sm_120) |

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `COMFY_EXTRA_ARGS` | — | Extra ComfyUI flags (`--lowvram`, `--highvram`, …) |
| `COMFY_MODELS_SYNC` | RunPod: `background`; else `off` | Download `models.lock.yaml` at start: `background`, `wait` (before ComfyUI starts) or `off` |
| `COMFY_MODELS_GROUPS` | all | Only these groups from `models.lock.yaml` (e.g. `z-image-turbo`) |
| `HF_TOKEN` | — | Hugging Face token, for gated or private models |
| `PUBLIC_KEY` | — | Starts sshd with key-only root login (RunPod sets it from your account's SSH keys) |
| `COMFY_ENABLE_MANAGER` | `0` | `1` adds `--enable-manager` |
| `COMFY_CORS_ORIGIN` | RunPod: the pod's proxy origin; else off | Value for `--enable-cors-header` (`*` = any origin, `off` = disabled) |
| `COMFY_KEEPALIVE_ON_CRASH` | RunPod: `1`; else `0` | `1` keeps the container alive if ComfyUI exits, for debugging |
| `COMFY_ALLOW_VOLUME_NODES` | `0` | `1` also loads `custom_nodes/` from the volume (not reproducible) |
| `COMFY_DATA_DIR` | `/workspace` | Volume root |
| `COMFY_PORT` | `8188` | Port |
| `HF_HOME` | `/workspace/.cache/huggingface` | Hugging Face cache and `hf auth login` token |

ComfyUI flags can also go in `/workspace/comfyui_args.txt`. The file is created on first start and read at every start, so flags change with a restart instead of a redeploy.

## Models

The *Download* buttons in ComfyUI's "Missing Models" panel save the file to your **browser**, not to the pod. From a pod shell (web terminal or SSH), use instead:

```bash
get-model <ref> [folder]            # one model, onto the volume
sync-models [group ...] [--verify]  # everything in models.lock.yaml (--verify re-hashes)
```

- `<ref>` is the model's Hugging Face link (the 🔗 in the "Missing Models" panel), `org/repo[@revision]/path/to/file`, or a file name already in `models.lock.yaml`.
- `folder` is a ComfyUI model folder (`loras`, `vae`, `diffusion_models`, …), a subfolder such as `loras/style`, or an absolute path. It is created if missing. When omitted, it is taken from the path (`split_files/text_encoders/x.safetensors` → `text_encoders`).

```bash
get-model https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors
get-model some-org/some-lora/style.safetensors loras
```

Downloads resume if interrupted and only one runs at a time. A file appears in the models folder only after its size and sha256 match. `get-model` ends by printing a `models.lock.yaml` entry pinned to the exact commit: add it to the repo to get that model on every new pod. For gated models, accept the license on huggingface.co, then set `HF_TOKEN` or run `hf auth login` once (the token is kept on the volume).

## How releases work

1. **build** runs every 6 hours and on every change to the recipe. It computes a tag from the ComfyUI version and a hash of the recipe files, builds only tags that don't exist yet, runs the CPU smoke test, and publishes the immutable tag plus `latest`.
2. **The maintainer checks the image on a GPU**, because a CPU run can't catch out-of-memory errors, driver or CUDA kernel problems, or a render that changes.
3. **promote** re-points `stable` and `stable-<variant>` to that image, with no rebuild or re-upload, and publishes a GitHub Release for it (ComfyUI and torch versions, digest, PRs since the previous release). The default variant's release is marked *Latest*:
   ```bash
   gh workflow run promote -R landygg/diffusion-runtime -f tag=0.37.3-cu130-r82550d79
   # keep one forever instead:
   gh workflow run promote -R landygg/diffusion-runtime -f tag=0.37.3-cu130-r82550d79 -f channel=keep-episode01
   ```
4. **retention** runs weekly. It keeps the 5 newest immutable images per variant and never deletes `latest*`, `stable*`, `keep-*` or `buildcache-*`.

If an image fails on the GPU it is simply not promoted and `stable` stays where it was. To roll back, promote an older immutable tag; its release becomes *Latest* again.

## Development

Everything the image contains is defined by these files:

| File | Controls | Enforced by |
|---|---|---|
| `nodes.lock.yaml` | Custom nodes, pinned by commit | build (`install_nodes.py`) |
| `models.lock.yaml` | Models downloaded to the volume, pinned by commit + sha256 | `sync-models`; validated at build and in the smoke test |
| `required_nodes.txt` | Node types the workflows need | smoke test (`smoke.py`) |
| `variants.json` | CUDA / torch / Python variants | build (matrix) |
| `renovate.json` | Which dependencies update automatically, and how | Renovate (weekly PRs) |
| `retention.json` | How many images to keep in GHCR | `retention` workflow |

**Adding a custom node:** add it to `nodes.lock.yaml` (`repo`, `ref: main`, `commit` = `git ls-remote <repo> HEAD`) and its `class_type` values to `required_nodes.txt`, then open a PR. Renovate proposes later commit bumps. **Adding a model:** paste the entry `get-model` prints into `models.lock.yaml`. See [CONTRIBUTING.md](CONTRIBUTING.md).

**Local build and smoke test** on a Mac, with Apple's `container` (or Docker, same flags):

```bash
container builder start --cpus 8 --memory 16g
container build --platform linux/amd64 -t runtime:dev .
container run --rm --platform linux/amd64 --memory 8g --entrypoint python runtime:dev /opt/comfy/smoke.py
```

The smoke test boots ComfyUI on CPU and checks that:
- `torch` and `comfyui_manager` import;
- no node reports `IMPORT FAILED`;
- `/object_info` lists every node type in `required_nodes.txt`;
- the model tools work and `models.lock.yaml` is valid;
- a C compiler is present, which Triton needs on the GPU.

## License

This repository is [MIT](LICENSE). The images bundle third-party software under its own licenses (ComfyUI GPL-3.0, NVIDIA SDK EULA, …); [licenses/NOTICE.md](licenses/NOTICE.md) lists them and says where the corresponding source is.
