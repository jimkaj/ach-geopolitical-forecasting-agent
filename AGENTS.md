# AI Agent Instructions — Geopolitical ACH Forecasting Agent

Cross-tool guide for AI agents working in this repo. **`CLAUDE.md` is the
detailed, authoritative companion** (architecture, gotchas, file map) and
`README.md` covers setup/usage; keep all three consistent when you change the build.

**Project**: James Kajdasz — CMU Agentic AI Certificate capstone (July 2026).

## What this is

A three-tier, linearly-orchestrated multi-agent system applying **Analysis of
Competing Hypotheses (ACH)** to geopolitical news across multiple nations:
**Scraper → Assessment → Matrix**, one full pass per nation. Each nation is
assessed on a US-alignment axis with three fixed hypotheses (supports / neutral /
opposes the United States) and gets its own isolated ACH matrix, time-series
line graph, and HTML page. A summary page shows all nations together.

**Status**: v3 complete — multi-nation pipeline, per-nation matrices and line
graphs, all-nations summary page; 86-test hermetic pytest suite; verified
end-to-end against Ollama + `llama3.1`; now defaults to `llama3.3` for
stronger reasoning.

**Currently tracked nations** (defined in `config/hypothesis_config.yaml`):
China, Iran, Israel, Qatar, Saudi Arabia, Pakistan, Kuwait, Bahrain.

## Tech stack (what's actually used)

| Component | Role |
|-----------|------|
| **requests + The Guardian Content API** | Per-nation full-text article sourcing (free developer key) |
| **Ollama** (default `llama3.3`) over HTTP | Local LLM for assessment |
| **pydantic / pydantic-settings** | State schemas + configuration |
| **truststore** | TLS via the OS trust store (works behind a TLS-inspecting proxy) |
| **rich** | Live console logging + per-nation result tables |
| **pytest** | 86-test hermetic suite |

**Not used despite being installed**: `langgraph`/`langchain` (orchestration is
plain sequential Python in `main.py`). `torch`/`transformers`/`sentence-transformers`
are present for GPU/future work but the runtime LLM path is the Ollama HTTP API.

## Environment & commands

- **Python 3.13**, managed by **`uv`** (`.venv`).
- Ollama with a **long-context** model (`ollama pull llama3.3`).

```bash
uv sync                      # install deps
uv run python main.py        # run the per-nation pipeline
uv run pytest                # hermetic tests (no network/LLM needed)
uv run --with ruff ruff check .   # lint
```

## Architecture (current)

The pipeline loops over each nation defined in `config/hypothesis_config.yaml`:

1. **Scraper** (`agents/scraper_agent.py` + `tools/web_scraper.py`) — queries the
   Guardian API using that nation's `search_query`, enforces `config/domain_whitelist.txt`,
   dedups against `data/processed_urls.csv` (global), and emits `ArticleData`.
   Each nation's AssessmentAgent only ever sees articles from its own search.

2. **Assessment** (`agents/assessment_agent.py` + `tools/llm_interface.py`) —
   **comparative ACH**: all three hypotheses are scored together in one Ollama call
   per pass; `LLM_NUM_PASSES` passes give per-hypothesis self-consistency confidence;
   results below `confidence_threshold` are flagged. Cost = `LLM_NUM_PASSES` calls
   per article (not × hypotheses).

3. **Matrix** (`agents/matrix_agent.py`) — Heuer Ch. 8 layout: one `EvidenceRow`
   per article, **accumulating across runs** from `data/matrix/{nation_id}/matrix_state.json`
   (dedup by article id). Ranks hypotheses by **inconsistency** (`--`=2, `-`=1;
   lowest = most likely, Step 5). Renders to `data/matrix/{nation_id}/acch_matrix.html`
   (includes embedded line graph + "← Back to Summary" nav) via `tools/matrix_view.py`.
   Nation directory is created automatically by `FileManager.get_nation_matrix_dir()`.

4. **Summary** (`tools/matrix_view.py` → `render_summary_html()`) — after all
   nations are processed, `main.py` writes `data/matrix/summary.html`: a standalone
   multi-line Canvas chart with one line per nation and clickable legend/line
   navigation to individual ACH pages.

`agents/base.py` holds the Pydantic schemas that are the contract between tiers
(`ArticleData`, `AssessmentResult`, `EvidenceRow`, …). `MatrixAgentState` now
carries `nation_id: str`.

**Hypothesis config** (`config/hypothesis_config.yaml`) is nation-keyed:
```yaml
nations:
  israel:
    search_query: "Israel United States relations"
    hypotheses:
      - {id: h1, name: "Israel supports the United States", description: "..."}
      - {id: h2, name: "Israel maintains a neutral stance ...", description: "..."}
      - {id: h3, name: "Israel opposes the United States", description: "..."}
```
Adding a nation requires only a new YAML entry — no code changes.

**Line graph scoring**: `contribution = weight[h1_mark] − weight[h3_mark]`
(weights: `++`=2, `+`=1, `N/A`=0, `-`=-1, `--`=-2; h2 contributes 0).
Cumulative sum plotted oldest → newest. Implemented in `_compute_score_series()`
and rendered by `_render_line_graph()` in `tools/matrix_view.py`.

## Conventions & constraints

- **Config flows through `Settings`** — agents/tools take a `config` object in
  `__init__` and read values off it; don't re-read env vars ad hoc.
- **Local LLM only** — no external LLM APIs. `LLMInterface` verifies Ollama on init.
- **No user chat interface** (prompt-injection avoidance) — inputs are config
  files + fetched article content.
- **Keep secrets out of logs** — pass API keys via `requests` params, not URLs.
- **Logging** — `AuditLogger` helpers (`tools/audit_logger.py`) + `rich` console.
- **Tests stay hermetic** — mock network/LLM, use `tmp_path` for filesystem.
- **`MatrixAgent` requires `nation_id`** — `MatrixAgent(config, file_manager, nation_id="china")`.
  All per-nation path logic flows through `FileManager.get_nation_matrix_dir(nation_id)`.

## Pitfalls

- **Use a long-context model** (`llama3.3`) or Ollama silently truncates long articles.
- **Preserve the comparative prompt's relevance gate** — scoring hypotheses in
  isolation makes the model over-affirm them; the single-call comparative prompt
  and the explicit "not relevant → N/A" rule are what fix it.
- **Matrix accumulates per nation** — deleting `data/matrix/{nation}/` resets that
  nation's evidence tally. `data/processed_urls.csv` deduplicates scraping globally;
  deleting it causes all previously seen articles to be re-fetched.
- **Nation colours**: `_NATION_COLORS` in `tools/matrix_view.py` has 8 entries
  (matching the current 8 nations). A 9th nation cycles back to the first colour
  on the summary chart — add a colour to keep lines visually distinct.
- **Runtime scale**: 8 nations × N articles × 10 passes = many LLM calls.
  Smoke-test with `SCRAPER_MAX_ARTICLES=3 LLM_NUM_PASSES=2`.

## Future

Conclusion Agent (synthesis + decay weighting), Notification Agent (threshold
alerts), RAG/semantic re-ranking, multi-source ingestion, configurable hypothesis
axes beyond US-alignment. See README.

---

**Last Updated**: 2026-06-23 · **Project Version**: 0.3.0 (v3)
