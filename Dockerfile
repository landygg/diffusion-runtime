# syntax=docker/dockerfile:1.7
#
# ComfyUI runtime image. Layers are ordered from least- to most-frequently
# changing so a new ComfyUI release only rebuilds the last few layers:
#
#   OS deps -> torch (pinned) -> ComfyUI requirements -> ComfyUI source -> custom nodes -> model tools -> entrypoint
#
# No CUDA base image: the torch wheels from download.pytorch.org ship the CUDA
# runtime as nvidia-* pip packages. The host only needs the NVIDIA driver and
# the NVIDIA Container Toolkit (RunPod has both).

ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim-bookworm

ARG TORCH_VERSION=2.14.0
ARG CUDA_TAG=cu130
ARG COMFYUI_REF=v0.37.2
ARG COMFYUI_REPO=https://github.com/Comfy-Org/ComfyUI.git

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    COMFY_HOME=/opt/ComfyUI \
    COMFY_DATA_DIR=/workspace \
    COMFY_PORT=8188 \
    HF_HOME=/workspace/.cache/huggingface

# 1. OS packages. ffmpeg CLI is used by video nodes (VideoHelperSuite);
#    libgl/libglib are needed by opencv-based nodes; openssh-server backs the
#    optional SSH access (started only when PUBLIC_KEY is set). The packaged
#    host keys are removed so no two containers share them; start.sh creates
#    per-volume keys.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ffmpeg libgl1 libglib2.0-0 ca-certificates curl tini openssh-server \
    && rm -rf /var/lib/apt/lists/* /etc/ssh/ssh_host_*

# COPY --from does not expand ARGs; bump this tag by hand.
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /usr/local/bin/uv

# 2. torch, pinned. The freeze becomes a constraints file so no later
#    `requirements.txt` (ComfyUI's lists plain `torch`) can swap it out.
# --seed adds pip: the Manager and some nodes' install.py shell out to `python -m pip`.
RUN uv venv --seed "$VIRTUAL_ENV" \
    && uv pip install \
        "torch==${TORCH_VERSION}" torchvision torchaudio \
        --index-url "https://download.pytorch.org/whl/${CUDA_TAG}" \
    && uv pip freeze | grep -iE '^(torch|torchvision|torchaudio|nvidia-|triton)' > /opt/constraints.txt \
    && cat /opt/constraints.txt

# 3. ComfyUI source + its requirements. The Manager has its own file
#    (manager_requirements.txt -> comfyui_manager + GitPython, PyGithub, uv, ...);
#    it is required: the image refuses to build without it.
RUN git clone --depth 1 --branch "${COMFYUI_REF}" "${COMFYUI_REPO}" "$COMFY_HOME" \
    && uv pip install -c /opt/constraints.txt -r "$COMFY_HOME/requirements.txt" \
    && test -f "$COMFY_HOME/manager_requirements.txt" \
    && uv pip install -c /opt/constraints.txt -r "$COMFY_HOME/manager_requirements.txt" \
    && uv pip install -c /opt/constraints.txt "huggingface_hub[hf_xet]" \
    && rm -rf "$COMFY_HOME/.git"

# 4. Custom nodes, pinned by commit in nodes.lock.yaml (changes here bump the recipe hash).
COPY nodes.lock.yaml /opt/comfy/nodes.lock.yaml
COPY scripts/install_nodes.py /opt/comfy/install_nodes.py
RUN python /opt/comfy/install_nodes.py /opt/comfy/nodes.lock.yaml "$COMFY_HOME/custom_nodes" \
    && uv pip freeze > /opt/comfy/pip-freeze.txt

# 5. Model downloader: models.lock.yaml is only the list of what to fetch onto
#    the volume (no weights in the image). get-model / sync-models dispatch on argv[0].
COPY models.lock.yaml /opt/comfy/models.lock.yaml
COPY scripts/models.py /opt/comfy/models.py
RUN chmod +x /opt/comfy/models.py \
    && ln -s /opt/comfy/models.py /usr/local/bin/get-model \
    && ln -s /opt/comfy/models.py /usr/local/bin/sync-models \
    && python /opt/comfy/models.py check

# 6. Entrypoint + smoke test (run with: --entrypoint python ... /opt/comfy/smoke.py).
COPY docker/start.sh /opt/comfy/start.sh
COPY scripts/smoke.py required_nodes.txt /opt/comfy/
COPY licenses/NOTICE.md /opt/comfy/licenses/NOTICE.md
# License inventory of the final environment. pip-licenses runs from a throwaway
# uvx env (--python points it at the image venv), so it is not left installed.
RUN chmod +x /opt/comfy/start.sh \
    && uvx --from pip-licenses pip-licenses --python /opt/venv/bin/python \
        --from=mixed --with-urls --with-license-file --no-license-path --format=plain-vertical \
        > /opt/comfy/licenses/THIRD_PARTY_LICENSES.txt \
    && grep -c . /opt/comfy/licenses/THIRD_PARTY_LICENSES.txt

ARG RECIPE_HASH=dev
ARG SOURCE_URL=""
LABEL org.opencontainers.image.title="diffusion-runtime" \
      org.opencontainers.image.description="Unofficial ComfyUI runtime (no models). Not affiliated with Comfy Org or NVIDIA. See /opt/comfy/licenses." \
      org.opencontainers.image.licenses="GPL-3.0-only AND LicenseRef-NVIDIA-SDK-EULA AND LicenseRef-Mixed" \
      org.opencontainers.image.source="${SOURCE_URL}" \
      org.opencontainers.image.version="${COMFYUI_REF}" \
      dev.landygg.runtime.comfyui-ref="${COMFYUI_REF}" \
      dev.landygg.runtime.torch="${TORCH_VERSION}+${CUDA_TAG}" \
      dev.landygg.runtime.recipe="${RECIPE_HASH}"

EXPOSE 8188 22
WORKDIR /opt/ComfyUI
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${COMFY_PORT}/system_stats" > /dev/null || exit 1
# -s: RunPod runs its own init as PID 1, so tini registers as a subreaper to
# still reap zombies (a no-op when tini is PID 1).
ENTRYPOINT ["/usr/bin/tini", "-s", "--", "/opt/comfy/start.sh"]
