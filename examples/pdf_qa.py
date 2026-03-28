"""QuantumRAG PDF Question-Answering Example.

Demonstrates PDF-specific features:
- Font-based heading detection (H1/H2 auto-generation)
- Table extraction as Markdown
- Bidi character normalization
- Structural chunking with breadcrumbs

Requirements:
    pip install quantumrag[all]
    export OPENAI_API_KEY=your-key
"""

from pathlib import Path

from quantumrag import Engine


def main() -> None:
    # Ingest PDFs — heading structure is auto-detected from font sizes
    engine = Engine(data_dir="./pdf_qa_data")

    pdf_dir = Path("./pdfs")
    if not pdf_dir.exists():
        print("Create a ./pdfs directory with PDF files to get started.")
        print("Example: mkdir pdfs && cp your-paper.pdf pdfs/")
        return

    result = engine.ingest(str(pdf_dir))
    print(f"Ingested {result.documents} PDFs -> {result.chunks} chunks\n")

    # Ask questions about PDF content
    questions = [
        "What are the main findings?",
        "Summarize the methodology.",
        "What data was used in the analysis?",
    ]

    for q in questions:
        answer = engine.query(q)
        print(f"Q: {q}")
        print(f"A: {answer.answer[:200]}...")
        print(f"   [{answer.confidence.value}]\n")


if __name__ == "__main__":
    main()
