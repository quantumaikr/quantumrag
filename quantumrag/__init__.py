"""QuantumRAG — Index-Heavy, Query-Light RAG Engine.

Usage::

    from quantumrag import Engine

    engine = Engine()
    engine.ingest("./docs")
    result = engine.query("What is the revenue?")
    print(result.answer)
"""

from quantumrag._version import __version__
from quantumrag.core.engine import Engine

__all__ = ["Engine", "__version__"]
