# Contributing to QuantumRAG

Thank you for your interest in contributing to QuantumRAG! This guide will help you get started.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/quantumrag/quantumrag.git
cd quantumrag

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest tests/

# Run linting
ruff check quantumrag/ tests/
```

## Project Structure

```
quantumrag/
  core/           # Core engine (models, config, storage, ingest, retrieve, generate)
  api/            # FastAPI HTTP server
  cli/            # Typer CLI interface
  connectors/     # External data source connectors
  korean/         # Korean language support (morphology, encoding)
  plugins/        # Plugin system
tests/
  unit/           # Unit tests
  integration/    # Integration tests (require external services)
  benchmarks/     # Performance benchmarks
```

## Making Changes

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Write code** following existing patterns:
   - Use type hints everywhere
   - Follow the existing code style (ruff enforced)
   - Add docstrings for public APIs
   - Use lazy imports for optional dependencies

3. **Write tests** for new functionality:
   - Unit tests go in `tests/unit/`
   - Mock external services (LLM, embedding APIs)
   - Aim for >80% coverage on new code

4. **Run checks** before submitting:
   ```bash
   ruff check quantumrag/ tests/
   pytest tests/ -q
   ```

5. **Submit a Pull Request** with:
   - Clear description of what changed and why
   - Link to related issue (if any)
   - Test results

## Code Style

- **Python 3.10+** — use modern syntax (`X | Y` unions, not `Optional[X]`)
- **Pydantic v2** for data models
- **structlog** for logging
- **Protocol classes** for interfaces (not ABCs)
- **Lazy imports** for optional dependencies (lancedb, tantivy, etc.)

## Adding a New Parser

```python
# quantumrag/core/ingest/parser/my_format.py
from quantumrag.core.models import Document

class MyFormatParser:
    supported_extensions = {".myext"}

    def parse(self, path: Path) -> Document:
        # Parse your format and return a Document
        ...
```

## Adding a Plugin

See the plugin system documentation in `quantumrag/plugins/registry.py`.

## Reporting Issues

- Use GitHub Issues
- Include Python version, OS, and QuantumRAG version
- Provide minimal reproduction steps

## Code of Conduct

Be respectful, constructive, and inclusive. We welcome contributions from everyone regardless of background or experience level.

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
