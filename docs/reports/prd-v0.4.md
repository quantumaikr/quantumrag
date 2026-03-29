# PRD: QuantumRAG v0.4 — Production-Grade Retrieval

## Goal
Combined QA 80% → 90%+ with full 105 questions (no sampling bias).

## Success Metrics
| Metric | v0.3 Baseline | v0.4 Target |
|--------|--------------|-------------|
| Combined QA (full 105q) | ~65% estimated | 80%+ |
| Combined QA (sampled 20q) | 80% | 90%+ |
| Timeout | 0/20 | 0/105 |
| Wall Time (full) | N/A | < 10min |
| Wall Time (sampled) | 2.1min | < 2min |

## WBS (Work Breakdown)

### Phase 1: Generator Prompt (30min, +3-5%)
- [ ] Add table-aware rules to Korean system prompt
- [ ] Add multi-keyword validation rule
- [ ] Test: individual ds-004 QA

### Phase 2: Adaptive Fetch (30min, +4%)
- [ ] Scale fetch_k by corpus chunk count
- [ ] Move document coherence boost before RRF
- [ ] Test: Combined QA sampled

### Phase 3: Full Test Infrastructure (20min)
- [ ] Run full 105 questions (SAMPLE_PER_DATASET=0)
- [ ] Establish true baseline without sampling bias
- [ ] Identify all failures for targeted fixes

### Phase 4: Post-Correction Merge (30min, +2%)
- [ ] Merge RetrievalRetry + SelfCorrect into single adaptive processor
- [ ] Add per-query strategy selection
- [ ] Test: Combined QA full

### Phase 5: Final Validation & Release (20min)
- [ ] Run full Combined QA 3 times for consistency
- [ ] Update documentation
- [ ] Version bump, commit, push
