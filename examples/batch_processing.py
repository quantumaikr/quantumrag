"""QuantumRAG Batch Processing Example.

Process multiple queries in parallel with controlled concurrency.

Requirements:
    pip install quantumrag[all]
"""

import asyncio

from quantumrag import Engine
from quantumrag.core.batch import BatchProcessor


async def main():
    # Create engine
    engine = Engine()

    # Create batch processor with max 3 concurrent queries
    processor = BatchProcessor(engine, default_concurrency=3)

    # Create a batch job from a list of questions
    questions = [
        "What is the main revenue source?",
        "Who are the key executives?",
        "What are the major risks?",
        "What is the company strategy?",
        "How has revenue changed over time?",
    ]

    job = processor.create_job(questions)
    print(f"Created batch job: {job.job_id}")
    print(f"Total queries: {job.total}")

    # Run the batch
    result = await processor.run(job)

    # Print results
    print(f"\nBatch complete!")
    print(f"  Status: {result.status.value}")
    print(f"  Success: {result.success_count}/{result.total}")
    print(f"  Errors: {result.error_count}")
    print(f"  Elapsed: {result.elapsed_seconds:.1f}s")

    for q in result.queries:
        print(f"\n  Q: {q.query}")
        if q.result:
            print(f"  A: {q.result['answer'][:100]}...")
        if q.error:
            print(f"  Error: {q.error}")


if __name__ == "__main__":
    asyncio.run(main())
