"""QuantumRAG HTTP API Server Example.

Start the API server and use it from any HTTP client.

Requirements:
    pip install quantumrag[all,api]

Usage:
    # Start the server
    quantumrag serve --port 8000

    # Or programmatically:
    python examples/api_server.py
"""

from quantumrag.api.server import create_app

# Create the FastAPI app
app = create_app()

if __name__ == "__main__":
    import uvicorn

    # Start the server
    # API docs available at http://localhost:8000/docs
    uvicorn.run(app, host="0.0.0.0", port=8000)

# Example API calls (using httpx or curl):
#
# Ingest documents:
#   curl -X POST http://localhost:8000/v1/ingest \
#     -H "Content-Type: application/json" \
#     -d '{"path": "./docs"}'
#
# Query:
#   curl -X POST http://localhost:8000/v1/query \
#     -H "Content-Type: application/json" \
#     -d '{"query": "What is the revenue?"}'
#
# Stream query (SSE):
#   curl -X POST http://localhost:8000/v1/query/stream \
#     -H "Content-Type: application/json" \
#     -d '{"query": "Summarize the document"}'
#
# Status:
#   curl http://localhost:8000/v1/status
