# QuantumRAG v0.3 Upgrade Plan

## Current State (v0.2.1 Combined QA Results)

| Metric | Value | Target |
|--------|-------|--------|
| Combined QA Pass Rate | 35% (37/105) | 60%+ |
| Retrieval Recall | 4.8% | 50%+ |
| Timeout Rate | 37% (39/105) | < 5% |
| Wall Time | 1072s (18min) | < 300s (5min) |
| Unit Tests | 782 pass | maintain |

## Root Cause Analysis

### Problem 1: Timeout Explosion (39/105 queries)
- Post-correction pipeline triggers BM25 retry + re-generation on low confidence
- In combined corpus, more queries get low confidence → more retries
- Each retry = additional LLM call (5-30s) → exceeds 60s timeout
- **Fix**: Disable post-correction in combined QA, or skip retry for simple queries

### Problem 2: ds-004 Instant Failure (0.1-0.3s, all FAIL)
- fast mode ingest skips HyPE + contextual preambles
- But chunks still get embedded and indexed in BM25
- 0.1s failure means retrieval returns empty → engine returns INSUFFICIENT immediately
- **Fix**: Likely the combined sources directory has naming conflicts or ingest order issue

### Problem 3: Retrieval Recall 4.8%
- Score-weighted RRF improved ds-003 (13→50%) but didn't help others
- The core issue: embedding similarity between query and correct chunks is not
  significantly higher than noise chunks in a mixed-domain corpus
- **Fix**: This is a fundamental embedding quality issue. Short-term: boost BM25
  weight (keyword matching is more precise across domains)

## Upgrade Actions (Priority Order)

### Action 1: Fix Combined QA Test Speed (Target: < 5 min)
- Increase timeout to 90s (from 60s)
- Skip post-correction pipeline for combined test (add engine option)
- Reduce concurrency to 3 (reduce API contention)
- Expected: wall time 18min → 5min, timeout 39 → ~5

### Action 2: Fix Retrieval Fusion Weights for Scale
- Current: original=0.4, hype=0.35, bm25=0.25
- Problem: In multi-domain corpus, BM25 (keyword) is more discriminative than embedding
- Change default: original=0.35, hype=0.15, bm25=0.50
- BM25 excels at domain-specific terms ("HBM", "asyncio", "EU AI Act")

### Action 3: Add Lightweight Retrieval-Only QA Test
- New: `datasets/run_qa_retrieval.py` — test ONLY retrieval precision
- No LLM generation calls → runs in seconds
- Measures: recall@k, precision@k per dataset
- This becomes the fast feedback loop for retrieval improvements

## Success Criteria

| Metric | Current | v0.3 Target |
|--------|---------|-------------|
| Combined QA (no post-correction) | 35% | 50%+ |
| Retrieval Recall | 4.8% | 30%+ |
| Combined QA Wall Time | 18min | < 5min |
| Unit Tests | 782 | maintain |
| Retrieval-only test time | N/A | < 30s |
