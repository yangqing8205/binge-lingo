"""Watch a folder for new screenshots and drive the full pipeline."""
from __future__ import annotations

import json
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import config, notion_writer, settings, vision


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
    def __init__(self, processed: set[str], show: str = "", episode: str = "") -> None:
        self._processed = processed
        self._show = show
        self._episode = episode

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
            urls = notion_writer.write_entry(
                analysis, path, show=self._show, episode=self._episode
            )
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


def _ask(prompt: str) -> str:
    try:
        answer = input(prompt)
    except EOFError:
        return ""
    return answer.strip()


def _ask_show_and_episode() -> tuple[str, str]:
    """Ask once, at startup, which show (and optionally episode) this session
    is for. Both are stamped onto every card written this session — separately
    now (Notion's Show/Episode fields), not squeezed into one string. Either
    can be left blank; a non-interactive stdin (e.g. piped) yields both blank.
    """
    show = _ask("今天看什么剧？（直接回车跳过）\n> ")
    if not show:
        return "", ""
    episode = _ask("第几集？（例:S3E5，直接回车跳过）\n> ")
    return show, episode


def run() -> None:
    processed = _load_state()

    show, episode = _ask_show_and_episode()
    if show:
        print(f"[BingeLingo] 本轮 Show = {show}" + (f"，Episode = {episode}" if episode else ""))
        # Only touch current_show when one was actually given — skipping this
        # prompt shouldn't silently clear a show picked earlier via the web
        # switcher.
        settings.set_current_show(show)
    else:
        print("[BingeLingo] 未设置 Show，本轮留空（当前剧集设置保持不变）。")

    # Screenshots are filed under screenshots/<show>/ so different shows never
    # mix in the same folder. No show → stays at the watch root, same as before.
    config.WATCH_DIR.mkdir(parents=True, exist_ok=True)
    show_dirname = config.safe_show_dirname(show)
    watch_dir = (config.WATCH_DIR / show_dirname) if show_dirname else config.WATCH_DIR
    watch_dir.mkdir(parents=True, exist_ok=True)

    handler = _Handler(processed, show=show, episode=episode)
    observer = Observer()
    # Recursive so screenshots dropped into any per-show subfolder are caught,
    # not just ones landing directly in the watched root.
    observer.schedule(handler, str(config.WATCH_DIR), recursive=True)
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
