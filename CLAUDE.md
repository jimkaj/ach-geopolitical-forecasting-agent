# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A three-tier multi-agent system applying **Analysis of Competing Hypotheses (ACH)** to geopolitical news: ingest full-text articles (The Guardian Content API) → score each article's diagnostic value against competing hypotheses → maintain a versioned evidence matrix. CMU Agentic AI Certificate capstone (James Kajdasz).

**Current state: all three tiers implemented and verified end-to-end.** `python main.py` runs the full Scraper → Assessment → Matrix pipeline live (verified with Ollama + `llama3.1`). The **Scraper Agent** (Tier 1, Guardian Content API, full body text), **Assessment Agent + LLMInterface** (Tier 2, comparative ACH self-consistency scoring), and **Matrix Agent** (Tier 3, Heuer-style evidence-row matrix ranked by inconsistency, accumulating across runs, rendered to a color-coded HTML view) all work.

Known remaining gaps / notes:
- `tools/file_manager.py` — `save_matrix_snapshot()` is still an unused stub; the Matrix Agent writes its own CSVs (and reloads them in `_load_matrix_state()`). Not on the critical path.
- Assessment directional accuracy is bounded by the local model (8B); low/unstable confidence is surfaced via the human-review flag by design.
- Hermetic `tests/` suite exists (63 tests, ~89% coverage of `agents`/`tools`); all external I/O is mocked. The remaining uncovered lines are mostly logging-setup and error branches.

When implementing a stub, the surrounding non-stub code already defines the expected signature and downstream consumers — match them rather than redesigning.

## Commands

```bash
uv sync                 # Install deps
cp .env.template .env   # Optional — Settings auto-loads .env; defaults work out of the box
uv run python main.py   # Run the full Scraper → Assessment → Matrix pipeline (live console + table)
```

Use `uv run python main.py`, not bare `python main.py`, so the project `.venv` and its deps are used regardless of shell activation. Requires Ollama running with a long-context model (`ollama pull llama3.1`).

```bash
uv run pytest                              # run the test suite (hermetic; no network/LLM needed)
uv run pytest tests/test_matrix_agent.py   # a single test file
uv run pytest -k accumulation              # tests matching a keyword
uv run pytest --cov=agents --cov=tools     # with coverage
```

Tooling configured in `pyproject.toml` dev group: `black`, `ruff`, `pytest` + `pytest-cov`. Pytest config (`testpaths`, warning filters) is in `[tool.pytest.ini_options]`.

## Non-obvious facts

- **Articles come from The Guardian, not Reuters** (despite the project name). Reuters' ToS prohibit scraping and its full text is licensed-only (Reuters Connect, `documentation/Reuters_Delivery_Overview.pdf`); the Guardian Open Platform Content API (`content.guardianapis.com`) returns full body text for free. `settings.guardian_api_key` defaults to the literal `"test"` key (dev only, rate-limited); set `GUARDIAN_API_KEY` for a real free key. (An earlier iteration used Google News RSS but it only yields snippets, not full text.)
- **Orchestration is plain sequential Python, not LangGraph.** `main.py` calls `agent.execute(...)` in order and passes return values by hand. `langgraph`/`langchain` — and `torch`/`transformers`/`sentence-transformers` — are installed but unused at runtime (the LLM path is the Ollama HTTP API). Don't assume a state graph or local transformer inference.
- **Dependencies are injected in `main.py`**: `ScraperAgent(config, web_scraper, file_manager)`, `AssessmentAgent(config, hypotheses, llm_interface)`, `MatrixAgent(config, file_manager)`. Config lives in `config/settings.py` (Pydantic `Settings`), `config/hypothesis_config.yaml`, and `config/domain_whitelist.txt` (there is no `config/agent_config.py`).

## Architecture

Single linear pass in `main.py` → `run_agent_pipeline()`:

1. **ScraperAgent** (`agents/scraper_agent.py`) → `execute(search_query)` returns `list[ArticleData]`. Takes `(config, web_scraper, file_manager)`. Sources articles via **The Guardian Content API** (`WebScraper.search_articles()` → JSON with `show-fields=bodyText`, `section`/`from-date`/`page-size` from settings), and dedups against `data/processed_urls.csv` (owned by `FileManager`). `WebScraper` enforces `config/domain_whitelist.txt` (includes `content.guardianapis.com`). `ArticleData.content` is the **full article body text**; `url` is the Guardian `webUrl`; `article_id` is the Guardian id slug. The API key is passed via `params` (not the URL) so it never lands in logs.
2. **AssessmentAgent** (`agents/assessment_agent.py`) → `execute(articles)` returns `list[AssessmentResult]`. Uses **comparative ACH scoring**: each pass sends *all* competing hypotheses in one prompt (`LLMInterface.evaluate_hypotheses()`) and the model assigns a mark to each, so it discriminates between them. Runs `llm_num_passes` (default 10) such passes; **per-hypothesis confidence = fraction of passes agreeing with that hypothesis's majority mark** (self-consistency, `measure_self_consistency()`). Flags for human review when any confidence `< confidence_threshold` (0.6). The LLM sees the **full article body** (no truncation); `generate()` sets Ollama `num_ctx=llm_context_window` (default 8192) so long articles aren't silently cut — the chosen model must support that context. Cost: `llm_num_passes` LLM calls per article (default 10, not × hypotheses). Prompt design matters here: the LLM must treat articles that don't discuss the hypotheses' subject as `N/A`, not weak support.
3. **MatrixAgent** (`agents/matrix_agent.py`) → `execute(assessments)` returns `MatrixAgentState`. Takes `(config, file_manager)`. Follows Heuer Ch. 8: the matrix is **one `EvidenceRow` per article** (`agents/base.py`) with a mark per hypothesis — *not* collapsed tallies. On init, `_load_matrix_state()` reloads `data/matrix/matrix_state.json` so rows **accumulate across runs** (dedup by `article_id`). Hypotheses are ranked by **inconsistency** (`compute_scores` + `rank_by_inconsistency`, module-level): inconsistency = weighted evidence-against (`--`=2, `-`=1; `INCONSISTENCY_WEIGHTS`), and **lowest inconsistency = most likely** (Heuer Step 5 — explicitly *not* most-support). Each run writes the JSON state, a stable `acch_matrix.html`, and a timestamped HTML snapshot (rendered by `tools/matrix_view.py`), then prunes old `acch_matrix_v*` snapshots past `matrix_storage_cap_gb`.

**Evidence marks** (`++, +, N/A, -, --`) are the central vocabulary. Ranking is driven by **inconsistency** (`-`/`--`), not support — this is the v2 ACH-faithful correction (the old `net_support`/most-pluses ranking was removed). `EvidenceRow.is_diagnostic` flags rows whose marks differ across hypotheses (Heuer: evidence consistent with all hypotheses has no diagnostic value).

**Schemas** (`agents/base.py`) are the contract between tiers: Pydantic models (`ArticleData`, `HypothesisScore`, `AssessmentResult`, `MatrixAggregation`) for data crossing boundaries; `@dataclass` `*AgentState` for per-agent internal state. Changing a model ripples to the producing and consuming agent.

**Tools** (`tools/`) are stateless helpers, separate from agent decision logic: `llm_interface.py` (Ollama HTTP client at `llm_endpoint` + ACH prompt/parse), `web_scraper.py` (Guardian Content API JSON client), `file_manager.py` (processed-URL + snapshot persistence/pruning), `audit_logger.py` (file audit logs + `rich` console logging), `matrix_view.py` (renders the ACH matrix to self-contained color-coded HTML).

**Logging** is split by concern via named loggers configured in `tools/audit_logger.py` (`setup_audit_logging` called once at `main.py` import): `logs/agent_interactions.log`, `logs/assessments.log`, `logs/errors.log`. Use `AuditLogger.log_scrape/log_assessment/log_error` rather than ad-hoc logging. `setup_console_logging()` additionally attaches a `rich` console handler to the root logger so a `main.py` run streams live progress to the terminal (module `logger.info` calls in agents/tools surface here); `main.py` then prints the final matrix as a `rich` table via `render_matrix()`. Set `ENABLE_DEBUG_LOGGING=true` for DEBUG-level console output.

## Conventions & constraints

- **Config flows through `Settings`**: agents/tools take a `config` object in `__init__`; read values off it, don't re-read env vars. Env keys map case-insensitively to fields (e.g. `LLM_NUM_PASSES` → `llm_num_passes`).
- **Local LLM only** — no external API calls. `LLMInterface._verify_connection()` hits `{llm_endpoint}/api/tags` on init and raises if unreachable, so `main.py` fails fast without a running Ollama/vLLM.
- **TLS behind a proxy**: this machine sits behind a TLS-inspecting proxy whose CA is in the OS store but not `certifi`, so plain `requests` to HTTPS fails cert verification. `WebScraper` calls `truststore.inject_into_ssl()` at init (gated by `settings.use_system_truststore`, default on) to verify against the OS trust store. Keep verification on — do not switch to `verify=False`.
- **No user chat interface by design** (prompt-injection avoidance); inputs come from config files and scraped content only.
- **GPU**: `torch` is pinned to the CUDA 13.0 index in `pyproject.toml` (`[[tool.uv.index]]` + `[tool.uv.sources]`) for a dual TITAN RTX box. Keep `torch` sourced from `pytorch-cu130`; pandas/matrix work stays on CPU.
