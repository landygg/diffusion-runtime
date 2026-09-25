# Contribuir

Las contribuciones son bienvenidas: nuevos custom nodes, variantes CUDA, mejoras del smoke test, documentación.

## Flujo

1. Haz fork y abre un PR contra `main`. Nadie (tampoco el mantenedor) hace push directo a `main`.
2. El workflow `pr` compila la imagen y ejecuta el smoke test. En PRs desde forks, un mantenedor debe aprobar la ejecución la primera vez (evita abuso de los runners).
3. Hace falta **1 revisión aprobada del code owner** y el check `smoke` en verde. Se mergea con squash.

## Reglas de la receta

- **Custom nodes**: entrada en `nodes.lock.yaml` con `repo`, `ref` y el **SHA completo** (nunca una rama), y sus `class_type` en `required_nodes.txt`. Explica en el PR qué workflow lo necesita.
- **Nada de modelos, LoRAs ni datos** dentro de la imagen.
- **No cambies la versión de torch** sin justificarlo: puede cambiar resultados para una seed fija.
- Actions fijadas por SHA; permisos mínimos por job; nunca `pull_request_target`.
- Verifica en local antes del PR (Docker o Apple `container`), ver README.

## Licencia de las contribuciones

Al contribuir aceptas que tu aporte se publique bajo la licencia MIT de este repositorio (inbound = outbound). No añadas código de terceros con licencias incompatibles ni con marcas de otros en nombres de archivos o imágenes.
