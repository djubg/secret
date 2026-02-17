import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import psutil
from PySide6.QtCore import QObject, QTimer, Signal


class YoloEngineManager(QObject):
    status_changed = Signal(str)
    runtime_changed = Signal(str)
    output_line = Signal(str)
    model_changed = Signal(str)

    def __init__(self, project_root: Path, engine_executable: Path | None = None):
        super().__init__()
        self.project_root = project_root
        self.main_script = self.project_root / "main.py"
        self.engine_executable = engine_executable
        self.status = "Stopped"
        self.model = "unknown"
        self.started_at: datetime | None = None
        self._paused_seconds = 0
        self._pause_started: datetime | None = None
        self._process: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._suppress_next_nonzero_exit_log = False
        self.runtime_timer = QTimer(self)
        self.runtime_timer.timeout.connect(self._emit_runtime)

    def set_model(self, model_path: str) -> None:
        self.model = model_path
        self.model_changed.emit(Path(model_path).name if model_path else "unknown")

    def start(self) -> None:
        if self._is_running():
            return

        command: list[str] | None = None
        if self.engine_executable and self.engine_executable.exists():
            command = [str(self.engine_executable)]
        elif self.main_script.exists():
            command = [sys.executable, str(self.main_script)]
        else:
            self._set_status("Error")
            if getattr(sys, "frozen", False):
                self.output_line.emit(
                    "Engine executable not found. Expected NovaEngine.exe next to NovaDesktop.exe."
                )
            else:
                self.output_line.emit(f"main.py not found: {self.main_script}")
            return

        try:
            self._process = subprocess.Popen(
                command,
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as exc:
            self._set_status("Error")
            self.output_line.emit(f"Failed to start main.py: {exc}")
            return

        self.started_at = datetime.utcnow()
        self._paused_seconds = 0
        self._pause_started = None
        self._suppress_next_nonzero_exit_log = False
        self.runtime_timer.start(1000)
        self._set_status("Running")
        self._start_reader_thread()

    def pause(self) -> None:
        if not self._is_running() or self.status != "Running":
            return
        try:
            psutil.Process(self._process.pid).suspend()
            self._pause_started = datetime.utcnow()
            self._set_status("Paused")
            self.output_line.emit("main.py paused.")
        except Exception as exc:
            self._set_status("Error")
            self.output_line.emit(f"Pause failed: {exc}")

    def resume(self) -> None:
        if not self._is_running() or self.status != "Paused":
            return
        try:
            psutil.Process(self._process.pid).resume()
            if self._pause_started:
                self._paused_seconds += int((datetime.utcnow() - self._pause_started).total_seconds())
            self._pause_started = None
            self._set_status("Running")
            self.output_line.emit("main.py resumed.")
        except Exception as exc:
            self._set_status("Error")
            self.output_line.emit(f"Resume failed: {exc}")

    def stop(self) -> None:
        if self._process and self._is_running():
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        self._process = None
        self.runtime_timer.stop()
        self.started_at = None
        self._paused_seconds = 0
        self._pause_started = None
        self._suppress_next_nonzero_exit_log = False
        self.runtime_changed.emit("00:00:00")
        self._set_status("Stopped")

    def restart(self) -> None:
        self.stop()
        self.start()

    def _is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _start_reader_thread(self) -> None:
        if not self._process or not self._process.stdout:
            return

        def _pump_output():
            assert self._process is not None
            assert self._process.stdout is not None
            suppress_traceback = False
            for line in self._process.stdout:
                msg = line.rstrip()
                if not msg:
                    continue

                if msg.startswith("Traceback (most recent call last):"):
                    suppress_traceback = True
                    continue

                if suppress_traceback:
                    lowered = msg.lower()
                    if msg.startswith(("ImportError:", "ModuleNotFoundError:", "OSError:")):
                        if "cv2" in lowered and (
                            "application control policy" in lowered
                            or "blocked this file" in lowered
                            or "a bloque ce fichier" in lowered
                            or "bloque ce fichier" in lowered
                        ):
                            self.output_line.emit(
                                "Erreur demarrage: OpenCV (cv2) est bloque par la politique de controle "
                                "d'application Windows."
                            )
                            self._suppress_next_nonzero_exit_log = True
                        else:
                            self.output_line.emit(msg)
                        suppress_traceback = False
                    continue

                self.output_line.emit(msg)

        self._reader_thread = threading.Thread(target=_pump_output, daemon=True)
        self._reader_thread.start()

    def _set_status(self, value: str) -> None:
        self.status = value
        self.status_changed.emit(value)

    def _emit_runtime(self) -> None:
        if not self.started_at:
            self.runtime_changed.emit("00:00:00")
            return

        if self._process and self._process.poll() is not None:
            code = self._process.returncode
            self._process = None
            self.runtime_timer.stop()
            self.started_at = None
            self._paused_seconds = 0
            self._pause_started = None
            self.runtime_changed.emit("00:00:00")
            if code == 0:
                self._set_status("Stopped")
                self.output_line.emit("main.py stopped.")
            else:
                self._set_status("Error")
                if not self._suppress_next_nonzero_exit_log:
                    self.output_line.emit(f"main.py exited with code {code}.")
                self._suppress_next_nonzero_exit_log = False
            return

        now = datetime.utcnow()
        paused = self._paused_seconds
        if self.status == "Paused" and self._pause_started:
            paused += int((now - self._pause_started).total_seconds())
        elapsed = max(int((now - self.started_at).total_seconds()) - paused, 0)
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        self.runtime_changed.emit(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

