"""Watch a folder for new screenshots and drive the full pipeline."""
from __future__ import annotations

import json
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import config, notion_writer, vision


def _load_state() -> set[str]:
    if config.STATE_FILE.exists():
        try:
            return set(json.loads(config.STATE_FILE.read_text()))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def _save_state(processed: set[str]) -> None:
    try:
        config.STATE_FILE.write_text(json.dumps(sorted(processed)))
    except OSError:
        pass


def _wait_until_stable(path: Path, tries: int = 10, interval: float = 0.3) -> bool:
    """Screenshots land incrementally; wait until the file size stops changing."""
    last = -1
    for _ in range(tries):
        if not path.exists():
            return False
        size = path.stat().st_size
        if size == last and size > 0:
            return True
        last = size
        time.sleep(interval)
    return path.exists() and path.stat().st_size > 0


class _Handler(FileSystemEventHandler):
    def __init__(self, processed: set[str], source: str = "") -> None:
        self._processed = processed
        self._source = source

    def _handle(self, raw_path: str) -> None:
        path = Path(raw_path)
        if path.suffix.lower() not in config.IMAGE_EXTENSIONS:
            return
        key = str(path.resolve())
        if key in self._processed:
            return
        if not _wait_until_stable(path):
            return

        print(f"[BingeLingo] New screenshot: {path.name}")
        try:
            analysis = vision.analyze_screenshot(path)
        except Exception as exc:  # noqa: BLE001 — keep the watcher alive
            print(f"  ! vision failed: {exc}")
            return

        if analysis.is_empty:
            print("  · no learn-worthy expressions found, skipping Notion write")
            self._processed.add(key)
            _save_state(self._processed)
            return

        try:
            urls = notion_writer.write_entry(analysis, path, source=self._source)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! Notion write failed: {exc}")
            return

        print(f"  ✓ wrote {len(urls)} expression(s) to Notion")
        self._processed.add(key)
        _save_state(self._processed)

    def on_created(self, event) -> None:
        if not event.is_directory:
            self._handle(event.src_path)

    def on_moved(self, event) -> None:
        # Screenshot tools often write to a temp name then rename into place.
        if not event.is_directory:
            self._handle(event.dest_path)


def _ask_source() -> str:
    """Ask once, at startup, which show this watch session is for.

    The answer is stamped onto every card written this session (Notion's Source
    field). Empty input keeps the old behaviour: Source left blank, filled in
    later by hand. A non-interactive stdin (e.g. piped) also yields empty.
    """
    try:
        answer = input("今天看什么剧？（例:Modern Family S3E5，直接回车跳过）\n> ")
    except EOFError:
        return ""
    return answer.strip()


def run() -> None:
    watch_dir = config.WATCH_DIR
    watch_dir.mkdir(parents=True, exist_ok=True)
    processed = _load_state()

    source = _ask_source()
    if source:
        print(f"[BingeLingo] 本轮 Source = {source}")
    else:
        print("[BingeLingo] 未设置 Source，本轮留空。")

    handler = _Handler(processed, source=source)
    observer = Observer()
    observer.schedule(handler, str(watch_dir), recursive=False)
    observer.start()
    print(f"[BingeLingo] Watching {watch_dir} for new screenshots. Ctrl-C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[BingeLingo] Stopping…")
    finally:
        observer.stop()
        observer.join()
