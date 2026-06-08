# shebanq-mcp

MCP server for querying the BHSA Hebrew Bible (the ETCBC database behind
SHEBANQ) in plain language. Returns a citable MQL query plus glossed,
verse-referenced results, produced by a local Emdros engine.

## Tools
- `search_bhsa(question)` — NL question -> generated MQL + results
- `run_mql(mql)` — validate and run MQL you already have
- `lookup_feature(name_or_term)` — BHSA feature gloss + valid values

## Setup
1. Install Emdros (provides the `mql` CLI and the `emdros` Python binding).
2. Build the database (see Data below).
3. `pip install -e ".[dev]"` (Python 3.10+).
4. Set `ANTHROPIC_API_KEY` (needed only for `search_bhsa`).
5. Run: `BHSA_SQLITE=data/bhsa.sqlite3 shebanq-mcp`

## Data
BHSA version: **2021** (pinned). Download the MQL dump to `data/bhsa.mql`, then:
`mql --backend sqlite3 -d data/bhsa.sqlite3 data/bhsa.mql`
Data files are gitignored.

## Tests
- `pytest -q` runs unit tests (no db required). Emdros-backed tests skip when the
  binding or database is absent.
- `BHSA_SQLITE=data/bhsa.sqlite3 pytest -m emdros` runs db-backed tests.

After building the database, pin the featured-search counts:
`BHSA_SQLITE=data/bhsa.sqlite3 python scripts/spike_emdros.py data/bhsa.sqlite3`
confirms the Emdros Python API, then fill in `expected_count` values in
`tests/fixtures/featured_searches.json` from real runs.

## Deploy
Render Pro Web Service (Docker, Emdros-on-SQLite, data baked into the image).
See the separate deploy plan.
