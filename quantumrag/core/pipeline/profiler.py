"""Document profiler — analyzes document characteristics at ingest time.

The profiler runs once per document during ingest and produces a
DocumentProfile that guides all downstream pipeline decisions.
This is the core of the "Index-Heavy, Query-Light" approach to
domain adaptation.
"""

from __future__ import annotations

import re

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Document
from quantumrag.core.pipeline.context import (
    DocumentProfile,
    DomainType,
    InformationType,
)
from quantumrag.core.utils.text import (
    numeric_density as compute_numeric_density,
)
from quantumrag.core.utils.text import (
    split_sentences,
    tokenize,
    tokenize_set,
)

logger = get_logger("quantumrag.profiler")

# ---------------------------------------------------------------------------
# Domain vocabulary patterns
# ---------------------------------------------------------------------------

_DOMAIN_VOCABULARIES: dict[DomainType, set[str]] = {
    DomainType.LEGAL: {
        # Korean legal
        "조",
        "항",
        "호",
        "별첨",
        "계약",
        "당사자",
        "갑",
        "을",
        "위약금",
        "손해배상",
        "해지",
        "해제",
        "약정",
        "준거법",
        "관할",
        "소송",
        "판례",
        "법률",
        "규정",
        "조항",
        "의무",
        "권리",
        "시행령",
        "고시",
        # English legal
        "clause",
        "article",
        "agreement",
        "liability",
        "indemnify",
        "jurisdiction",
        "arbitration",
        "breach",
        "warranty",
        "termination",
        "pursuant",
        "notwithstanding",
        "herein",
        "thereof",
        "whereas",
    },
    DomainType.FINANCIAL: {
        # Korean financial
        "매출",
        "영업이익",
        "당기순이익",
        "자산",
        "부채",
        "자본",
        "배당",
        "투자",
        "수익률",
        "이자",
        "예산",
        "비용",
        "결산",
        "재무제표",
        "손익계산서",
        "대차대조표",
        "현금흐름",
        "전년대비",
        "성장률",
        "CAGR",
        "ROI",
        "ROE",
        "EBITDA",
        "시가총액",
        "PER",
        "PBR",
        # English financial
        "revenue",
        "profit",
        "margin",
        "asset",
        "dividend",
        "fiscal",
        "quarterly",
        "annual",
        "budget",
        "capex",
        "opex",
        "amortization",
    },
    DomainType.MEDICAL: {
        # Korean medical
        "환자",
        "진단",
        "치료",
        "투여",
        "부작용",
        "증상",
        "처방",
        "임상",
        "시험",
        "효능",
        "약물",
        "수술",
        "검사",
        "병력",
        # English medical
        "patient",
        "diagnosis",
        "treatment",
        "dosage",
        "symptom",
        "clinical",
        "trial",
        "efficacy",
        "adverse",
        "contraindication",
        "prognosis",
        "pathology",
        "pharmaceutical",
    },
    DomainType.TECHNICAL: {
        # Technical terms
        "API",
        "SDK",
        "배포",
        "서버",
        "데이터베이스",
        "아키텍처",
        "인프라",
        "컨테이너",
        "마이크로서비스",
        "CI/CD",
        "파이프라인",
        "쿠버네티스",
        "도커",
        "function",
        "class",
        "module",
        "deploy",
        "endpoint",
        "cluster",
        "container",
        "kubernetes",
        "docker",
        "terraform",
        "nginx",
        "repository",
        "commit",
        "branch",
        "merge",
    },
    DomainType.SUPPORT: {
        # Korean support
        "문의",
        "답변",
        "상담",
        "고객",
        "접수",
        "처리",
        "요청",
        "환불",
        "교환",
        "반품",
        "AS",
        "배송",
        "결제",
        "FAQ",
        "Q&A",
        # English support
        "ticket",
        "request",
        "resolution",
        "escalation",
        "SLA",
        "customer",
        "refund",
        "inquiry",
    },
}

# Structure detection patterns
_TABLE_PATTERNS = [
    re.compile(r"\|.*\|.*\|", re.MULTILINE),  # Markdown tables
    re.compile(r"<table[\s>]", re.IGNORECASE),  # HTML tables
    re.compile(r"\t.*\t", re.MULTILINE),  # Tab-delimited
]

_CODE_PATTERNS = [
    re.compile(r"```[\s\S]*?```"),  # Fenced code blocks
    re.compile(r"<code[\s>]", re.IGNORECASE),  # HTML code
    re.compile(r"^\s{4,}\S", re.MULTILINE),  # Indented code
    re.compile(r"(?:def |class |import |from |function |const |let |var )\w"),
]

_LIST_PATTERNS = [
    re.compile(r"^\s*[-*•]\s+", re.MULTILINE),  # Unordered lists
    re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE),  # Ordered lists
    re.compile(r"^\s*[가-힣]\.\s+", re.MULTILINE),  # Korean ordered lists
]

_HEADING_PATTERNS = [
    re.compile(r"^#{1,6}\s+", re.MULTILINE),  # Markdown headings
    re.compile(r"<h[1-6][\s>]", re.IGNORECASE),  # HTML headings
]

# Legal structure patterns
_LEGAL_STRUCTURE = re.compile(r"제\s*\d+\s*조|제\s*\d+\s*항|Article\s+\d+", re.IGNORECASE)

# Language detection
_KOREAN_CHAR = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")
_CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")
_LATIN_CHAR = re.compile(r"[a-zA-Z]")


class DocumentProfiler:
    """Analyzes documents to produce rich profiles for pipeline optimization.

    The profiler examines structure, content, language, and domain vocabulary
    to produce a DocumentProfile that guides chunking, retrieval, and
    generation strategies.

    Usage:
        profiler = DocumentProfiler()
        profile = profiler.profile(document)
        # profile is also written to document.metadata.custom["profile"]
    """

    def profile(self, document: Document) -> DocumentProfile:
        """Analyze a document and produce its profile.

        Args:
            document: Document to analyze.

        Returns:
            DocumentProfile with all detected characteristics.
        """
        content = document.content
        if not content or not content.strip():
            return DocumentProfile()

        profile = DocumentProfile(
            # Structure analysis
            structure_type=self._detect_structure(content),
            heading_depth=self._detect_heading_depth(content),
            paragraph_count=self._count_paragraphs(content),
            table_count=self._count_tables(content),
            list_count=self._count_lists(content),
            code_block_count=self._count_code_blocks(content),
            # Content analysis
            information_type=self._detect_information_type(content),
            avg_sentence_length=self._avg_sentence_length(content),
            vocabulary_richness=self._vocabulary_richness(content),
            # Language
            primary_language=self._detect_primary_language(content),
            language_mix=self._detect_language_mix(content),
            # Density
            information_density=self._information_density(content),
            numeric_density=self._numeric_density(content),
        )

        # Domain detection (uses multiple signals)
        domain, confidence, vocab = self._detect_domain(content, profile)
        profile.domain = domain
        profile.domain_confidence = confidence
        profile.domain_vocabulary = vocab

        # Strategy recommendations
        profile.recommended_chunking = self._recommend_chunking(profile)
        profile.recommended_fusion_weights = self._recommend_fusion_weights(profile)

        # Store in document metadata for downstream access
        document.metadata.custom["profile"] = profile.to_metadata()

        logger.debug(
            "document_profiled",
            doc_id=document.id,
            domain=profile.domain.value,
            domain_confidence=profile.domain_confidence,
            structure=profile.structure_type,
            info_type=profile.information_type.value,
            language=profile.primary_language,
        )

        return profile

    # --- Structure Detection ---

    def _detect_structure(self, content: str) -> str:
        """Detect document structure type."""
        has_headings = any(p.search(content) for p in _HEADING_PATTERNS)
        has_legal = bool(_LEGAL_STRUCTURE.search(content))
        has_tables = any(p.search(content) for p in _TABLE_PATTERNS)

        if has_legal:
            return "legal_hierarchical"
        if has_headings:
            return "hierarchical"
        if has_tables and not has_headings:
            return "tabular"
        if content.count("\n\n") >= 3:
            return "paragraphed"
        return "flat"

    def _detect_heading_depth(self, content: str) -> int:
        """Find maximum heading depth."""
        md_headings = re.findall(r"^(#{1,6})\s+", content, re.MULTILINE)
        if md_headings:
            return max(len(h) for h in md_headings)
        html_headings = re.findall(r"<h([1-6])", content, re.IGNORECASE)
        if html_headings:
            return max(int(h) for h in html_headings)
        return 0

    def _count_paragraphs(self, content: str) -> int:
        """Count paragraph breaks."""
        return len(re.split(r"\n\s*\n", content))

    def _count_tables(self, content: str) -> int:
        """Count table occurrences."""
        count = 0
        for p in _TABLE_PATTERNS:
            count += len(p.findall(content))
        return count

    def _count_lists(self, content: str) -> int:
        """Count list items."""
        count = 0
        for p in _LIST_PATTERNS:
            count += len(p.findall(content))
        return count

    def _count_code_blocks(self, content: str) -> int:
        """Count code blocks."""
        fenced = len(re.findall(r"```", content)) // 2
        indented = len(re.findall(r"^\s{4,}\S", content, re.MULTILINE))
        return fenced + (indented // 3)  # Rough: 3 indented lines ≈ 1 block

    # --- Content Analysis ---

    def _detect_information_type(self, content: str) -> InformationType:
        """Detect dominant information type."""
        scores: dict[InformationType, float] = {t: 0.0 for t in InformationType}

        table_count = self._count_tables(content)
        code_count = self._count_code_blocks(content)
        list_count = self._count_lists(content)
        has_legal = bool(_LEGAL_STRUCTURE.search(content))
        paragraph_count = self._count_paragraphs(content)

        if table_count >= 3:
            scores[InformationType.TABULAR] += 3.0
        elif table_count >= 1:
            scores[InformationType.TABULAR] += 1.5

        if code_count >= 2:
            scores[InformationType.CODE] += 3.0
        elif code_count >= 1:
            scores[InformationType.CODE] += 1.5

        if list_count >= 5:
            scores[InformationType.ENUMERATION] += 2.0
        elif list_count >= 2:
            scores[InformationType.ENUMERATION] += 1.0

        if has_legal:
            scores[InformationType.LEGAL] += 3.0

        if paragraph_count >= 3 and table_count == 0 and code_count == 0:
            scores[InformationType.NARRATIVE] += 2.0

        # Check for mixed
        active = sum(1 for s in scores.values() if s > 0)
        if active >= 2:
            max_score = max(scores.values())
            second = sorted(scores.values(), reverse=True)[1]
            if second > max_score * 0.5:
                return InformationType.MIXED

        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        if scores[best] == 0:
            return InformationType.NARRATIVE
        return best

    def _avg_sentence_length(self, content: str) -> float:
        """Average sentence length in words."""
        sentences = split_sentences(content)
        if not sentences:
            return 0.0
        total_words = sum(len(s.split()) for s in sentences)
        return total_words / len(sentences)

    def _vocabulary_richness(self, content: str) -> float:
        """Ratio of unique words to total words."""
        words = tokenize(content)
        if not words:
            return 0.0
        return len(set(words)) / len(words)

    # --- Language Detection ---

    def _detect_primary_language(self, content: str) -> str:
        """Detect the primary language."""
        mix = self._detect_language_mix(content)
        if not mix:
            return "unknown"
        return max(mix, key=mix.get)  # type: ignore[arg-type]

    def _detect_language_mix(self, content: str) -> dict[str, float]:
        """Detect language composition as ratios."""
        sample = content[:5000]
        total = len(sample)
        if total == 0:
            return {}

        ko_count = len(_KOREAN_CHAR.findall(sample))
        cjk_count = len(_CJK_CHAR.findall(sample))
        latin_count = len(_LATIN_CHAR.findall(sample))

        char_total = ko_count + cjk_count + latin_count
        if char_total == 0:
            return {"unknown": 1.0}

        result: dict[str, float] = {}
        if ko_count > 0:
            result["ko"] = round(ko_count / char_total, 2)
        if cjk_count > 0:
            result["zh"] = round(cjk_count / char_total, 2)
        if latin_count > 0:
            result["en"] = round(latin_count / char_total, 2)

        return result

    # --- Density Metrics ---

    def _information_density(self, content: str) -> float:
        """Non-whitespace ratio."""
        if not content:
            return 0.0
        non_ws = len(content.replace(" ", "").replace("\n", "").replace("\t", ""))
        return round(non_ws / len(content), 3)

    def _numeric_density(self, content: str) -> float:
        """Ratio of tokens that contain digits."""
        return compute_numeric_density(content.split())

    # --- Domain Detection ---

    def _detect_domain(
        self, content: str, profile: DocumentProfile
    ) -> tuple[DomainType, float, list[str]]:
        """Detect document domain using vocabulary matching and structure.

        Returns:
            (domain, confidence, top_domain_terms)
        """
        content_lower = content.lower()
        words = tokenize_set(content)

        scores: dict[DomainType, float] = {}
        matched_terms: dict[DomainType, list[str]] = {}

        for domain, vocab in _DOMAIN_VOCABULARIES.items():
            # Count word-level matches
            matches = words & {v.lower() for v in vocab}
            # Also check substring matches for multi-word terms
            substr_matches = set()
            for term in vocab:
                if len(term) > 3 and term.lower() in content_lower:
                    substr_matches.add(term)
            all_matches = matches | {m.lower() for m in substr_matches}
            scores[domain] = len(all_matches)
            matched_terms[domain] = sorted(all_matches)[:10]

        # Structure bonuses
        if profile.structure_type == "legal_hierarchical":
            scores[DomainType.LEGAL] = scores.get(DomainType.LEGAL, 0) + 5
        if profile.numeric_density > 0.15:
            scores[DomainType.FINANCIAL] = scores.get(DomainType.FINANCIAL, 0) + 2
        if profile.table_count >= 3:
            scores[DomainType.FINANCIAL] = scores.get(DomainType.FINANCIAL, 0) + 1

        if not scores or max(scores.values()) == 0:
            return DomainType.GENERAL, 0.0, []

        best_domain = max(scores, key=scores.get)  # type: ignore[arg-type]
        best_score = scores[best_domain]
        second_score = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0

        # Confidence: higher if dominant domain is clearly ahead
        if best_score == 0:
            confidence = 0.0
        elif second_score == 0:
            confidence = min(1.0, best_score / 5)
        else:
            ratio = best_score / (best_score + second_score)
            confidence = round(ratio * min(1.0, best_score / 3), 2)

        return best_domain, confidence, matched_terms.get(best_domain, [])

    # --- Strategy Recommendations ---

    def _recommend_chunking(self, profile: DocumentProfile) -> str:
        """Recommend chunking strategy based on profile."""
        if profile.structure_type in ("hierarchical", "legal_hierarchical"):
            return "structural"
        if profile.information_type == InformationType.TABULAR:
            return "structural"  # Preserve table boundaries
        if profile.paragraph_count >= 3:
            return "semantic"
        return "fixed"

    def _recommend_fusion_weights(self, profile: DocumentProfile) -> dict[str, float]:
        """Recommend Triple Index fusion weights based on profile."""
        if profile.domain == DomainType.LEGAL:
            return {"original": 0.2, "hype": 0.2, "bm25": 0.6}
        if profile.domain == DomainType.FINANCIAL:
            return {"original": 0.3, "hype": 0.3, "bm25": 0.4}
        if profile.domain == DomainType.SUPPORT:
            return {"original": 0.2, "hype": 0.6, "bm25": 0.2}
        if profile.domain == DomainType.TECHNICAL:
            return {"original": 0.5, "hype": 0.25, "bm25": 0.25}
        # General: balanced defaults
        return {"original": 0.4, "hype": 0.35, "bm25": 0.25}
