"""QuantumRAG Korean Document Example.

This example shows how to use QuantumRAG with Korean documents,
including HWP files and Korean-aware search.

Requirements:
    pip install quantumrag[all]
    pip install kiwipiepy  # For Korean morphology (optional but recommended)
"""

from quantumrag import Engine

# Create engine with Korean language setting
engine = Engine()

# Ingest Korean documents (supports HWP, HWPX, PDF, DOCX, etc.)
result = engine.ingest("./korean-docs")
print(f"문서 {result.documents}개 인덱싱 완료, 청크 {result.chunks}개 생성")

# Ask questions in Korean
answer = engine.query("이 문서의 주요 내용은 무엇인가요?")
print(f"\n답변: {answer.answer}")
print(f"신뢰도: {answer.confidence.value}")

# Korean morphology-aware BM25 search works automatically
# when Kiwi is installed: pip install kiwipiepy

# Ask a comparison question (triggers Complex path)
answer = engine.query("A 정책과 B 정책의 차이점을 비교해주세요")
print(f"\n비교 답변: {answer.answer}")

# Ask a procedural question (triggers Medium path)
answer = engine.query("신청 절차는 어떻게 되나요?")
print(f"\n절차 답변: {answer.answer}")
