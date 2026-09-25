#!/usr/bin/env bash
# Point ComfyUI at the persistent volume without touching the image's own
# directories (the baked custom_nodes stay intact; no rm -rf + symlink dance).
set -euo pipefail

DATA="${COMFY_DATA_DIR:-/workspace}"
mkdir -p "$DATA"/{models,input,output,user,temp,custom_nodes}

args=(
  --listen 0.0.0.0
  --port "${COMFY_PORT:-8188}"
  --disable-auto-launch
  --models-directory "$DATA/models"
  --input-directory "$DATA/input"
  --output-directory "$DATA/output"
  --user-directory "$DATA/user"
  --temp-directory "$DATA/temp"
)

# Nodes living on the volume are opt-in: their pip deps are NOT in this image,
# so loading them silently breaks reproducibility. Bake them via nodes.lock.yaml.
if [[ "${COMFY_ALLOW_VOLUME_NODES:-0}" == "1" ]]; then
  cat > /tmp/extra_model_paths.yaml <<YAML
volume:
  base_path: $DATA
  custom_nodes: custom_nodes/
YAML
  args+=(--extra-model-paths-config /tmp/extra_model_paths.yaml)
  echo "[start] WARNING: loading custom nodes from $DATA/custom_nodes (not reproducible)"
fi

[[ "${COMFY_ENABLE_MANAGER:-0}" == "1" ]] && args+=(--enable-manager)

echo "[start] ComfyUI $(grep -m1 -oE '[0-9]+\.[0-9]+\.[0-9]+' "$COMFY_HOME/comfyui_version.py" 2>/dev/null || echo '?') data=$DATA"
# COMFY_EXTRA_ARGS e.g. "--lowvram" on the 8 GB box, "--highvram" on a 48 GB pod.
# shellcheck disable=SC2086
exec python "$COMFY_HOME/main.py" "${args[@]}" ${COMFY_EXTRA_ARGS:-} "$@"
