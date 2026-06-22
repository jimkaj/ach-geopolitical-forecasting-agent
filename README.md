# Geopolitical ACH Forecasting Agent

**Final Project for CMU Agentic AI Certificate Program (July 2026)**  
**Student**: James Kajdasz

## Overview

This is a **deployable three-tier multi-agent system** that applies **Analysis of Competing Hypotheses (ACH)** methodology to autonomously analyze geopolitical news and forecast competing outcomes in international relations scenarios.

**Key Features**:
- 🔄 **Linear multi-agent architecture**: Scraper → Assessment → Matrix agents with sequential handoff
- 🧠 **Self-consistent confidence scoring**: Temperature-sampled multi-pass evaluation with human-in-the-loop escalation
- 📊 **ACH decision matrix**: Versioned snapshots tracking evidence accumulation across hypotheses  
- 🔒 **Security-first design**: Domain whitelisting, no user chat interface, file-based approvals, comprehensive audit logging
- 🚀 **GPU-accelerated LLM inference**: CUDA 13.0 with local open-source LLMs (Ollama/vLLM)
- 📁 **Production-ready**: File-based state management, 1GB storage caps, graceful error handling

## Quick Start

### Prerequisites

- Python 3.13+
- `uv` package manager
- Local LLM service (Ollama or vLLM)
- NVIDIA GPU (dual TITAN RTX recommended, CPU fallback supported)

### Installation

```bash
# Install dependencies
uv sync

# Copy environment template and configure
cp .env.template .env
# Edit .env as needed (LLM endpoint, storage caps, etc.)

# Ensure local LLM is running
ollama serve  # In separate terminal
```

### First Run

```bash
# Start the agent pipeline
python main.py
```

This will:
1. **Tier 1**: Scrape Reuters for geopolitical articles matching search criteria
2. **Tier 2**: Evaluate each article's diagnostic value against 3 competing hypotheses using multi-pass sampling
3. **Tier 3**: Maintain ACH decision matrix with versioned snapshots

Results are logged to:
- `logs/agent_interactions.log` — All agent I/O events
- `logs/assessments.log` — Assessment scores and confidence metrics
- `logs/errors.log` — Errors and warnings
- `data/matrix/acch_matrix_v*.csv` — Versioned matrix snapshots

## Project Structure

```
.
├── main.py                          # Orchestrator (entry point)
├── config/
│   ├── settings.py                  # Global configuration (Pydantic)
│   ├── hypothesis_config.yaml       # Target hypotheses for assessment
│   ├── domain_whitelist.txt         # Approved domains for scraping
│   └── __init__.py
├── agents/
│   ├── base.py                      # Shared state schemas and models
│   ├── scraper_agent.py             # Reuters crawler with URL dedup
│   ├── assessment_agent.py          # Multi-pass hypothesis evaluation
│   ├── matrix_agent.py              # ACH matrix management
│   └── __init__.py
├── tools/
│   ├── audit_logger.py              # Comprehensive interaction logging
│   ├── file_manager.py              # State persistence & versioning
│   ├── llm_interface.py             # Local LLM API client
│   ├── web_scraper.py               # BeautifulSoup-based crawler
│   └── __init__.py
├── data/
│   ├── processed_urls.csv           # Long-term memory: URLs already scraped
│   ├── matrix/                      # ACH matrix snapshots (versioned)
│   └── articles/                    # Scraped article content (temporary)
├── logs/
│   ├── agent_interactions.log
│   ├── assessments.log
│   └── errors.log
├── pyproject.toml                   # Dependencies (uv-managed)
├── .env.template                    # Environment configuration template
├── AGENTS.md                        # AI agent development guide
└── README.md                        # This file
```

## Architecture

### Three-Tier Agent Mesh

```
Reuters News Stream
        ↓
[Tier 1: Scraper Agent]
  - Crawl Reuters for geopolitical articles
  - Enforce domain whitelist
  - Maintain URL deduplication index
  - Output: ArticleData[] → Assessment Agent
        ↓
[Tier 2: Assessment Agent]
  - Evaluate article diagnostic value against 3 hypotheses
  - Run 10 temperature-sampled LLM passes per hypothesis
  - Measure self-consistency confidence (0.0-1.0)
  - Flag articles with low confidence for human review
  - Output: AssessmentResult[] → Matrix Agent
        ↓
[Tier 3: Matrix Agent]
  - Ingest scored evidence into ACH matrix
  - Maintain cumulative tally: ++, +, N/A, -, --
  - Compute net support per hypothesis
  - Save versioned snapshots (ACH matrix as CSV)
  - Enforce 1GB storage cap with automatic pruning
  - Output: Versioned ACH matrix snapshots
```

### Assessment Agent: Self-Consistency Scoring

For each article-hypothesis pair:

1. **Multi-pass evaluation**: Run 10 LLM passes with `temperature=0.7`
2. **Evidence mark selection**: Each pass selects one: ++, +, N/A, -, or --
3. **Self-consistency**: Compute fraction of passes agreeing with majority mark
4. **Confidence = agreement rate**
   - Example: If 8/10 passes agree on "+", confidence = 0.8
   - If 5/10 agree, confidence = 0.5 (ambiguous → flag for human)

### Example ACH Matrix

```
Hypothesis,++,+,N/A,-,--,Net Support
"China supports US",5,12,2,1,0,+17
"China neutral",8,6,3,2,1,+14
"China supports Iran",2,4,5,10,8,-11
```

Net Support = (++ × 2) + (+ × 1) + (N/A × 0) + (- × -1) + (-- × -2)

## Configuration

### Hypotheses (`config/hypothesis_config.yaml`)

Define competing hypotheses. Default: China's position in US-Iran conflict

```yaml
hypotheses:
  - id: "h1"
    name: "China supports US position"
    description: "..."
```

Edit to customize hypotheses for different scenarios.

### Domain Whitelist (`config/domain_whitelist.txt`)

Only approved domains are accessible to Scraper Agent. Default: Reuters variants only.

### Environment Variables (`.env`)

```bash
LLM_MODEL=llama2                  # Local model to use
LLM_ENDPOINT=http://localhost:11434
CONFIDENCE_THRESHOLD=0.6          # Flag articles below this confidence
MATRIX_STORAGE_CAP_GB=1.0        # Max storage for matrix snapshots
```

## Development

### Running Tests

```bash
pytest tests/ -v --cov=agents --cov=tools
```

### Adding Hypotheses

Edit `config/hypothesis_config.yaml` with new hypotheses, then re-run:

```bash
python main.py
```

### Running in Debug Mode

```bash
ENABLE_DEBUG_LOGGING=true python main.py
```

### Checking GPU

```python
python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.device_count())"
```

## Future Enhancements (v2+)

- **Conclusion Agent** — Tree-of-Thought synthesis of matrix snapshots with hypothesis decay weighting
- **Notification Agent** — Daily SMS summaries when conclusions shift beyond thresholds
- **RAG Integration** — Cache article embeddings for historical context retrieval
- **Fine-Tuning** — Use human tie-breaker judgments to fine-tune local LLM
- **Reflexion Loops** — Add self-critique to Assessment Agent for improved confidence
- **Web Dashboard** — Visualize matrix, manage hypotheses, interface with human judgments

## Troubleshooting

| Issue | Solution |
|-------|----------|
| LLM not found | Ensure `ollama serve` is running. Check `LLM_ENDPOINT` in .env |
| GPU out of memory | Reduce `LLM_NUM_PASSES` from 10 to 5. Use CPU fallback. |
| Assessment timeouts | Increase `AGENT_TIMEOUT_SECONDS` in .env |
| Storage full | Set `MATRIX_STORAGE_CAP_GB` lower. Old snapshots auto-prune. |
| Articles not found | Check Reuters site structure. Verify `REUTERS_BASE_URL`. |

## References

- **ACH Framework**: Philip E. Heuer, *Psychology of Intelligence Analysis*
- **Self-Consistency**: Wei et al., *Self-Consistency Improves Chain of Thought Reasoning in Language Models*
- **LangChain/LangGraph**: State management for multi-agent systems
- **OpenSSF**: Deployment security best practices

## License

Academic project — Carnegie Mellon University Agentic AI Certificate Program

---

**Version**: 0.1.0 (July 2026)  
**Status**: Development (Pre-Production)  
**Last Updated**: 2026-06-22
