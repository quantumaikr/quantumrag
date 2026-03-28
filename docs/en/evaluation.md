# Evaluation

> Built-in evaluation system for measuring and improving RAG quality.

---

## Overview

QuantumRAG includes a comprehensive evaluation system that measures retrieval and generation quality across 6 metrics. It supports both synthetic QA generation and custom benchmark files.

---

## Quick Start

```python
from quantumrag import Engine

engine = Engine()
engine.ingest("./docs")

result = engine.evaluate()
print(result.summary)
for metric in result.metrics:
    print(f"  {metric.name}: {metric.score:.2f}")
for suggestion in result.suggestions:
    print(f"  - {suggestion}")
```

---

## Metrics

| Metric | Description | Range |
|--------|-------------|-------|
| **retrieval_recall** | Percentage of relevant chunks retrieved | 0.0 - 1.0 |
| **faithfulness** | Percentage of answer supported by retrieved sources | 0.0 - 1.0 |
| **answer_relevancy** | Percentage of answer that directly addresses the query | 0.0 - 1.0 |
| **completeness** | Percentage of query aspects covered in the answer | 0.0 - 1.0 |
| **latency** | Average query processing time | seconds |
| **cost** | Average cost per query | USD |

### Metric Details

**Retrieval Recall**: Measures whether the retrieval pipeline finds the right chunks. High recall means relevant information isn't being missed.

**Faithfulness**: Measures hallucination risk. Every claim in the answer should be supported by a retrieved source. Low faithfulness indicates the model is generating unsupported claims.

**Answer Relevancy**: Measures how directly the answer addresses the query. Low relevancy indicates off-topic or overly broad responses.

**Completeness**: Measures whether all aspects of a multi-part question are addressed. Low completeness indicates partial answers.

---

## Synthetic QA Generation

When no benchmark file is provided, QuantumRAG auto-generates QA pairs from indexed documents:

```python
result = engine.evaluate(sample_count=20)
```

The synthetic QA generator:
1. Selects representative document sections
2. Uses LLM to generate questions per section
3. Extracts expected answers from chunk content
4. Classifies difficulty (simple / medium / hard)

---

## Custom Benchmark

Provide your own QA benchmark as JSON:

```json
[
  {
    "question": "What chunking strategies does QuantumRAG support?",
    "expected_answer": "auto, structural, semantic, fixed",
    "reference_chunks": ["chunk_id_1", "chunk_id_2"]
  },
  {
    "question": "Who is the CTO?",
    "expected_answer": "Jane Doe",
    "reference_chunks": ["chunk_id_3"]
  }
]
```

```python
result = engine.evaluate(benchmark_file="benchmark.json")
```

Via CLI:

```bash
quantumrag evaluate --benchmark benchmark.json
```

Via API:

```bash
curl -X POST http://localhost:8000/v1/evaluate \
  -H "Content-Type: application/json" \
  -d '{"benchmark_file": "benchmark.json", "sample_count": 50}'
```

---

## A/B Comparison

Compare two configurations side by side:

```python
from quantumrag.core.evaluate.evaluator import Evaluator

evaluator = Evaluator(engine)
comparison = await evaluator.compare(
    config_a={"retrieval": {"top_k": 5}},
    config_b={"retrieval": {"top_k": 10}},
    sample_count=20,
)
```

---

## Scenario Test Suite

QuantumRAG includes a comprehensive E2E scenario test suite with 87 test cases across 16 categories and 4 difficulty levels.

### Categories

| # | Category | Tests | Description |
|---|----------|:-----:|-------------|
| S1 | Factual Confirmation | 7 | Basic fact retrieval, personnel, dates |
| S2 | Multi-Hop Reasoning | 6 | Cross-document information fusion |
| S3 | Numerical Calculations | 6 | Math, percentages, comparisons |
| S4 | Temporal Reasoning | 6 | Timeline, changelog, version tracking |
| S5 | Negation/Exclusion | 5 | "Not supported", incomplete features |
| S6 | Cross-Document Synthesis | 5 | Multi-source data integration |
| S7 | Paraphrase Robustness | 6 | Colloquial and rephrased queries |
| S8 | Multi-Turn Conversation | 5 | Coreference resolution, entity tracking |
| S9 | Edge Cases | 7 | Boundary inputs, adversarial queries |
| S10 | Precision Search | 6 | Fine-grained detail extraction |
| S11 | Implicit Inference | 5 | Information not directly stated |
| S12 | Competitive Analysis | 3 | Market positioning, competitor comparison |
| S13 | Conditional Reasoning | 5 | IF/THEN scenarios, sufficiency checks |
| S14 | Multi-Constraint Filtering | 5 | Multiple criteria intersection |
| S15 | Derived Quantitative | 5 | Calculations from multiple sources |
| S16 | Cross-Verification | 4 | Consistency checks across documents |

### Difficulty Distribution

| Level | Count | Description |
|-------|:-----:|-------------|
| Easy | 18 | Single-hop factual queries |
| Medium | 37 | Multi-step reasoning |
| Hard | 21 | Cross-document synthesis |
| Extreme | 6 | Complex conditional + aggregation |

### Running Scenario Tests

```bash
uv run python tests/run_scenario_tests.py
```

Output includes per-scenario pass/fail with latency and confidence details.

---

## QA Dataset Framework

A structured approach to RAG validation using real-world web content.

### Individual QA (per-dataset)

Each dataset tests specific RAG capabilities in isolation:

```bash
.venv/bin/python datasets/run_qa.py ds-001    # Run specific dataset
.venv/bin/python datasets/run_qa.py            # Auto-select latest
```

Features:
- **Ingest caching**: Skip re-ingest if sources unchanged (SHA256 hash check)
- **Per-query timeout**: 120s limit prevents slow queries from blocking
- **Parallel execution**: 3 concurrent queries
- **Auto-graduation**: When pass_rate >= threshold for min_runs, status updates automatically

| Dataset | Focus | Sources | Questions | Threshold |
|---------|-------|:-------:|:---------:|:---------:|
| ds-001 | Multilingual + numerical precision | 4 | 20 | 85% |
| ds-002 | Type system + cross-topic confusion | 6 | 25 | 80% |
| ds-003 | Dense technical + cross-document | 7 | 30 | 75% |
| ds-004 | Table extraction + contradiction detection | 6 | 30 | 75% |

### Combined QA (retrieval precision)

Merges all datasets into a single corpus to test retrieval under noise — what individual tests cannot catch.

```bash
.venv/bin/python datasets/run_qa_combined.py
```

Key metrics:
- **Retrieval Recall**: Did the engine find chunks from the correct source documents?
- **Noise Ratio**: What fraction of retrieved chunks are from irrelevant sources?
- **Degradation**: How much does pass rate drop vs individual tests?

Baseline results (23 sources, ~300 chunks, 105 questions):
- Individual: 83% avg → Combined: 29% (-54% degradation)
- Retrieval Recall: 9% — confirms retrieval is the key bottleneck at scale
- 68/75 failures are retrieval-caused, not generation-caused

### QA Lifecycle

```
/qa-create → /qa-run → /qa-analyze → /qa-improve → /qa-run (verify) → graduated
```

Full status: `datasets/STATUS.md`

---

## Configuration

```yaml
evaluation:
  auto_synthetic: true       # Auto-generate QA pairs when no benchmark provided
  metrics:
    - "retrieval_recall"
    - "faithfulness"
    - "answer_relevancy"
    - "completeness"
    - "latency"
    - "cost"
```
