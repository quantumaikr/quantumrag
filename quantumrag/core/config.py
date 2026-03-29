"""Configuration management for QuantumRAG.

Merge order: defaults <- yaml file <- environment variables <- code arguments
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# --- Nested config models ---


class EmbeddingModelConfig(BaseModel):
    provider: str = "gemini"  # openai, gemini, ollama, local
    model: str = "gemini-embedding-001"
    dimensions: int = 768
    api_key: str | None = None  # None → SDK 기본 환경 변수 사용
    base_url: str | None = None  # 커스텀 엔드포인트 (Azure 등)


class GenerationTierConfig(BaseModel):
    provider: str = "gemini"
    model: str = "gemini-3.1-flash-lite-preview"
    api_key: str | None = None  # None → SDK 기본 환경 변수 사용
    base_url: str | None = None  # 커스텀 엔드포인트 (Azure, Ollama 원격 등)


class GenerationConfig(BaseModel):
    simple: GenerationTierConfig = Field(
        default_factory=lambda: GenerationTierConfig(
            provider="gemini", model="gemini-3.1-flash-lite-preview"
        )
    )
    medium: GenerationTierConfig = Field(
        default_factory=lambda: GenerationTierConfig(
            provider="gemini", model="gemini-3.1-flash-lite-preview"
        )
    )
    complex: GenerationTierConfig = Field(
        default_factory=lambda: GenerationTierConfig(
            provider="gemini", model="gemini-3.1-flash-lite-preview"
        )
    )


class RerankerConfig(BaseModel):
    provider: str = "flashrank"  # flashrank, bge, cohere, jina, noop
    model: str | None = None  # provider-specific model override


class HypeConfig(BaseModel):
    provider: str = "gemini"
    model: str = "gemini-3.1-flash-lite-preview"
    questions_per_chunk: int = 4
    api_key: str | None = None
    base_url: str | None = None


class ModelsConfig(BaseModel):
    embedding: EmbeddingModelConfig = Field(default_factory=EmbeddingModelConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    hype: HypeConfig = Field(default_factory=HypeConfig)


class ChunkingConfig(BaseModel):
    strategy: str = "auto"  # auto, semantic, fixed, custom
    chunk_size: int = 512
    overlap: int = 50


class IngestConfig(BaseModel):
    mode: str = "fast"  # full, fast, minimal (fast recommended for Gemini free tier)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    quality_check: bool = True
    contextual_preamble: bool = True  # LLM-generated context for each chunk (Anthropic-style)
    max_concurrency: int = 3  # Max concurrent LLM calls (HyPE, preambles)
    parse_concurrency: int = 4  # Max concurrent document parsing threads


class FusionWeightsConfig(BaseModel):
    original: float = 0.35
    hype: float = 0.15
    bm25: float = 0.50


class RetrievalConfig(BaseModel):
    top_k: int = 12
    fusion_candidate_multiplier: int = 5
    fusion_weights: FusionWeightsConfig = Field(default_factory=FusionWeightsConfig)
    rerank: bool = True
    compression: bool = True
    slow_retrieval_threshold_ms: int = 2000
    retrieval_retry: bool = True  # Auto-retry with BM25-dominant strategy on insufficient evidence


class GenerationOutputConfig(BaseModel):
    streaming: bool = True
    max_tokens: int = 2048
    temperature: float = 0.0
    citation_style: str = "inline"  # inline, footnote
    confidence_signal: bool = True
    high_confidence_threshold: float = 0.8
    low_confidence_threshold: float = 0.5
    no_answer_penalty: float = 0.3
    max_context_chars: int = 16000


class EvaluationConfig(BaseModel):
    auto_synthetic: bool = True
    metrics: list[str] = Field(
        default_factory=lambda: [
            "retrieval_recall",
            "faithfulness",
            "answer_relevancy",
            "completeness",
            "latency",
            "cost",
        ]
    )


class StorageConfig(BaseModel):
    backend: str = "local"  # local, server, cluster
    vector_db: str = "lancedb"
    document_store: str = "sqlite"
    data_dir: str = "./quantumrag_data"


class CostConfig(BaseModel):
    budget_daily: float | None = None
    budget_monthly: float | None = None
    semantic_cache: bool = False
    prompt_caching: bool = True


class KoreanConfig(BaseModel):
    morphology: str = "kiwi"  # mecab, kiwi
    hwp_parser: str = "auto"  # auto, pyhwp, libreoffice
    mixed_script: bool = True


# --- Main config ---


class QuantumRAGConfig(BaseSettings):
    """Main configuration for QuantumRAG engine.

    Merge order: defaults <- yaml <- env vars <- code args
    """

    model_config = SettingsConfigDict(
        env_prefix="QUANTUMRAG_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_name: str = "my-knowledge-base"
    language: str = "auto"  # auto: detect from query language, ko, en
    domain: str = "general"  # general, legal, medical, financial, technical, support

    models: ModelsConfig = Field(default_factory=ModelsConfig)
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    generation: GenerationOutputConfig = Field(default_factory=GenerationOutputConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    cost: CostConfig = Field(default_factory=CostConfig)
    korean: KoreanConfig = Field(default_factory=KoreanConfig)

    @classmethod
    def from_yaml(cls, path: str | Path, **overrides: Any) -> QuantumRAGConfig:
        """Load config from YAML file with optional overrides."""
        _load_dotenv()
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        data.update(overrides)
        return cls(**data)

    @classmethod
    def default(cls, **overrides: Any) -> QuantumRAGConfig:
        """Create config with auto-detected provider and optional overrides.

        This is an alias for ``auto()`` — the recommended way to create
        a config. Detects available API keys and selects optimal models.
        """
        return cls.auto(**overrides)

    @classmethod
    def auto(cls, **overrides: Any) -> QuantumRAGConfig:
        """Auto-detect provider from environment and configure accordingly.

        Checks for API keys in order: Gemini → Anthropic → OpenAI → Ollama.
        Gemini is preferred for its free tier and cost-effectiveness.
        This is the recommended way to create a config for quick-start usage.

        Usage::

            config = QuantumRAGConfig.auto()
            # Or with overrides:
            config = QuantumRAGConfig.auto(language="en", storage={"data_dir": "/data"})
        """
        import os

        # Load .env file if present (for API keys like GOOGLE_API_KEY)
        _load_dotenv()

        provider, gen_models, emb_model, emb_dims = _detect_provider(os.environ)

        models_cfg = {
            "embedding": {"provider": provider, "model": emb_model, "dimensions": emb_dims},
            "generation": {
                "simple": {"provider": provider, "model": gen_models[0]},
                "medium": {"provider": provider, "model": gen_models[1]},
                "complex": {"provider": provider, "model": gen_models[2]},
            },
            "hype": {"provider": provider, "model": gen_models[0]},
        }

        # Merge with user overrides (overrides win)
        data: dict[str, Any] = {"models": models_cfg}
        data.update(overrides)
        return cls(**data)

    def to_yaml(self, path: str | Path) -> None:
        """Write config to YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.model_dump(mode="json")
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _load_dotenv() -> None:
    """Load .env file into os.environ if present."""
    import os

    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _detect_provider(
    env: Mapping[str, str],
) -> tuple[str, tuple[str, str, str], str, int]:
    """Detect the best available LLM provider from environment variables.

    Returns:
        (provider, (simple_model, medium_model, complex_model), embedding_model, embedding_dims)
    """
    # Gemini first: free tier available, cost-effective for most use cases
    if env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY"):
        return (
            "gemini",
            (
                "gemini-3.1-flash-lite-preview",
                "gemini-3.1-flash-lite-preview",
                "gemini-3.1-flash-lite-preview",
            ),
            "gemini-embedding-001",
            768,
        )
    if env.get("ANTHROPIC_API_KEY"):
        # Anthropic has no embedding model; pair with local embedding
        return (
            "anthropic",
            ("claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-sonnet-4-6"),
            "local:BAAI/bge-m3",
            1024,
        )
    if env.get("OPENAI_API_KEY"):
        return (
            "openai",
            ("gpt-5.4-nano", "gpt-5.4-mini", "gpt-5.4-mini"),
            "text-embedding-3-small",
            1536,
        )
    # Fallback: Ollama (local, no API key needed)
    return (
        "ollama",
        ("llama3.2:3b", "llama3.2:3b", "llama3.2:3b"),
        "local:BAAI/bge-m3",
        1024,
    )


def generate_default_yaml() -> str:
    """Generate a commented default YAML config template."""
    return """\
# QuantumRAG Configuration
# https://quantumrag.dev/docs/config

# Basic settings
project_name: "my-knowledge-base"
language: "auto"                        # auto (detect from query), ko, en
domain: "general"                       # general, legal, medical, financial, technical, support

# Model settings
models:
  embedding:
    provider: "gemini"
    model: "gemini-embedding-001"
    dimensions: 768
    # 로컬 임베딩 (API 키 불필요, 한국어 최적):
    # provider: "local"
    # model: "BAAI/bge-m3"
    # dimensions: 1024

  generation:
    simple:
      provider: "gemini"
      model: "gemini-3.1-flash-lite-preview"
    medium:
      provider: "gemini"
      model: "gemini-3.1-flash-lite-preview"
    complex:
      provider: "gemini"
      model: "gemini-3.1-flash-lite-preview"

  reranker:
    provider: "noop"                    # noop (disabled), flashrank (free/CPU), bge (free/multilingual), cohere, jina

  hype:                                 # HyPE question generation model
    provider: "gemini"
    model: "gemini-3.1-flash-lite-preview"
    questions_per_chunk: 3

# Ingest settings
ingest:
  mode: "full"                          # full (all enrichment), fast (skip HyPE/preamble), minimal (embed+BM25 only)
  chunking:
    strategy: "auto"                    # auto, semantic, fixed, custom
    chunk_size: 512                     # Token count
    overlap: 50                         # Overlap tokens
  quality_check: true                   # Parse quality verification
  contextual_preamble: true             # LLM-generated context per chunk (Anthropic-style)
  max_concurrency: 5                    # Max concurrent LLM calls (HyPE, preambles)
  parse_concurrency: 4                  # Max concurrent document parsing threads

# Retrieval settings
retrieval:
  top_k: 10
  fusion_weights:                       # Triple Index weights
    original: 0.35
    hype: 0.15
    bm25: 0.50
  fusion_candidate_multiplier: 4        # Candidates = top_k * multiplier
  rerank: true
  compression: true                     # Context compression
  retrieval_retry: true                 # Auto-retry with BM25-dominant strategy on insufficient evidence

# Generation settings
generation:
  streaming: true                        # Note: streaming skips correction pipeline
  max_tokens: 2048
  temperature: 0.0
  citation_style: "inline"             # inline, footnote
  confidence_signal: true
  high_confidence_threshold: 0.8       # Score above this = STRONGLY_SUPPORTED
  low_confidence_threshold: 0.5        # Score above this = PARTIALLY_SUPPORTED
  no_answer_penalty: 0.3               # Multiplier for insufficient evidence check
  max_context_chars: 16000             # Max characters in built context

# Evaluation settings
evaluation:
  auto_synthetic: true                  # Auto synthetic eval data generation
  metrics:
    - "retrieval_recall"
    - "faithfulness"
    - "answer_relevancy"
    - "completeness"
    - "latency"
    - "cost"

# Storage settings
storage:
  backend: "local"                      # local, server, cluster
  vector_db: "lancedb"                  # lancedb, chroma, faiss
  document_store: "sqlite"              # sqlite, postgresql
  data_dir: "./quantumrag_data"

# Cost settings
cost:
  budget_monthly: null                  # Monthly budget cap (null = unlimited) [planned]
  semantic_cache: false                 # Semantic cache [planned]
  prompt_caching: true                  # Provider prompt caching

# Korean-specific settings
korean:
  morphology: "kiwi"                    # mecab, kiwi
  hwp_parser: "auto"                    # auto, pyhwp, libreoffice
  mixed_script: true                    # Korean-English mixed processing

# API keys — 3가지 방법으로 설정 가능 (우선순위 순):
# 1. YAML config의 api_key 필드 (위 models 섹션 참고)
# 2. QuantumRAG 환경 변수: QUANTUMRAG_MODELS__EMBEDDING__API_KEY=sk-...
# 3. SDK 기본 환경 변수: OPENAI_API_KEY=sk-..., ANTHROPIC_API_KEY=sk-ant-..., GOOGLE_API_KEY=AIza...
"""
