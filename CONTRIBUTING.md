# Contributing

Contributions are welcome: new custom nodes, CUDA variants, smoke-test improvements, documentation.

## Workflow

1. Fork the repo and open a PR against `main`. Nobody — the maintainer included — pushes to `main` directly.
2. The `pr` workflow builds the image and runs the smoke test. For PRs from forks, a maintainer must approve the workflow run (this protects the runners from abuse).
3. A PR needs **1 approving review from the code owner** and a green `smoke` check. PRs are squash-merged.

## Recipe rules

- **Custom nodes**: add an entry to `nodes.lock.yaml` with `repo`, `ref` and the **full commit SHA** (never a branch), and add its `class_type` values to `required_nodes.txt`. Say in the PR which workflow needs it.
- **No models, LoRAs or data** in the image. Models go in `models.lock.yaml` (downloaded to the volume): `repo`, full-SHA `revision`, `file`, `folder`, `sha256`, `size` — `get-model` prints a ready entry. Say in the PR which workflow needs it.
- **Don't change the torch version** without a reason: it can change outputs for a fixed seed.
- Actions pinned by SHA; least-privilege permissions per job; never `pull_request_target`.
- Don't use third-party trademarks (e.g. "Comfy") in file, image or project names.
- Test locally before opening the PR (Docker or Apple `container`); see the README.

## License of contributions

By contributing, you agree that your contribution is published under this repository's MIT license (inbound = outbound). Don't add third-party code under incompatible licenses.
