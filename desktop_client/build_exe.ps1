param(
    [string]$PythonExe = "python"
)

Set-Location $PSScriptRoot

$env:PYTHONPATH = (Resolve-Path "..").Path

# Build desktop GUI executable
& $PythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --name "NovaDesktop" `
    --onefile `
    --windowed `
    --add-data "config/checksums.json;desktop_client/config" `
    --add-data "gui/icons;desktop_client/gui/icons" `
    main.py

# Build engine executable (runs root main.py through engine_runner)
& $PythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --name "NovaEngine" `
    --onefile `
    --console `
    --hidden-import "queue" `
    --hidden-import "cv2" `
    --hidden-import "numpy" `
    --hidden-import "numpy._core._exceptions" `
    --hidden-import "onnxruntime" `
    --hidden-import "screeninfo" `
    --hidden-import "torch" `
    --hidden-import "ultralytics" `
    --hidden-import "win32api" `
    --hidden-import "win32con" `
    --hidden-import "win32gui" `
    --hidden-import "win32ui" `
    --collect-submodules "numpy" `
    --collect-binaries "numpy" `
    --collect-data "numpy" `
    engine_runner.py

# Copy runtime engine sources next to executables
$projectRoot = (Resolve-Path "..").Path
$engineDir = Join-Path $PSScriptRoot "dist\\engine"
New-Item -ItemType Directory -Force -Path $engineDir | Out-Null

$engineFiles = @(
    "main.py",
    "options.py",
    "config_validation.py",
    "frame.py",
    "logging_config.py",
    "mouse.py",
    "screen.py",
    "targets.py",
    "ghub_mouse.dll"
)

foreach ($relPath in $engineFiles) {
    $src = Join-Path $projectRoot $relPath
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination (Join-Path $engineDir (Split-Path $relPath -Leaf)) -Force
    }
}

$modelsSrc = Join-Path $projectRoot "models"
$modelsDst = Join-Path $engineDir "models"
if (Test-Path $modelsSrc) {
    Copy-Item -Path $modelsSrc -Destination $modelsDst -Recurse -Force
}
