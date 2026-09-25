# diffusion-runtime

[English](README.md)

**Unofficial Docker runtime for [ComfyUI](https://github.com/Comfy-Org/ComfyUI).** No afiliado ni respaldado por Comfy Org ni NVIDIA; "ComfyUI" es marca de Comfy Org, Inc.

Imagen Docker de ComfyUI (sin modelos) que se reconstruye sola cuando sale una
nueva versión de ComfyUI o cambia la receta. Pensada para RunPod y para GPUs
locales con NVIDIA Container Toolkit.

## Qué hay dentro / fuera

| Imagen | Volumen (`$COMFY_DATA_DIR`, default `/workspace`) |
|---|---|
| ComfyUI (tag fijo), torch + CUDA (wheels), ffmpeg, ComfyUI-Manager (`manager_requirements.txt`), custom nodes de `nodes.lock.yaml` (hoy vacío: Wan 2.2 y Z-Image son core) | `models/`, `input/`, `output/`, `user/` (workflows, settings), `temp/`, `custom_nodes/` (opt-in) |

## Tags

`<comfyui>-<variant>-r<hash>` inmutable · `<comfyui>` · `latest` (auto) · `stable` (manual, workflow **promote**).
Variantes en `variants.json`: `cu130` (torch 2.14, driver ≥580, default) y `cu128` (torch 2.11, compat).

## Uso

```bash
# RunPod: Container Image = ghcr.io/landygg/diffusion-runtime:stable, puerto 8188/http, Network Volume en /workspace
docker run --gpus all -p 8188:8188 -v "$PWD/data:/workspace" \
  -e COMFY_EXTRA_ARGS="--lowvram" ghcr.io/landygg/diffusion-runtime:stable
```

En pipelines reproducibles, fija la imagen por digest (`ghcr.io/landygg/diffusion-runtime@sha256:…`) y no por un tag móvil.

| Variable | Default | Efecto |
|---|---|---|
| `COMFY_DATA_DIR` | `/workspace` | Raíz del volumen |
| `COMFY_PORT` | `8188` | Puerto |
| `COMFY_EXTRA_ARGS` | — | Flags extra (`--lowvram`, `--highvram`, …) |
| `COMFY_ENABLE_MANAGER` | `0` | `1` añade `--enable-manager` |
| `COMFY_ALLOW_VOLUME_NODES` | `0` | `1` carga también `custom_nodes/` del volumen (no reproducible) |
| `COMFY_CORS_ORIGIN` | RunPod: `https://<pod>-<puerto>.proxy.runpod.net`; si no, desactivado | Valor de `--enable-cors-header` (`*` = cualquier origen, `off` = desactivado) |
| `COMFY_KEEPALIVE_ON_CRASH` | RunPod: `1`; si no, `0` | `1` mantiene vivo el contenedor si ComfyUI se cae, para depurar |
| `PUBLIC_KEY` | — | Arranca sshd con login de root solo por clave (las host keys persisten en `/workspace/.ssh-host-keys`) |

También puedes poner flags de ComfyUI en `/workspace/comfyui_args.txt` (se crea en el primer arranque y se lee en cada arranque), para cambiarlos sin redesplegar.

### Template de RunPod

| Ajuste | Valor |
|---|---|
| Container image | `ghcr.io/landygg/diffusion-runtime:stable` (o un digest) |
| Expose HTTP ports | `8188` |
| Expose TCP ports | `22` (solo si usas `PUBLIC_KEY`) |
| Volume mount path | `/workspace` (recomendado Network Volume) |
| Environment | `PUBLIC_KEY` (opcional); `COMFY_EXTRA_ARGS` (opcional) |

Detrás del proxy de RunPod, ComfyUI rechaza con 403 las llamadas a la API y al websocket si CORS no está activado (el host y el origen del proxy no coinciden). La imagen lo activa automáticamente para el origen del proxy del propio pod.

## Archivos de política (todo se define en el repo)

| Archivo | Qué controla | Quién lo aplica |
|---|---|---|
| `nodes.lock.yaml` | Custom nodes, fijados por SHA | build (`install_nodes.py`) |
| `required_nodes.txt` | Nodos que necesitan los workflows consumidores; el build falla si falta uno | smoke test (`smoke.py`) |
| `variants.json` | Variantes CUDA / torch / Python | build (matriz) |
| `renovate.json` | Qué dependencias se actualizan solas y cómo | Renovate (PRs semanales) |
| `retention.json` | Cuántas imágenes conservar en GHCR | workflow `retention` (semanal) |

## Añadir / actualizar un nodo

Añade una entrada a `nodes.lock.yaml` (`repo`, `ref: main`, `commit` = `git ls-remote <repo> HEAD`) y su `class_type` a `required_nodes.txt`. Abre un PR; al mergearlo cambia el hash de la receta y se genera una imagen nueva. A partir de ahí Renovate propone los bumps de SHA. Ver [CONTRIBUTING.md](CONTRIBUTING.md) (en inglés).

## Build y smoke test local (Mac)

Con la app `container` de Apple (o Docker, mismos flags):

```bash
container builder start --cpus 8 --memory 16g
container build --platform linux/amd64 -t runtime:dev .
container run --rm --platform linux/amd64 --memory 8g --entrypoint python runtime:dev /opt/comfy/smoke.py
```

El smoke arranca ComfyUI en CPU, verifica `torch`, `comfyui_manager`, que ningún nodo dé `IMPORT FAILED` y que `/object_info` tenga todo lo de `required_nodes.txt`.

## Licencia

MIT para este repositorio. Las imágenes agregan software de terceros con sus propias licencias (ComfyUI GPL-3.0, NVIDIA EULA…): ver [licenses/NOTICE.md](licenses/NOTICE.md).

## Puesta en marcha (mantenedor)

1. Tras el primer build: *Packages → diffusion-runtime → Package settings → Change visibility* → público (GitHub no ofrece API para esto).
2. Instala la [GitHub App de Renovate](https://github.com/apps/renovate) y añádela como excepción (solo vía PR) en el ruleset `main: review`. La protección de ramas y los ajustes de Actions los gestiona el mantenedor fuera de este repo.
3. Valida cada imagen nueva en una GPU real y lanza el workflow `promote` con su tag inmutable para mover `stable`.
4. Lanza el workflow `retention` en dry run para revisar qué borraría.
