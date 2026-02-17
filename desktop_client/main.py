import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from desktop_client.gui.main_window import MainWindow


def app_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.getenv("APPDATA", Path.home()))
        new_path = base / "NovaDesktop"
        legacy_path = base / "ProLicenseDesktop"
    else:
        home = Path.home()
        new_path = home / ".nova_desktop"
        legacy_path = home / ".pro_license_desktop"
    if legacy_path.exists() and not new_path.exists():
        return legacy_path
    return new_path


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow(app_data_dir())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
