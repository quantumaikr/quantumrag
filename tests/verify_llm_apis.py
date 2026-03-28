"""Real LLM API verification script.

Verifies that QuantumRAG can actually call each configured provider
through its Engine/Provider layer with real API keys.

Usage:
    uv run python tests/verify_llm_apis.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

# Load .env file manually
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)

# ── Helpers ─────────────────────────────────────────────────────────────

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"

results: list[tuple[str, str, str]] = []  # (test_name, status, detail)


def record(name: str, status: str, detail: str = "") -> None:
    results.append((name, status, detail))
    symbol = PASS if status == "PASS" else FAIL if status == "FAIL" else SKIP
    print(f"  {symbol}  {name}" + (f"  ({detail})" if detail else ""))


# ── OpenAI Tests ────────────────────────────────────────────────────────


async def test_openai_generate() -> None:
    name = "OpenAI generate (gpt-5.4-nano)"
    if not os.environ.get("OPENAI_API_KEY"):
        record(name, "SKIP", "OPENAI_API_KEY not set")
        return
    try:
        from quantumrag.core.llm.providers.openai import OpenAILLMProvider

        provider = OpenAILLMProvider(model="gpt-5.4-nano")
        start = time.perf_counter()
        resp = await provider.generate(
            "1 + 1 = ?  Answer with just the number.",
            system="You are a calculator. Reply with only the number.",
            max_tokens=16,
        )
        latency = (time.perf_counter() - start) * 1000
        assert "2" in resp.text, f"Expected '2' in response, got: {resp.text!r}"
        detail = (
            f"text={resp.text!r}, tokens_in={resp.tokens_in}, "
            f"tokens_out={resp.tokens_out}, cost=${resp.estimated_cost:.6f}, "
            f"latency={latency:.0f}ms"
        )
        record(name, "PASS", detail)
    except Exception as exc:
        record(name, "FAIL", str(exc)[:200])


async def test_openai_stream() -> None:
    name = "OpenAI stream (gpt-5.4-nano)"
    if not os.environ.get("OPENAI_API_KEY"):
        record(name, "SKIP", "OPENAI_API_KEY not set")
        return
    try:
        from quantumrag.core.llm.providers.openai import OpenAILLMProvider

        provider = OpenAILLMProvider(model="gpt-5.4-nano")
        chunks: list[str] = []
        start = time.perf_counter()
        async for chunk in provider.generate_stream(
            "Say 'hello world' and nothing else.",
            max_tokens=16,
        ):
            chunks.append(chunk)
        latency = (time.perf_counter() - start) * 1000
        full = "".join(chunks)
        assert len(chunks) > 0, "No chunks received"
        record(name, "PASS", f"chunks={len(chunks)}, text={full!r}, latency={latency:.0f}ms")
    except Exception as exc:
        record(name, "FAIL", str(exc)[:200])


async def test_openai_structured() -> None:
    name = "OpenAI structured (gpt-5.4-nano)"
    if not os.environ.get("OPENAI_API_KEY"):
        record(name, "SKIP", "OPENAI_API_KEY not set")
        return
    try:
        from quantumrag.core.llm.providers.openai import OpenAILLMProvider

        provider = OpenAILLMProvider(model="gpt-5.4-nano")
        start = time.perf_counter()
        result = await provider.generate_structured(
            'Return JSON: {"capital": "<capital of France>"}',
            max_tokens=32,
        )
        latency = (time.perf_counter() - start) * 1000
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert "capital" in result, f"Missing 'capital' key in {result}"
        record(name, "PASS", f"result={result}, latency={latency:.0f}ms")
    except Exception as exc:
        record(name, "FAIL", str(exc)[:200])


async def test_openai_embedding() -> None:
    name = "OpenAI embedding (text-embedding-3-small)"
    if not os.environ.get("OPENAI_API_KEY"):
        record(name, "SKIP", "OPENAI_API_KEY not set")
        return
    try:
        from quantumrag.core.llm.providers.openai import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider(model="text-embedding-3-small", dimensions=1536)
        start = time.perf_counter()
        embeddings = await provider.embed(["안녕하세요", "Hello world"])
        latency = (time.perf_counter() - start) * 1000
        assert len(embeddings) == 2, f"Expected 2 embeddings, got {len(embeddings)}"
        assert len(embeddings[0]) == 1536, f"Expected 1536 dims, got {len(embeddings[0])}"

        # Also test single query
        query_emb = await provider.embed_query("테스트 쿼리")
        assert len(query_emb) == 1536

        record(
            name,
            "PASS",
            f"dims={len(embeddings[0])}, batch=2, latency={latency:.0f}ms",
        )
    except Exception as exc:
        record(name, "FAIL", str(exc)[:200])


# ── Gemini Tests ────────────────────────────────────────────────────────


async def test_gemini_generate() -> None:
    name = "Gemini generate (gemini-3.1-flash-lite-preview)"
    if not os.environ.get("GOOGLE_API_KEY"):
        record(name, "SKIP", "GOOGLE_API_KEY not set")
        return
    try:
        from quantumrag.core.llm.providers.gemini import GeminiLLMProvider

        provider = GeminiLLMProvider(model="gemini-3.1-flash-lite-preview")
        start = time.perf_counter()
        resp = await provider.generate(
            "1 + 1 = ?  Answer with just the number.",
            system="You are a calculator. Reply with only the number.",
            max_tokens=16,
        )
        latency = (time.perf_counter() - start) * 1000
        assert "2" in resp.text, f"Expected '2' in response, got: {resp.text!r}"
        detail = (
            f"text={resp.text!r}, tokens_in={resp.tokens_in}, "
            f"tokens_out={resp.tokens_out}, cost=${resp.estimated_cost:.6f}, "
            f"latency={latency:.0f}ms"
        )
        record(name, "PASS", detail)
    except Exception as exc:
        record(name, "FAIL", str(exc)[:200])


async def test_gemini_stream() -> None:
    name = "Gemini stream (gemini-3.1-flash-lite-preview)"
    if not os.environ.get("GOOGLE_API_KEY"):
        record(name, "SKIP", "GOOGLE_API_KEY not set")
        return
    try:
        from quantumrag.core.llm.providers.gemini import GeminiLLMProvider

        provider = GeminiLLMProvider(model="gemini-3.1-flash-lite-preview")
        chunks: list[str] = []
        start = time.perf_counter()
        async for chunk in provider.generate_stream(
            "Say 'hello world' and nothing else.",
            max_tokens=16,
        ):
            chunks.append(chunk)
        latency = (time.perf_counter() - start) * 1000
        full = "".join(chunks)
        assert len(chunks) > 0, "No chunks received"
        record(name, "PASS", f"chunks={len(chunks)}, text={full!r}, latency={latency:.0f}ms")
    except Exception as exc:
        record(name, "FAIL", str(exc)[:200])


async def test_gemini_structured() -> None:
    name = "Gemini structured (gemini-3.1-flash-lite-preview)"
    if not os.environ.get("GOOGLE_API_KEY"):
        record(name, "SKIP", "GOOGLE_API_KEY not set")
        return
    try:
        from quantumrag.core.llm.providers.gemini import GeminiLLMProvider

        provider = GeminiLLMProvider(model="gemini-3.1-flash-lite-preview")
        start = time.perf_counter()
        result = await provider.generate_structured(
            'Return JSON: {"capital": "<capital of France>"}',
            max_tokens=32,
        )
        latency = (time.perf_counter() - start) * 1000
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert "capital" in result, f"Missing 'capital' key in {result}"
        record(name, "PASS", f"result={result}, latency={latency:.0f}ms")
    except Exception as exc:
        record(name, "FAIL", str(exc)[:200])


async def test_gemini_embedding() -> None:
    name = "Gemini embedding (gemini-embedding-001)"
    if not os.environ.get("GOOGLE_API_KEY"):
        record(name, "SKIP", "GOOGLE_API_KEY not set")
        return
    try:
        from quantumrag.core.llm.providers.gemini import GeminiEmbeddingProvider

        provider = GeminiEmbeddingProvider(model="gemini-embedding-001", dimensions=3072)
        start = time.perf_counter()
        embeddings = await provider.embed(["안녕하세요", "Hello world"])
        latency = (time.perf_counter() - start) * 1000
        assert len(embeddings) == 2, f"Expected 2 embeddings, got {len(embeddings)}"
        assert len(embeddings[0]) == 3072, f"Expected 768 dims, got {len(embeddings[0])}"

        query_emb = await provider.embed_query("테스트 쿼리")
        assert len(query_emb) == 3072

        record(
            name,
            "PASS",
            f"dims={len(embeddings[0])}, batch=2, latency={latency:.0f}ms",
        )
    except Exception as exc:
        record(name, "FAIL", str(exc)[:200])


# ── Engine Integration Test ─────────────────────────────────────────────


async def test_engine_config_wiring() -> None:
    """Verify that Engine correctly wires config api_key/base_url to providers."""
    name = "Engine config → provider wiring"
    if not os.environ.get("OPENAI_API_KEY"):
        record(name, "SKIP", "OPENAI_API_KEY not set")
        return
    try:
        from quantumrag.core.config import QuantumRAGConfig
        from quantumrag.core.engine import Engine

        config = QuantumRAGConfig.default(
            models={
                "embedding": {
                    "provider": "openai",
                    "model": "text-embedding-3-small",
                    "dimensions": 1536,
                },
                "generation": {
                    "simple": {"provider": "openai", "model": "gpt-5.4-nano"},
                    "medium": {"provider": "openai", "model": "gpt-5.4-nano"},
                    "complex": {"provider": "openai", "model": "gpt-5.4-nano"},
                },
                "hype": {
                    "provider": "openai",
                    "model": "gpt-5.4-nano",
                },
            },
        )
        engine = Engine(config=config)

        # Verify embedding provider is created and works
        emb_provider = engine._get_embedding_provider()
        emb = await emb_provider.embed_query("테스트")
        assert len(emb) == 1536

        # Verify LLM provider is created and works
        from quantumrag.core.engine import QueryComplexity

        llm_provider = engine._get_llm_provider(QueryComplexity.SIMPLE)
        resp = await llm_provider.generate("Say OK", max_tokens=8)
        assert len(resp.text) > 0

        record(name, "PASS", f"embedding_dims={len(emb)}, llm_text={resp.text!r}")
    except Exception as exc:
        record(name, "FAIL", str(exc)[:200])


async def test_engine_gemini_wiring() -> None:
    """Verify Engine creates Gemini providers correctly from config."""
    name = "Engine Gemini config wiring"
    if not os.environ.get("GOOGLE_API_KEY"):
        record(name, "SKIP", "GOOGLE_API_KEY not set")
        return
    try:
        from quantumrag.core.config import QuantumRAGConfig
        from quantumrag.core.engine import Engine, QueryComplexity

        config = QuantumRAGConfig.default(
            models={
                "embedding": {
                    "provider": "gemini",
                    "model": "gemini-embedding-001",
                    "dimensions": 3072,
                },
                "generation": {
                    "simple": {
                        "provider": "gemini",
                        "model": "gemini-3.1-flash-lite-preview",
                    },
                    "medium": {
                        "provider": "gemini",
                        "model": "gemini-3.1-flash-lite-preview",
                    },
                    "complex": {
                        "provider": "gemini",
                        "model": "gemini-3.1-flash-lite-preview",
                    },
                },
                "hype": {
                    "provider": "gemini",
                    "model": "gemini-3.1-flash-lite-preview",
                },
            },
        )
        engine = Engine(config=config)

        emb_provider = engine._get_embedding_provider()
        emb = await emb_provider.embed_query("테스트")
        assert len(emb) == 3072

        llm_provider = engine._get_llm_provider(QueryComplexity.SIMPLE)
        resp = await llm_provider.generate("Say OK", max_tokens=8)
        assert len(resp.text) > 0

        record(name, "PASS", f"embedding_dims={len(emb)}, llm_text={resp.text!r}")
    except Exception as exc:
        record(name, "FAIL", str(exc)[:200])


# ── Main ────────────────────────────────────────────────────────────────


async def main() -> None:
    print("=" * 70)
    print("QuantumRAG — Real LLM API Verification")
    print("=" * 70)

    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_gemini = bool(os.environ.get("GOOGLE_API_KEY"))

    print(
        f"\n  API Keys: OpenAI={'SET' if has_openai else 'NOT SET'}, "
        f"Gemini={'SET' if has_gemini else 'NOT SET'}\n"
    )

    print("── OpenAI Provider ──")
    await test_openai_generate()
    await test_openai_stream()
    await test_openai_structured()
    await test_openai_embedding()

    print("\n── Gemini Provider ──")
    await test_gemini_generate()
    await test_gemini_stream()
    await test_gemini_structured()
    await test_gemini_embedding()

    print("\n── Engine Integration ──")
    await test_engine_config_wiring()
    await test_engine_gemini_wiring()

    # Summary
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    skipped = sum(1 for _, s, _ in results if s == "SKIP")
    total = len(results)

    print(f"\n{'=' * 70}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped / {total} total")
    print(f"{'=' * 70}")

    if failed > 0:
        print("\nFailed tests:")
        for name, status, detail in results:
            if status == "FAIL":
                print(f"  ✗ {name}: {detail}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
