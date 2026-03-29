"""Source-grounded answer generation with citations and confidence."""

from __future__ import annotations

import re
import time
from collections.abc import AsyncIterator
from typing import Any

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Confidence, QueryResult, Source, TraceStep
from quantumrag.core.retrieve.fusion import ScoredChunk
from quantumrag.core.utils.text import detect_korean

logger = get_logger("quantumrag.generator")

# System prompts for different languages
_SYSTEM_PROMPT_EN = """You are a helpful assistant that answers questions based on the provided context.

Rules:
1. ONLY use information from the provided context to answer
2. Cite sources using [1], [2], etc. for each claim
3. If the context doesn't contain enough information, say so clearly
4. Be concise and accurate
5. At the end, rate your confidence: STRONGLY_SUPPORTED, PARTIALLY_SUPPORTED, or INSUFFICIENT_EVIDENCE"""

_SYSTEM_PROMPT_KO = """당신은 제공된 컨텍스트를 기반으로 질문에 답변하는 전문 도우미입니다.

핵심 원칙:
1. 컨텍스트에 있는 정보만 사용하세요. 없으면 INSUFFICIENT_EVIDENCE로 답하세요
2. 각 주장에 [1], [2] 등으로 출처를 인용하세요
3. 모든 출처를 빠짐없이 검토하세요. 상태(확정/진행중/계획)와 무관하게 모든 항목을 포함하세요
4. 수치/계산이 필요하면 관련 항목을 먼저 나열한 후 단계적으로 계산하세요
5. 여러 조건이 있으면 각 항목이 모든 조건을 충족하는지 개별 검증하세요
6. 비교/최상급 질문에는 후보를 모두 나열하고 비교한 후 답하세요
7. 서로 다른 출처의 수치가 다르면 각각의 수치와 출처를 모두 제시하세요
8. 특정 회사/조직에 대한 질문일 때 다른 회사의 정보를 혼동하지 마세요
9. 테이블이 있으면 모든 행과 열을 검토하세요. 정확한 셀 값(이름, 점수, 금액)을 그대로 인용하세요
10. 질문이 이름과 수치를 함께 요구하면 반드시 둘 다 포함하세요 (예: "모델명은 X이고 점수는 Y입니다")
11. 마지막에 신뢰도를 평가하세요: STRONGLY_SUPPORTED, PARTIALLY_SUPPORTED, INSUFFICIENT_EVIDENCE"""

_CONTEXT_TEMPLATE = """Context:
{context}

Question: {query}

Answer (with citations [1], [2], etc.):"""

_INSUFFICIENT_TEMPLATE_EN = """I don't have enough information to answer this question confidently.

I searched through {n_docs} document(s) but couldn't find sufficient relevant content.

Suggestions:
- Try rephrasing your question
- Add more documents to the knowledge base
- Check if the relevant documents have been ingested"""

_INSUFFICIENT_TEMPLATE_KO = """이 질문에 충분히 답변하기 위한 정보가 부족합니다.

{n_docs}개의 문서를 검색했으나 충분히 관련된 내용을 찾지 못했습니다.

제안:
- 질문을 다른 방식으로 시도해 보세요
- 관련 문서를 더 추가하세요
- 관련 문서가 인제스트되었는지 확인하세요"""


class Generator:
    """Source-grounded answer generator with citation support."""

    def __init__(
        self,
        llm_provider: Any,  # LLMProvider
        language: str = "auto",
        temperature: float = 0.1,
        max_tokens: int = 2048,
        confidence_threshold: float = 0.6,
        high_confidence_threshold: float = 0.8,
        low_confidence_threshold: float = 0.5,
        no_answer_penalty: float = 0.3,
        max_context_chars: int = 8000,
    ) -> None:
        self._llm = llm_provider
        self._language = language
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._confidence_threshold = confidence_threshold
        self._high_confidence_threshold = high_confidence_threshold
        self._low_confidence_threshold = low_confidence_threshold
        self._no_answer_penalty = no_answer_penalty
        self._max_context_chars = max_context_chars

    async def generate(
        self,
        query: str,
        chunks: list[ScoredChunk],
        sources: list[Source],
    ) -> QueryResult:
        """Generate an answer from retrieved chunks."""
        trace_steps: list[TraceStep] = []

        # Check if we have enough evidence
        if not chunks or (
            chunks and chunks[0].score < self._confidence_threshold * self._no_answer_penalty
        ):
            return self._insufficient_evidence(query, sources, trace_steps)

        # Build context
        context = self._build_context(chunks)
        system_prompt = self._get_system_prompt(query)
        user_prompt = _CONTEXT_TEMPLATE.format(context=context, query=query)

        # Generate answer
        t0 = time.perf_counter()
        response = await self._llm.generate(
            user_prompt,
            system=system_prompt,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        gen_ms = (time.perf_counter() - t0) * 1000

        trace_steps.append(
            TraceStep(
                step="generate",
                result=f"{response.tokens_out} tokens",
                latency_ms=gen_ms,
                details={
                    "model": response.model,
                    "tokens_in": response.tokens_in,
                    "tokens_out": response.tokens_out,
                    "cost": response.estimated_cost,
                },
            )
        )

        # Parse answer and confidence
        answer_text = response.text
        confidence = self._extract_confidence(answer_text, chunks)

        # Clean up confidence signal from answer text
        answer_text = self._clean_answer(answer_text)

        # Map citation numbers to sources
        cited_sources = self._map_citations(answer_text, sources)

        return QueryResult(
            answer=answer_text,
            sources=cited_sources,
            confidence=confidence,
            trace=trace_steps,
            metadata={
                "tokens_used": response.tokens_in + response.tokens_out,
                "estimated_cost": response.estimated_cost,
                "model": response.model,
            },
        )

    async def generate_stream(
        self,
        query: str,
        chunks: list[ScoredChunk],
    ) -> AsyncIterator[str]:
        """Generate answer as a stream of tokens."""
        if not chunks:
            yield self._get_insufficient_text(query, 0)
            return

        context = self._build_context(chunks)
        system_prompt = self._get_system_prompt(query)
        user_prompt = _CONTEXT_TEMPLATE.format(context=context, query=query)

        async for token in self._llm.generate_stream(
            user_prompt,
            system=system_prompt,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        ):
            yield token

    def _build_context(self, chunks: list[ScoredChunk]) -> str:
        """Build context string from chunks with source labels.

        Includes Adjacent Chunk Merging: consecutive chunks from the same
        document are merged into a single context unit, preventing information
        loss from chunk boundary splits (e.g., "확정 PoC" and "진행 중" in
        separate chunks).

        Fact-Aware Context Injection: when a chunk has structured facts
        (extracted at ingest time by fact_extractor), those verified facts
        are injected BEFORE the raw text so the LLM sees authoritative
        structured data first, reducing hallucination risk.

        Uses score-proportional budget: high-scoring chunks get full content,
        low-scoring chunks get truncated.
        """
        if not chunks:
            return ""

        # Adjacent Chunk Merging: merge consecutive chunks from same document
        merged = _merge_adjacent_chunks(chunks)

        budget = self._max_context_chars
        parts: list[str] = []
        total_chars = 0

        max_score = merged[0].score if merged else 1.0

        for i, sc in enumerate(merged, 1):
            header = f"[Source {i}]"
            if sc.chunk.metadata.get("title"):
                header += f" {sc.chunk.metadata['title']}"
            if sc.chunk.metadata.get("section"):
                header += f" — {sc.chunk.metadata['section']}"
            if sc.chunk.metadata.get("page"):
                header += f" (p.{sc.chunk.metadata['page']})"

            # Fact-Aware Context Injection: present verified structured data
            # before raw text to anchor LLM reasoning on extracted facts
            fact_block = _format_fact_block(sc.chunk.metadata.get("facts"))

            content = _normalize_status_headers(sc.chunk.content)
            # Proportional truncation: low-scoring chunks get less space
            score_ratio = sc.score / max_score if max_score > 0 else 0.5
            if score_ratio < 0.5 and len(content) > 300:
                content = content[:300] + "..."

            if fact_block:
                part = f"{header}\n{fact_block}\n{content}"
            else:
                part = f"{header}\n{content}"
            if parts and total_chars + len(part) > budget:
                remaining = budget - total_chars - len(header) - 10
                if remaining > 100:
                    part = f"{header}\n{content[:remaining]}..."
                    parts.append(part)
                break
            parts.append(part)
            total_chars += len(part)
        return "\n\n".join(parts)

    def _get_system_prompt(self, query: str) -> str:
        """Get system prompt based on language."""
        if self._language == "ko" or (self._language == "auto" and detect_korean(query)):
            return _SYSTEM_PROMPT_KO
        return _SYSTEM_PROMPT_EN

    def _extract_confidence(self, answer: str, chunks: list[ScoredChunk]) -> Confidence:
        """Extract confidence level from answer and retrieval scores."""
        answer_lower = answer.lower()

        # Check LLM's self-assessment
        if "strongly_supported" in answer_lower:
            return Confidence.STRONGLY_SUPPORTED
        if "insufficient_evidence" in answer_lower:
            return Confidence.INSUFFICIENT_EVIDENCE
        if "partially_supported" in answer_lower:
            return Confidence.PARTIALLY_SUPPORTED

        # Fallback: use retrieval scores
        if chunks:
            top_score = chunks[0].score
            if top_score > self._high_confidence_threshold:
                return Confidence.STRONGLY_SUPPORTED
            if top_score > self._low_confidence_threshold:
                return Confidence.PARTIALLY_SUPPORTED

        return Confidence.INSUFFICIENT_EVIDENCE

    def _clean_answer(self, text: str) -> str:
        """Remove confidence signal from answer text."""
        # Remove lines like "Confidence: STRONGLY_SUPPORTED"
        text = re.sub(
            r"\n*(?:Confidence|신뢰도):\s*(?:STRONGLY_SUPPORTED|PARTIALLY_SUPPORTED|INSUFFICIENT_EVIDENCE)\s*$",
            "",
            text,
            flags=re.IGNORECASE,
        )
        return text.strip()

    def _map_citations(self, answer: str, sources: list[Source]) -> list[Source]:
        """Map [1], [2] citations in answer to sources."""
        cited_numbers = set(int(m) for m in re.findall(r"\[(\d+)\]", answer))
        cited_sources = []
        for i, src in enumerate(sources, 1):
            if i in cited_numbers:
                cited_sources.append(src)
        # If no citations found, include all sources
        return cited_sources if cited_sources else sources

    def _insufficient_evidence(
        self,
        query: str,
        sources: list[Source],
        trace: list[TraceStep],
    ) -> QueryResult:
        text = self._get_insufficient_text(query, len(sources))
        return QueryResult(
            answer=text,
            sources=sources,
            confidence=Confidence.INSUFFICIENT_EVIDENCE,
            trace=trace,
        )

    def _get_insufficient_text(self, query: str, n_docs: int) -> str:
        if self._language == "ko" or (self._language == "auto" and detect_korean(query)):
            return _INSUFFICIENT_TEMPLATE_KO.format(n_docs=n_docs)
        return _INSUFFICIENT_TEMPLATE_EN.format(n_docs=n_docs)


def _format_fact_block(facts: list[dict[str, Any]] | None) -> str:
    """Format structured facts into a verified-data block for context injection.

    Returns an empty string if no facts are present or all facts are trivial.
    The block uses a distinctive header so the LLM can distinguish verified
    structured data from raw text.
    """
    if not facts:
        return ""

    lines: list[str] = []
    for f in facts:
        ft = f.get("type", "")
        if ft == "customer_contract":
            line = f"  - 고객: {f['customer']} | 등급: {f.get('tier', 'N/A')}"
            if f.get("deployment"):
                line += f" | 배포: {f['deployment']}"
            lines.append(line)
        elif ft == "finance_metric":
            lines.append(f"  - {f['metric']}: {f['value']}")
        elif ft == "fund_allocation":
            ctx = f.get("context", "")
            lines.append(f"  - {f['item']}: {f['value']}원" + (f" ({ctx})" if ctx else ""))
        elif ft == "security_issue":
            sev = f.get("severity", "N/A")
            status = f.get("status", "N/A")
            lines.append(f"  - {f['entity']}: 심각도={sev}, 상태={status}")
        elif ft == "team_info":
            lines.append(f"  - {f['team']}: {f['headcount']}명")
        elif ft == "team_leader":
            lines.append(f"  - {f['team']} 팀장: {f['leader']}")
        elif ft == "patent":
            status = f.get("status", "N/A")
            inv = ", ".join(f.get("inventors", [])) or "N/A"
            lines.append(f"  - {f['entity']}: 상태={status}, 발명자={inv}")
        elif ft == "product_version":
            lines.append(f"  - {f['version']} ({f.get('release_date', 'N/A')})")
        elif ft == "security_summary":
            sevs = ", ".join(f.get("severities", []))
            lines.append(f"  - 보안 심각도: {sevs}")

    if not lines:
        return ""
    return "[검증된 데이터 — 이 정보만이 이 출처에서 확인된 사실입니다]\n" + "\n".join(lines)


def _merge_adjacent_chunks(chunks: list[ScoredChunk]) -> list[ScoredChunk]:
    """Merge consecutive chunks from the same document section.

    When chunk splitting breaks related information across boundaries
    (e.g., "확정 PoC" in chunk N and "진행 중 PoC" in chunk N+1),
    this merges them into a single context unit so the LLM sees
    complete information.

    Only merges chunks that are:
    1. From the same document
    2. Adjacent by chunk_index (within distance 1)
    3. Share a parent breadcrumb section
    """
    if len(chunks) <= 1:
        return chunks

    # Group by document_id
    from collections import defaultdict

    doc_groups: dict[str, list[ScoredChunk]] = defaultdict(list)
    for sc in chunks:
        doc_id = getattr(sc.chunk, "document_id", "") or sc.chunk.metadata.get("document_id", "")
        doc_groups[doc_id].append(sc)

    merged: list[ScoredChunk] = []
    merged_ids: set[str] = set()

    for sc in chunks:
        if sc.chunk.id in merged_ids:
            continue

        doc_id = getattr(sc.chunk, "document_id", "") or sc.chunk.metadata.get("document_id", "")
        idx = getattr(sc.chunk, "chunk_index", -1)

        if idx < 0 or not doc_id:
            merged.append(sc)
            merged_ids.add(sc.chunk.id)
            continue

        # Find adjacent chunks from the same document that are also in our list
        adjacent_to_merge: list[ScoredChunk] = []
        for other in doc_groups.get(doc_id, []):
            if other.chunk.id == sc.chunk.id or other.chunk.id in merged_ids:
                continue
            other_idx = getattr(other.chunk, "chunk_index", -1)
            if other_idx >= 0 and abs(idx - other_idx) == 1:
                # Check if they share a parent section
                bc_a = sc.chunk.metadata.get("breadcrumb", "")
                bc_b = other.chunk.metadata.get("breadcrumb", "")
                if bc_a and bc_b:
                    parent_a = bc_a.strip("[]").rsplit(" > ", 1)[0] if " > " in bc_a else bc_a
                    parent_b = bc_b.strip("[]").rsplit(" > ", 1)[0] if " > " in bc_b else bc_b
                    if parent_a == parent_b:
                        adjacent_to_merge.append(other)
                elif doc_id:  # Same doc, adjacent index
                    adjacent_to_merge.append(other)

        if adjacent_to_merge:
            # Merge: combine content, keep higher score
            all_to_merge = [sc] + adjacent_to_merge
            all_to_merge.sort(key=lambda x: getattr(x.chunk, "chunk_index", 0))

            combined_content = "\n\n".join(s.chunk.content for s in all_to_merge)
            # Create a merged chunk using the first chunk's metadata
            from quantumrag.core.models import Chunk

            merged_chunk = Chunk(
                content=combined_content,
                document_id=doc_id,
                chunk_index=getattr(all_to_merge[0].chunk, "chunk_index", 0),
                metadata={**sc.chunk.metadata},
            )
            merged_chunk.id = sc.chunk.id  # Keep original ID for citation

            best_score = max(s.score for s in all_to_merge)
            merged.append(ScoredChunk(chunk=merged_chunk, score=best_score))

            for s in all_to_merge:
                merged_ids.add(s.chunk.id)
        else:
            merged.append(sc)
            merged_ids.add(sc.chunk.id)

    # Re-sort by score
    merged.sort(key=lambda x: x.score, reverse=True)
    return merged


def _normalize_status_headers(content: str) -> str:
    """Flatten status section headers into inline labels.

    Converts hierarchical status groupings into flat, uniform presentation.
    This prevents LLM from devaluing items under "진행 중" vs "확정" headers.

    Example:
        ### 확정 PoC (2건)
        1. 미쓰비시 — 2.5억원
        2. 소프트뱅크 — 1.8억원
        ### 진행 중 (1건)
        3. NTT — 3.2억원

    Becomes:
        1. 미쓰비시 — 2.5억원 [확정]
        2. 소프트뱅크 — 1.8억원 [확정]
        3. NTT — 3.2억원 [진행 중]
    """
    # Detect status section headers
    status_pattern = re.compile(
        r"^(#{1,4})\s+(.+?)\s*(?:\(\d+건?\))?\s*$",
        re.MULTILINE,
    )
    status_keywords = {"확정", "진행 중", "진행중", "계획", "예정", "완료", "보류", "검토", "미정"}

    matches = list(status_pattern.finditer(content))
    if not matches:
        return content

    # Check if any header contains a status keyword
    status_headers = []
    for m in matches:
        header_text = m.group(2).strip()
        for kw in status_keywords:
            if kw in header_text:
                status_headers.append((m, kw))
                break

    if not status_headers:
        return content

    # Process content: remove status headers, add inline status to list items
    lines = content.split("\n")
    result_lines: list[str] = []
    current_status = ""

    for line in lines:
        stripped = line.strip()

        # Check if this line is a status header
        header_match = re.match(r"^#{1,4}\s+(.+?)(?:\s*\(\d+건?\))?\s*$", stripped)
        if header_match:
            header_text = header_match.group(1).strip()
            matched_status = None
            for kw in status_keywords:
                if kw in header_text:
                    matched_status = kw
                    break
            if matched_status:
                current_status = matched_status
                continue  # Skip the header line
            else:
                # Non-status header — keep it
                current_status = ""

        # Add inline status label to list items
        if current_status and re.match(r"\s*(?:\d+\.|\-|\*|•)\s+", stripped):
            result_lines.append(f"{line} [{current_status}]")
        else:
            result_lines.append(line)

    return "\n".join(result_lines)
