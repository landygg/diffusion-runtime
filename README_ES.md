# diffusion-runtime

[English](README.md)

**Unofficial Docker runtime for [ComfyUI](https://github.com/Comfy-Org/ComfyUI).** No afiliado ni respaldado por Comfy Org ni NVIDIA; "ComfyUI" es marca de Comfy Org, Inc.

Imagen Docker de ComfyUI (sin modelos) que se reconstruye sola cuando sale una
nueva versión de ComfyUI o cambia la receta. Pensada para RunPod y para GPUs
locales con NVIDIA Container Toolkit.

## Qué hay dentro / fuera

| Imagen | Volumen (`$COMFY_DATA_DIR`, default `/workspace`) |
|---|---|
| ComfyUI (tag fijo), torch + CUDA (wheels), ffmpeg, ComfyUI-Manager (`manager_requirements.txt`), custom nodes de `nodes.lock.yaml` (hoy vacío: Wan 2.2 y Z-Image son core), `get-model` / `sync-models` + la lista de modelos `models.lock.yaml` (sin pesos) | `models/` (lo descarga `sync-models`), `input/`, `output/`, `user/` (workflows, settings), `temp/`, `custom_nodes/` (opt-in) |

## Tags

`<comfyui>-<variant>-r<hash>` inmutable · `<comfyui>` · `latest` (auto) · `stable` (manual, workflow **promote**).
Variantes en `variants.json`: `cu130` (torch 2.14, driver ≥580, default) y `cu128` (torch 2.11, compat).

## Promover una imagen (`stable`) y conservar una (`keep-*`)

`build` publica cada imagen nueva automáticamente, pero `latest` solo garantiza que compila y pasa el smoke test **en CPU**. Los problemas que solo aparecen con GPU (falta de memoria, drivers, kernels de CUDA, un render que cambia) no se detectan ahí. Por eso los templates de producción deben usar **`stable`**, que solo avanza cuando el mantenedor promueve una imagen tras validarla en una GPU real:

1. Busca el tag inmutable de la imagen nueva (p. ej. `0.37.2-cu130-r1a2b3c4d`) en el resumen del run de `build` (*Pin by digest*).
2. Despliega ese tag exacto en RunPod (o en una GPU local) y haz una generación real.
3. Si funciona, lanza el workflow `promote` con ese tag. Apunta `stable` y `stable-<variante>` a esa misma imagen, sin recompilar ni volver a subir nada:
   ```bash
   gh workflow run promote -R landygg/diffusion-runtime -f tag=0.37.2-cu130-r1a2b3c4d
   ```
   O desde *Actions → promote → Run workflow*.

Si una imagen nueva falla en GPU, no la promuevas: `stable` sigue en la anterior. Para volver atrás, promueve otra vez un tag inmutable anterior. Hasta la primera promoción `stable` no existe; mientras tanto usa `latest` o un digest.

**Conservar una imagen:** el workflow `retention` conserva las 5 imágenes inmutables más recientes por variante y borra las anteriores. Para conservar una imagen concreta para siempre (p. ej. el stack exacto con el que se produjo un proyecto), promuévela a un canal llamado `keep-<nombre>` en lugar de `stable`:

```bash
gh workflow run promote -R landygg/diffusion-runtime -f tag=0.37.2-cu130-r1a2b3c4d -f channel=keep-episode01
```

Los tags que empiezan por `latest`, `stable`, `keep-` o `buildcache-` nunca se borran (`retention.json`).

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
| `COMFY_MODELS_SYNC` | RunPod: `background`; si no, `off` | Descarga `models.lock.yaml` al volumen al arrancar: `background`, `wait` (antes de arrancar ComfyUI) u `off` |
| `COMFY_MODELS_GROUPS` | todos | Solo estos grupos de `models.lock.yaml` (p. ej. `z-image-turbo`) |
| `HF_TOKEN` | — | Token de Hugging Face, para modelos gated o privados |
| `HF_HOME` | `/workspace/.cache/huggingface` | Caché de Hugging Face y token de `hf auth login`, en el volumen |

También puedes poner flags de ComfyUI en `/workspace/comfyui_args.txt` (se crea en el primer arranque y se lee en cada arranque), para cambiarlos sin redesplegar.

## Modelos

La imagen no trae pesos. `models.lock.yaml` lista los que necesitan los workflows de Z-Image Turbo y Wan 2.2 TI2V 5B, fijados por commit del repo y sha256, y en RunPod se descargan a `/workspace/models/<carpeta>/` en segundo plano en cada arranque (solo lo que falta; en los arranques siguientes solo se comprueban tamaños). ComfyUI arranca enseguida: pulsa **R** en la interfaz (o recarga) cuando el log muestre `[models] ... ready`.

Los botones *Download* del panel "Missing Models" de ComfyUI descargan en tu **navegador**, no en el pod. Desde una shell del pod usa en su lugar:

```bash
get-model <ref> [carpeta]           # un modelo, al volumen
sync-models [grupo ...] [--verify]  # todo models.lock.yaml (--verify vuelve a calcular hashes)
```

`<ref>` es el enlace de Hugging Face del modelo (el 🔗 del panel "Missing Models"), `org/repo[@revision]/ruta/al/archivo` o un nombre de archivo que ya esté en `models.lock.yaml`. `carpeta` es una carpeta de modelos de ComfyUI (`loras`, `vae`, `diffusion_models`, …; también una subcarpeta como `loras/estilo` o una ruta absoluta) y se crea si no existe. Si se omite, se deduce de la ruta (`split_files/text_encoders/x.safetensors` → `text_encoders`).

```bash
get-model https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors
get-model some-org/some-lora/style.safetensors loras
```

Las descargas se reanudan si se cortan, se verifican (tamaño + sha256) antes de aparecer en la carpeta de modelos y solo corre una a la vez. `get-model` termina imprimiendo una entrada de `models.lock.yaml` fijada al commit exacto: pégala en el repo para tener ese modelo en cada pod nuevo. Para modelos gated, acepta la licencia en huggingface.co y define `HF_TOKEN` (o ejecuta `hf auth login` una vez; el token queda en el volumen). También está disponible el CLI `hf`.

### Template de RunPod

| Ajuste | Valor |
|---|---|
| Container image | `ghcr.io/landygg/diffusion-runtime:stable` (o un digest) |
| Expose HTTP ports | `8188` |
| Expose TCP ports | `22` (solo si usas `PUBLIC_KEY`) |
| Volume mount path | `/workspace` (recomendado Network Volume) |
| Environment | `PUBLIC_KEY` (opcional); `COMFY_EXTRA_ARGS` (opcional); `COMFY_MODELS_GROUPS`, `HF_TOKEN` (opcional) |

Detrás del proxy de RunPod, ComfyUI rechaza con 403 las llamadas a la API y al websocket si CORS no está activado (el host y el origen del proxy no coinciden). La imagen lo activa automáticamente para el origen del proxy del propio pod.

## Archivos de política (todo se define en el repo)

| Archivo | Qué controla | Quién lo aplica |
|---|---|---|
| `nodes.lock.yaml` | Custom nodes, fijados por SHA | build (`install_nodes.py`) |
| `models.lock.yaml` | Modelos a descargar al volumen, fijados por commit + sha256 | `sync-models` (al arrancar y a mano); se valida en el build |
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
3. Valida cada imagen nueva en una GPU real y promuévela (ver *Promover una imagen*).
4. Lanza el workflow `retention` en dry run para revisar qué borraría.
