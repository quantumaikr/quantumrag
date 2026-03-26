"""Multi-tenant isolation — separate data and config per tenant.

Each tenant gets isolated storage (documents, vectors, BM25 index) while
sharing the same QuantumRAG instance for resource efficiency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quantumrag.core.logging import get_logger

logger = get_logger(__name__)

_TENANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")


@dataclass
class TenantConfig:
    """Configuration for a single tenant."""

    tenant_id: str
    display_name: str = ""
    data_dir: str = ""
    embedding_model: str | None = None
    generation_model: str | None = None
    max_documents: int | None = None
    max_queries_per_day: int | None = None
    allowed_file_types: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _TENANT_ID_PATTERN.match(self.tenant_id):
            msg = f"Invalid tenant ID: {self.tenant_id!r}. Must match [a-zA-Z0-9][a-zA-Z0-9_-]{{0,62}}"
            raise ValueError(msg)
        if not self.display_name:
            self.display_name = self.tenant_id


class TenantManager:
    """Manages tenant lifecycle and provides tenant-scoped engine access.

    Usage::

        manager = TenantManager(base_dir="/data/quantumrag")
        manager.create_tenant("acme-corp", display_name="Acme Corporation")

        engine = manager.get_engine("acme-corp")
        engine.ingest("./docs")
        result = engine.query("What is the policy?")
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._tenants: dict[str, TenantConfig] = {}
        self._engines: dict[str, Any] = {}  # Lazy engine cache
        self._load_tenants()

    def _load_tenants(self) -> None:
        """Load existing tenants from the base directory."""
        tenants_dir = self._base_dir / "tenants"
        if not tenants_dir.exists():
            return

        for path in tenants_dir.iterdir():
            if path.is_dir() and _TENANT_ID_PATTERN.match(path.name):
                config_file = path / "tenant.json"
                if config_file.exists():
                    import json

                    data = json.loads(config_file.read_text(encoding="utf-8"))
                    self._tenants[path.name] = TenantConfig(**data)
                else:
                    self._tenants[path.name] = TenantConfig(
                        tenant_id=path.name,
                        data_dir=str(path / "data"),
                    )

    def create_tenant(
        self,
        tenant_id: str,
        display_name: str = "",
        **kwargs: Any,
    ) -> TenantConfig:
        """Create a new tenant with isolated storage."""
        if tenant_id in self._tenants:
            msg = f"Tenant already exists: {tenant_id}"
            raise ValueError(msg)

        tenant_dir = self._base_dir / "tenants" / tenant_id
        data_dir = tenant_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        config = TenantConfig(
            tenant_id=tenant_id,
            display_name=display_name or tenant_id,
            data_dir=str(data_dir),
            **kwargs,
        )

        # Save config
        import json

        config_file = tenant_dir / "tenant.json"
        config_data = {
            "tenant_id": config.tenant_id,
            "display_name": config.display_name,
            "data_dir": config.data_dir,
            "max_documents": config.max_documents,
            "max_queries_per_day": config.max_queries_per_day,
            "allowed_file_types": config.allowed_file_types,
            "metadata": config.metadata,
        }
        if config.embedding_model:
            config_data["embedding_model"] = config.embedding_model
        if config.generation_model:
            config_data["generation_model"] = config.generation_model

        config_file.write_text(json.dumps(config_data, indent=2), encoding="utf-8")

        self._tenants[tenant_id] = config
        logger.info("tenant_created", tenant_id=tenant_id)
        return config

    def delete_tenant(self, tenant_id: str) -> bool:
        """Delete a tenant and all its data."""
        if tenant_id not in self._tenants:
            return False

        # Close any cached engine
        self._engines.pop(tenant_id, None)

        # Remove data
        tenant_dir = self._base_dir / "tenants" / tenant_id
        if tenant_dir.exists():
            import shutil

            shutil.rmtree(tenant_dir)

        del self._tenants[tenant_id]
        logger.info("tenant_deleted", tenant_id=tenant_id)
        return True

    def get_tenant(self, tenant_id: str) -> TenantConfig | None:
        """Get tenant configuration."""
        return self._tenants.get(tenant_id)

    def list_tenants(self) -> list[TenantConfig]:
        """List all tenants."""
        return list(self._tenants.values())

    def get_engine(self, tenant_id: str) -> Any:
        """Get or create an Engine instance scoped to a tenant.

        The engine uses isolated storage (separate document store,
        vector store, BM25 index) in the tenant's data directory.
        """
        if tenant_id not in self._tenants:
            msg = f"Unknown tenant: {tenant_id}"
            raise ValueError(msg)

        if tenant_id not in self._engines:
            from quantumrag.core.config import QuantumRAGConfig
            from quantumrag.core.engine import Engine

            config = self._tenants[tenant_id]
            engine_config = QuantumRAGConfig.default(
                storage={"data_dir": config.data_dir}
            )

            # Apply tenant-specific model overrides
            kwargs: dict[str, Any] = {}
            if config.embedding_model:
                kwargs["embedding_model"] = config.embedding_model
            if config.generation_model:
                kwargs["generation_model"] = config.generation_model

            self._engines[tenant_id] = Engine(config=engine_config, **kwargs)

        return self._engines[tenant_id]

    def tenant_status(self, tenant_id: str) -> dict[str, Any]:
        """Get status information for a tenant."""
        config = self._tenants.get(tenant_id)
        if not config:
            return {"error": f"Unknown tenant: {tenant_id}"}

        data_dir = Path(config.data_dir)
        total_size = sum(
            f.stat().st_size for f in data_dir.rglob("*") if f.is_file()
        ) if data_dir.exists() else 0

        result: dict[str, Any] = {
            "tenant_id": config.tenant_id,
            "display_name": config.display_name,
            "data_dir": config.data_dir,
            "storage_bytes": total_size,
            "storage_mb": round(total_size / (1024 * 1024), 2),
        }

        # Try to get engine status
        try:
            engine = self.get_engine(tenant_id)
            result.update(engine.status())
        except Exception:
            pass

        return result
