# AI Agent Instructions for CMU Agentic AI Capstone Project

**Project**: Geopolitical ACH Forecasting Agent — James Kajdasz Final Project for CMU Agentic AI Certificate Program (July 2026)

## Project Overview

**System**: A three-tier linear multi-agent forecasting engine that applies **Analysis of Competing Hypotheses (ACH)** to geopolitical news, autonomously scraping Reuters articles, assessing diagnostic value against competing hypotheses, and maintaining an evidence matrix for probabilistic forecasting on international relations scenarios (e.g., China's position in US-Iran conflicts).

**Agent Architecture** (linear sequential handoff):
1. **Scraper Agent** → Crawls Reuters for geopolitical articles; maintains long-term memory of processed URLs; enforces whitelist-only domain access
2. **Assessment Agent** → Evaluates article diagnostic value against 3 human-selected hypotheses; uses temperature-sampled multi-pass evaluation to measure confidence via self-consistency
3. **Matrix Agent** → Ingests scored evidence and maintains ACH decision matrix; versioned snapshots stored to disk with 1GB cap; optional downstream Conclusion & Notification agents reserved for v2

**Key Constraints**: No user chat interface (prevents prompt injection); local open-source LLM only; file-based state (no vector DB); agent-specific communication boundaries; comprehensive logging & audit trails.

### Core Tech Stack

| Component | Purpose |
|-----------|---------|
| **langgraph + langchain** | Multi-agent orchestration, sequential handoff, state management |
| **torch (GPU-enabled)** | Local LLM inference with CUDA 13.0 (dual TITAN RTX) |
| **requests + BeautifulSoup** | Reuters web scraping with domain whitelisting |
| **pandas + numpy** | ACH matrix operations, CSV state persistence, evidence aggregation |
| **pydantic** | Agent state schemas, configuration validation |
| **ollama/vLLM** | Local open-source LLM deployment (e.g., Llama 2, Mistral) |

## Development Environment

### Python & Dependency Management

- **Python Version**: 3.13.12
- **Manager**: `uv` (fast, deterministic package management)
- **Virtual Environment**: `.venv/` (committed to `.python-version`)

**Key Commands**:
```bash
uv sync              # Install dependencies with lock file
uv add <package>     # Add new package and update lock
uv remove <package>  # Remove package
python main.py       # Run the orchestrator
```

### Local LLM Setup

**Required**: Install Ollama or vLLM to serve local LLMs (no external API calls).

**Ollama** (recommended for development):
```bash
# Install from https://ollama.ai
ollama pull llama2              # Pull a model
ollama serve                    # Run server (default: http://localhost:11434)
```

**vLLM** (alternative for higher throughput):
```bash
pip install vllm
python -m vllm.entrypoints.openai.api_server --model meta-llama/Llama-2-7b-chat-hf
```

### GPU Configuration

- **PyTorch Build**: CUDA 13.0 wheels (`torch>=2.12.0`)
- **Driver Compatibility**: NVIDIA 591.86 supports CUDA up to 13.1
- **Hardware**: Dual TITAN RTX GPUs
- **Verification**:
```python
import torch
print(torch.cuda.is_available())   # True if GPUs detected
print(torch.cuda.device_count())    # Number of GPUs
print(torch.cuda.get_device_name()) # GPU model
```

## Project Structure

```
.
├── main.py                          # Orchestrator entry point (launches agent mesh)
├── pyproject.toml                   # Dependencies & metadata (uv-managed)
├── config/
│   ├── __init__.py
│   ├── agent_config.py              # Agent initialization parameters
│   ├── hypothesis_config.yaml       # Target hypotheses for assessment
│   ├── domain_whitelist.txt         # Approved domains for web scraping
│   └── settings.py                  # Global settings (LLM endpoint, storage caps, etc.)
├── agents/
│   ├── __init__.py
│   ├── base.py                      # Base agent class & state schemas (pydantic)
│   ├── scraper_agent.py             # Reuters crawler with URL deduplication
│   ├── assessment_agent.py          # Multi-pass hypothesis evaluation with confidence scoring
│   └── matrix_agent.py              # ACH matrix state management & versioning
├── tools/
│   ├── __init__.py
│   ├── web_scraper.py               # BeautifulSoup-based Reuters crawler
│   ├── llm_interface.py             # Local LLM interaction (Ollama/vLLM)
│   ├── file_manager.py              # State persistence & versioning
│   └── audit_logger.py              # Comprehensive interaction logging
├── data/
│   ├── processed_urls.csv           # Long-term memory: URLs already scraped
│   ├── matrix/                      # ACH matrix snapshots (versioned)
│   └── articles/                    # Scraped article content (temporary)
├── logs/
│   ├── agent_interactions.log       # All agent I/O events
│   ├── assessments.log              # Assessment scores & confidence metrics
│   └── errors.log                   # Error and exception log
└── tests/                           # Unit tests for agents and tools
    ├── test_scraper_agent.py
    ├── test_assessment_agent.py
    └── test_matrix_agent.py
```

## Common Development Tasks

### Running the Project
```bash
python main.py             # Launches the orchestrator with all three agents
```

### Interactive Development
```bash
# For notebook-based exploration (optional)
jupyter notebook          # Launch Jupyter (ipykernel installed)

# For local LLM testing
ollama serve              # Start Ollama server in separate terminal
python -c "import requests; print(requests.get('http://localhost:11434/api/tags').json())"
```

### Adding Dependencies
```bash
uv add requests           # Web scraping utilities
uv add beautifulsoup4     # HTML parsing
uv sync                   # Resync after manual edits to pyproject.toml
```

## Agent Architecture & Conventions

### 1. **Scraper Agent** (Tier 1)
- **Responsibility**: Autonomously crawl Reuters for geopolitical news matching search criteria
- **State Schema**: `(iteration_id, articles[], next_page_token, last_crawl_time)`
- **Tools**: `web_scraper.fetch_reuters()`, `file_manager.load_processed_urls()`, `audit_logger.log_scrape()`
- **Constraints**:
  - Only access domains in `config/domain_whitelist.txt`
  - Check `data/processed_urls.csv` before fetching to prevent duplication
  - Log every scrape attempt (success/failure) to `logs/agent_interactions.log`
  - Graceful handling of network failures with exponential backoff
- **Output**: New articles → Assessment Agent

### 2. **Assessment Agent** (Tier 2)
- **Responsibility**: Evaluate each article's diagnostic value against competing hypotheses using multi-pass temperature sampling
- **State Schema**: `(article, hypothesis_scores{}, confidence, flagged_for_human)`
- **Core Logic**:
  - For each article, run 10 LLM passes with `temperature=0.7` to evaluate diagnostic value
  - Measure self-consistency across passes (e.g., "if 8/10 agree on same score, confidence=0.8")
  - Flag for human review if confidence < 0.6 or if majority is split
  - Use evidence marks: `++` (strong support), `+` (weak support), `N/A` (neutral), `-` (weak against), `--` (strong against)
- **Tools**: `llm_interface.evaluate_hypothesis()`, `audit_logger.log_assessment()`
- **Output**: Scored assessments `{article_id, hypothesis_scores[], confidence}` → Matrix Agent
- **Self-Consistency Pseudocode**:
  ```python
  scores_list = []
  for i in range(10):
      prompt = f"Rate article diagnostic value for each hypothesis..."
      score = llm_interface.call(prompt, temperature=0.7)
      scores_list.append(score)
  
  # Compute confidence as fraction of agreement
  most_common = mode(scores_list)
  confidence = sum(1 for s in scores_list if s == most_common) / 10
  ```

### 3. **Matrix Agent** (Tier 3)
- **Responsibility**: Maintain versioned ACH decision matrix, aggregate evidence, enforce storage caps
- **State Schema**: `(matrix_version, hypothesis_aggregates{}, article_count, last_update)`
- **Core Logic**:
  - Append new scores to the hypothesis aggregates (cumulative tallies of ++, +, N/A, -, --)
  - Generate versioned snapshot: `data/matrix/acch_matrix_v{timestamp}.csv`
  - Track evidence totals for each hypothesis (e.g., "China Support: ++:5, +:12, N/A:2, -:1, --:0")
  - Enforce 1GB cap on `data/matrix/` directory; prune oldest snapshots if exceeded
- **Tools**: `file_manager.save_matrix_snapshot()`, `file_manager.cleanup_old_snapshots()`
- **Output**: Versioned ACH matrix snapshots (future Conclusion Agent can consume these for narrative synthesis)
- **Example Matrix Row**:
  ```
  Hypothesis,++,+,N/A,-,--,Cumulative_Support
  "China supports US",5,12,2,1,0,+17
  "China neutral",8,6,3,2,1,+14
  "China supports Iran",2,4,5,10,8,-11
  ```

## Common Pitfalls & Solutions

| Issue | Solution |
|-------|----------|
| Assessment confidence scores inconsistent across runs | Expected behavior; self-consistency variation is a feature. Log confidence metrics to understand variance. Increase passes from 10 → 20 if more stability needed. |
| LLM context window exceeded on long articles | Implement article chunking in Assessment Agent; evaluate each chunk separately and aggregate confidence scores. |
| Scraper blocked by Reuters rate limiting | Implement exponential backoff in `web_scraper.py`; add random delays between requests (1-3s). Consider rotating user-agent strings. |
| Disk storage filling up (`data/matrix/` > 1GB) | Matrix Agent's cleanup logic should trigger automatically. Verify 1GB cap enforcement in `file_manager.py`. Manually prune old snapshots if needed. |
| Processed URLs CSV not found on first run | Initialize empty CSV in `data/processed_urls.csv` on first agent startup; add check in `scraper_agent.py`. |
| Multi-pass evaluation timeout | Reduce parallel passes or increase LLM timeout. Consider batching evaluations across articles. |
| GPU out of memory | Reduce batch size in Assessment Agent; move hypothesis scoring to CPU if needed; ensure `torch.no_grad()` is used during inference. |
| Agent handoff state not flowing to next tier | Verify `langgraph` state graph edges and ensure prior agent's output matches next agent's input schema. Add debug logging at each handoff boundary. |

## Tips for AI Agents

1. **Preserve self-consistency semantics** — The Assessment Agent's multi-pass evaluation is intentionally stochastic; high variance in confidence scores indicates genuine ambiguity in source material, not a bug.
2. **Monitor state transitions** — Log every agent handoff (Scraper → Assessment → Matrix) to catch silent failures or state schema mismatches.
3. **Separate concerns** — Agent logic (decision-making) should be isolated from tools (API calls, file I/O). Tools should be wrapped as LangChain tools with clear docstrings.
4. **Use GPU for LLM inference only** — Keep matrix/pandas operations on CPU; GPU is not beneficial for sparse data operations.
5. **Test agents independently** — Unit test each agent with mocked tools before integrating into the full mesh. Use pytest or similar.
6. **Version matrix snapshots aggressively** — More frequent snapshots (e.g., every 5 articles) enable fine-grained debugging and re-evaluation.
7. **Implement human-in-the-loop escalation** — Low-confidence assessments (< 0.6) should surface to a UI or log file for human review; don't silently accept them.

## Future Customizations (v2 & Beyond)

As the project scales, consider:

- **Conclusion Agent** — Consume matrix snapshots with Tree-of-Thought reasoning to generate narrative summaries of hypothesis likelihood; implement hypothesis decay weighting based on temporal distance.
- **Notification Agent** — Send daily SMS summaries when matrix conclusions shift beyond threshold (e.g., "China support for US crosses 60%").
- **RAG Integration** — Cache article embeddings using `sentence-transformers` if Assessment Agent needs historical context retrieval for refined scoring.
- **Fine-Tuning** — Use human tie-breaker judgments from low-confidence escalations to fine-tune local LLM for improved assessment accuracy.
- **Reflexion Loops** — Add Reflexion pattern to Assessment Agent if post-hoc confidence validation improves agreement across multiple evaluation runs.
- **Web UI** — Create a dashboard for matrix visualization, hypothesis tracking, and manual judgment interface (for human escalations).
- `.cursorrules` or `.windsurf/rules/` — For IDE-level agent guidance on ACH framework principles and deployment constraints.

---

**Last Updated**: 2026-06-22 | **Project Version**: 0.1.0
