"""QuantumRAG CLI entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from quantumrag._version import __version__
from quantumrag.core.config import QuantumRAGConfig, generate_default_yaml
from quantumrag.core.logging import setup_logging

app = typer.Typer(
    name="quantumrag",
    help="QuantumRAG — Index-Heavy, Query-Light RAG Engine",
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"QuantumRAG v{__version__}")
        raise typer.Exit()


def _load_config(config: Path | None) -> QuantumRAGConfig:
    """Load config from path, or auto-detect from environment."""
    if config and config.exists():
        return QuantumRAGConfig.from_yaml(config)
    # Auto-detect YAML in current directory
    auto_yaml = Path("quantumrag.yaml")
    if auto_yaml.exists():
        return QuantumRAGConfig.from_yaml(auto_yaml)
    # Auto-detect provider from env
    return QuantumRAGConfig.auto()


def _parse_metadata(metadata: list[str] | None) -> dict[str, Any] | None:
    """Parse key=value metadata pairs into a dict."""
    if not metadata:
        return None
    result: dict[str, Any] = {}
    for item in metadata:
        if "=" not in item:
            console.print(f"[red]Invalid metadata format: '{item}'. Expected key=value.[/red]")
            raise typer.Exit(code=1)
        key, value = item.split("=", 1)
        result[key.strip()] = value.strip()
    return result


@app.callback()
def main(
    version: bool | None = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True, help="Show version."
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose logging."),
    json_log: bool = typer.Option(False, "--json-log", help="Output logs as JSON."),
) -> None:
    """QuantumRAG — Put in docs, ask questions, it just works."""
    level = "DEBUG" if verbose else "INFO"
    setup_logging(level=level, json_output=json_log)


@app.command()
def init(
    config: Path = typer.Option(
        Path("quantumrag.yaml"), "--config", "-c", help="Config file path."
    ),
) -> None:
    """Initialize a QuantumRAG project with default configuration."""
    import os

    from quantumrag.core.config import _detect_provider

    if config.exists():
        console.print(f"[yellow]Config file already exists: {config}[/yellow]")
        overwrite = typer.confirm("Overwrite?", default=False)
        if not overwrite:
            raise typer.Abort()

    # Auto-detect provider and show status
    provider, gen_models, emb_model, emb_dims = _detect_provider(os.environ)
    provider_icons = {
        "openai": "OpenAI",
        "gemini": "Google Gemini",
        "anthropic": "Anthropic",
        "ollama": "Ollama (local)",
    }
    provider_label = provider_icons.get(provider, provider)

    config.write_text(generate_default_yaml(), encoding="utf-8")
    console.print(f"[green]Created config: {config}[/green]")
    console.print(f"  [dim]Detected provider:[/dim] [bold]{provider_label}[/bold]")
    console.print(f"  [dim]Embedding:[/dim] {emb_model} ({emb_dims}d)")
    console.print(f"  [dim]Generation:[/dim] {gen_models[0]} / {gen_models[1]}")
    console.print()
    console.print("Run [bold]quantumrag ingest <path>[/bold] to start.")


@app.command()
def ingest(
    path: str = typer.Argument(..., help="Path to file or directory to ingest."),
    config: Path | None = typer.Option(None, "--config", "-c", help="Config file path."),
    recursive: bool = typer.Option(
        True, "--recursive/--no-recursive", help="Recurse into directories."
    ),
    strategy: str | None = typer.Option(
        None, "--strategy", "-s", help="Chunking strategy override."
    ),
    metadata: list[str] | None = typer.Option(
        None, "--metadata", "-m", help="Metadata key=value pairs."
    ),
    watch: bool = typer.Option(
        False, "--watch", "-w", help="Watch directory for changes after initial ingest."
    ),
    mode: str = typer.Option("full", "--mode", help="Ingest mode: full, fast, or minimal."),
    fast: bool = typer.Option(False, "--fast", help="Shortcut for --mode fast."),
) -> None:
    """Ingest documents from a file or directory."""
    from rich.progress import Progress, SpinnerColumn, TextColumn

    target = Path(path)
    if not target.exists():
        console.print(f"[red]Error: Path not found: {target}[/red]")
        raise typer.Exit(code=1)

    ingest_mode = "fast" if fast else mode

    parsed_metadata = _parse_metadata(metadata)
    cfg = _load_config(config)

    try:
        from quantumrag.core.engine import Engine

        engine = Engine(config=cfg)

        mode_label = f" ({ingest_mode})" if ingest_mode != "full" else ""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description=f"Ingesting {target.name}{mode_label}...", total=None)
            result = engine.ingest(
                target,
                chunking_strategy=strategy,
                metadata=parsed_metadata,
                recursive=recursive,
                mode=ingest_mode,
            )

        # Show result summary
        console.print()
        table = Table(title="Ingest Summary", show_header=False)
        table.add_column("Key", style="bold")
        table.add_column("Value")
        table.add_row("Documents parsed", str(result.documents))
        table.add_row("Chunks created", str(result.chunks))
        table.add_row("Time elapsed", f"{result.elapsed_seconds:.1f}s")
        if result.errors:
            table.add_row("Errors", str(len(result.errors)))
        console.print(table)

        if result.errors:
            console.print("\n[yellow]Errors:[/yellow]")
            for err in result.errors:
                console.print(f"  [red]- {err}[/red]")

        if result.documents == 0:
            console.print(
                "\n[yellow]No documents were ingested. Check that the path contains supported files.[/yellow]"
            )
        else:
            console.print(f"\n[green]Successfully ingested {result.documents} document(s).[/green]")

        # Start watching if requested
        if watch:
            if not target.is_dir():
                console.print("[red]--watch requires a directory path, not a file.[/red]")
                raise typer.Exit(code=1)
            _run_watcher(
                target, engine, strategy=strategy, metadata=parsed_metadata, recursive=recursive
            )

    except Exception as e:
        console.print(f"[red]Error during ingestion: {e}[/red]")
        raise typer.Exit(code=1)


def _run_watcher(
    directory: Path,
    engine: Any,
    *,
    strategy: str | None = None,
    metadata: dict[str, Any] | None = None,
    recursive: bool = True,
) -> None:
    """Start the file watcher loop (blocking)."""
    import asyncio

    from quantumrag.core.watcher import FileWatcher

    async def on_change(
        added: list[Path],
        modified: list[Path],
        deleted: list[Path],
    ) -> None:
        if added:
            console.print(f"[cyan]New files detected: {[str(p) for p in added]}[/cyan]")
        if modified:
            console.print(f"[yellow]Modified files detected: {[str(p) for p in modified]}[/yellow]")
        if deleted:
            console.print(f"[red]Deleted files detected: {[str(p) for p in deleted]}[/red]")

        for file_path in [*added, *modified]:
            try:
                result = engine.ingest(
                    file_path,
                    chunking_strategy=strategy,
                    metadata=metadata,
                    recursive=False,
                )
                console.print(
                    f"  [green]Ingested {file_path.name}: "
                    f"{result.documents} doc(s), {result.chunks} chunk(s)[/green]"
                )
            except Exception as e:
                console.print(f"  [red]Error ingesting {file_path.name}: {e}[/red]")

        # Deletion handling is logged; actual index cleanup depends on engine capability
        for file_path in deleted:
            console.print(
                f"  [dim]Noted deletion: {file_path.name} (cleanup depends on storage backend)[/dim]"
            )

    async def _run() -> None:
        watcher = FileWatcher(directory, on_change, recursive=recursive)
        console.print(f"\n[bold]Watching {directory} for changes (Ctrl+C to stop)...[/bold]")
        await watcher.start()
        try:
            while watcher.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await watcher.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("\n[bold]Watcher stopped.[/bold]")


@app.command()
def query(
    question: str = typer.Argument(..., help="Question to ask."),
    config: Path | None = typer.Option(None, "--config", "-c", help="Config file path."),
    top_k: int | None = typer.Option(None, "--top-k", "-k", help="Number of results to retrieve."),
    no_rerank: bool = typer.Option(False, "--no-rerank", help="Disable reranking."),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text or json."),
    verbose: bool = typer.Option(False, "--verbose", help="Show processing trace."),
    no_stream: bool = typer.Option(False, "--no-stream", help="Disable streaming output."),
) -> None:
    """Query the knowledge base."""
    cfg = _load_config(config)

    try:
        from quantumrag.core.engine import Engine

        engine = Engine(config=cfg)

        rerank = None if not no_rerank else False

        result = engine.query(
            question,
            top_k=top_k,
            rerank=rerank,
        )

        if format == "json":
            console.print(result.model_dump_json(indent=2))
            return

        # Text format output
        console.print()
        console.print("[bold]Answer:[/bold]")
        console.print(result.answer)
        console.print()

        # Confidence
        confidence_colors = {
            "strongly_supported": "green",
            "partially_supported": "yellow",
            "insufficient_evidence": "red",
        }
        color = confidence_colors.get(result.confidence.value, "white")
        console.print(f"[bold]Confidence:[/bold] [{color}]{result.confidence.value}[/{color}]")

        # Sources
        if result.sources:
            console.print()
            sources_table = Table(title="Sources")
            sources_table.add_column("#", style="dim")
            sources_table.add_column("Document")
            sources_table.add_column("Excerpt")
            sources_table.add_column("Score", justify="right")
            for i, src in enumerate(result.sources, 1):
                title = src.document_title or src.chunk_id[:12]
                excerpt = src.excerpt[:80] + "..." if len(src.excerpt) > 80 else src.excerpt
                sources_table.add_row(str(i), title, excerpt, f"{src.relevance_score:.2f}")
            console.print(sources_table)

        # Verbose trace
        if verbose and result.trace:
            console.print()
            trace_table = Table(title="Processing Trace")
            trace_table.add_column("Step")
            trace_table.add_column("Result")
            trace_table.add_column("Latency", justify="right")
            for step in result.trace:
                trace_table.add_row(step.step, step.result, f"{step.latency_ms:.0f}ms")
            console.print(trace_table)

    except Exception as e:
        console.print(f"[red]Error during query: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def chat(
    config: Path | None = typer.Option(None, "--config", "-c", help="Config file path."),
    top_k: int | None = typer.Option(None, "--top-k", "-k", help="Number of results."),
    verbose: bool = typer.Option(False, "--verbose", help="Show processing trace."),
) -> None:
    """Interactive multi-turn chat with the knowledge base."""
    from rich.markdown import Markdown

    cfg = _load_config(config)

    try:
        from quantumrag.core.engine import Engine

        engine = Engine(config=cfg)
        info = engine.status()
        console.print(
            f"[bold green]QuantumRAG Chat[/bold green] — "
            f"{info.get('documents', 0)} docs, {info.get('chunks', 0)} chunks"
        )
        console.print("[dim]Type 'exit' or Ctrl+C to quit.[/dim]\n")

        history: list[dict[str, str]] = []

        while True:
            try:
                question = console.input("[bold cyan]You:[/bold cyan] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Bye![/dim]")
                break

            if not question or question.lower() in ("exit", "quit", "q"):
                console.print("[dim]Bye![/dim]")
                break

            try:
                result = engine.query(
                    question,
                    top_k=top_k,
                    conversation_history=history or None,
                )

                # Display answer
                console.print()
                console.print(Markdown(result.answer))
                console.print()

                # Confidence badge
                colors = {
                    "strongly_supported": "green",
                    "partially_supported": "yellow",
                    "insufficient_evidence": "red",
                }
                color = colors.get(result.confidence.value, "white")
                cost_info = ""
                if "token_usage" in result.metadata:
                    tokens = result.metadata["token_usage"].get("total_tokens", 0)
                    cost = result.metadata["token_usage"].get("total_estimated_cost", 0)
                    cost_info = f" | {tokens} tokens, ${cost:.4f}"
                console.print(
                    f"[dim][{color}]{result.confidence.value}[/{color}]{cost_info}[/dim]\n"
                )

                # Trace
                if verbose and result.trace:
                    for step in result.trace:
                        console.print(
                            f"  [dim]{step.step}: {step.result} ({step.latency_ms:.0f}ms)[/dim]"
                        )
                    console.print()

                # Update history
                history.append({"role": "user", "content": question})
                history.append({"role": "assistant", "content": result.answer})

                # Keep history manageable (last 10 turns)
                if len(history) > 20:
                    history = history[-20:]

            except Exception as e:
                console.print(f"[red]Error: {e}[/red]\n")

    except Exception as e:
        console.print(f"[red]Failed to start chat: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def status(
    config: Path | None = typer.Option(None, "--config", "-c", help="Config file path."),
) -> None:
    """Show engine status (index info, document count, storage usage)."""
    cfg = _load_config(config)

    try:
        from quantumrag.core.engine import Engine

        engine = Engine(config=cfg)
        info = engine.status()

        table = Table(title="QuantumRAG Status", show_header=False)
        table.add_column("Key", style="bold")
        table.add_column("Value")
        table.add_row("Project", info.get("project_name", "N/A"))
        table.add_row("Documents", str(info.get("documents", 0)))
        table.add_row("Chunks", str(info.get("chunks", 0)))
        table.add_row("Data directory", str(info.get("data_dir", "N/A")))
        table.add_row("Embedding model", str(info.get("embedding_model", "N/A")))
        table.add_row("Language", str(info.get("language", "N/A")))
        console.print(table)

    except Exception as e:
        console.print(f"[red]Error getting status: {e}[/red]")
        console.print("[dim]No index found. Run 'quantumrag ingest <path>' to get started.[/dim]")
        raise typer.Exit(code=1)


@app.command()
def cost(
    config: Path | None = typer.Option(None, "--config", "-c", help="Config file path."),
) -> None:
    """Show cost usage summary (daily/monthly totals, budgets, remaining)."""
    from quantumrag.core.observability.tracer import BudgetManager

    cfg = _load_config(config)
    data_dir = Path(cfg.storage.data_dir)
    db_path = data_dir / "budget.db"

    if not db_path.exists():
        console.print(
            "[yellow]No cost data found. Queries must be run first to track costs.[/yellow]"
        )
        console.print(f"[dim]Expected database at: {db_path}[/dim]")
        raise typer.Exit()

    manager = BudgetManager(
        db_path=db_path,
        daily_limit=cfg.cost.budget_daily,
        monthly_limit=cfg.cost.budget_monthly,
    )
    summary = manager.get_usage_summary()

    # -- Cost Summary table --
    table = Table(title="Cost Summary", show_header=True)
    table.add_column("Period", style="bold")
    table.add_column("Spent", justify="right")
    table.add_column("Limit", justify="right")
    table.add_column("Remaining", justify="right")

    daily_limit_str = (
        f"${summary['daily_limit']:.4f}" if summary["daily_limit"] is not None else "unlimited"
    )
    monthly_limit_str = (
        f"${summary['monthly_limit']:.4f}" if summary["monthly_limit"] is not None else "unlimited"
    )
    daily_remaining_str = (
        f"${summary['daily_remaining']:.4f}" if summary["daily_remaining"] is not None else "-"
    )
    monthly_remaining_str = (
        f"${summary['monthly_remaining']:.4f}" if summary["monthly_remaining"] is not None else "-"
    )

    table.add_row(
        "Daily",
        f"${summary['daily_total']:.4f}",
        daily_limit_str,
        daily_remaining_str,
    )
    table.add_row(
        "Monthly",
        f"${summary['monthly_total']:.4f}",
        monthly_limit_str,
        monthly_remaining_str,
    )
    console.print(table)


_DEMO_TEXT = """\
# QuantumRAG Demo Document

## What is QuantumRAG?
QuantumRAG is an Index-Heavy, Query-Light RAG engine. It deeply indexes documents \
at ingest time using Triple Index (Original Embedding + HyPE + BM25), so every query \
is fast, accurate, and cited.

## Key Features
- **Triple Index Fusion**: Combines semantic, hypothetical-question, and keyword search \
via Reciprocal Rank Fusion (RRF).
- **Fact Extraction & Verification**: Rule-based (zero LLM cost) fact extraction at ingest, \
cross-checked against answers to prevent hallucination.
- **Adaptive Query Routing**: Simple queries use lightweight models; complex queries use \
more capable models — automatically.
- **Korean-First Design**: Native HWP/HWPX parsing, Kiwi morphology for BM25, \
EUC-KR encoding detection.
- **Post-Correction Pipeline**: Retrieval retry, self-correction, fact verification, \
and completeness checking — all modular and composable.

## Architecture
The pipeline has three phases:
1. **Ingest (Index-Heavy)**: Parse → Chunk → Multi-Resolution Summary → Fact Extract → \
Triple Index Build (Original + HyPE + BM25).
2. **Query (Query-Light)**: Rewrite → Classify → Triple Fusion Search → Rerank → \
Context Compress → Generate with Citations.
3. **Post-Process**: Retrieval Retry → Self-Correct → Fact Verify → Completeness Check.

## Supported Formats
PDF, DOCX, PPTX, XLSX, HWP/HWPX, HTML, Markdown, CSV, and plain text.

## LLM Providers
OpenAI, Google Gemini, Anthropic, and Ollama (local, offline).

## Cost Optimization
- Three-tier model routing (simple/medium/complex)
- Free reranking (FlashRank, CPU-based)
- Semantic caching (planned)
- Temperature fixed at 0.0 for deterministic output
"""


@app.command()
def demo(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind host."),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port."),
) -> None:
    """Launch a demo with built-in sample content — try QuantumRAG instantly."""
    import asyncio
    import tempfile

    try:
        import uvicorn
    except ImportError:
        console.print("[red]Install the api extra: pip install quantumrag[api][/red]")
        raise typer.Exit(code=1)

    from quantumrag.core.config import QuantumRAGConfig
    from quantumrag.core.engine import Engine

    console.print("[bold green]QuantumRAG Demo[/bold green]")
    console.print("Ingesting sample document...")

    # Use temp dir for demo data
    demo_dir = Path(tempfile.mkdtemp(prefix="quantumrag_demo_"))
    cfg = QuantumRAGConfig.auto(storage={"data_dir": str(demo_dir)})

    # Demo uses Gemini API embedding for fast startup (no 270M model download)
    import os

    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        cfg.models.embedding.provider = "gemini"
        cfg.models.embedding.model = "gemini-embedding-001"
        cfg.models.embedding.dimensions = 768

    engine = Engine(config=cfg)

    # Ingest built-in demo text via temp file
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(_DEMO_TEXT)
        demo_path = f.name
    try:
        result = engine.ingest(demo_path, mode="fast")
        console.print(f"  [green]Done:[/green] {result.chunks} chunks indexed")
    finally:
        Path(demo_path).unlink(missing_ok=True)
    console.print(f"  Open [bold cyan]http://localhost:{port}[/bold cyan] to try it!")
    console.print("  [dim]Try: 'What is QuantumRAG?' or 'What formats are supported?'[/dim]")

    from quantumrag.api.server import create_app

    fastapi_app = create_app()
    # Inject the pre-loaded engine
    fastapi_app.state.engine = engine
    uvicorn.run(fastapi_app, host=host, port=port)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind host."),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port."),
    config: Path | None = typer.Option(None, "--config", "-c", help="Config file path."),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development."),
) -> None:
    """Start the HTTP API server."""
    try:
        import uvicorn
    except ImportError:
        console.print(
            "[red]uvicorn is not installed. "
            "Install the api extra: pip install quantumrag[api][/red]"
        )
        raise typer.Exit(code=1)

    # Auto-detect quantumrag.yaml in current directory if no --config given
    if config and config.exists():
        config_path: str | None = str(config)
    elif Path("quantumrag.yaml").exists():
        config_path = str(Path("quantumrag.yaml"))
    else:
        config_path = None

    console.print(f"[bold green]Starting QuantumRAG API server on {host}:{port}[/bold green]")
    if config_path:
        console.print(f"Using config: {config_path}")

    # Show provider/model info so users can verify their setup
    try:
        from quantumrag.core.config import QuantumRAGConfig

        _cfg = QuantumRAGConfig.from_yaml(config_path) if config_path else QuantumRAGConfig.auto()
        _emb = f"{_cfg.models.embedding.provider}/{_cfg.models.embedding.model}"
        _gen = f"{_cfg.models.generation.simple.provider}/{_cfg.models.generation.simple.model}"
        _hype = f"{_cfg.models.hype.provider}/{_cfg.models.hype.model}"
        console.print(f"  Embedding: [cyan]{_emb}[/cyan]")
        console.print(f"  Generation: [cyan]{_gen}[/cyan]")
        console.print(f"  HyPE: [cyan]{_hype}[/cyan]")
    except Exception:
        pass

    if reload:
        # When using reload uvicorn needs an import string
        import os

        if config_path:
            os.environ["QUANTUMRAG_API_CONFIG"] = config_path
        uvicorn.run(
            "quantumrag.api.server:create_app",
            host=host,
            port=port,
            reload=True,
            factory=True,
        )
    else:
        from quantumrag.api.server import create_app

        fastapi_app = create_app(config_path=config_path)
        uvicorn.run(fastapi_app, host=host, port=port)


@app.command()
def autotune(
    target: str = typer.Argument(
        "retrieval", help="What to optimize: retrieval, generation, or all."
    ),
    config: Path | None = typer.Option(None, "--config", "-c", help="Config file path."),
    trials: int = typer.Option(30, "--trials", "-n", help="Number of optimization trials."),
    checklist: Path | None = typer.Option(None, "--checklist", help="Custom checklist YAML file."),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Output directory for results."
    ),
    apply: bool = typer.Option(False, "--apply", help="Apply best params to config file."),
) -> None:
    """Auto-tune parameters using Bayesian optimization."""
    try:
        import optuna  # noqa: F401
    except ImportError:
        console.print(
            "[red]optuna is required for autotune. Install with: pip install optuna[/red]"
        )
        raise typer.Exit(code=1)

    cfg = _load_config(config)

    console.print(f"[bold]AutoTune: optimizing {target} parameters[/bold]")
    console.print(f"  Trials: {trials}")

    try:
        from quantumrag.core.autotune.checklist import Checklist
        from quantumrag.core.autotune.scorer import create_scenario_scorer
        from quantumrag.core.autotune.tuner import AutoTuner
        from quantumrag.core.engine import Engine

        # Load checklist
        if checklist and checklist.exists():
            cl = Checklist.from_yaml(checklist)
            console.print(f"  Checklist: {checklist}")
        else:
            cl = Checklist.default()
            console.print("  Checklist: default (6 criteria)")

        console.print(f"  Criteria: {len(cl.criteria)}")
        for c in cl.criteria:
            console.print(
                f"    - {c.id}: {c.description} (target={c.target}, weight={c.weight:.0%})"
            )

        engine = Engine(config=cfg)
        scorer = create_scenario_scorer(sample_size=9)

        tuner = AutoTuner(engine, checklist=cl, scorer=scorer)
        console.print("\n[bold green]Starting optimization...[/bold green]\n")

        result = tuner.run(
            n_trials=trials,
            target=target,
            output_dir=str(output) if output else None,
        )

        # Show results
        console.print("\n[bold green]Optimization complete![/bold green]")
        console.print(f"\n  Best score: [bold]{result.best_score:.4f}[/bold]")
        console.print(f"  Trials: {result.n_trials}")
        console.print(f"  Time: {result.elapsed_seconds:.0f}s")

        # Best params table
        table = Table(title="Best Parameters", show_header=True)
        table.add_column("Parameter", style="bold")
        table.add_column("Value", justify="right")
        for k, v in result.best_params.items():
            table.add_row(k, f"{v:.4f}" if isinstance(v, float) else str(v))
        console.print(table)

        # Checklist results
        console.print(
            f"\n[bold]Checklist: {result.best_checklist.passed_count}/{result.best_checklist.total_count} passed[/bold]"
        )
        for cr in result.best_checklist.criteria_results:
            icon = "[green]PASS[/green]" if cr.passed else "[red]FAIL[/red]"
            console.print(
                f"  {icon} {cr.criterion.id}: {cr.value:.4f} (target: {cr.criterion.target})"
            )

        # Apply to config
        if apply and config and config.exists():
            tuner.export_config(result, config)
            console.print(f"\n[green]Best parameters applied to {config}[/green]")

        if output:
            console.print(f"\n[dim]Results saved to {output}[/dim]")

    except Exception as e:
        console.print(f"[red]AutoTune error: {e}[/red]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
