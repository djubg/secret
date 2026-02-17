#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONPATH="$(cd .. && pwd)"

python -m PyInstaller \
  --noconfirm \
  --clean \
  --name "NovaDesktop" \
  --onefile \
  --windowed \
  --add-data "config/checksums.json:desktop_client/config" \
  --add-data "gui/icons:desktop_client/gui/icons" \
  main.py

# Engine executable wrapper
python -m PyInstaller \
  --noconfirm \
  --clean \
  --name "NovaEngine" \
  --onefile \
  --console \
  --hidden-import "queue" \
  --hidden-import "cv2" \
  --hidden-import "numpy" \
  --hidden-import "numpy._core._exceptions" \
  --hidden-import "onnxruntime" \
  --hidden-import "screeninfo" \
  --hidden-import "torch" \
  --hidden-import "ultralytics" \
  --hidden-import "win32api" \
  --hidden-import "win32con" \
  --hidden-import "win32gui" \
  --hidden-import "win32ui" \
  --collect-submodules "numpy" \
  --collect-binaries "numpy" \
  --collect-data "numpy" \
  engine_runner.py

# Runtime engine sources near binaries
ENGINE_DIR="dist/engine"
mkdir -p "$ENGINE_DIR"
PROJECT_ROOT="$(cd .. && pwd)"

for rel in main.py options.py config_validation.py frame.py logging_config.py mouse.py screen.py targets.py ghub_mouse.dll; do
  src="$PROJECT_ROOT/$rel"
  if [ -f "$src" ]; then
    cp -f "$src" "$ENGINE_DIR/"
  fi
done

if [ -d "$PROJECT_ROOT/models" ]; then
  rm -rf "$ENGINE_DIR/models"
  cp -R "$PROJECT_ROOT/models" "$ENGINE_DIR/models"
fi
