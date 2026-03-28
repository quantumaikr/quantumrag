"""QuantumRAG Interactive Chat Example.

Multi-turn conversational RAG with entity tracking.
The engine remembers context across turns, resolving pronouns
and tracking topic continuity automatically.

Requirements:
    pip install quantumrag[all]
    export OPENAI_API_KEY=your-key

Usage:
    python examples/chat.py ./docs
"""

from __future__ import annotations

import sys

from quantumrag import Engine


def main() -> None:
    docs_path = sys.argv[1] if len(sys.argv) > 1 else "./docs"

    engine = Engine()
    result = engine.ingest(docs_path)
    print(f"Ingested {result.documents} docs, {result.chunks} chunks\n")

    history: list[dict[str, str]] = []

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not question or question.lower() in ("exit", "quit"):
            break

        answer = engine.query(question, conversation_history=history or None)
        print(f"\nRAG: {answer.answer}")
        print(f"[{answer.confidence.value}]\n")

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer.answer})

        if len(history) > 20:
            history = history[-20:]


if __name__ == "__main__":
    main()
