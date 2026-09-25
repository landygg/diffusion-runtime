#!/usr/bin/env bash
# Point ComfyUI at the persistent volume without touching the image's own
# directories (the baked custom_nodes stay intact; no rm -rf + symlink dance).
#
# RunPod-aware (detected via RUNPOD_POD_ID):
#   - CORS limited to the pod's proxy origin, so API/websocket calls coming
#     through the proxy are not rejected by ComfyUI's host/origin check (403).
#   - The container stays alive if ComfyUI crashes, so it can be debugged.
#   - Models from models.lock.yaml are synced to the volume in the background.
set -euo pipefail

DATA="${COMFY_DATA_DIR:-/workspace}"
PORT="${COMFY_PORT:-8188}"
ARGS_FILE="$DATA/comfyui_args.txt"
mkdir -p "$DATA"/{models,input,output,user,temp,custom_nodes}

log() { echo "[start] $*"; }

# --- sshd (only when PUBLIC_KEY is set) --------------------------------------
# Key-only root login. Host keys are persisted on the volume so the fingerprint
# survives pod restarts instead of triggering "host key changed" warnings, but
# sshd reads them from a local copy: RunPod volumes can refuse chmod, and sshd
# rejects private host keys that aren't 0600.
start_sshd() {
  # RunPod passes the literal string "null" when the account has no SSH key.
  [[ -n "${PUBLIC_KEY:-}" && "$PUBLIC_KEY" != "null" ]] || return 0
  local store="$DATA/.ssh-host-keys" keys=/etc/ssh/runtime-host-keys
  mkdir -p "$keys" /root/.ssh /run/sshd
  chmod 700 "$keys" /root/.ssh
  mkdir -p "$store" 2>/dev/null || true
  for type in ed25519 rsa; do
    local key="ssh_host_${type}_key"
    if [[ -f "$store/$key" && -f "$store/$key.pub" ]]; then
      cp "$store/$key" "$store/$key.pub" "$keys/"
    else
      ssh-keygen -q -t "$type" -N "" -f "$keys/$key"
      cp "$keys/$key" "$keys/$key.pub" "$store/" 2>/dev/null \
        || log "WARNING: could not persist SSH host keys to $store"
    fi
    chmod 600 "$keys/$key"
  done
  cat > /etc/ssh/sshd_config.d/runtime.conf <<CONF
HostKey $keys/ssh_host_ed25519_key
HostKey $keys/ssh_host_rsa_key
PermitRootLogin prohibit-password
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitUserEnvironment yes
CONF
  printf '%s\n' "$PUBLIC_KEY" > /root/.ssh/authorized_keys
  # SSH sessions (interactive or `ssh host cmd`) don't inherit the container
  # env; sshd applies ~/.ssh/environment to every session.
  printenv | grep -E '^(PATH|VIRTUAL_ENV|COMFY_|RUNPOD_|NVIDIA_|HF_)' > /root/.ssh/environment
  chmod 600 /root/.ssh/authorized_keys /root/.ssh/environment
  if /usr/sbin/sshd; then log "sshd started (key auth only)"; else log "WARNING: sshd failed to start"; fi
}

# --- ComfyUI arguments --------------------------------------------------------
args=(
  --listen 0.0.0.0
  --port "$PORT"
  --disable-auto-launch
  --models-directory "$DATA/models"
  --input-directory "$DATA/input"
  --output-directory "$DATA/output"
  --user-directory "$DATA/user"
  --temp-directory "$DATA/temp"
)

# COMFY_CORS_ORIGIN: explicit origin, "*" for any, or "off". Default: the pod's
# RunPod proxy origin when running on RunPod, otherwise off.
cors="${COMFY_CORS_ORIGIN:-}"
if [[ -z "$cors" && -n "${RUNPOD_POD_ID:-}" ]]; then
  cors="https://${RUNPOD_POD_ID}-${PORT}.proxy.runpod.net"
fi
if [[ -n "$cors" && "$cors" != "off" ]]; then
  args+=(--enable-cors-header "$cors")
  log "CORS origin: $cors"
fi

# Nodes living on the volume are opt-in: their pip deps are NOT in this image,
# so loading them silently breaks reproducibility. Bake them via nodes.lock.yaml.
if [[ "${COMFY_ALLOW_VOLUME_NODES:-0}" == "1" ]]; then
  cat > /tmp/extra_model_paths.yaml <<YAML
volume:
  base_path: $DATA
  custom_nodes: custom_nodes/
YAML
  args+=(--extra-model-paths-config /tmp/extra_model_paths.yaml)
  log "WARNING: loading custom nodes from $DATA/custom_nodes (not reproducible)"
fi

[[ "${COMFY_ENABLE_MANAGER:-0}" == "1" ]] && args+=(--enable-manager)

# Extra flags, editable on the volume without redeploying: one or more per
# line, "#" starts a comment. COMFY_EXTRA_ARGS is appended after the file.
if [[ ! -f "$ARGS_FILE" ]]; then
  printf '%s\n' "# Extra ComfyUI arguments, e.g. --lowvram or --preview-method auto." \
    "# Read at every container start. Lines starting with # are ignored." > "$ARGS_FILE"
fi
while read -r word; do
  [[ -n "$word" ]] && args+=("$word")
done < <(grep -v '^[[:space:]]*#' "$ARGS_FILE" | tr -s '[:space:]' '\n')
# shellcheck disable=SC2206  # word splitting of COMFY_EXTRA_ARGS is intended
args+=(${COMFY_EXTRA_ARGS:-} "$@")

# SSH is a convenience: a failure here must never keep ComfyUI from starting.
start_sshd || log "WARNING: SSH setup failed; continuing without SSH"

# --- Models (models.lock.yaml -> $DATA/models) ---------------------------------
# COMFY_MODELS_SYNC: "background" (ComfyUI starts at once; press R in the UI once
# the downloads finish), "wait" (download before ComfyUI starts) or "off".
# Default: background on RunPod, off elsewhere. COMFY_MODELS_GROUPS narrows it
# (space/comma separated group names, default all).
models_sync="${COMFY_MODELS_SYNC:-$([[ -n "${RUNPOD_POD_ID:-}" ]] && echo background || echo off)}"
model_groups_env="${COMFY_MODELS_GROUPS:-}"
read -ra model_groups <<< "${model_groups_env//,/ }"
case "$models_sync" in
  background) log "syncing models in the background (COMFY_MODELS_SYNC=background)"
              sync-models "${model_groups[@]}" || log "model sync failed; retry with: sync-models" & ;;
  wait)       sync-models "${model_groups[@]}" || log "model sync failed; retry with: sync-models" ;;
  off)        ;;
  *)          log "WARNING: unknown COMFY_MODELS_SYNC=$models_sync (use background, wait or off)" ;;
esac

# --- Run ComfyUI --------------------------------------------------------------
log "ComfyUI $(grep -m1 -oE '[0-9]+\.[0-9]+\.[0-9]+' "$COMFY_HOME/comfyui_version.py" 2>/dev/null || echo '?') data=$DATA"
log "args: ${args[*]}"

python "$COMFY_HOME/main.py" "${args[@]}" &
comfy_pid=$!

# A stop/restart sends SIGTERM (tini forwards it here): stop ComfyUI and exit
# cleanly, and don't mistake it for a crash.
shutting_down=0
trap 'shutting_down=1; kill -TERM "$comfy_pid" 2>/dev/null || true; [[ -n "${sleep_pid:-}" ]] && kill "$sleep_pid" 2>/dev/null || true' TERM INT

exit_code=0
wait "$comfy_pid" || exit_code=$?
[[ "$shutting_down" == "1" ]] && { log "shutting down"; exit 0; }

# Keep the container alive after a crash so it can be debugged (default on
# RunPod, where an exiting container is restarted in a loop).
keepalive="${COMFY_KEEPALIVE_ON_CRASH:-$([[ -n "${RUNPOD_POD_ID:-}" ]] && echo 1 || echo 0)}"
if [[ "$keepalive" != "1" ]]; then
  exit "$exit_code"
fi
log "============================================================"
log " ComfyUI exited unexpectedly (exit code $exit_code). See the log above."
log " Container kept alive for debugging (web terminal or SSH). Restart with:"
log "   python $COMFY_HOME/main.py ${args[*]}"
log "============================================================"
sleep infinity &
sleep_pid=$!
wait "$sleep_pid" || true
exit 0
