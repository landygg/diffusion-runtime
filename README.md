# diffusion-runtime

**Unofficial Docker runtime for [ComfyUI](https://github.com/Comfy-Org/ComfyUI).** No afiliado ni respaldado por Comfy Org ni NVIDIA; "ComfyUI" es marca de Comfy Org, Inc.

Imagen Docker de ComfyUI (sin modelos) que se reconstruye sola cuando sale una
nueva versión de ComfyUI o cambia la receta. Pensada para RunPod y para GPUs
locales con NVIDIA Container Toolkit. Análisis completo y decisiones: [docs/ANALYSIS.md](docs/ANALYSIS.md).

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

| Variable | Default | Efecto |
|---|---|---|
| `COMFY_DATA_DIR` | `/workspace` | Raíz del volumen |
| `COMFY_PORT` | `8188` | Puerto |
| `COMFY_EXTRA_ARGS` | — | Flags extra (`--lowvram`, `--highvram`, …) |
| `COMFY_ENABLE_MANAGER` | `0` | `1` añade `--enable-manager` |
| `COMFY_ALLOW_VOLUME_NODES` | `0` | `1` carga también `custom_nodes/` del volumen (no reproducible) |

## Archivos de política (todo se define en el repo)

| Archivo | Qué controla | Quién lo aplica |
|---|---|---|
| `nodes.lock.yaml` | Custom nodes, fijados por SHA | build (`install_nodes.py`) |
| `required_nodes.txt` | Nodos que necesitan los workflows consumidores; el build falla si falta uno | smoke test (`smoke.py`) |
| `variants.json` | Variantes CUDA / torch / Python | build (matriz) |
| `renovate.json` | Qué dependencias se actualizan solas y cómo | Renovate (PRs semanales) |
| `retention.json` | Cuántas imágenes conservar en GHCR | workflow `retention` (semanal) |

## Añadir / actualizar un nodo

Añade una entrada a `nodes.lock.yaml` (`repo`, `ref: main`, `commit` = `git ls-remote <repo> HEAD`) y su `class_type` a `required_nodes.txt`. Push a `main` → cambia el hash → build nuevo. A partir de ahí Renovate propone los bumps de SHA.

## Build y smoke test local (Mac)

Con la app `container` de Apple (o Docker, mismos flags):

```bash
container builder start --cpus 8 --memory 16g
container build --platform linux/amd64 -t runtime:dev .
container run --rm --platform linux/amd64 --entrypoint python runtime:dev /opt/comfy/smoke.py
```

El smoke arranca ComfyUI en CPU, verifica `torch`, `comfyui_manager`, que ningún nodo dé `IMPORT FAILED` y que `/object_info` tenga todo lo de `required_nodes.txt`.

## Licencia

MIT para este repositorio. Las imágenes agregan software de terceros con sus propias licencias (ComfyUI GPL-3.0, NVIDIA EULA…): ver [licenses/NOTICE.md](licenses/NOTICE.md) y análisis §12. Para contribuir: [CONTRIBUTING.md](CONTRIBUTING.md).

## Puesta en marcha del repo

1. Crear el repo público y hacer el push inicial (antes de los rulesets).
2. Tras el primer build, en *Packages → diffusion-runtime → Package settings → Change visibility* ponerlo público (o dar un PAT `read:packages` a RunPod).
3. `scripts/apply_repo_settings.sh landygg/diffusion-runtime` (protección de `main`, permisos de Actions; ver análisis §11).
4. Instalar la [GitHub App de Renovate](https://github.com/apps/renovate) en el repo (gratis).
5. Lanzar `build` manualmente una vez; validar en GPU; ejecutar `promote` con el tag inmutable.
6. Lanzar `retention` en dry run para revisar qué borraría.
