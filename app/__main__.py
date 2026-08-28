"""진입점:  python -m app  또는  PyInstaller 번들 실행."""

from __future__ import annotations

import multiprocessing
import sys


def main() -> None:
    # PyInstaller onefile/onedir 에서 자식 프로세스 재귀 실행 방지
    multiprocessing.freeze_support()

    try:
        from .gui import main as gui_main
    except ImportError:
        # 번들에서 패키지 상대 경로가 안 잡히는 경우 대비
        from app.gui import main as gui_main  # type: ignore

    gui_main()


if __name__ == "__main__":
    sys.exit(main())
