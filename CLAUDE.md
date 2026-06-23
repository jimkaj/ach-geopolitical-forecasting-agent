# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A three-tier multi-agent system applying **Analysis of Competing Hypotheses (ACH)** to geopolitical news across multiple nations: ingest full-text articles (The Guardian Content API) → score each article's diagnostic value against per-nation competing hypotheses → maintain a versioned evidence matrix per nation. CMU Agentic AI Certificate capstone (James Kajdasz).

**Current state: v3 implemented and verified end-to-end.** `uv run python main.py` runs the full per-nation Scraper → Assessment → Matrix pipeline. Each configured nation (China, Iran, Israel, Qatar, Saudi Arabia, Pakistan, Kuwait, Bahrain) gets its own isolated ACH matrix, a time-series US-alignment line graph, and a per-nation HTML page. A summary page (`data/matrix/summary.html`) displays all nations on one multi-line chart with click-through navigation to individual matrices.

Known notes:
- `tools/file_manager.py` — `save_matrix_snapshot()` is still an unused stub; the Matrix Agent writes its own JSON/HTML directly. Not on the critical path.
- Assessment directional accuracy is bounded by the local model (8B); low/unstable confidence is surfaced via the human-review flag by design.
- Hermetic `tests/` suite: 86 tests; all external I/O is mocked. Uncovered lines are mostly logging-setup and error branches.

## Commands

```bash
uv sync                 # Install deps
cp .env.template .env   # Optional — Settings auto-loads .env; defaults work out of the box
uv run python main.py   # Run the full per-nation pipeline (live console + per-nation tables)
```

Use `uv run python main.py`, not bare `python main.py`. Requires Ollama running with a long-context model (`ollama pull llama3.1`).

```bash
uv run pytest                              # run the test suite (hermetic; no network/LLM needed)
uv run pytest tests/test_matrix_agent.py   # a single test file
uv run pytest -k accumulation              # tests matching a keyword
uv run pytest --cov=agents --cov=tools     # with coverage
```

Tooling configured in `pyproject.toml` dev group: `black`, `ruff`, `pytest` + `pytest-cov`. Pytest config (`testpaths`, warning filters) is in `[tool.pytest.ini_options]`.

## Non-obvious facts

- **Articles come from The Guardian, not Reuters** (despite the project name). Reuters' ToS prohibit scraping and its full text is licensed-only (Reuters Connect, `documentation/Reuters_Delivery_Overview.pdf`); the Guardian Open Platform Content API (`content.guardianapis.com`) returns full body text for free. `settings.guardian_api_key` defaults to the literal `"test"` key (dev only, rate-limited); set `GUARDIAN_API_KEY` for a real free key.
- **Orchestration is plain sequential Python, not LangGraph.** `main.py` loops over nations and calls `agent.execute(...)` in order. `langgraph`/`langchain` — and `torch`/`transformers`/`sentence-transformers` — are installed but unused at runtime (the LLM path is the Ollama HTTP API).
- **Dependencies are injected in `main.py`**: `ScraperAgent(config, web_scraper, file_manager)`, `AssessmentAgent(config, hypotheses, llm_interface)`, `MatrixAgent(config, file_manager, nation_id=nation_id)`. Config lives in `config/settings.py` (Pydantic `Settings`), `config/hypothesis_config.yaml`, and `config/domain_whitelist.txt`.
- **Hypothesis config is nation-keyed** (v3). `hypothesis_config.yaml` has a top-level `nations:` dict; each entry has a `search_query` and a `hypotheses` list with the three fixed h1/h2/h3 marks. To add a nation, add it to the YAML — no code changes needed.
- **`_NATION_COLORS` in `tools/matrix_view.py`** defines 8 colours for the summary chart. If you add a 9th nation the colours cycle (two lines share a colour) — add a colour to the list if that matters.

## Architecture

Per-nation linear pass in `main.py` → `run_agent_pipeline()`, looping over each configured nation:

1. **ScraperAgent** (`agents/scraper_agent.py`) → `execute(search_query)` returns `list[ArticleData]`. Takes `(config, web_scraper, file_manager)`. Each nation supplies its own `search_query` (e.g. `"Israel United States relations"`); the Scraper fetches only that nation's articles. Sources via **The Guardian Content API** (`WebScraper.search_articles()` → JSON with `show-fields=bodyText`), deduplicates against `data/processed_urls.csv`. `ArticleData.content` is the **full article body text**.
2. **AssessmentAgent** (`agents/assessment_agent.py`) → `execute(articles)` returns `list[AssessmentResult]`. Takes `(config, hypotheses, llm_interface)` where `hypotheses` is the nation-specific list from the YAML. Uses **comparative ACH scoring**: each pass sends *all three* competing hypotheses in one prompt so the model discriminates between them. Runs `llm_num_passes` (default 10) passes; **per-hypothesis confidence = fraction of passes agreeing with that hypothesis's majority mark** (self-consistency). Flags for human review when any confidence `< confidence_threshold` (0.6). Cost: `llm_num_passes` LLM calls per article.
3. **MatrixAgent** (`agents/matrix_agent.py`) → `execute(assessments)` returns `MatrixAgentState`. Takes `(config, file_manager, nation_id)`. Writes all state to `data/matrix/{nation_id}/` (created automatically by `FileManager.get_nation_matrix_dir()`). Follows Heuer Ch. 8: one `EvidenceRow` per article accumulating across runs (dedup by `article_id`). Ranks hypotheses by **inconsistency** (lowest = most likely, Heuer Step 5). Each run writes `matrix_state.json`, a stable `acch_matrix.html` (with "← Back to Summary" button), and a timestamped snapshot; prunes old snapshots past `matrix_storage_cap_gb`.

After all nations are processed, `main.py` calls `render_summary_html(results_by_nation)` and writes `data/matrix/summary.html` — a standalone page with the multi-nation line chart and legend links.

**Hypotheses** are always h1 (supports US) / h2 (neutral) / h3 (opposes US). The three IDs are fixed; only the nation-specific names change.

**Evidence marks** (`++, +, N/A, -, --`) are the central vocabulary. Ranking is driven by **inconsistency** (`-`/`--`), not support. `EvidenceRow.is_diagnostic` flags rows whose marks differ across hypotheses.

**Line graph scoring** (v3): per article, `contribution = weight[h1_mark] − weight[h3_mark]` (weights: `++`=2, `+`=1, `N/A`=0, `-`=-1, `--`=-2). h2 contributes 0 (it is the neutral midpoint). Cumulative sum plotted oldest-to-newest — line goes up for pro-US evidence, down for anti-US evidence.

**Schemas** (`agents/base.py`) are the contract between tiers: Pydantic models (`ArticleData`, `HypothesisScore`, `AssessmentResult`) for data crossing boundaries; `@dataclass` `*AgentState` for per-agent internal state. `MatrixAgentState` carries `nation_id: str`. Changing a model ripples to the producing and consuming agent.

**Tools** (`tools/`) are stateless helpers: `llm_interface.py` (Ollama HTTP client + ACH prompt/parse), `web_scraper.py` (Guardian API client), `file_manager.py` (processed-URL dedup + per-nation snapshot pruning via `get_nation_matrix_dir()`), `audit_logger.py` (file audit logs + `rich` console), `matrix_view.py` (renders ACH matrix + line graph to self-contained HTML; `render_summary_html()` produces the all-nations overview).

**Logging**: named loggers in `tools/audit_logger.py` → `logs/agent_interactions.log`, `logs/assessments.log`, `logs/errors.log`. Use `AuditLogger.log_scrape/log_assessment/log_error`. `setup_console_logging()` attaches a `rich` handler for live terminal output. Set `ENABLE_DEBUG_LOGGING=true` for DEBUG-level output.

## Conventions & constraints

- **Config flows through `Settings`**: agents/tools take a `config` object in `__init__`; read values off it, don't re-read env vars. Env keys map case-insensitively to fields (e.g. `LLM_NUM_PASSES` → `llm_num_passes`).
- **Local LLM only** — no external API calls. `LLMInterface._verify_connection()` hits `{llm_endpoint}/api/tags` on init and raises if unreachable, so `main.py` fails fast without Ollama.
- **TLS behind a proxy**: `WebScraper` calls `truststore.inject_into_ssl()` at init (gated by `settings.use_system_truststore`, default on) to verify against the OS trust store. Keep verification on — do not switch to `verify=False`.
- **No user chat interface by design** (prompt-injection avoidance); inputs come from config files and scraped content only.
- **GPU**: `torch` is pinned to the CUDA 13.0 index in `pyproject.toml` for a dual TITAN RTX box. Keep `torch` sourced from `pytorch-cu130`.
- **Adding a nation**: add it to `config/hypothesis_config.yaml` under `nations:` with a `search_query` and three hypotheses. No code changes required.
