import os
import runpy
import sys
from pathlib import Path


def _pyinstaller_hidden_imports() -> None:
    """
    Dependency anchors for PyInstaller.
    NovaEngine loads engine/main.py dynamically with runpy, so static analysis
    may miss imports used by that runtime script unless we declare them here.
    """
    import queue  # noqa: F401
    import cv2  # noqa: F401
    import numpy  # noqa: F401
    import onnxruntime  # noqa: F401
    import screeninfo  # noqa: F401
    import torch  # noqa: F401
    import ultralytics  # noqa: F401
    import win32api  # noqa: F401
    import win32con  # noqa: F401
    import win32gui  # noqa: F401
    import win32ui  # noqa: F401


def _engine_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "engine"
    return Path(__file__).resolve().parent.parent


def main() -> int:
    engine_root = _engine_root()
    main_script = engine_root / "main.py"
    if not main_script.exists():
        print(f"Engine script not found: {main_script}")
        return 1

    os.chdir(engine_root)
    sys.path.insert(0, str(engine_root))
    runpy.run_path(str(main_script), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
