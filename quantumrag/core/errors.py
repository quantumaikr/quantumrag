"""Custom exception hierarchy for QuantumRAG."""

from __future__ import annotations


class QuantumRAGError(Exception):
    """Base exception for all QuantumRAG errors."""

    def __init__(self, message: str, suggestion: str = "") -> None:
        self.suggestion = suggestion
        full_msg = message
        if suggestion:
            full_msg = f"{message}\n  Hint: {suggestion}"
        super().__init__(full_msg)


class ConfigError(QuantumRAGError):
    """Configuration-related errors."""

    def __init__(self, message: str, suggestion: str = "") -> None:
        if not suggestion:
            suggestion = "Check your quantumrag.yaml or environment variables."
        super().__init__(message, suggestion)


class ParseError(QuantumRAGError):
    """Document parsing errors."""

    def __init__(self, message: str, file_path: str = "", suggestion: str = "") -> None:
        self.file_path = file_path
        if not suggestion and file_path:
            suggestion = f"Check that '{file_path}' is a valid, non-corrupted file."
        super().__init__(message, suggestion)


class IndexingError(QuantumRAGError):
    """Indexing errors."""

    def __init__(self, message: str, suggestion: str = "") -> None:
        if not suggestion:
            suggestion = "Try rebuilding the index with 'quantumrag ingest --rebuild'."
        super().__init__(message, suggestion)


class RetrievalError(QuantumRAGError):
    """Retrieval/search errors."""

    def __init__(self, message: str, suggestion: str = "") -> None:
        if not suggestion:
            suggestion = "Ensure documents have been ingested and the index is not corrupted."
        super().__init__(message, suggestion)


class GenerationError(QuantumRAGError):
    """LLM generation errors."""

    def __init__(self, message: str, provider: str = "", suggestion: str = "") -> None:
        self.provider = provider
        if not suggestion and provider:
            suggestion = f"Check your {provider} API key and network connectivity."
        super().__init__(message, suggestion)


class StorageError(QuantumRAGError):
    """Storage layer errors."""

    def __init__(self, message: str, suggestion: str = "") -> None:
        if not suggestion:
            suggestion = "Check disk space and file permissions in the data directory."
        super().__init__(message, suggestion)


class ConnectorError(QuantumRAGError):
    """Data source connector errors."""

    def __init__(self, message: str, source: str = "", suggestion: str = "") -> None:
        self.source = source
        if not suggestion and source:
            suggestion = f"Verify credentials and connectivity for '{source}'."
        super().__init__(message, suggestion)


# ---------------------------------------------------------------------------
# LLM provider errors
# ---------------------------------------------------------------------------


class LLMAuthenticationError(QuantumRAGError):
    """Raised when LLM provider authentication fails."""

    def __init__(
        self,
        provider: str,
        *,
        suggestion: str = "",
    ) -> None:
        self.provider = provider
        if not suggestion:
            suggestion = (
                f"Check your {provider} API key. "
                f"Set it via the environment variable or configuration file."
            )
        super().__init__(
            f"[{provider}] Authentication failed",
            suggestion=suggestion,
        )


class LLMRateLimitError(QuantumRAGError):
    """Raised when LLM provider rate limit is exceeded."""

    def __init__(
        self,
        provider: str,
        *,
        retry_after_seconds: float | None = None,
        suggestion: str = "",
    ) -> None:
        self.provider = provider
        self.retry_after_seconds = retry_after_seconds
        if not suggestion:
            retry_hint = (
                f" Retry after {retry_after_seconds:.0f}s."
                if retry_after_seconds
                else ""
            )
            suggestion = (
                f"{provider} rate limit exceeded.{retry_hint} "
                f"Consider adding a delay between requests or upgrading your plan."
            )
        super().__init__(
            f"[{provider}] Rate limit exceeded",
            suggestion=suggestion,
        )


class LLMModelNotFoundError(QuantumRAGError):
    """Raised when the requested model is not found."""

    def __init__(
        self,
        provider: str,
        model: str,
        *,
        available_models: list[str] | None = None,
        suggestion: str = "",
    ) -> None:
        self.provider = provider
        self.model = model
        self.available_models = available_models or []
        if not suggestion:
            models_hint = (
                f" Available models: {', '.join(self.available_models)}"
                if self.available_models
                else ""
            )
            suggestion = (
                f"Model '{model}' was not found on {provider}.{models_hint}"
            )
        super().__init__(
            f"[{provider}] Model '{model}' not found",
            suggestion=suggestion,
        )


class LLMContextLengthError(QuantumRAGError):
    """Raised when the request exceeds the model's context length."""

    def __init__(
        self,
        provider: str,
        *,
        max_tokens: int = 0,
        requested_tokens: int = 0,
        suggestion: str = "",
    ) -> None:
        self.provider = provider
        self.max_tokens = max_tokens
        self.requested_tokens = requested_tokens
        if not suggestion:
            suggestion = (
                f"Requested {requested_tokens} tokens but {provider} model supports "
                f"at most {max_tokens}. Reduce input size or use a model with a larger context window."
            )
        super().__init__(
            f"[{provider}] Context length exceeded ({requested_tokens} > {max_tokens})",
            suggestion=suggestion,
        )


class LLMProviderError(QuantumRAGError):
    """Generic fallback for unclassified LLM provider errors."""

    def __init__(
        self,
        provider: str,
        original_error: BaseException | str,
        *,
        suggestion: str = "",
    ) -> None:
        self.provider = provider
        self.original_error = original_error
        if not suggestion:
            suggestion = (
                f"An unexpected error occurred with {provider}: {original_error}"
            )
        super().__init__(
            f"[{provider}] Provider error: {original_error}",
            suggestion=suggestion,
        )


class BudgetExceededError(QuantumRAGError):
    """Raised when a budget limit (daily or monthly) is exceeded."""

    def __init__(
        self,
        message: str,
        current_spend: float = 0.0,
        limit: float = 0.0,
        period: str = "",
        suggestion: str = "",
    ) -> None:
        self.current_spend = current_spend
        self.limit = limit
        self.period = period
        if not suggestion:
            suggestion = (
                f"Your {period} budget of ${limit:.2f} has been reached "
                f"(spent ${current_spend:.4f}). Increase the limit or wait for the next period."
            )
        super().__init__(message, suggestion)
