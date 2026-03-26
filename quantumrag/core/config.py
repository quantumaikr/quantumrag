"""Configuration management for QuantumRAG.

Merge order: defaults <- yaml file <- environment variables <- code arguments
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# --- Nested config models ---


class EmbeddingModelConfig(BaseModel):
    provider: str = "openai"  # openai, gemini, ollama, local
    model: str = "text-embedding-3-small"
    dimensions: int = 1536
    api_key: str | None = None  # None → SDK 기본 환경 변수 사용
    base_url: str | None = None  # 커스텀 엔드포인트 (Azure 등)


class GenerationTierConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-5.4-nano"
    api_key: str | None = None  # None → SDK 기본 환경 변수 사용
    base_url: str | None = None  # 커스텀 엔드포인트 (Azure, Ollama 원격 등)


class GenerationConfig(BaseModel):
    simple: GenerationTierConfig = Field(
        default_factory=lambda: GenerationTierConfig(provider="openai", model="gpt-5.4-nano")
    )
    medium: GenerationTierConfig = Field(
        default_factory=lambda: GenerationTierConfig(provider="openai", model="gpt-5.4-mini")
    )
    complex: GenerationTierConfig = Field(
        default_factory=lambda: GenerationTierConfig(
            provider="openai", model="gpt-5.4-mini"
        )
    )


class RerankerConfig(BaseModel):
    provider: str = "flashrank"  # flashrank, bge, cohere, jina, noop
    model: str | None = None  # provider-specific model override


class HypeConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-5.4-nano"
    questions_per_chunk: int = 3
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
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    quality_check: bool = True
    contextual_preamble: bool = True  # LLM-generated context for each chunk (Anthropic-style)


class FusionWeightsConfig(BaseModel):
    original: float = 0.4
    hype: float = 0.35
    bm25: float = 0.25


class RetrievalConfig(BaseModel):
    top_k: int = 7
    fusion_candidate_multiplier: int = 3
    fusion_weights: FusionWeightsConfig = Field(default_factory=FusionWeightsConfig)
    rerank: bool = True
    compression: bool = True
    slow_retrieval_threshold_ms: int = 2000


class GenerationOutputConfig(BaseModel):
    streaming: bool = True
    max_tokens: int = 2048
    temperature: float = 0.1
    citation_style: str = "inline"  # inline, footnote
    confidence_signal: bool = True
    high_confidence_threshold: float = 0.8
    low_confidence_threshold: float = 0.5
    no_answer_penalty: float = 0.3
    max_context_chars: int = 12000


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
        extra="ignore",
    )

    project_name: str = "my-knowledge-base"
    language: str = "ko"
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
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        data.update(overrides)
        return cls(**data)

    @classmethod
    def default(cls, **overrides: Any) -> QuantumRAGConfig:
        """Create config with defaults and optional overrides."""
        return cls(**overrides)

    def to_yaml(self, path: str | Path) -> None:
        """Write config to YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.model_dump(mode="json")
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def generate_default_yaml() -> str:
    """Generate a commented default YAML config template."""
    return """\
# QuantumRAG Configuration
# https://quantumrag.dev/docs/config

# Basic settings
project_name: "my-knowledge-base"
language: "ko"                          # Primary language (ko, en, auto)
domain: "general"                       # general, legal, medical, financial, technical, support

# Model settings
models:
  embedding:
    provider: "openai"
    model: "text-embedding-3-small"
    dimensions: 1536
    # api_key: "sk-..."               # null → OPENAI_API_KEY 환경 변수 사용
    # base_url: "https://..."         # Azure OpenAI 등 커스텀 엔드포인트
    # 로컬 임베딩 (API 키 불필요, 한국어 최적):
    # provider: "local"
    # model: "BAAI/bge-m3"
    # dimensions: 1024

  generation:
    simple:
      provider: "openai"
      model: "gpt-5.4-nano"
      # api_key: "sk-..."
      # base_url: null
    medium:
      provider: "openai"
      model: "gpt-5.4-mini"
      # api_key: "sk-..."
      # base_url: null
    complex:
      provider: "openai"
      model: "gpt-5.4-mini"
      # api_key: "sk-..."
      # base_url: null
      # Anthropic 사용 예시:
      # provider: "anthropic"
      # model: "claude-sonnet-4-20250514"
      # api_key: "sk-ant-..."         # null → ANTHROPIC_API_KEY 환경 변수 사용
    # Gemini 사용 예시:
    # complex:
    #   provider: "gemini"
    #   model: "gemini-3.1-flash-lite-preview"
    #   api_key: "AIza..."            # null → GOOGLE_API_KEY 환경 변수 사용

  reranker:
    provider: "flashrank"               # flashrank (free/CPU), bge (free/multilingual), cohere, jina

  hype:                                 # HyPE question generation model
    provider: "openai"
    model: "gpt-5.4-nano"
    questions_per_chunk: 3
    # api_key: "sk-..."
    # base_url: null

# Ingest settings
ingest:
  chunking:
    strategy: "auto"                    # auto, semantic, fixed, custom
    chunk_size: 512                     # Token count
    overlap: 50                         # Overlap tokens
  quality_check: true                   # Parse quality verification
  contextual_preamble: true              # LLM-generated context per chunk (Anthropic-style)

# Retrieval settings
retrieval:
  top_k: 5
  fusion_weights:                       # Triple Index weights
    original: 0.4
    hype: 0.35
    bm25: 0.25
  fusion_candidate_multiplier: 3        # Candidates = top_k * multiplier
  rerank: true
  compression: true                     # Context compression

# Generation settings
generation:
  streaming: true
  max_tokens: 2048
  temperature: 0.1
  citation_style: "inline"             # inline, footnote
  confidence_signal: true
  high_confidence_threshold: 0.8       # Score above this = STRONGLY_SUPPORTED
  low_confidence_threshold: 0.5        # Score above this = PARTIALLY_SUPPORTED
  no_answer_penalty: 0.3               # Multiplier for insufficient evidence check
  max_context_chars: 8000              # Max characters in built context

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
  vector_db: "lancedb"                  # lancedb, qdrant, pgvector
  document_store: "sqlite"              # sqlite, postgresql
  data_dir: "./quantumrag_data"

# Cost settings
cost:
  budget_monthly: null                  # Monthly budget cap (null = unlimited)
  semantic_cache: false                 # Semantic cache (Phase 2)
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
