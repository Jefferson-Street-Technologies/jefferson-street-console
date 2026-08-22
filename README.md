# Jefferson Street Data (jstdata)

A Python interface and Research OS for the Jefferson Street financial and economic data API.

## Design Philosophy: From Filing Cabinet to Knowledge Graph

`jstdata` is built to minimize the friction between human thought and actionable data.

- **Series-First**: The individual data series is the primary resource, carrying its own metadata (frequency, units, source).
- **Entity Graph**: Entities are nodes in a relational graph, allowing you to "walk" from a company to its sector, or a country to its states.
- **Intent over IDs**: Both the CLI and Python API favor human-readable intent (fuzzy search) over memorizing obscure slugs.
- **Reproducible Discovery**: High-speed discovery in the CLI transitions seamlessly into immutable, reproducible code in Python Notebooks.

---

## Installation

```bash
# Using poetry
poetry install

# Manual install
pip install .
```

## Authentication & Configuration

Before you can query data, you need to authenticate with your Jefferson Street API key.

### Quick Start (CLI)

The easiest way to get set up is using the interactive login command:

```bash
# This will prompt for your API key and validate it
jst login
```

The CLI will guide you through the setup and save your credentials to `~/.jstdata/config.json` with secure permissions.

### Environment Variables

For CI/CD or temporary sessions, you can use environment variables. These take precedence over the config file:

```bash
export JSTDATA_API_KEY="your-api-key-here"
# Optional: export JSTDATA_BASE_URL="https://api.jeffersonst.io"
```

### Managing Configuration

You can view or update your configuration at any time:

```bash
# Show current (masked) API key
jst config show

# Show advanced config (base URL)
jst config show --verbose

# Manually update a value
jst config set api_key XXX
```

## The TUI Workbench (`jst tui`)

The "Telescope" for your data. Launch an interactive workbench for high-density discovery.

- **Live Fuzzy Refinement**: Type keywords to see Metrics, Entities, and Series update in real-time.
- **Deep Drill-down**: Press `Enter` on any result to fetch associated series, graph relations, or recent observations.
- **The Intent Bridge**:
    - Press `c` to copy a resource ID.
    - Press `p` to copy a fully-formed Python snippet for your Notebook.
- **Navigation**: Vim-style `j`/`k` for scrolling, `Enter` to focus results, and `Ctrl+C` or `q` to quit.

## The Scriptable CLI (`jst`)

A "pipe-friendly" interface designed for automation and quick extraction.

```bash
# Fuzzy query by intent (latest 20 observations per series)
jst query --metric inflation --entity "United States" --frequency Monthly --tail 20

# Deep history for one known series
jst series observations ABC123 --start-date 2000-01-01 --limit 1000

# Explore the entity graph
jst entity relations usa --format pretty

# Search for resources
jst series search "housing starts"
```

## The Python API

Designed for a robust experience in Jupyter/IPython notebooks.

```python
from jstdata import JSTDataClient

client = JSTDataClient()

# Cross-sectional observations (bounded per series)
df = client.query_df(
    metric="gross-domestic-product",
    entity=["usa", "gbr"],
    tail=20,
)

# Deep history for one series
obs = client.get_series_observations("ABC123", start_date="2000-01-01")

# Semantic exploration
series = client.get_entity_series("apple-inc")
relations = client.get_entity_relations("usa")
```
