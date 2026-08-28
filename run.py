"""단일 진입점 (PyInstaller 번들용). 개발 중에는 `python -m app` 도 가능."""

from __future__ import annotations

import multiprocessing


def main() -> None:
    multiprocessing.freeze_support()
    from app.gui import main as gui_main

    gui_main()


if __name__ == "__main__":
    main()
