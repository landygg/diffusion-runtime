# diffusion-runtime

[![stable](https://img.shields.io/github/v/release/landygg/diffusion-runtime?label=stable&sort=date)](https://github.com/landygg/diffusion-runtime/releases/latest)
[![build](https://github.com/landygg/diffusion-runtime/actions/workflows/build.yml/badge.svg)](https://github.com/landygg/diffusion-runtime/actions/workflows/build.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Image on GHCR](https://img.shields.io/badge/ghcr.io-diffusion--runtime-2496ED?logo=docker&logoColor=white)](https://github.com/landygg/diffusion-runtime/pkgs/container/diffusion-runtime)

[English](README.md) · **Español**

**Una imagen Docker no oficial de ComfyUI para RunPod y GPUs NVIDIA locales.** Se reconstruye sola con cada versión de ComfyUI, y el tag `stable` solo avanza cuando una imagen se ha comprobado en una GPU real. Los custom nodes y los modelos están fijados en el repo, y la imagen no incluye pesos de modelos.

> Sin afiliación ni respaldo de Comfy Org ni de NVIDIA. "ComfyUI" es una marca de Comfy Org, Inc.; ver [licenses/NOTICE.md](licenses/NOTICE.md).

```
ghcr.io/landygg/diffusion-runtime:stable
```

## Inicio rápido

**RunPod.** Crea un template de pod con estos ajustes:

| Ajuste | Valor |
|---|---|
| Container image | `ghcr.io/landygg/diffusion-runtime:stable` (o un digest, ver [Tags](#tags)) |
| Expose HTTP ports | `8188` |
| Expose TCP ports | `22` (solo si usas SSH) |
| Volume mount path | `/workspace` |
| Environment (opcional) | `COMFY_MODELS_GROUPS`, `HF_TOKEN`, `COMFY_EXTRA_ARGS` |

Abre *Connect → HTTP 8188*. En el primer arranque, los modelos de [`models.lock.yaml`](models.lock.yaml) se descargan al volumen en segundo plano; pulsa **R** en ComfyUI cuando el log muestre `[models] ... ready`.

**GPU local** (driver NVIDIA + [Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)):

```bash
docker run --gpus all -p 8188:8188 -v "$PWD/data:/workspace" \
  -e COMFY_MODELS_SYNC=background ghcr.io/landygg/diffusion-runtime:stable
```

Luego abre http://localhost:8188. En GPUs pequeñas añade `-e COMFY_EXTRA_ARGS="--lowvram"`.

## Características

- **Sigue las versiones de ComfyUI.** Un tag nuevo upstream dispara un build en unas 6 horas como máximo. Cada imagen pasa un smoke test en CPU antes de publicarse.
- **Un canal `stable` comprobado en GPU.** `latest` avanza solo; `stable` solo avanza cuando el mantenedor promueve una imagen tras un render real en GPU.
- **Todo fijado.** El tag de ComfyUI, los wheels de torch/CUDA, los custom nodes (por commit) y los modelos (por commit de Hugging Face + sha256) se definen en este repo.
- **Modelos en el volumen, no en la imagen.** `sync-models` descarga el conjunto fijado; `get-model` añade cualquier modelo de Hugging Face desde una shell del pod.
- **Hecha para RunPod.** CORS configurado para el proxy del pod (la API y el websocket funcionan a través de él), SSH solo con clave, el contenedor sigue vivo si ComfyUI se cae, y los flags de ComfyUI se cambian sin redesplegar.
- **Licencias incluidas.** Cada imagen lleva su inventario de licencias de terceros y las versiones exactas de los paquetes.

## Qué hay dentro

| En la imagen | En el volumen (`$COMFY_DATA_DIR`, por defecto `/workspace`) |
|---|---|
| ComfyUI (tag fijo), wheels de torch + CUDA, ffmpeg, ComfyUI-Manager, custom nodes de `nodes.lock.yaml`, las herramientas `get-model` / `sync-models` y el CLI `hf`, un compilador de C para Triton | `models/`, `input/`, `output/`, `user/` (workflows, ajustes), `temp/`, `custom_nodes/` (opcional), caché y token de Hugging Face |

Los workflows de Z-Image Turbo y Wan 2.2 TI2V 5B solo usan nodos core, así que `nodes.lock.yaml` está vacío por ahora.

## Tags

| Tag | Cuándo cambia | Para qué usarlo |
|---|---|---|
| `stable`, `stable-<variante>` | A mano (workflow `promote`), tras un render en GPU | Templates de pod y el trabajo diario |
| `latest`, `<comfyui>` (p. ej. `0.37.3`) | Solo, en cada build | Probar pronto una versión nueva de ComfyUI |
| `<comfyui>-<variante>-r<hash>` (p. ej. `0.37.3-cu130-r82550d79`) | Nunca (inmutable) | Pipelines reproducibles; se conservan las 5 más recientes por variante |
| `keep-<nombre>` | A mano | Una imagen que conservar para siempre (p. ej. el stack exacto con el que se produjo un episodio) |

Para ejecuciones totalmente reproducibles, fija por digest: `ghcr.io/landygg/diffusion-runtime@sha256:…`. La [última release](https://github.com/landygg/diffusion-runtime/releases/latest) es siempre el `stable` actual, con su digest. Desde una shell:

```bash
docker buildx imagetools inspect ghcr.io/landygg/diffusion-runtime:stable
```

| Variante | torch | Driver NVIDIA del host | |
|---|---|---|---|
| `cu130` | 2.14 | ≥ 580 | Por defecto (`stable`, `latest`) |
| `cu128` | 2.11 | 570–579 | Compatibilidad; sigue cubriendo Blackwell (sm_120) |

## Configuración

| Variable | Por defecto | Efecto |
|---|---|---|
| `COMFY_EXTRA_ARGS` | — | Flags extra de ComfyUI (`--lowvram`, `--highvram`, …) |
| `COMFY_MODELS_SYNC` | RunPod: `background`; si no, `off` | Descarga `models.lock.yaml` al arrancar: `background`, `wait` (antes de arrancar ComfyUI) u `off` |
| `COMFY_MODELS_GROUPS` | todos | Solo estos grupos de `models.lock.yaml` (p. ej. `z-image-turbo`) |
| `HF_TOKEN` | — | Token de Hugging Face, para modelos gated o privados |
| `PUBLIC_KEY` | — | Arranca sshd con login de root solo por clave (RunPod lo rellena con las claves SSH de tu cuenta) |
| `COMFY_ENABLE_MANAGER` | `0` | `1` añade `--enable-manager` |
| `COMFY_CORS_ORIGIN` | RunPod: el origen del proxy del pod; si no, desactivado | Valor de `--enable-cors-header` (`*` = cualquier origen, `off` = desactivado) |
| `COMFY_KEEPALIVE_ON_CRASH` | RunPod: `1`; si no, `0` | `1` mantiene vivo el contenedor si ComfyUI termina, para depurar |
| `COMFY_ALLOW_VOLUME_NODES` | `0` | `1` carga también `custom_nodes/` del volumen (no reproducible) |
| `COMFY_DATA_DIR` | `/workspace` | Raíz del volumen |
| `COMFY_PORT` | `8188` | Puerto |
| `HF_HOME` | `/workspace/.cache/huggingface` | Caché de Hugging Face y token de `hf auth login` |

Los flags de ComfyUI también pueden ir en `/workspace/comfyui_args.txt`. El archivo se crea en el primer arranque y se lee en cada arranque, así que los flags cambian con un reinicio en lugar de un redespliegue.

## Modelos

Los botones *Download* del panel "Missing Models" de ComfyUI guardan el archivo en tu **navegador**, no en el pod. Desde una shell del pod (terminal web o SSH), usa en su lugar:

```bash
get-model <ref> [carpeta]           # un modelo, al volumen
sync-models [grupo ...] [--verify]  # todo models.lock.yaml (--verify vuelve a calcular hashes)
```

- `<ref>` es el enlace de Hugging Face del modelo (el 🔗 del panel "Missing Models"), `org/repo[@revision]/ruta/al/archivo` o un nombre de archivo que ya esté en `models.lock.yaml`.
- `carpeta` es una carpeta de modelos de ComfyUI (`loras`, `vae`, `diffusion_models`, …), una subcarpeta como `loras/estilo` o una ruta absoluta. Se crea si no existe. Si se omite, se deduce de la ruta (`split_files/text_encoders/x.safetensors` → `text_encoders`).

```bash
get-model https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors
get-model some-org/some-lora/style.safetensors loras
```

Las descargas se reanudan si se cortan y solo corre una a la vez. Un archivo solo aparece en la carpeta de modelos cuando su tamaño y su sha256 coinciden. `get-model` termina imprimiendo una entrada de `models.lock.yaml` fijada al commit exacto: añádela al repo para tener ese modelo en cada pod nuevo. Para modelos gated, acepta la licencia en huggingface.co y define `HF_TOKEN` o ejecuta `hf auth login` una vez (el token queda en el volumen).

## Cómo se publican las versiones

1. **build** corre cada 6 horas y con cada cambio en la receta. Calcula un tag a partir de la versión de ComfyUI y un hash de los archivos de la receta, construye solo los tags que aún no existen, pasa el smoke test en CPU y publica el tag inmutable más `latest`.
2. **El mantenedor comprueba la imagen en una GPU**, porque una ejecución en CPU no detecta errores de memoria, problemas de driver o de kernels CUDA, ni un render que cambie.
3. **promote** apunta `stable` y `stable-<variante>` a esa imagen, sin reconstruir ni volver a subir nada, y publica una GitHub Release para ella (versiones de ComfyUI y torch, digest y PRs desde la release anterior). La release de la variante por defecto queda marcada como *Latest*:
   ```bash
   gh workflow run promote -R landygg/diffusion-runtime -f tag=0.37.3-cu130-r82550d79
   # o conservar una para siempre:
   gh workflow run promote -R landygg/diffusion-runtime -f tag=0.37.3-cu130-r82550d79 -f channel=keep-episode01
   ```
4. **retention** corre cada semana. Conserva las 5 imágenes inmutables más recientes por variante y nunca borra `latest*`, `stable*`, `keep-*` ni `buildcache-*`.

Si una imagen falla en la GPU, simplemente no se promueve y `stable` se queda donde estaba. Para volver atrás, promueve otra vez un tag inmutable anterior; su release vuelve a ser *Latest*.

## Desarrollo

Todo lo que contiene la imagen se define en estos archivos:

| Archivo | Qué controla | Quién lo aplica |
|---|---|---|
| `nodes.lock.yaml` | Custom nodes, fijados por commit | build (`install_nodes.py`) |
| `models.lock.yaml` | Modelos que se descargan al volumen, fijados por commit + sha256 | `sync-models`; se valida en el build y en el smoke test |
| `required_nodes.txt` | Tipos de nodo que necesitan los workflows | smoke test (`smoke.py`) |
| `variants.json` | Variantes de CUDA / torch / Python | build (matriz) |
| `renovate.json` | Qué dependencias se actualizan solas y cómo | Renovate (PRs semanales) |
| `retention.json` | Cuántas imágenes conservar en GHCR | workflow `retention` |

**Añadir un custom node:** añádelo a `nodes.lock.yaml` (`repo`, `ref: main`, `commit` = `git ls-remote <repo> HEAD`) y sus `class_type` a `required_nodes.txt`, y abre un PR. Renovate propone después los bumps de commit. **Añadir un modelo:** pega en `models.lock.yaml` la entrada que imprime `get-model`. Ver [CONTRIBUTING.md](CONTRIBUTING.md) (en inglés).

**Build y smoke test en local** en un Mac, con `container` de Apple (o Docker, mismos flags):

```bash
container builder start --cpus 8 --memory 16g
container build --platform linux/amd64 -t runtime:dev .
container run --rm --platform linux/amd64 --memory 8g --entrypoint python runtime:dev /opt/comfy/smoke.py
```

El smoke test arranca ComfyUI en CPU y comprueba que:
- `torch` y `comfyui_manager` se importan;
- ningún nodo reporta `IMPORT FAILED`;
- `/object_info` lista todos los tipos de nodo de `required_nodes.txt`;
- las herramientas de modelos funcionan y `models.lock.yaml` es válido;
- hay un compilador de C, que Triton necesita en la GPU.

## Licencia

Este repositorio es [MIT](LICENSE). Las imágenes incluyen software de terceros con sus propias licencias (ComfyUI GPL-3.0, NVIDIA SDK EULA, …); [licenses/NOTICE.md](licenses/NOTICE.md) las lista e indica dónde está el código fuente correspondiente.
