# Korean Language Support

> QuantumRAG treats Korean as a first-class citizen across the entire pipeline.

---

## Overview

Korean presents unique challenges for RAG systems: agglutinative morphology, mixed-script text, legacy encodings, and proprietary document formats. QuantumRAG addresses each of these natively.

| Challenge | Solution |
|-----------|----------|
| Agglutinative morphology | Kiwi morphological analysis for BM25 |
| Mixed Korean-English text | Separate tokenization per script |
| HWP document format | Native parser (olefile-based) |
| EUC-KR legacy encoding | Automatic detection and conversion |
| Korean query patterns | Morphology-aware routing and decomposition |
| Bilingual usage | Auto-switching system prompts |

---

## Setup

### Install Korean Dependencies

```bash
pip install quantumrag[korean]
# or
pip install kiwipiepy
```

### Configuration

```yaml
# quantumrag.yaml
language: "ko"

korean:
  morphology: "kiwi"      # kiwi (recommended) or mecab
  hwp_parser: "auto"       # auto, pyhwp, libreoffice
  mixed_script: true        # Korean-English mixed text handling
```

---

## Kiwi Morphological Analysis

[Kiwi](https://github.com/bab2min/kiwipiepy) (Korean Intelligent Word Identifier) provides accurate tokenization for Korean text.

### Why Kiwi Matters for BM25

Standard whitespace tokenization fails for Korean:

```
Input:  "보안이슈의심각도가높습니다"
Whitespace: ["보안이슈의심각도가높습니다"]  → 1 token (useless for search)
Kiwi:       ["보안", "이슈", "심각도", "높"]  → 4 meaningful tokens
```

QuantumRAG uses Kiwi in:
- **BM25 indexing**: Chunks are tokenized with Kiwi at ingest time
- **BM25 query**: Queries are tokenized the same way for matching
- **Derived Index**: Korean synonym/hierarchy terms are generated correctly

### Fallback

If Kiwi is not installed, QuantumRAG falls back to regex-based tokenization:

```
Pattern: [\uac00-\ud7a3]+ | [a-zA-Z]+ | [0-9]+
```

This is functional but less accurate for compound words and inflected forms.

---

## HWP/HWPX Document Parsing

HWP is the standard document format for Korean government and office documents.

### Supported Formats

| Format | Extension | Parser |
|--------|-----------|--------|
| HWP (binary) | `.hwp` | olefile-based parser |
| HWPX (XML) | `.hwpx` | XML-based parser |

### Usage

```python
engine = Engine()
engine.ingest("./government_docs")  # Automatically detects .hwp files
```

No special configuration needed — the HWP parser is auto-selected by file extension.

---

## Korean Query Processing

### Morphology-Aware Query Routing

QuantumRAG detects Korean-specific query patterns for optimal routing:

| Pattern | Detection | Action |
|---------|-----------|--------|
| Severity range | "High 등급 이상" | Entity index lookup with hierarchy |
| Status filter | "조치 완료된" | Entity index attribute filter |
| Enumeration | "모두 나열해주세요" | Broad retrieval (top_k=12) |
| Comparative | "차이점은 무엇인가요" | Complex routing |
| Temporal | "상반기 동안" | Temporal-aware retrieval |

### Entity Detection (Korean)

The entity detector recognizes Korean patterns:

```
"조치 완료된 High 등급 이상 보안 이슈의 ID를 모두 나열"
  → severity_gte: "High"
  → status: "완료"
  → domain: "security"
```

Supported Korean patterns:
- Severity: 심각, 높음, 중간, 낮음 → Critical, High, Medium, Low
- Status: 완료, 미조치, 미해결, 진행중, 보류
- Domain indicators: 보안, 특허, 버전, 고객

### Query Decomposition

Compound Korean questions are split into independent sub-queries:

```
"Series C 투자금의 가장 큰 사용 용도는 무엇이고 얼마인가요?"
  → Sub-query 1: "Series C 투자금의 가장 큰 사용 용도는 무엇인가요?"
  → Sub-query 2: (skipped — too short, < 10 chars)
```

A minimum 10-character threshold prevents useless fragments like "얼마인가요?".

---

## Bilingual System Prompts

QuantumRAG automatically selects Korean or English system prompts based on the query language.

### Korean Generation Rules

The Korean system prompt includes 11 specialized rules:

1. Answer only from provided context
2. Use inline citations `[1]`, `[2]`
3. Include all status information (confirmed/in-progress/planned)
4. List all items for quantity/amount questions
5. Present both figures with sources when numbers differ
6. Explain uncertainty and cite conflicting sources
7. Include specific numbers from context
8. Apply logical reasoning for conditional questions
9. Use `INSUFFICIENT_EVIDENCE` when context is insufficient
10. Never fabricate information
11. Do not confuse competitor information with the subject company's data

---

## Derived Index for Korean

At ingest time, Korean-specific search terms are generated:

| Source | Generated Terms |
|--------|----------------|
| severity:Critical | "Critical 이상", "High 이상", "Medium 이상" |
| status:완료 | "조치 완료된", "해결됨" |
| Date 2024-07-20 | "하반기", "Q3", "2024년 Q3" |
| Amount 3.2억 | "약 3억", "억 단위" |
| Version v2.4.0 | "v2.4", "2.4 버전" |

These terms are indexed in BM25, ensuring Korean queries match even when the exact phrasing differs.

---

## Mixed Script Handling

Korean documents frequently mix Hangul, Latin, and numbers:

```
"QuantumSoft의 2024년 Q3 매출은 150억원입니다"
```

QuantumRAG handles this by:
1. Detecting script boundaries
2. Applying optimal tokenizer per segment (Kiwi for Korean, standard for Latin)
3. Preserving cross-script entities (e.g., "Series C", "v2.4.0")

---

## EUC-KR Encoding Support

Legacy Korean documents often use EUC-KR encoding. QuantumRAG:

1. Auto-detects encoding from file content
2. Converts to UTF-8 transparently
3. Handles malformed sequences gracefully

No configuration needed — encoding detection is automatic during parsing.
