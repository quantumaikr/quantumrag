# QuantumRAG — Open-Source RAG Engine That Actually Works

> March 31, 2026 | v0.4.4 | Apache 2.0

## TL;DR

Put documents in. Ask questions. Get cited answers. **No configuration needed.**

```python
from quantumrag import Engine

engine = Engine()
engine.ingest("./docs")
result = engine.query("What are the key findings?")
print(result.answer)   # ... [1][2] + Confidence: STRONGLY_SUPPORTED
```

## The Problem

Most RAG systems embed documents into vectors and hope the right chunks come back. When questions are phrased differently, when answers span multiple documents, or when you need exact entity matches — they fail silently.

QuantumRAG takes a different approach: **understand documents deeply at indexing time, so queries are fast and accurate by default.**

## How It Works

### Triple Index Fusion

Three retrieval methods combined via Score-Weighted Reciprocal Rank Fusion — each catches what the others miss:

| Index | What It Finds | Why It Matters |
|-------|--------------|----------------|
| **Original Embedding** | Semantically similar content | Handles paraphrasing |
| **HyPE Embedding** | Content that answers similar questions | Bridges question↔document gap |
| **Contextual BM25** | Exact keyword and entity matches | Precise for names, numbers, IDs |

### Hallucination Prevention

Two-layer defense:
1. **Fact Verifier** (Hard Gate): Cross-checks answers against facts extracted at ingest time. Zero LLM cost.
2. **System Prompt** (Soft Gate): 11 generation rules enforce source-only answers with citations.

### Adaptive Post-Correction

After generation, an automatic correction pipeline runs within a 20-second time budget:
- Retrieval Retry → Self-Correction → Fact Verification → Completeness Check
- Simple queries skip correction entirely (zero overhead on happy path)

## Korean as a First Language

Not a translation — designed from the ground up:

| Feature | Description |
|---------|-------------|
| HWP/HWPX Parsing | Native Korean government document support |
| Kiwi Morphology | Accurate Korean tokenization for BM25 |
| EUC-KR Detection | Automatic legacy encoding conversion |
| Mixed Script | Optimal tokenizer for Korean-English mixed text |
| Auto Language | Detects query language, responds in the same language |

## Measured Performance

105 QA questions across 73 source documents (including 50 noise documents):

- **Combined QA: 75% pass rate** (improved from 29% through 6 measurement-driven iterations)
- **Zero timeouts**
- 176 scenario tests, 831 unit tests, mypy 0 errors

## Zero Cost to Start

- **Embedding**: Microsoft Harrier 270M (local, free, MTEB 66.5, 94 languages)
- **LLM**: Gemini free tier (gemini-3.1-flash-lite-preview)
- **Reranker**: FlashRank (CPU, free)
- **No GPU required**

## Try It in 30 Seconds

```bash
pip install quantumrag
quantumrag demo
# Open http://localhost:8000
```

Or with Docker:

```bash
docker run -e GOOGLE_API_KEY=AIza... -p 8000:8000 quantumrag
```

## Three Ways to Use It

| | What You Do | What Happens |
|---|-------------|-------------|
| **Just use it** | `engine.ingest("./docs")` → `engine.query("...")` | Parser, chunker, index, routing — all auto-selected |
| **Tune it** | Adjust fusion weights, pick models, set domain | Better results for your specific use case |
| **Own it** | Custom parsers, chunkers, retrievers, generators | Every layer is replaceable via plugins |

## Supported Formats

PDF, DOCX, PPTX, XLSX, HWP/HWPX, HTML, Markdown, CSV, TXT

## Web Playground

Built-in interactive UI at `http://localhost:8000`:
- Upload documents (drag & drop) or paste text
- Ask questions with streaming or detailed mode
- Inspect pipeline trace with latency breakdown
- View source citations with relevance scores

## Comparison

| Feature | QuantumRAG | LangChain | LlamaIndex | OpenAI file_search |
|---------|:----------:|:---------:|:----------:|:------------------:|
| Triple Index Fusion | Yes | No | No | No |
| Hallucination Prevention | Yes | No | No | No |
| Korean Native (HWP, Kiwi) | Yes | Plugin | Plugin | No |
| Zero Config to First Answer | Yes | No | No | Partial |
| Zero GPU Required | Yes | Depends | Depends | N/A |
| Open Source | Apache 2.0 | MIT | MIT | No |

## Links

- **GitHub**: https://github.com/quantumaikr/quantumrag
- **PyPI**: `pip install quantumrag`
- **Docs**: [English](../../docs/en/index.md) | [한국어](../../docs/ko/index.md)
- **License**: Apache 2.0

---

*QuantumAI Inc. — hi@quantumai.kr*
