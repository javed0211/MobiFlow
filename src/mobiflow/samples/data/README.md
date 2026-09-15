# Test data files

JSON / YAML / `.env` fixtures referenced by cases via `data:`.

| File | Used by |
|------|---------|
| `example.json` | `cases/example.txt` |
| `wikipedia_complex_search.json` | `cases/wikipedia_complex_search.txt` |
| `joplin_smoke.json` | optional for `cases/android_joplin_smoke.txt` |
| `bitwarden_smoke.json.example` | copy → local `bitwarden_smoke.json` (do not commit secrets) |

See [docs/CASES.md](../docs/CASES.md#data--env) for path resolution and flattening rules.
See [docs/SAMPLE_APPS.md](../docs/SAMPLE_APPS.md) for Joplin / Bitwarden install notes.

Do not commit real passwords or API keys here — use `.env` locally (gitignored) or env-var indirection in case `env:`.
