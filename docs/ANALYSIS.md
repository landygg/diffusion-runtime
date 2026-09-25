# Análisis: imagen ComfyUI continua (GitHub Actions vs AWS ECR)

Fecha: 2026-09-25 · Datos verificados contra upstream ese día.

## 1. Hechos que condicionan el diseño

| Hecho | Dato | Consecuencia |
|---|---|---|
| Repo oficial | `Comfy-Org/ComfyUI` (el `comfyanonymous/ComfyUI` del borrador redirige) | Clonar desde Comfy-Org |
| Cadencia | ~1 release/semana (v0.27 → v0.37 entre jun y sep 2026) + tags de parche (v0.37.1, v0.37.2) que **no** siempre tienen GitHub Release | Detectar por **tags `vX.Y.Z`**, no por "Releases" |
| `requirements.txt` | Lista `torch` **sin versión**, más `comfyui-frontend-package`, `comfy-kitchen`, etc. fijados con `==` | Un `pip install -r` puede reemplazar el torch de la imagen base → usar **constraints** |
| Manager | Ya viene integrado: `manager_requirements.txt` (`comfyui_manager==4.2.2`) + flag `--enable-manager` | No hace falta clonar ComfyUI-Manager aparte |
| Flags de directorios | `--models-directory`, `--input-directory`, `--output-directory`, `--user-directory`, `--base-directory`, `--extra-model-paths-config` (soporta `custom_nodes:`) | El `rm -rf` + symlink del borrador sobra |
| Smoke test sin GPU | `--quick-test-for-ci` carga todo (incluidos custom nodes) y hace `exit(0)`; los fallos se loguean como `IMPORT FAILED` | Se puede validar en runners sin GPU |
| torch | cu128 llega hasta 2.11.0; cu130/cu132 tienen 2.14.0 (último) | Dos variantes: `cu130` (driver ≥580) y `cu128` (compat) |
| `runpod/pytorch` devel | 15–16 GB **comprimidos** | No cabe cómodo en un runner hospedado y es innecesario |

## 2. Problemas del borrador original

1. **`ln -s " $GLOBAL_DIR/..." "$ COMFY_DIR/..."`** — los espacios dentro de las comillas rompen las rutas; el script no arranca.
2. **`rm -rf custom_nodes` y luego symlink al volumen** — borra los nodos que acabas de hornear en la imagen. Contradice "los nodos de la imagen están disponibles inmediatamente".
3. **Nodos instalados en runtime al volumen** — sus dependencias pip se instalan en el contenedor (efímero). Al recrear el pod el nodo existe pero sus deps no → roturas intermitentes. Para un pipeline que exige reproducibilidad esto es inaceptable: **todos los nodos van horneados y fijados por commit**.
4. **`git clone` sin versión** — "la última de master" no es reproducible. Hay que fijar tag de ComfyUI y SHA de cada nodo.
5. **Imagen base `-devel` de 16 GB** — los wheels de torch ya traen el runtime CUDA (`nvidia-*`); el host solo necesita driver + NVIDIA Container Toolkit. `python:3.12-slim` + torch deja la imagen en ~6–8 GB. Solo usar `-devel` si un nodo compila CUDA (p. ej. SageAttention), y entonces en multi-stage.
6. **Solo `latest` / tag por mes** — no permite saber qué ComfyUI + qué nodos hay dentro. Ver §4.

## 3. GitHub Actions vs AWS ECR — no son alternativas

Son capas distintas:

- **Build (CI):** GitHub Actions · AWS CodeBuild
- **Registry:** GHCR (GitHub Container Registry) · Docker Hub · Amazon ECR (privado o Public)

La pregunta real es *dónde construir* y *dónde almacenar*, y quién la consume: **RunPod** (y opcionalmente una GPU local).

### 3.1 Build

| | GitHub Actions (hospedado) | AWS CodeBuild |
|---|---|---|
| Coste | Repo público: gratis. Privado: 2 000 min/mes gratis; un build ~20–40 min → ~50 builds/mes | ~$0.005–0.01/min (general1.medium/large) + tráfico; poco, pero no es cero |
| Disco | ~14 GB libres; ~30 GB+ tras limpiar (hecho en el workflow) | Configurable (hasta 128 GB+) |
| Trigger por release upstream | `schedule` cron + `git ls-remote` (trivial) | EventBridge Scheduler + Lambda/CodeBuild (más piezas) |
| Integración con el repo | Nativa | Requiere conexión CodeStar/GitHub |
| Mantenimiento | Un YAML | IAM roles, proyecto CodeBuild, EventBridge, logs en CloudWatch |

**Ganador: GitHub Actions.** Si algún día el disco no alcanza (nodos muy pesados), el salto es a un runner más grande de GitHub (de pago) o self-hosted, no a CodeBuild.

### 3.2 Registry — aquí está la diferencia importante

| | GHCR | Docker Hub | ECR privado | ECR Public |
|---|---|---|---|---|
| Almacenamiento | Gratis para imágenes públicas | Gratis público, límites en privado | ~$0.10/GB-mes | 50 GB gratis |
| **Egress hacia RunPod** | Gratis (público) | Gratis con límites de pulls anónimos | **~$0.09/GB** → una imagen de ~6 GB ≈ **$0.50 por cada pod que arranca** | Gratis para pulls anónimos (con límites) |
| Auth desde RunPod | Público: ninguna. Privado: usuario + PAT (**estático**) en "Container Registry Auth" | Usuario + token estático | **Token de 12 h** (`get-login-password`) → hay que rotarlo con una Lambda que actualice la credencial en RunPod vía API | Ninguna |
| Integración con GHA | `GITHUB_TOKEN`, cero secretos | Secreto extra | OIDC + rol IAM | OIDC + rol IAM |

**ECR privado es la peor opción para este caso**: cada arranque de pod paga egress y la credencial caduca cada 12 h, lo que exige infraestructura extra justo para lo que debía ser "sin esfuerzo manual". ECR solo tiene sentido si la GPU corriera **dentro de AWS** (misma región → sin egress, auth por rol IAM).

### 3.3 Recomendación

**GitHub Actions + GHCR, imagen pública** (el repo puede ser privado, ver §11). La imagen solo contiene software open-source (ComfyUI, torch, nodos); los modelos, LoRAs, bible y outputs viven en el volumen. No hay nada que proteger y se elimina la gestión de credenciales. Si se quiere privada: GHCR privado + PAT fine-grained con `read:packages` en RunPod.

## 4. Estrategia de versiones (lo que hace que "continuo" sea seguro)

"Si mañana sale otra versión que se genere automáticamente" — sí, pero **generar ≠ adoptar**. Un pipeline de producción necesita reproducibilidad; un cambio de ComfyUI o de un nodo puede cambiar el resultado de un seed.

```
0.37.2-cu130-r1a2b3c4d   inmutable: ComfyUI + variante + hash de la receta (Dockerfile, nodos, scripts)
0.37.2-cu130 / 0.37.2    móvil: última receta para esa versión de ComfyUI
latest-cu130 / latest    móvil, automático: lo último que pasó el smoke test
stable-cu130 / stable    móvil, MANUAL: promovido tras validar en GPU real (workflow `promote`)
```

- El hash de receta hace que cambiar `nodes.lock.yaml` genere una imagen nueva aunque ComfyUI no cambie.
- Si el tag inmutable ya existe, el workflow no hace nada (idempotente; el cron cada 6 h cuesta segundos).
- Las imágenes se publican primero como `candidate-*` y solo reciben tags reales si pasan el smoke test.
- **El pipeline consumidor debe fijar por digest** (`ghcr.io/landygg/diffusion-runtime@sha256:...`), y el `comfyui_version` que devuelve `/system_stats` entra en la procedencia de cada artefacto. Así "episodio 002" se regenera con exactamente el mismo stack.

## 5. Pipeline resultante

```
cron 6h / push receta / manual
        │
   resolve ── git ls-remote Comfy-Org/ComfyUI → último vX.Y.Z
        │     por cada variante: tag = ver-variant-rHASH ; ¿existe en GHCR? → skip
        ▼
   build (matrix cu130, cu128)
        │  liberar disco → buildx (cache en GHCR) → push candidate-*
        │  smoke: main.py --cpu --quick-test-for-ci, falla si "IMPORT FAILED"
        │  imagetools create → tags inmutable + móviles (sin re-subir capas)
        ▼
   GHCR ──► RunPod template (tag stable o digest) + Network Volume en /workspace
        └─► GPU local (docker + NVIDIA toolkit, COMFY_EXTRA_ARGS=--lowvram en 8 GB)
```

## 6. Volumen (RunPod)

- Montar en `/workspace` (default de RunPod) o fijar `COMFY_DATA_DIR`.
- Layout: `models/ input/ output/ user/ temp/ custom_nodes/`.
- **Network Volume** mejor que Global Volume si se escribe mucho (outputs, `user/` con la DB de ComfyUI); RunPod advierte que el Global Volume no garantiza locking ni renames atómicos.
- `custom_nodes/` del volumen solo se carga con `COMFY_ALLOW_VOLUME_NODES=1` (escape para experimentar; lo que se quede, pasa a `nodes.lock.yaml`).

## 7. Riesgos abiertos

| Riesgo | Mitigación |
|---|---|
| El smoke CPU no detecta fallos solo-GPU (OOM, kernels) | Promoción a `stable` manual tras un render de referencia en GPU; a futuro, job opcional en un pod RunPod efímero vía API |
| Un nodo rompe con un ComfyUI nuevo | `latest` falla el build → queda el anterior; alerta vía notificación de fallo de GitHub |
| Driver del host < 580 (cu130) | Variante `cu128` |
| Bumps de SHA de nodos / torch / uv a mano | Renovate (§8) |
| Crecimiento de GHCR | `retention.json` + workflow `retention` (§9) |

## 8. Renovate: qué es y por qué

El workflow `build` solo vigila **ComfyUI**. Todo lo demás está fijado a mano y envejece: el SHA de cada custom node, la versión de torch por variante, `uv`, las GitHub Actions. Renovate es un bot (GitHub App gratuita) que lee `renovate.json`, detecta esas versiones fijadas y abre **PRs** cuando hay versiones nuevas. Al mergear el PR cambia el hash de la receta → `build` genera la imagen nueva.

- **Nodos**: sigue `ref` (rama) de cada entrada en `nodes.lock.yaml` y propone el nuevo `commit`, agrupado en un PR semanal.
- **torch**: consulta el índice de wheels **de cada variante** (`download.pytorch.org/whl/cu130`, `.../cu128`), así `cu128` no propone versiones que PyTorch ya no publica para esa CUDA. Nunca automerge (puede cambiar resultados por seed).
- **uv / GitHub Actions**: automerge de minor/patch si el CI pasa.
- **Python**: se queda en 3.12.

Por qué PRs y no actualización ciega: un nodo nuevo puede romper o cambiar outputs; el PR deja rastro, pasa el smoke test y se puede revertir.

## 9. Retención en GHCR

GHCR no tiene lifecycle policies (ECR sí). La política vive en `retention.json` y la aplica el workflow `retention` (domingo, semanal; manual = dry run por defecto) vía la API de GitHub Packages con el `GITHUB_TOKEN`.

En GHCR una *versión* es un digest con 0..n tags; borrarla borra todos sus tags. Por eso se decide por versión:

| Caso | Acción |
|---|---|
| Tiene `latest*`, `stable*`, `keep-*` o `buildcache-*` | Conservar |
| Sin tags > 7 días (caché vieja, tags movidos) | Borrar |
| Solo `candidate-*` > 2 días (falló el smoke) | Borrar |
| Tag inmutable `<ver>-<variant>-r<hash>` | Conservar las 5 más recientes por variante |
| Otro | Conservar |

Si el pipeline consumidor fija un digest que debe sobrevivir a la retención, promoverlo con canal `keep-<nombre>` (workflow `promote`).

## 10. Build local con Apple `container`

`container` 1.4.1 construye con BuildKit y ejecuta amd64 vía Rosetta, así que el mismo Dockerfile se valida en el Mac. Una diferencia encontrada: rechaza un `.dockerignore` de tipo `*` + `!excepciones` (`changes out of order`); se usa una lista de exclusiones explícita, compatible con ambos.

## 11. Visibilidad, colaboración y protección

**Decisión (2026-09-25):** repo público `landygg/diffusion-runtime` + imagen pública `ghcr.io/landygg/diffusion-runtime`, con colaboración abierta.

### Rulesets (`.github/rulesets/`, aplicados con `scripts/apply_repo_settings.sh`)

| Ruleset | Reglas | Bypass |
|---|---|---|
| `main: integrity` | No borrar `main`, no force-push | Nadie |
| `main: checks` | Check `smoke` (workflow `pr`) obligatorio y al día con `main`; historial lineal | Nadie |
| `main: review` | Todo por PR; 1 aprobación del code owner (`CODEOWNERS` → @landygg); se invalida si hay push nuevo; el último push lo debe aprobar otra persona; hilos resueltos; solo squash | Admin y app Renovate (id 2740), **solo desde un PR** |

El bypass de `review` existe porque nadie puede aprobar sus propios PRs: el mantenedor y Renovate pueden mergear sin aprobación, pero **nunca sin `smoke` verde** (el ruleset `checks` no tiene bypass). Un colaborador con permiso de escritura no puede mergear sin la revisión del code owner.

### Resto de ajustes del script
- `GITHUB_TOKEN` solo lectura por defecto y sin poder aprobar PRs; solo Actions de GitHub y `docker/*`.
- Los workflows de PRs de forks necesitan aprobación para cualquier contribuidor externo (evita minería en los runners).
- Secret scanning + push protection, reporte privado de vulnerabilidades, alertas de Dependabot.
- Merge solo squash, auto-merge activado, ramas borradas tras el merge, sin wiki.

**Por qué un PR de un fork no puede publicar una imagen:** `pull_request` desde un fork recibe un token de solo lectura y ningún secreto; solo `build.yml` publica, y únicamente tras un push a `main`, que exige PR + `smoke` + revisión.

## 12. Revisión legal (2026-09-25, no es asesoría jurídica)

| Tema | Resultado | Cómo se cumple |
|---|---|---|
| ComfyUI, frontend, Manager, aimdo, embedded-docs: GPL-3.0 | Se puede redistribuir en una imagen, también comercialmente | Texto de la licencia + "Corresponding Source" localizable: `licenses/NOTICE.md` en la imagen, `THIRD_PARTY_LICENSES.txt` (115 paquetes, texto completo), versiones exactas en etiquetas y `pip-freeze.txt` |
| PyGithub (LGPL), ffmpeg de Debian (GPL/LGPL) | Igual | Fuente incluido (Python) o vía `apt-get source` / snapshot.debian.org, indicado en el NOTICE |
| NVIDIA CUDA/cuDNN (EULA propietario) | Redistribuible: binarios sin modificar, accedidos solo vía PyTorch dentro de una aplicación con funcionalidad propia; la agregación con GPL no somete el SDK a la GPL (ComfyUI no enlaza CUDA) | Aviso en el NOTICE; licencias de NVIDIA intactas en cada `dist-info`; sin insinuar respaldo de NVIDIA |
| Marca "ComfyUI" | Las [directrices de Comfy Org](https://comfy.org/brand) prohíben usar "Comfy" en el nombre de un producto o proyecto | Nombre `diffusion-runtime`; "ComfyUI" solo como descripción ("Unofficial Docker runtime for ComfyUI"); aviso de no afiliación en README, NOTICE y etiqueta OCI |
| Modelos (Wan 2.2, Z-Image…) | No aplica: nunca van en la imagen | — |
| Licencia del repo | MIT, contribuciones inbound = outbound | `LICENSE`, `CONTRIBUTING.md` |

Riesgo residual: si un upstream GPL retirara su código, la obligación de proveer el fuente sigue siendo del distribuidor; el NOTICE se compromete a entregar una copia si alguien la pide. Mejora futura: adjuntar un bundle de fuentes GPL por versión como asset de un release.
