"""BingeLingo entry point.

Usage:
    python main.py            # start watching the folder
    python main.py <image>    # process a single screenshot once (handy for testing)
"""
from __future__ import annotations

import sys
from pathlib import Path

from src import notion_writer, vision, watcher


def _process_once(image_path: str) -> None:
    path = Path(image_path).expanduser()
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)
    print(f"[BingeLingo] Analyzing {path.name} …")
    analysis = vision.analyze_screenshot(path)
    if analysis.is_empty:
        print("No learn-worthy expressions found.")
        return
    for expr in analysis.expressions:
        print(f"  • [{expr.difficulty}] {expr.expression} — {expr.meaning_zh}")
    urls = notion_writer.write_entry(analysis, path)
    print(f"Written {len(urls)} row(s) to Notion:")
    for u in urls:
        print(f"  - {u}")


def main() -> None:
    if len(sys.argv) > 1:
        _process_once(sys.argv[1])
    else:
        watcher.run()


if __name__ == "__main__":
    main()
