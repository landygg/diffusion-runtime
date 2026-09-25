# Notice

This image is an unofficial, community-built runtime. It is **not affiliated
with, sponsored or endorsed by Comfy Org, Inc. or NVIDIA Corporation**.
"ComfyUI" is a trademark of Comfy Org, Inc., and "NVIDIA" and "CUDA" are
trademarks of NVIDIA Corporation. These names are used here only to describe
what the image contains.

The image is an aggregate of independent programs, each under its own license.
The exact version of every component is recorded in the image:

| File in the image | Contents |
|---|---|
| `/opt/comfy/licenses/THIRD_PARTY_LICENSES.txt` | Every Python package: version, license, URL, full license text |
| `/opt/comfy/pip-freeze.txt` | Exact Python package versions |
| `/opt/ComfyUI/LICENSE` | GPL-3.0 text (ComfyUI) |
| `/usr/share/doc/*/copyright` | Debian package licenses |
| Image labels `dev.landygg.runtime.comfyui-ref`, `.torch`, `.recipe` | Upstream tag, torch build, recipe hash |

## GPL / LGPL components: where the Corresponding Source is

The build is fully reproducible from this repository's `Dockerfile` and the pins it references.
The components are unmodified.

| Component | License | Corresponding Source |
|---|---|---|
| ComfyUI | GPL-3.0 | Included as source in `/opt/ComfyUI`; upstream https://github.com/Comfy-Org/ComfyUI at the tag in label `dev.landygg.runtime.comfyui-ref` |
| comfyui-frontend-package (compiled JS) | GPL-3.0 | https://github.com/Comfy-Org/ComfyUI_frontend at tag `v<version>` (version in `pip-freeze.txt`) |
| comfyui-manager, comfyui-embedded-docs, comfy-aimdo | GPL-3.0 | Python source included in `/opt/venv/lib/python3.12/site-packages`; sdists on https://pypi.org |
| PyGithub | LGPL-3.0 | Source included in site-packages; https://github.com/PyGithub/PyGithub |
| ffmpeg / libav* (Debian bookworm build) | GPL-2.0+/LGPL-2.1+ | `apt-get source ffmpeg=<version>` or https://snapshot.debian.org |
| Custom nodes in `nodes.lock.yaml` | per node | The repository and commit listed in `nodes.lock.yaml` |

If any of these upstream sources stops being available, open an issue in this
repository and a source copy will be provided for as long as the image version
is distributed.

## NVIDIA components

`nvidia-*`, `cuda-*` and cuDNN libraries are redistributed **unmodified**, as
installed from PyPI as dependencies of PyTorch, and are accessed only through
PyTorch. They are subject to the NVIDIA Software License Agreement and the
CUDA/cuDNN EULAs (license text in each `nvidia_*.dist-info/licenses/`). They
may be used only on systems with NVIDIA GPUs. No NVIDIA component is licensed
under the GPL through this aggregate.
