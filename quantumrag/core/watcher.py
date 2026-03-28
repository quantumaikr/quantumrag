"""File system watcher for auto-ingestion of document changes."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.watcher")

# Same extensions as in the incremental indexer
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".txt",
        ".md",
        ".pdf",
        ".docx",
        ".doc",
        ".xlsx",
        ".xls",
        ".pptx",
        ".ppt",
        ".html",
        ".htm",
        ".csv",
        ".json",
        ".hwp",
        ".hwpx",
    }
)

OnChangeCallback = Callable[
    [list[Path], list[Path], list[Path]],
    Awaitable[None],
]


class _WatcherBackend(Protocol):
    """Protocol for pluggable watcher backends."""

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def poll_events(self) -> tuple[set[Path], set[Path], set[Path]]: ...


class _PollingBackend:
    """Polling-based fallback that tracks file mtimes."""

    def __init__(self, directory: Path, recursive: bool = True) -> None:
        self._directory = directory
        self._recursive = recursive
        self._snapshot: dict[Path, float] = {}
        self._running = False

    def start(self) -> None:
        self._snapshot = self._take_snapshot()
        self._running = True

    def stop(self) -> None:
        self._running = False

    def _take_snapshot(self) -> dict[Path, float]:
        snapshot: dict[Path, float] = {}
        pattern = "**/*" if self._recursive else "*"
        for p in self._directory.glob(pattern):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
                with contextlib.suppress(OSError):
                    snapshot[p] = p.stat().st_mtime
        return snapshot

    def poll_events(self) -> tuple[set[Path], set[Path], set[Path]]:
        if not self._running:
            return set(), set(), set()

        new_snapshot = self._take_snapshot()
        old_paths = set(self._snapshot)
        new_paths = set(new_snapshot)

        added = new_paths - old_paths
        deleted = old_paths - new_paths
        modified: set[Path] = set()
        for p in old_paths & new_paths:
            if new_snapshot[p] != self._snapshot[p]:
                modified.add(p)

        self._snapshot = new_snapshot
        return added, modified, deleted


class _WatchdogBackend:
    """Backend using the watchdog library for native filesystem events."""

    def __init__(self, directory: Path, recursive: bool = True) -> None:
        from watchdog.events import FileSystemEvent, FileSystemEventHandler
        from watchdog.observers import Observer

        self._directory = directory
        self._recursive = recursive
        self._added: set[Path] = set()
        self._modified: set[Path] = set()
        self._deleted: set[Path] = set()
        self._lock = asyncio.Lock()  # not needed in sync, but we use threading lock
        import threading

        self._lock_t = threading.Lock()

        class _Handler(FileSystemEventHandler):
            def __init__(self, backend: _WatchdogBackend) -> None:
                self._backend = backend

            def _is_supported(self, path: str) -> bool:
                return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS

            def on_created(self, event: FileSystemEvent) -> None:
                if not event.is_directory and self._is_supported(event.src_path):
                    with self._backend._lock_t:
                        self._backend._added.add(Path(event.src_path))

            def on_modified(self, event: FileSystemEvent) -> None:
                if not event.is_directory and self._is_supported(event.src_path):
                    with self._backend._lock_t:
                        self._backend._modified.add(Path(event.src_path))

            def on_deleted(self, event: FileSystemEvent) -> None:
                if not event.is_directory and self._is_supported(event.src_path):
                    with self._backend._lock_t:
                        self._backend._deleted.add(Path(event.src_path))

        self._observer = Observer()
        self._handler = _Handler(self)

    def start(self) -> None:
        self._observer.schedule(self._handler, str(self._directory), recursive=self._recursive)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join(timeout=5)

    def poll_events(self) -> tuple[set[Path], set[Path], set[Path]]:
        with self._lock_t:
            added = self._added.copy()
            modified = self._modified.copy()
            deleted = self._deleted.copy()
            self._added.clear()
            self._modified.clear()
            self._deleted.clear()
        return added, modified, deleted


def _create_backend(directory: Path, recursive: bool) -> _WatcherBackend:
    """Create the best available watcher backend."""
    try:
        import watchdog  # noqa: F401

        return _WatchdogBackend(directory, recursive)
    except ImportError:
        logger.info("watchdog not installed, using polling fallback")
        return _PollingBackend(directory, recursive)


class FileWatcher:
    """Monitor a directory for file changes and invoke a callback.

    Uses the ``watchdog`` library when available, otherwise falls back to
    a simple polling strategy based on file modification times.

    Args:
        directory: Root directory to watch.
        on_change: Async callback invoked with ``(added, modified, deleted)`` path lists.
        debounce_seconds: Wait this many seconds after the last detected change
            before firing the callback. Defaults to ``2.0``.
        poll_interval: Seconds between poll cycles. Defaults to ``1.0``.
        recursive: Watch subdirectories recursively. Defaults to ``True``.
    """

    def __init__(
        self,
        directory: Path,
        on_change: OnChangeCallback,
        *,
        debounce_seconds: float = 2.0,
        poll_interval: float = 1.0,
        recursive: bool = True,
    ) -> None:
        self._directory = Path(directory).resolve()
        self._on_change = on_change
        self._debounce_seconds = debounce_seconds
        self._poll_interval = poll_interval
        self._recursive = recursive
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._backend: _WatcherBackend | None = None

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Start watching the directory for changes."""
        if self._running:
            return
        if not self._directory.is_dir():
            raise NotADirectoryError(f"Not a directory: {self._directory}")

        self._backend = _create_backend(self._directory, self._recursive)
        self._backend.start()
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("file_watcher.started", directory=str(self._directory))

    async def stop(self) -> None:
        """Stop watching and clean up resources."""
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._backend is not None:
            self._backend.stop()
            self._backend = None
        logger.info("file_watcher.stopped")

    async def _watch_loop(self) -> None:
        """Main watch loop: poll backend, accumulate changes, debounce, fire callback."""
        accumulated_added: set[Path] = set()
        accumulated_modified: set[Path] = set()
        accumulated_deleted: set[Path] = set()
        last_change_time: float | None = None

        while self._running:
            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break

            if self._backend is None:
                break

            added, modified, deleted = self._backend.poll_events()

            if added or modified or deleted:
                accumulated_added.update(added)
                accumulated_modified.update(modified)
                accumulated_deleted.update(deleted)
                last_change_time = time.monotonic()
                logger.debug(
                    "file_watcher.changes_detected",
                    added=len(added),
                    modified=len(modified),
                    deleted=len(deleted),
                )

            # Fire callback after debounce period
            if last_change_time is not None:
                elapsed = time.monotonic() - last_change_time
                if elapsed >= self._debounce_seconds:
                    # Remove deleted from added/modified
                    accumulated_added -= accumulated_deleted
                    accumulated_modified -= accumulated_deleted

                    await self._on_change(
                        sorted(accumulated_added),
                        sorted(accumulated_modified),
                        sorted(accumulated_deleted),
                    )
                    accumulated_added.clear()
                    accumulated_modified.clear()
                    accumulated_deleted.clear()
                    last_change_time = None
