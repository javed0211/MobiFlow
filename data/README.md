# Test data files

JSON / YAML / `.env` fixtures referenced by cases via `data:`.

| File | Used by |
|------|---------|
| `example.json` | `cases/example.txt` |
| `wikipedia_complex_search.json` | `cases/wikipedia_complex_search.txt` |

See [docs/CASES.md](../docs/CASES.md#data--env) for path resolution and flattening rules.

Do not commit real passwords or API keys here — use `.env` locally (gitignored) or env-var indirection in case `env:`.
