"""Map-Reduce RAG — aggregation-aware query processing.

Solves the fundamental RAG limitation where top-k retrieval cannot answer
aggregation queries that require scanning ALL relevant chunks.

Example:
    "가장 많은 특허를 보유한 개인은?" requires:
    1. Broad retrieval of ALL patent chunks (not just top-k)
    2. MAP: Extract inventor names from each chunk
    3. REDUCE: Count per inventor, find maximum

Pipeline:
    [Aggregation detected] → [Broad retrieval k=20] → [Map: extract per chunk]
    → [Reduce: aggregate + answer]
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from quantumrag.core.logging import get_logger
from quantumrag.core.retrieve.fusion import ScoredChunk

logger = get_logger("quantumrag.map_reduce")

# Patterns that indicate an aggregation query (needs scanning ALL relevant chunks)
# Must be paired with domain indicators to avoid false positives
_AGGREGATION_PATTERNS = [
    # "가장 많은 X를 보유한 Y" — requires counting across chunks
    re.compile(r"가장\s*많은?\s*\w+을?\s*보유"),
    # "총 합계/규모/금액" — requires summing (allow intervening words)
    re.compile(r"총\s*(합계|규모|금액|인원|매출|비용)"),
    re.compile(r"총\s+\S+\s+.*(규모|금액|합계|비용)"),  # "총 예상 연 계약 규모"
    # "N건의 총" — specific count + aggregation
    re.compile(r"\d+\s*건.{0,10}총"),
    # "모두 알려/말해" — requires collecting info from all chunks
    re.compile(r"(?:모두|전부|모든).*(?:알려|말해)"),
    re.compile(r"각각\s*(?:알려|설명|말해|나열)"),
    # "전체 X 합/총/수" — requires aggregation
    re.compile(r"전체\s*\w+\s*(?:합|총|수)"),
    # Superlative + financial/contract terms — needs comparing ALL candidates
    re.compile(r"(?:가장|제일)\s*.{0,6}(?:큰|작은|높은|낮은|비싼|싼)\s*.{0,6}(?:계약|규모|금액|PoC|매출|투자)"),
]

# Patterns that look like aggregation but are really simple factual queries
_FALSE_POSITIVE_PATTERNS = [
    re.compile(r"가장\s*(큰|작은|높은|낮은)\s*(경쟁사|고객|회사|기업|제품)"),
]


def needs_aggregation(query: str) -> bool:
    """Detect if a query requires aggregation processing.

    Aggregation queries need to scan ALL chunks, not just top-k.
    Examples: "가장 많은 특허를 보유한 개인", "총 예산 합계"
    Non-examples: "가장 큰 경쟁사" (simple factual lookup)
    """
    # Check for false positives first
    if any(p.search(query) for p in _FALSE_POSITIVE_PATTERNS):
        return False
    return any(p.search(query) for p in _AGGREGATION_PATTERNS)


_MAP_PROMPT = """다음 텍스트에서 질문에 답하기 위해 필요한 핵심 정보만 추출하세요.

규칙:
- 질문의 조건(등급, 상태, 기간 등)에 정확히 부합하는 정보만 추출하세요
- 조건에 맞지 않는 정보는 추출하지 마세요
- "이상"은 해당 등급 포함 + 더 높은 등급 포함 (예: "High 이상" = High + Critical)
- 관련 정보가 없으면 "관련 정보 없음"이라고만 쓰세요

질문: {query}
텍스트: {chunk_content}

추출된 핵심 정보:"""

_REDUCE_PROMPT = """아래 여러 출처에서 추출된 정보를 종합하여 질문에 정확히 답하세요.

규칙:
1. 모든 추출 결과를 빠짐없이 검토하세요. 하나라도 놓치지 마세요
2. 질문의 조건(등급, 상태, 기간 등)에 부합하는 항목만 포함하세요
3. "모두 나열" 질문에는 조건에 맞는 모든 항목을 빠짐없이 나열하세요
4. 수량 질문은 정확한 숫자를 제시하세요
5. "가장 많은/큰" 등 최상급 질문은 모든 후보를 비교한 뒤 답하세요
6. 출처를 [1], [2] 등으로 인용하세요
7. 마지막에 STRONGLY_SUPPORTED로 신뢰도를 표시하세요

질문: {query}

추출된 정보:
{mapped_results}

종합 답변:"""


class MapReduceRAG:
    """Processes aggregation queries using a Map-Reduce pattern."""

    def __init__(self, llm_provider: Any) -> None:
        self._llm = llm_provider

    async def execute(
        self,
        query: str,
        chunks: list[ScoredChunk],
    ) -> str:
        """Execute Map-Reduce on the given chunks.

        Phase 1 (Map): Extract relevant info from each chunk in parallel.
        Phase 2 (Reduce): Aggregate extracted info into a final answer.
        """
        if not chunks:
            return "관련 정보를 찾을 수 없습니다."

        # Phase 1: Map — parallel extraction from each chunk
        map_tasks = [
            self._map_chunk(query, sc, i + 1)
            for i, sc in enumerate(chunks)
        ]
        map_results = await asyncio.gather(*map_tasks, return_exceptions=True)

        # Filter out failures and empty results
        valid_results: list[str] = []
        all_failed = True
        for i, result in enumerate(map_results):
            if isinstance(result, Exception):
                logger.warning("map_chunk_failed", chunk_index=i, error=str(result))
                # Fallback: include raw chunk content for failed map calls
                valid_results.append(f"[출처 {i + 1}] {chunks[i].chunk.content[:500]}")
                continue
            text = str(result).strip()
            if text and "관련 정보 없음" not in text:
                source_label = f"[출처 {i + 1}]"
                valid_results.append(f"{source_label} {text}")
                all_failed = False

        # If all map calls failed, include raw chunks directly for reduce
        if not valid_results or all_failed:
            valid_results = [
                f"[출처 {i + 1}] {sc.chunk.content[:500]}"
                for i, sc in enumerate(chunks)
            ]
            if not valid_results:
                return "여러 문서를 검색했으나 관련 정보를 종합하기 어렵습니다."

        # Phase 2: Reduce — aggregate into final answer
        combined = "\n".join(valid_results)
        logger.info(
            "map_reduce_reducing",
            query=query,
            map_results_count=len(valid_results),
            total_chunks=len(chunks),
        )

        try:
            response = await self._llm.generate(
                _REDUCE_PROMPT.format(query=query, mapped_results=combined),
                temperature=0.1,
                max_tokens=800,
            )
            return response.text.strip()
        except Exception as e:
            logger.error("reduce_failed", error=str(e))
            return f"정보 종합 중 오류가 발생했습니다: {combined}"

    async def _map_chunk(self, query: str, sc: ScoredChunk, index: int) -> str:
        """Extract relevant info from a single chunk."""
        response = await self._llm.generate(
            _MAP_PROMPT.format(query=query, chunk_content=sc.chunk.content),
            temperature=0.0,
            max_tokens=250,
        )
        return response.text.strip()
