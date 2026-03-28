# Troubleshooting

Common issues and solutions for QuantumRAG.

## Installation

### `uv sync` fails with dependency conflicts

```bash
# Clean install
rm -rf .venv uv.lock
uv sync --dev
```

### `kiwipiepy` fails to install on Apple Silicon

```bash
# Ensure Rosetta 2 is installed
softwareupdate --install-rosetta
uv sync --dev
```

## API Keys

### "insufficient_quota" or 429 errors

The OpenAI/Anthropic API quota is exhausted.

- Check your billing at https://platform.openai.com/account/billing
- Switch to a cheaper model in config:
  ```yaml
  models:
    generation:
      simple: { provider: openai, model: gpt-4.1-mini }
  ```
- Use local models (zero cost):
  ```bash
  ollama pull gemma3
  quantumrag init --local
  ```

### "Invalid API key" on ingest

Ingest uses the embedding model. Check:
```bash
echo $OPENAI_API_KEY        # Must be set
echo $GEMINI_API_KEY        # If using Gemini embeddings
```

## Ingest Issues

### "No documents ingested"

1. Check file format is supported (PDF, DOCX, PPTX, XLSX, HWP, HWPX, MD, CSV, TXT, HTML)
2. Check file is not empty or corrupted
3. Try verbose mode: `quantumrag ingest ./docs --verbose`

### HWP files not parsed

Install the HWP parser:
```bash
uv pip install pyhwpx
```

### Ingest is slow

- Large PDFs with images are slow due to OCR. Use `mode: fast` to skip HyPE:
  ```python
  engine.ingest("./docs", mode="fast")     # Skip HyPE + preambles
  engine.ingest("./docs", mode="minimal")  # Fastest: parse + chunk + embed only
  ```
- Reduce `ingest.max_concurrency` if hitting API rate limits

## Query Issues

### Answers say "INSUFFICIENT_EVIDENCE" for everything

1. Check ingest completed: `quantumrag status`
2. Increase `retrieval.top_k` (default: 10)
3. Check if the query language matches document language
4. Try disabling compression: `retrieval.compression: false`

### Hallucinated answers (fabricated facts)

The fact verifier should catch these. If it doesn't:
1. Ensure `ingest.mode: full` was used (fact extraction needs full mode)
2. Check `generation.temperature: 0.0` (must be zero)
3. Look at the trace: `result.trace` shows each pipeline step

### Queries are slow (>30s)

Common causes:
- **Map-Reduce triggered**: Aggregation queries ("모두 알려줘", "총 합계") scan all chunks. This is by design but slow.
- **Post-correction pipeline**: Complex queries trigger retry + self-correct + fact verify + completeness. Check trace for which step is slow.
- **Reranker**: FlashRank is CPU-based. On slow machines, set `retrieval.rerank: false` for speed.

### Timeout after 120s (in QA runner)

The QA runner enforces a 120s per-query limit. Queries hitting this are typically:
- Comparison queries across many sources
- Aggregation queries triggering map_reduce on 20+ chunks
- These need pipeline optimization, not timeout increases

## Testing

### `make check` fails

```bash
make fix       # Auto-fix lint issues
make check     # Retry
```

### Scenario tests fail

Scenario tests require API keys (they call real LLMs):
```bash
export OPENAI_API_KEY=sk-...
export GEMINI_API_KEY=AI...
make scenario-test
```

### QA dataset runner errors

```bash
# Check dataset exists
ls datasets/ds-001/qa.yaml

# Run with full output
.venv/bin/python datasets/run_qa.py ds-001
```

## Server Issues

### Port already in use

```bash
quantumrag serve --port 8001   # Use different port
# Or kill existing process:
lsof -ti:8000 | xargs kill
```

### CORS errors from frontend

Set allowed origins:
```yaml
api:
  cors_origins: ["http://localhost:3000"]
```

## Performance Tuning

### For speed (low latency)

```yaml
ingest:
  mode: fast                    # Skip HyPE, preambles
retrieval:
  top_k: 5                     # Fewer candidates
  rerank: false                 # Skip reranker
  compression: false            # Skip compression
generation:
  max_tokens: 512               # Shorter answers
```

### For accuracy (high quality)

```yaml
ingest:
  mode: full                    # All enrichment
  chunking:
    strategy: semantic          # Better chunk boundaries
retrieval:
  top_k: 15                    # More candidates
  rerank: true                  # Reranker on
  retrieval_retry: true         # Retry on insufficient
generation:
  max_tokens: 2048
  max_context_chars: 16000      # More context to LLM
```

### For cost (minimize API calls)

```yaml
models:
  generation:
    simple: { provider: openai, model: gpt-4.1-mini }
    medium: { provider: openai, model: gpt-4.1-mini }
    complex: { provider: openai, model: gpt-4.1 }
  embedding:
    provider: gemini             # Free tier available
cost:
  semantic_cache: true           # Cache repeated queries
  prompt_caching: true
```

## Debug Mode

Enable verbose logging to diagnose issues:

```python
from quantumrag.core.engine import Engine
engine = Engine(verbose=True)

# Query with trace
result = engine.query("your question")
for step in result.trace:
    print(f"{step.step}: {step.result[:100]}")
```

Or via CLI:
```bash
quantumrag query "your question" --verbose
```
