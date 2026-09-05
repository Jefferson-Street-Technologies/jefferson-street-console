# Jefferson Street Data (jstdata)

A Python interface and Research OS for the Jefferson Street financial and economic data API.

## Design Philosophy: From Filing Cabinet to Knowledge Graph

`jstdata` is built to minimize the friction between human thought and actionable data.

- **Series-First**: The individual data series is the primary resource, carrying its own metadata (frequency, units, source).
- **Entity Graph**: Entities are nodes in a relational graph — walk from a company to its SIC, a security ticker, or a geography.
- **Taxonomies**: Named populations (`country`, `sec-central-index-key`, …) scope search, query, and ranking.
- **Intent over IDs**: CLI and Python favor fuzzy search over memorizing slugs; always resolve before querying.
- **Sessions & workflows**: Stage resolved ids in a session JSON; compose interactive steps in the shell and save them as named workflows.
- **Reproducible Discovery**: High-speed discovery in the TUI transitions into immutable Python / CLI snippets.

---

## Installation

```bash
# Using poetry
poetry install

# Manual install
pip install .
```

## Authentication & Configuration

### Quick Start (CLI)

```bash
jst login
```

Credentials are saved to `~/.jstdata/config.json` with secure permissions.

### Environment Variables

These take precedence over the config file:

```bash
export JSTDATA_API_KEY="your-api-key-here"
# Optional: export JSTDATA_BASE_URL="https://api.jeffersonst.io"
```

### Managing Configuration

```bash
jst config show
jst config show --verbose
jst config set api_key XXX
```

## Interactive investigation (`jst run`)

Compose TUI **steps** in the shell. Steps share one **Session** (staged metrics /
entities / series + query filters) for the lifetime of the run.

```bash
# Catalog search → stage entities/metrics/series
jst run console

# Scope to a taxonomy and resource type
jst run console --taxonomy sec-central-index-key --resource-type entity

# Filter entities by typed graph edges (repeatable; OR'd)
jst run console --relation classified_as:sic:7372 --resource-type entity

# Chain steps
jst run console --taxonomy country : discover --mode union : rank --taxonomy country

# Preload a session JSON; set default export path
jst run --session labor.json --output out.json rank --taxonomy country
```

Built-in steps:

| Step | Role |
|------|------|
| `console` | Search catalog; stage into the session |
| `discover` | Find metrics for session entities; preview coverage |
| `rank` | Leaderboard entities for a session metric |

Host keys (every step): `s` session · `f` find · `e` export · `n`/`p` next/prev · `?` step help · `q` quit.

```bash
jst steps
jst step console
jst step rank --json
```

### Saved workflows

Persist step pipelines (not session contents) under `~/.jstdata/workflows/`:

```bash
jst workflow create --id gdp-rank --description "GDP board" -- \
  console --taxonomy country : rank --taxonomy country

jst workflow ls
jst workflow run gdp-rank --session labor.json
jst workflow rm gdp-rank
```

(`jst workflows` remains a compatibility alias.)

### Tutorial

```bash
jst tutorial
# same as: jst workflow run tutorial
```

### Agents

```bash
jst agent-guide
```

Prints a version-tied operating manual (hard rules, modes, recipes, and the live
CLI/step reference). Prefer it over guessing command shapes or inventing ids.

## The Scriptable CLI (`jst`)

Pipe-friendly commands for automation and quick extraction.

```bash
# Fuzzy / set search (omit QUERY to list the matching set)
jst metric search "defense spending" --taxonomy country --limit 20 --format json
jst entity search --relation classified_as:sic:3674 --limit 50 --format json
jst entity search --metric gdp --metric cpi --mode intersect --format json

# Taxonomies
jst taxonomy ls --format json
jst taxonomy entities country --limit 20 --format json

# Bounded cross-sectional query (head/tail per series)
jst query --metric inflation --entity "United States" --frequency Monthly --tail 20
jst query --metric gdp --taxonomy country --tail 1 --sort-by value --limit 50 --format json

# Deep history for one known series
jst series observations ABC123 --start-date 2000-01-01 --limit 1000

# Entity graph
jst entity relations cik:1045810 --format pretty
```

## The Python API

```python
from jstdata import JSTDataClient, Session

client = JSTDataClient()

# Cross-sectional observations (bounded per series)
df = client.query_df(
    metric="gross-domestic-product",
    entity=["usa", "gbr"],
    tail=20,
)

# Rank a taxonomy population by latest value
top = client.query(
    metric="gross-domestic-product",
    taxonomy="country",
    frequency="Annual",
    tail=1,
    sort_by="value",
    limit=50,
)

# Relation-scoped entity search (OR when multiple)
entities = client.search_entities(
    relation=["classified_as:sic:7372", "classified_as:sic:5961"],
    taxonomy="sec-central-index-key",
    limit=50,
)

# Deep history for one series
obs = client.get_series_observations("ABC123", start_date="2000-01-01")

# Stage intent for a later `jst run` / `jst workflow run`
session = Session(
    metric=["gross-domestic-product"],
    taxonomy="country",
    tail=1,
    sort_by="value",
)
session.save("labor.json")
```

## Extending the product

See [AGENTS.md](AGENTS.md) for how steps, the host, and saved workflows are
structured when adding new interactive surface area.
