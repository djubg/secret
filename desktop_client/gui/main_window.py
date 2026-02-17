from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import requests
from PySide6.QtCore import QSize, QTimer, Qt, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QComboBox,
    QSystemTrayIcon,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from desktop_client.config.manager import ConfigManager
from desktop_client.config.version import APP_NAME, APP_VERSION
from desktop_client.license_client.anti_tamper import debugger_detected, verify_checksums
from desktop_client.license_client.client import LicenseApiClient
from desktop_client.license_client.license_manager import LicenseManager, LicenseState
from desktop_client.updater.updater_client import UpdaterClient
from desktop_client.utils.crypto.aes_store import SecureKeyStore
from desktop_client.utils.crypto.hmac_signer import HMACSigner
from desktop_client.utils.logging_utils import LogEmitter, configure_logger
from desktop_client.utils.system_info import machine_stats
from desktop_client.yolo_engine.manager import YoloEngineManager
from desktop_client.yolo_engine.options_adapter import OptionsAdapter


def _format_seconds(seconds: int | None) -> str:
    if seconds is None:
        return "lifetime"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def _bool_to_text(value: bool) -> str:
    return "True" if value else "False"


def _text_to_bool(value: str) -> bool:
    return value.strip().lower() == "true"


LOG_LEVEL_RE = re.compile(r"\[(INFO|WARNING|ERROR|DEBUG)\]")
# Change this to "nova_logo_b.svg" if you prefer the second logo.
BRAND_ICON_FILE = "nova_logo_a.svg"
DISCORD_INVITE_URL = "https://discord.gg/fsf2tMGe35"


class MainWindow(QMainWindow):
    def __init__(self, app_dir: Path):
        super().__init__()
        self.app_dir = app_dir
        self.app_dir.mkdir(parents=True, exist_ok=True)
        if getattr(sys, "frozen", False):
            self.install_root = Path(sys.executable).resolve().parent
            self.project_root = self.install_root / "engine"
            self.engine_executable = self.install_root / "NovaEngine.exe"
        else:
            self.install_root = Path(__file__).resolve().parents[2]
            self.project_root = self.install_root
            self.engine_executable = None
        self.icons_dir = Path(__file__).resolve().parent / "icons"
        self.options_path = self.project_root / "options.py"
        self.options_adapter = OptionsAdapter(self.options_path)

        self.config_manager = ConfigManager(self.app_dir / "config.json")
        self.settings = self.config_manager.settings

        self.log_emitter = LogEmitter()
        self.logger = configure_logger(self.app_dir / "logs" / "app.log", self.log_emitter)

        self.engine = YoloEngineManager(self.project_root, self.engine_executable)
        self.license_manager = self._build_license_manager()
        self.license_manager.set_user_token(self.settings.user_token)
        self.updater = UpdaterClient(self.settings.api_base_url)
        self._all_log_lines: list[str] = []
        self._latest_update_payload: dict | None = None
        self._notified_update_version: str = ""
        self._notified_update_notice_id: str = ""

        self.validation_timer = QTimer(self)
        self.validation_timer.timeout.connect(self.validate_license_silent)
        self.validation_timer.start(60 * 1000)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.check_updates_silent)

        self.brand_icon = self._resolve_brand_icon()
        self.setWindowIcon(self.brand_icon)
        self.tray = QSystemTrayIcon(self.brand_icon, self)
        self.tray.setToolTip(APP_NAME)
        self.tray.show()

        self._build_ui()
        self._wire_events()
        self._run_security_checks()
        self._load_settings_into_ui()
        self._load_options_into_ui()
        self._startup_validation()
        self._schedule_update_check()

    def _build_license_manager(self) -> LicenseManager:
        api_client = LicenseApiClient(self.settings.api_base_url)
        key_store = SecureKeyStore(
            target_file=self.app_dir / "license.sec",
            secret_phrase=f"{APP_NAME}:{machine_stats().machine_name}:{APP_VERSION}",
        )
        signer = HMACSigner(secret=f"{APP_NAME}:{APP_VERSION}:signer")
        return LicenseManager(api_client, key_store, signer)

    def _resolve_brand_icon(self) -> QIcon:
        preferred = self.icons_dir / BRAND_ICON_FILE
        if preferred.exists():
            icon = QIcon(str(preferred))
            if not icon.isNull():
                return icon
        fallback = self.icons_dir / "dashboard.svg"
        if fallback.exists():
            icon = QIcon(str(fallback))
            if not icon.isNull():
                return icon
        return self.style().standardIcon(QStyle.StandardPixmap.SP_DesktopIcon)

    def _build_ui(self) -> None:
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1440, 900)

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        side_rail = QFrame()
        side_rail.setObjectName("SideRail")
        side_rail.setFixedWidth(74)
        side_layout = QVBoxLayout(side_rail)
        side_layout.setContentsMargins(10, 12, 10, 12)
        side_layout.setSpacing(10)

        self.nav_dashboard_btn = QPushButton()
        self.nav_dashboard_btn.setObjectName("NavButtonActive")
        self.nav_dashboard_btn.setToolTip("Dashboard")
        self.nav_settings_btn = QPushButton()
        self.nav_settings_btn.setObjectName("NavButton")
        self.nav_settings_btn.setToolTip("Settings")
        self.nav_profile_btn = QPushButton()
        self.nav_profile_btn.setObjectName("NavButton")
        self.nav_profile_btn.setToolTip("Profile")
        self.nav_logs_btn = QPushButton()
        self.nav_logs_btn.setObjectName("NavButton")
        self.nav_logs_btn.setToolTip("Logs")

        icons_dir = self.icons_dir
        nav_buttons = (
            (self.nav_dashboard_btn, "dashboard.svg", QStyle.StandardPixmap.SP_DesktopIcon),
            (self.nav_settings_btn, "settings.svg", QStyle.StandardPixmap.SP_FileDialogDetailedView),
            (self.nav_profile_btn, "profile.svg", QStyle.StandardPixmap.SP_DirHomeIcon),
            (self.nav_logs_btn, "logs.svg", QStyle.StandardPixmap.SP_FileDialogListView),
        )
        for button, svg_name, fallback_pixmap in nav_buttons:
            button.setFixedSize(46, 46)
            svg_path = icons_dir / svg_name
            icon = QIcon(str(svg_path)) if svg_path.exists() else self.style().standardIcon(fallback_pixmap)
            button.setIcon(icon)
            button.setIconSize(QSize(20, 20))
            button.setText("")
            side_layout.addWidget(button)
        side_layout.addStretch()

        self.discord_btn = QPushButton()
        self.discord_btn.setObjectName("NavButton")
        self.discord_btn.setToolTip("Community")
        self.discord_btn.setFixedSize(46, 46)
        community_svg = icons_dir / "community.svg"
        community_icon = (
            QIcon(str(community_svg))
            if community_svg.exists()
            else self.style().standardIcon(QStyle.StandardPixmap.SP_DialogHelpButton)
        )
        self.discord_btn.setIcon(community_icon)
        self.discord_btn.setIconSize(QSize(20, 20))
        self.discord_btn.setText("")
        self.community_icon = community_icon
        side_layout.addWidget(self.discord_btn)
        root.addWidget(side_rail)

        content_root = QVBoxLayout()
        content_root.setSpacing(12)
        root.addLayout(content_root, 1)

        top_header = QFrame()
        top_header.setObjectName("TopHeader")
        top_layout = QHBoxLayout(top_header)
        top_layout.setContentsMargins(16, 12, 16, 12)

        brand_col = QVBoxLayout()
        self.brand_title = QLabel(f"{APP_NAME} v{APP_VERSION}")
        self.brand_title.setObjectName("BrandTitle")
        self.brand_subtitle = QLabel("Aimbot orchestration, telemetry and license control")
        self.brand_subtitle.setObjectName("BrandSubtitle")
        brand_col.addWidget(self.brand_title)
        brand_col.addWidget(self.brand_subtitle)
        top_layout.addLayout(brand_col)
        top_layout.addStretch()
        self.page_name_label = QLabel("Dashboard")
        self.page_name_label.setObjectName("PageName")
        top_layout.addWidget(self.page_name_label)
        content_root.addWidget(top_header)

        self.content_stack = QStackedWidget()
        content_root.addWidget(self.content_stack, 1)

        # Shared widgets
        self.start_btn = QPushButton("Start")
        self.start_btn.setObjectName("BtnPrimary")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("BtnGhost")
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setObjectName("BtnGhost")
        self.restart_btn = QPushButton("Restart")
        self.restart_btn.setObjectName("BtnGhost")

        self.model_path_input = QLineEdit()
        self.model_browse_btn = QPushButton("Browse Model")
        self.ai_conf_input = QLineEdit()
        self.ai_iou_input = QLineEdit()
        self.auto_aim_combo = QComboBox()
        self.auto_shoot_combo = QComboBox()
        self.show_window_combo = QComboBox()
        for combo in (self.auto_aim_combo, self.auto_shoot_combo, self.show_window_combo):
            combo.addItems(["True", "False"])
        self.save_options_btn = QPushButton("Save options.py")
        self.reload_options_btn = QPushButton("Reload options.py")

        self.license_prompt_label = QLabel("Activation required to unlock controls.")
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("Enter access key (LIC-...)")
        self.activate_btn = QPushButton("Activate Key")
        self.validate_btn = QPushButton("Validate Now")
        self.buy_license_btn = QPushButton("Acheter sur Discord")
        self.buy_license_btn.setObjectName("BtnDiscord")
        self.buy_license_btn.setToolTip("Ouvrir Discord pour acheter une licence")
        self.access_message_label = QLabel("License active. Activation form hidden.")
        self.access_remaining_label = QLabel("Remaining: -")
        self.revalidate_btn = QPushButton("Revalidate Now")

        self.account_email_input = QLineEdit()
        self.account_email_input.setPlaceholderText("Email")
        self.account_password_input = QLineEdit()
        self.account_password_input.setPlaceholderText("Password")
        self.account_password_input.setEchoMode(QLineEdit.Password)
        self.account_login_btn = QPushButton("Login")
        self.account_login_btn.setObjectName("BtnGhost")
        self.account_register_btn = QPushButton("Create Account")
        self.account_register_btn.setObjectName("BtnPrimary")
        self.account_logout_btn = QPushButton("Logout")
        self.account_logout_btn.setObjectName("BtnGhost")
        self.account_status_label = QLabel("Not connected")
        self.account_status_label.setObjectName("InlineStatus")

        self.profile_user_id_label = QLabel("User ID: -")
        self.profile_display_name_input = QLineEdit()
        self.profile_display_name_input.setPlaceholderText("Display name")
        self.profile_avatar_label = QLabel("Avatar: -")
        self.profile_avatar_upload_btn = QPushButton("Upload Avatar")
        self.profile_avatar_upload_btn.setObjectName("BtnGhost")
        self.profile_save_btn = QPushButton("Save Profile")
        self.profile_save_btn.setObjectName("BtnPrimary")
        self.profile_refresh_btn = QPushButton("Refresh Profile")
        self.profile_refresh_btn.setObjectName("BtnGhost")

        self.system_label = QLabel("-")
        self.license_label = QLabel("License: Not validated")
        self.runtime_label = QLabel("Runtime: 00:00:00")
        self.model_label = QLabel("Active model: -")
        self.status_label = QLabel("Status: Stopped")
        self.entrypoint_label = QLabel(f"Entrypoint: {self.project_root / 'main.py'}")
        self.system_label.setWordWrap(True)
        self.entrypoint_label.setWordWrap(True)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["nova", "light"])
        self.reset_btn = QPushButton("Reset to Default")

        self.update_banner = QFrame()
        self.update_banner.setObjectName("UpdateBanner")
        self.update_banner.setVisible(False)
        update_banner_layout = QVBoxLayout(self.update_banner)
        update_banner_layout.setContentsMargins(20, 16, 20, 16)
        update_banner_layout.setSpacing(8)
        self.update_banner_title = QLabel("Mise a jour disponible")
        self.update_banner_title.setObjectName("UpdateBannerTitle")
        self.update_banner_text = QLabel("Une nouvelle version est prete.")
        self.update_banner_text.setObjectName("UpdateBannerText")
        self.update_banner_text.setWordWrap(True)
        update_action_layout = QHBoxLayout()
        self.update_action_btn = QPushButton("Mettre a jour")
        self.update_action_btn.setObjectName("BtnPrimary")
        self.update_progress = QProgressBar()
        self.update_progress.setRange(0, 100)
        self.update_progress.setValue(0)
        self.update_progress.setVisible(False)
        update_action_layout.addWidget(self.update_action_btn)
        update_action_layout.addWidget(self.update_progress, 1)
        update_banner_layout.addWidget(self.update_banner_title)
        update_banner_layout.addWidget(self.update_banner_text)
        update_banner_layout.addLayout(update_action_layout)

        self.log_filter_combo = QComboBox()
        self.log_filter_combo.addItems(["ALL", "INFO", "WARNING", "ERROR", "DEBUG"])
        self.clear_logs_btn = QPushButton("Clear")
        self.clear_logs_btn.setObjectName("BtnGhost")
        self.logs_view = QTextEdit()
        self.logs_view.setObjectName("LogsView")
        self.logs_view.setFontFamily("Consolas")
        self.logs_view.setReadOnly(True)
        self.export_logs_btn = QPushButton("Export Logs (.txt)")
        self.version_label = QLabel(f"Version: {APP_VERSION}")
        self.version_label.setAlignment(Qt.AlignRight)
        self.version_label.setObjectName("VersionLabel")

        # Dashboard page
        dashboard_page = QWidget()
        dashboard_layout = QVBoxLayout(dashboard_page)
        dashboard_layout.setSpacing(12)

        hero = QFrame()
        hero.setObjectName("HeroPanel")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 24, 28, 24)
        hero_title = QLabel("Ready To Run")
        hero_title.setObjectName("HeroTitle")
        hero_subtitle = QLabel("Start engine, monitor capture quality, and manage keys in one place")
        hero_subtitle.setObjectName("HeroSubtitle")
        hero_layout.addWidget(hero_title)
        hero_layout.addWidget(hero_subtitle)
        dashboard_layout.addWidget(hero)
        dashboard_layout.addWidget(self.update_banner)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)

        def make_kpi(title: str, value: str, hint: str) -> tuple[QFrame, QLabel]:
            card = QFrame()
            card.setObjectName("KpiCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)
            title_label = QLabel(title)
            title_label.setObjectName("KpiTitle")
            value_label = QLabel(value)
            value_label.setObjectName("KpiValue")
            hint_label = QLabel(hint)
            hint_label.setObjectName("KpiHint")
            card_layout.addWidget(title_label)
            card_layout.addWidget(value_label)
            card_layout.addWidget(hint_label)
            return card, value_label

        kpi_engine, self.kpi_engine_value = make_kpi("Engine", "STOPPED", "Status")
        kpi_runtime, self.kpi_runtime_value = make_kpi("Runtime", "00:00:00", "Session")
        kpi_model, self.kpi_model_value = make_kpi("Model", "-", "Active")
        kpi_license, self.kpi_license_value = make_kpi("License", "UNKNOWN", "Entitlement")
        kpi_capture, self.kpi_capture_value = make_kpi("Capture FPS", "-", "Stream")
        for card in (kpi_engine, kpi_runtime, kpi_model, kpi_license, kpi_capture):
            kpi_row.addWidget(card)
        dashboard_layout.addLayout(kpi_row)

        controls_box = QGroupBox("Quick Actions")
        controls_box.setObjectName("CardGroup")
        controls_layout = QHBoxLayout(controls_box)
        controls_layout.addWidget(self.start_btn)
        controls_layout.addWidget(self.pause_btn)
        controls_layout.addWidget(self.stop_btn)
        controls_layout.addWidget(self.restart_btn)
        dashboard_layout.addWidget(controls_box)

        self.system_box = QGroupBox("System Overview")
        self.system_box.setObjectName("CardGroup")
        system_layout = QGridLayout(self.system_box)
        system_layout.addWidget(self.system_label, 0, 0, 1, 2)
        system_layout.addWidget(self.license_label, 1, 0, 1, 2)
        system_layout.addWidget(self.runtime_label, 2, 0)
        system_layout.addWidget(self.model_label, 2, 1)
        system_layout.addWidget(self.status_label, 3, 0, 1, 2)
        system_layout.addWidget(self.entrypoint_label, 4, 0, 1, 2)
        dashboard_layout.addWidget(self.system_box)
        dashboard_layout.addStretch()
        self.content_stack.addWidget(dashboard_page)

        # Settings page
        settings_page = QWidget()
        settings_layout = QVBoxLayout(settings_page)
        settings_layout.setSpacing(12)

        options_box = QGroupBox("Aimbot Settings (options.py)")
        options_box.setObjectName("CardGroup")
        options_layout = QGridLayout(options_box)
        options_layout.addWidget(QLabel("AI_model_path"), 0, 0)
        options_layout.addWidget(self.model_path_input, 0, 1)
        options_layout.addWidget(self.model_browse_btn, 0, 2)
        options_layout.addWidget(QLabel("AI_conf"), 1, 0)
        options_layout.addWidget(self.ai_conf_input, 1, 1)
        options_layout.addWidget(QLabel("AI_iou"), 1, 2)
        options_layout.addWidget(self.ai_iou_input, 1, 3)
        options_layout.addWidget(QLabel("mouse_auto_aim"), 2, 0)
        options_layout.addWidget(self.auto_aim_combo, 2, 1)
        options_layout.addWidget(QLabel("mouse_auto_shoot"), 2, 2)
        options_layout.addWidget(self.auto_shoot_combo, 2, 3)
        options_layout.addWidget(QLabel("show_window"), 3, 0)
        options_layout.addWidget(self.show_window_combo, 3, 1)
        options_layout.addWidget(self.save_options_btn, 4, 2)
        options_layout.addWidget(self.reload_options_btn, 4, 3)
        settings_layout.addWidget(options_box)

        app_settings_box = QGroupBox("Desktop App Settings")
        app_settings_box.setObjectName("CardGroup")
        app_settings_layout = QGridLayout(app_settings_box)
        app_settings_layout.addWidget(QLabel("Theme"), 0, 0)
        app_settings_layout.addWidget(self.theme_combo, 0, 1)
        app_settings_layout.addWidget(self.reset_btn, 1, 1)
        settings_layout.addWidget(app_settings_box)

        settings_layout.addStretch()
        self.content_stack.addWidget(settings_page)

        # Profile page
        profile_page = QWidget()
        profile_layout = QVBoxLayout(profile_page)
        profile_layout.setSpacing(12)

        account_box = QGroupBox("Account")
        account_box.setObjectName("CardGroup")
        account_layout = QGridLayout(account_box)
        account_layout.addWidget(QLabel("Email"), 0, 0)
        account_layout.addWidget(self.account_email_input, 0, 1, 1, 2)
        account_layout.addWidget(QLabel("Password"), 1, 0)
        account_layout.addWidget(self.account_password_input, 1, 1, 1, 2)
        account_layout.addWidget(self.account_register_btn, 2, 0)
        account_layout.addWidget(self.account_login_btn, 2, 1)
        account_layout.addWidget(self.account_logout_btn, 2, 2)
        account_layout.addWidget(self.account_status_label, 3, 0, 1, 3)
        profile_layout.addWidget(account_box)

        profile_box = QGroupBox("Public Profile")
        profile_box.setObjectName("CardGroup")
        profile_box_layout = QGridLayout(profile_box)
        profile_box_layout.addWidget(self.profile_user_id_label, 0, 0, 1, 3)
        profile_box_layout.addWidget(QLabel("Display name"), 1, 0)
        profile_box_layout.addWidget(self.profile_display_name_input, 1, 1, 1, 2)
        profile_box_layout.addWidget(self.profile_avatar_label, 2, 0, 1, 3)
        profile_box_layout.addWidget(self.profile_avatar_upload_btn, 3, 0)
        profile_box_layout.addWidget(self.profile_save_btn, 3, 1)
        profile_box_layout.addWidget(self.profile_refresh_btn, 3, 2)
        profile_layout.addWidget(profile_box)

        self.license_box = QGroupBox("License")
        self.license_box.setObjectName("CardGroup")
        license_layout = QGridLayout(self.license_box)
        self.buy_license_btn.setIcon(self.community_icon)
        self.buy_license_btn.setIconSize(QSize(16, 16))
        license_layout.addWidget(self.license_prompt_label, 0, 0, 1, 2)
        license_layout.addWidget(self.key_input, 1, 0, 1, 2)
        license_layout.addWidget(self.activate_btn, 2, 0)
        license_layout.addWidget(self.validate_btn, 2, 1)
        license_layout.addWidget(self.buy_license_btn, 3, 0, 1, 2)
        profile_layout.addWidget(self.license_box)

        self.access_box = QGroupBox("Access Status")
        self.access_box.setObjectName("CardGroup")
        access_layout = QGridLayout(self.access_box)
        access_layout.addWidget(self.access_message_label, 0, 0, 1, 2)
        access_layout.addWidget(self.access_remaining_label, 1, 0, 1, 2)
        access_layout.addWidget(self.revalidate_btn, 2, 1)
        self.access_box.setVisible(False)
        profile_layout.addWidget(self.access_box)
        profile_layout.addStretch()
        self.content_stack.addWidget(profile_page)

        # Logs page
        logs_page = QWidget()
        logs_page_layout = QVBoxLayout(logs_page)
        logs_page_layout.setSpacing(12)

        logs_box = QGroupBox("Realtime Logs (main.py + app)")
        logs_box.setObjectName("CardGroup")
        logs_layout = QVBoxLayout(logs_box)
        log_toolbar = QHBoxLayout()
        log_toolbar.addWidget(QLabel("Level"))
        log_toolbar.addWidget(self.log_filter_combo)
        log_toolbar.addStretch()
        log_toolbar.addWidget(self.clear_logs_btn)
        logs_layout.addLayout(log_toolbar)
        logs_layout.addWidget(self.logs_view)
        logs_layout.addWidget(self.export_logs_btn)
        logs_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        logs_page_layout.addWidget(logs_box, 1)
        logs_page_layout.addWidget(self.version_label)
        self.content_stack.addWidget(logs_page)

        self._set_active_nav(0)

    def _wire_events(self) -> None:
        self.engine.status_changed.connect(self._on_engine_status)
        self.engine.runtime_changed.connect(self._on_engine_runtime)
        self.engine.model_changed.connect(self._on_engine_model)
        self.engine.output_line.connect(self._on_engine_output)

        self.log_emitter.line_ready.connect(self._on_app_log_line)

        self.start_btn.clicked.connect(self.on_start)
        self.stop_btn.clicked.connect(self.on_stop)
        self.pause_btn.clicked.connect(self.on_pause_resume)
        self.restart_btn.clicked.connect(self.on_restart)
        self.model_browse_btn.clicked.connect(self.on_select_model)
        self.save_options_btn.clicked.connect(self.on_save_options)
        self.reload_options_btn.clicked.connect(self.on_reload_options)

        self.activate_btn.clicked.connect(self.on_activate_key)
        self.validate_btn.clicked.connect(self.on_validate_key)
        self.revalidate_btn.clicked.connect(self.on_validate_key)

        self.theme_combo.currentTextChanged.connect(self.on_settings_changed)
        self.reset_btn.clicked.connect(self.on_reset_settings)

        self.update_action_btn.clicked.connect(self.on_update_now)
        self.export_logs_btn.clicked.connect(self.on_export_logs)
        self.clear_logs_btn.clicked.connect(self.on_clear_logs)
        self.log_filter_combo.currentTextChanged.connect(lambda _value: self._render_logs())
        self.account_login_btn.clicked.connect(self.on_account_login)
        self.account_register_btn.clicked.connect(self.on_account_register)
        self.account_logout_btn.clicked.connect(self.on_account_logout)
        self.profile_refresh_btn.clicked.connect(self.on_profile_refresh)
        self.profile_save_btn.clicked.connect(self.on_profile_save)
        self.profile_avatar_upload_btn.clicked.connect(self.on_profile_upload_avatar)
        self.buy_license_btn.clicked.connect(self.on_open_discord)
        self.discord_btn.clicked.connect(self.on_open_discord)

        self.nav_dashboard_btn.clicked.connect(lambda: self._set_active_nav(0))
        self.nav_settings_btn.clicked.connect(lambda: self._set_active_nav(1))
        self.nav_profile_btn.clicked.connect(lambda: self._set_active_nav(2))
        self.nav_logs_btn.clicked.connect(lambda: self._set_active_nav(3))
        self.account_email_input.editingFinished.connect(self._save_profile_draft)
        self.profile_display_name_input.editingFinished.connect(self._save_profile_draft)

    def _set_active_nav(self, page_index: int) -> None:
        self._save_profile_draft()
        titles = ("Dashboard", "Settings", "Profile", "Logs")
        buttons = (
            self.nav_dashboard_btn,
            self.nav_settings_btn,
            self.nav_profile_btn,
            self.nav_logs_btn,
        )
        self.content_stack.setCurrentIndex(page_index)
        self.page_name_label.setText(titles[page_index])

        for index, button in enumerate(buttons):
            button.setObjectName("NavButtonActive" if index == page_index else "NavButton")
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def _save_profile_draft(self) -> None:
        email = self.account_email_input.text().strip()
        display_name = self.profile_display_name_input.text().strip()
        changed = False
        if self.settings.user_email != email:
            self.settings.user_email = email
            changed = True
        if self.settings.user_display_name != display_name:
            self.settings.user_display_name = display_name
            changed = True
        if changed:
            self.config_manager.save()

    def _http_error_detail(self, exc: Exception) -> str:
        if not isinstance(exc, requests.HTTPError):
            return str(exc)
        response = exc.response
        if response is None:
            return str(exc)
        try:
            payload = response.json()
            detail = payload.get("detail")
            if detail:
                return str(detail)
        except Exception:
            pass
        text = response.text.strip()
        return text or str(exc)

    def _account_required_state(self, message: str | None = None) -> LicenseState:
        return LicenseState(
            is_valid=False,
            key="",
            status="account_required",
            message=message or "Create or login to your account first, then enter your license key.",
        )

    def _validate_license_after_auth(self, prompt_if_needed: bool = True) -> None:
        try:
            self.license_manager.set_user_token(self.settings.user_token)
            state = self.license_manager.validate_current()
            self._apply_license_state(state, show_popup=False)
            if state.is_valid or not prompt_if_needed:
                return
            activated = self._prompt_for_license_key(state.message, allow_cancel=True)
            self._apply_license_state(activated, show_popup=False)
        except Exception as exc:
            self.logger.exception("Post-login license validation failed: %s", exc)
            self._apply_license_state(
                LicenseState(False, "", "error", f"Validation error: {exc}"),
                show_popup=False,
            )

    def _load_settings_into_ui(self) -> None:
        stats = machine_stats()
        self.system_label.setText(
            f"{stats.machine_name} | CPU: {stats.cpu_name} | RAM: {stats.ram_gb} GB | OS: {stats.os_name}"
        )
        selected_theme = self.settings.theme
        if selected_theme in {"dark", "lunar"}:
            selected_theme = "nova"
        if selected_theme not in {"nova", "light"}:
            selected_theme = "nova"
        self.theme_combo.setCurrentText(selected_theme)
        self.apply_theme(selected_theme)
        self.account_email_input.setText(self.settings.user_email or "")
        self.profile_display_name_input.setText(self.settings.user_display_name or "")
        self.profile_user_id_label.setText(f"User ID: {self.settings.user_id or '-'}")
        self.profile_avatar_label.setText(f"Avatar: {self.settings.user_avatar_url or '-'}")
        if self.settings.user_token:
            self.account_status_label.setText(f"Connected as {self.settings.user_email or 'user'}")
            self.on_profile_refresh(silent=True)
        else:
            self.account_status_label.setText("Not connected")
            self._apply_license_state(self._account_required_state(), show_popup=False)

    def _load_options_into_ui(self) -> None:
        try:
            options = self.options_adapter.load()
        except Exception as exc:
            self.logger.warning("Cannot read options.py: %s", exc)
            QMessageBox.warning(self, "options.py", f"Impossible de lire options.py:\n{exc}")
            return

        model_path = str(options.get("AI_model_path", "models/best.onnx"))
        self.model_path_input.setText(model_path)
        self.ai_conf_input.setText(str(options.get("AI_conf", 0.35)))
        self.ai_iou_input.setText(str(options.get("AI_iou", 0.1)))
        self.auto_aim_combo.setCurrentText(_bool_to_text(bool(options.get("mouse_auto_aim", True))))
        self.auto_shoot_combo.setCurrentText(_bool_to_text(bool(options.get("mouse_auto_shoot", True))))
        self.show_window_combo.setCurrentText(_bool_to_text(bool(options.get("show_window", True))))
        self.engine.set_model(model_path)

    def _run_security_checks(self) -> None:
        if debugger_detected():
            QMessageBox.critical(self, "Security", "Debugger detected. Application will close.")
            raise SystemExit(1)
        if getattr(sys, "frozen", False):
            # In packaged mode, source file paths from checksums.json do not map
            # 1:1 to extracted runtime files, so strict source checksum validation
            # is skipped to avoid false positives like "Missing file: main.py".
            self.logger.info("Checksum validation skipped in packaged runtime mode.")
            return
        ok, message = verify_checksums(
            checksum_file=Path(__file__).resolve().parent.parent / "config" / "checksums.json",
            root_dir=Path(__file__).resolve().parent.parent,
        )
        if not ok:
            QMessageBox.critical(self, "Security", message)
            raise SystemExit(1)

    def _startup_validation(self) -> None:
        try:
            if not self.settings.user_token:
                self._apply_license_state(self._account_required_state(), show_popup=False)
                self._set_active_nav(2)
                return
            state = self.license_manager.validate_current()
            if state.is_valid:
                self._apply_license_state(state, show_popup=False)
                return
            activated = self._prompt_for_license_key(state.message, allow_cancel=True)
            self._apply_license_state(activated, show_popup=False)
        except Exception as exc:
            self.logger.exception("Startup validation failed: %s", exc)
            self._apply_license_state(
                LicenseState(False, "", "error", f"Validation error: {exc}"),
                show_popup=True,
            )

    def _prompt_for_license_key(self, reason: str, allow_cancel: bool) -> LicenseState:
        if not self.settings.user_token:
            return self._account_required_state()
        message = reason or "A valid license key is required."
        while True:
            key, ok = QInputDialog.getText(
                self,
                "License Required",
                f"{message}\n\nEnter your access key:",
                QLineEdit.Normal,
            )
            if not ok:
                if allow_cancel:
                    self._set_active_nav(2)
                    return LicenseState(
                        False,
                        "",
                        "cancelled",
                        "License validation cancelled. Use 'Acheter sur Discord' if you do not have a key.",
                    )
                self._set_active_nav(2)
                return LicenseState(
                    False,
                    "",
                    "missing",
                    "License key required. Use 'Acheter sur Discord' if you do not have a key.",
                )

            key = key.strip()
            if not key:
                message = "Access key is required."
                continue

            state = self._activate_or_validate_key(key)
            if state.is_valid:
                return state
            message = state.message or "Invalid access key."

    def _activate_or_validate_key(self, key: str) -> LicenseState:
        try:
            state = self.license_manager.activate(key)
            if state.is_valid:
                return state
            return self.license_manager.validate_key(key)
        except Exception as exc:
            return LicenseState(False, key, "error", str(exc))

    def _apply_license_state(self, state: LicenseState, show_popup: bool = False) -> None:
        text = f"License: {state.status} | {state.message}"
        if state.seconds_left is not None:
            text += f" | Remaining: {_format_seconds(state.seconds_left)}"
        elif state.expires_at is None and state.is_valid:
            text += " | Remaining: lifetime"
        self.license_label.setText(text)
        if state.is_valid:
            self.kpi_license_value.setText("ACTIVE")
        elif state.status == "account_required":
            self.kpi_license_value.setText("ACCOUNT")
        elif state.status == "cancelled":
            self.kpi_license_value.setText("PENDING")
        else:
            self.kpi_license_value.setText("INVALID")

        self.start_btn.setEnabled(state.is_valid)
        self.pause_btn.setEnabled(state.is_valid)
        self.stop_btn.setEnabled(state.is_valid)
        self.restart_btn.setEnabled(state.is_valid)

        account_required = state.status == "account_required"
        self.license_box.setVisible(not state.is_valid)
        self.access_box.setVisible(state.is_valid)
        self.license_prompt_label.setVisible(not state.is_valid)
        self.key_input.setVisible(not state.is_valid and not account_required)
        self.activate_btn.setVisible(not state.is_valid and not account_required)
        self.validate_btn.setVisible(not state.is_valid and not account_required)
        if account_required:
            self.license_prompt_label.setText("Create/login account first, then activate your license key.")
        else:
            self.license_prompt_label.setText("Activation required to unlock controls.")
        if state.is_valid:
            self.access_message_label.setText("License active. Activation form hidden.")
            if state.seconds_left is not None:
                self.access_remaining_label.setText(f"Remaining: {_format_seconds(state.seconds_left)}")
            elif state.expires_at is None:
                self.access_remaining_label.setText("Remaining: lifetime")
            else:
                self.access_remaining_label.setText(f"Expires at: {state.expires_at}")

        if not state.is_valid and self.engine.status in ("Running", "Paused"):
            self.engine.stop()
            self.logger.warning("Engine stopped because license is not valid.")

        if not state.is_valid and show_popup and not account_required:
            refreshed = self._prompt_for_license_key(state.message, allow_cancel=True)
            if refreshed.is_valid:
                self._apply_license_state(refreshed, show_popup=False)

    def on_start(self) -> None:
        if not self.on_save_options(show_message=False):
            return
        self.engine.start()

    def on_stop(self) -> None:
        self.engine.stop()
        self.pause_btn.setText("Pause")

    def on_pause_resume(self) -> None:
        if self.engine.status == "Running":
            self.engine.pause()
            return
        if self.engine.status == "Paused":
            self.engine.resume()

    def on_restart(self) -> None:
        if not self.on_save_options(show_message=False):
            return
        self.engine.restart()
        self.pause_btn.setText("Pause")

    def on_select_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select model",
            str(self.project_root / "models"),
            "YOLO model (*.onnx *.pt *.engine)",
        )
        if not path:
            return
        model_path = Path(path)
        try:
            rel = model_path.relative_to(self.project_root)
            self.model_path_input.setText(rel.as_posix())
        except ValueError:
            self.model_path_input.setText(str(model_path))
        self.engine.set_model(self.model_path_input.text().strip())

    def on_save_options(self, show_message: bool = True) -> bool:
        try:
            ai_conf = float(self.ai_conf_input.text().strip())
            ai_iou = float(self.ai_iou_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "options.py", "AI_conf et AI_iou doivent etre numeriques.")
            return False

        model_path = self.model_path_input.text().strip()
        if not model_path:
            QMessageBox.warning(self, "options.py", "AI_model_path est requis.")
            return False

        updates = {
            "AI_model_path": model_path,
            "AI_conf": ai_conf,
            "AI_iou": ai_iou,
            "mouse_auto_aim": _text_to_bool(self.auto_aim_combo.currentText()),
            "mouse_auto_shoot": _text_to_bool(self.auto_shoot_combo.currentText()),
            "show_window": _text_to_bool(self.show_window_combo.currentText()),
        }
        try:
            self.options_adapter.update(updates)
        except Exception as exc:
            self.logger.exception("Failed to save options.py: %s", exc)
            QMessageBox.critical(self, "options.py", f"Echec sauvegarde options.py:\n{exc}")
            return False

        self.engine.set_model(model_path)
        if show_message:
            QMessageBox.information(self, "options.py", "Settings sauvegardes dans options.py.")
        return True

    def on_reload_options(self) -> None:
        self._load_options_into_ui()

    def _store_user_session(self, payload: dict) -> None:
        token = payload.get("token", "")
        user = payload.get("user", {}) or {}
        self.settings.user_token = token
        self.settings.user_email = user.get("email", "")
        self.settings.user_display_name = user.get("display_name", "")
        self.settings.user_avatar_url = user.get("avatar_url") or ""
        self.settings.user_id = user.get("id", "")
        self.config_manager.save()
        self.license_manager.set_user_token(token)

        self.account_email_input.setText(self.settings.user_email)
        self.profile_display_name_input.setText(self.settings.user_display_name)
        self.profile_user_id_label.setText(f"User ID: {self.settings.user_id or '-'}")
        self.profile_avatar_label.setText(f"Avatar: {self.settings.user_avatar_url or '-'}")
        self.account_status_label.setText(f"Connected as {self.settings.user_email or 'user'}")

    def _clear_user_session(self) -> None:
        self.settings.user_token = ""
        self.settings.user_email = ""
        self.settings.user_display_name = ""
        self.settings.user_avatar_url = ""
        self.settings.user_id = ""
        self.config_manager.save()
        self.license_manager.set_user_token("")

        self.account_email_input.clear()
        self.account_password_input.clear()
        self.profile_display_name_input.clear()
        self.profile_user_id_label.setText("User ID: -")
        self.profile_avatar_label.setText("Avatar: -")
        self.account_status_label.setText("Not connected")

    def on_account_register(self) -> None:
        email = self.account_email_input.text().strip()
        password = self.account_password_input.text()
        display_name = self.profile_display_name_input.text().strip() or email.split("@")[0]
        if not email or not password:
            QMessageBox.warning(self, "Account", "Email and password are required.")
            return
        try:
            payload = self.license_manager.api_client.register(email=email, password=password, display_name=display_name)
            self._store_user_session(payload)
            self.account_password_input.clear()
            self.on_profile_refresh(silent=True)
            self._validate_license_after_auth(prompt_if_needed=True)
            QMessageBox.information(self, "Account", "Account created. License check refreshed.")
        except requests.HTTPError as exc:
            detail = self._http_error_detail(exc)
            self.logger.warning("Account registration failed: %s", detail)
            QMessageBox.warning(self, "Account", f"Registration failed:\n{detail}")
        except Exception as exc:
            self.logger.exception("Account registration failed: %s", exc)
            QMessageBox.critical(self, "Account", f"Registration failed:\n{exc}")

    def on_account_login(self) -> None:
        email = self.account_email_input.text().strip()
        password = self.account_password_input.text()
        if not email or not password:
            QMessageBox.warning(self, "Account", "Email and password are required.")
            return
        try:
            payload = self.license_manager.api_client.login(email=email, password=password)
            self._store_user_session(payload)
            self.account_password_input.clear()
            self.on_profile_refresh(silent=True)
            self._validate_license_after_auth(prompt_if_needed=True)
            QMessageBox.information(self, "Account", "Logged in. Profile and license refreshed.")
        except requests.HTTPError as exc:
            detail = self._http_error_detail(exc)
            self.logger.warning("Account login failed: %s", detail)
            QMessageBox.warning(self, "Account", f"Login failed:\n{detail}\n\nTip: create account first if needed.")
        except Exception as exc:
            self.logger.exception("Account login failed: %s", exc)
            QMessageBox.critical(self, "Account", f"Login failed:\n{exc}")

    def on_account_logout(self) -> None:
        self._clear_user_session()
        self._apply_license_state(self._account_required_state(), show_popup=False)
        self._set_active_nav(2)
        QMessageBox.information(self, "Account", "Logged out.")

    def on_profile_refresh(self, silent: bool = False) -> None:
        if not self.settings.user_token:
            if not silent:
                QMessageBox.warning(self, "Profile", "Connect an account first.")
            return
        try:
            self.license_manager.set_user_token(self.settings.user_token)
            user = self.license_manager.api_client.me()
            payload = {"token": self.settings.user_token, "user": user}
            self._store_user_session(payload)
            self._validate_license_after_auth(prompt_if_needed=False)
        except requests.HTTPError as exc:
            detail = self._http_error_detail(exc)
            self.logger.warning("Profile refresh failed: %s", detail)
            if exc.response is not None and exc.response.status_code == 401:
                self._clear_user_session()
                self._apply_license_state(
                    self._account_required_state("Session expired. Login first, then activate/validate license."),
                    show_popup=False,
                )
                if not silent:
                    QMessageBox.warning(self, "Profile", "Session expired. Please login again.")
                return
            if not silent:
                QMessageBox.warning(self, "Profile", f"Cannot refresh profile:\n{detail}")
        except Exception as exc:
            self.logger.warning("Profile refresh failed: %s", exc)
            if not silent:
                QMessageBox.warning(self, "Profile", f"Cannot refresh profile:\n{exc}")

    def on_profile_save(self) -> None:
        if not self.settings.user_token:
            QMessageBox.warning(self, "Profile", "Connect an account first.")
            return
        display_name = self.profile_display_name_input.text().strip()
        if not display_name:
            QMessageBox.warning(self, "Profile", "Display name is required.")
            return
        try:
            self.license_manager.set_user_token(self.settings.user_token)
            user = self.license_manager.api_client.update_profile(display_name=display_name)
            payload = {"token": self.settings.user_token, "user": user}
            self._store_user_session(payload)
            QMessageBox.information(self, "Profile", "Profile updated.")
        except Exception as exc:
            self.logger.exception("Profile update failed: %s", exc)
            QMessageBox.critical(self, "Profile", f"Profile update failed:\n{exc}")

    def on_profile_upload_avatar(self) -> None:
        if not self.settings.user_token:
            QMessageBox.warning(self, "Profile", "Connect an account first.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select avatar",
            str(self.project_root),
            "Image (*.png *.jpg *.jpeg *.webp)",
        )
        if not path:
            return
        try:
            self.license_manager.set_user_token(self.settings.user_token)
            user = self.license_manager.api_client.upload_avatar(path)
            payload = {"token": self.settings.user_token, "user": user}
            self._store_user_session(payload)
            QMessageBox.information(self, "Profile", "Avatar updated.")
        except Exception as exc:
            self.logger.exception("Avatar upload failed: %s", exc)
            QMessageBox.critical(self, "Profile", f"Avatar upload failed:\n{exc}")

    def on_open_discord(self) -> None:
        if not QDesktopServices.openUrl(QUrl(DISCORD_INVITE_URL)):
            QMessageBox.warning(self, "Discord", "Impossible d'ouvrir le lien Discord.")

    def on_activate_key(self) -> None:
        if not self.settings.user_token:
            self._set_active_nav(2)
            QMessageBox.warning(self, "License", "Create/login account first, then activate license.")
            return
        key = self.key_input.text().strip()
        if not key:
            QMessageBox.warning(self, "License", "Access key is required.")
            return
        try:
            state = self._activate_or_validate_key(key)
            self._apply_license_state(state, show_popup=not state.is_valid)
            if state.is_valid:
                self.key_input.clear()
        except Exception as exc:
            self.logger.exception("Activation failed: %s", exc)
            QMessageBox.critical(self, "License", str(exc))

    def on_validate_key(self) -> None:
        if not self.settings.user_token:
            self._set_active_nav(2)
            QMessageBox.warning(self, "License", "Create/login account first, then validate license.")
            return
        try:
            state = self.license_manager.validate_current()
            self._apply_license_state(state, show_popup=not state.is_valid)
        except Exception as exc:
            self.logger.exception("Validation failed: %s", exc)
            QMessageBox.critical(self, "License", str(exc))

    def on_settings_changed(self) -> None:
        self.settings.theme = self.theme_combo.currentText()
        self.config_manager.save()
        self.apply_theme(self.settings.theme)

    def on_reset_settings(self) -> None:
        self.settings = self.config_manager.reset()
        self.config_manager.settings = self.settings
        self._load_settings_into_ui()

    def _schedule_update_check(self) -> None:
        if not self.settings.update_check_on_start:
            return
        QTimer.singleShot(1200, self.check_updates_silent)
        self.update_timer.start(10 * 60 * 1000)

    def check_updates_silent(self) -> None:
        original_timeout = self.updater.timeout
        self.updater.timeout = 5
        try:
            latest = self.updater.check()
        except Exception as exc:
            self.logger.warning("Update check failed: %s", exc)
            return
        finally:
            self.updater.timeout = original_timeout

        notice_id = str(latest.get("notice_id") or "").strip()
        if notice_id and notice_id != self._notified_update_notice_id:
            notice_message = str(latest.get("notice_message") or "").strip()
            version_label = str(latest.get("version") or "unknown")
            body = notice_message or f"Notification admin: mise a jour {version_label}."
            self._notify("Mise a jour", body)
            self._notified_update_notice_id = notice_id

        if not latest.get("is_newer"):
            self._latest_update_payload = None
            self.update_banner.setVisible(False)
            return

        self._latest_update_payload = latest
        version = latest.get("version")
        notes = str(latest.get("notes", "") or "").strip()
        self.update_banner_title.setText(f"Mise a jour {version} disponible")
        if notes:
            self.update_banner_text.setText(f"Une nouvelle version est disponible.\n{notes}")
        else:
            self.update_banner_text.setText("Une nouvelle version est disponible. Clique sur Mettre a jour.")
        self.update_action_btn.setEnabled(True)
        self.update_action_btn.setText("Mettre a jour")
        self.update_progress.setValue(0)
        self.update_progress.setVisible(False)
        self.update_banner.setVisible(True)
        if version and version != self._notified_update_version:
            self._notify("Mise a jour disponible", f"Version {version} detectee. Ouvre le Dashboard pour mettre a jour.")
            self._notified_update_version = str(version)

    def _find_update_executable(self, payload_dir: Path, expected_name: str) -> Path | None:
        matches = list(payload_dir.rglob(expected_name))
        if matches:
            matches.sort(key=lambda item: len(item.parts))
            return matches[0]
        if expected_name.lower().endswith(".exe"):
            fallback = list(payload_dir.rglob("*.exe"))
            if len(fallback) == 1:
                return fallback[0]
        return None

    def _start_windows_self_update(
        self, payload_dir: Path, version: str, preferred_executable_name: str | None = None
    ) -> bool:
        if sys.platform != "win32" or not getattr(sys, "frozen", False):
            return False

        current_exe = Path(sys.executable).resolve()
        expected_name = preferred_executable_name or current_exe.name
        new_exe = self._find_update_executable(payload_dir, expected_name)
        if not new_exe:
            raise FileNotFoundError(
                f"Cannot find updated executable in {payload_dir} (expected {expected_name})."
            )
        source_root = new_exe.parent

        script_path = self.app_dir / "updates" / f"apply_update_{version}.ps1"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(
            (
                "param(\n"
                "  [string]$CurrentExe,\n"
                "  [string]$NewExe,\n"
                "  [string]$SourceRoot,\n"
                "  [string]$InstallRoot,\n"
                "  [int]$OldPid\n"
                ")\n"
                "$ErrorActionPreference = 'Stop'\n"
                "for ($i = 0; $i -lt 240; $i++) {\n"
                "  if (-not (Get-Process -Id $OldPid -ErrorAction SilentlyContinue)) { break }\n"
                "  Start-Sleep -Milliseconds 250\n"
                "}\n"
                "Start-Sleep -Milliseconds 350\n"
                "Get-ChildItem -Path $SourceRoot -Force | ForEach-Object {\n"
                "  $dest = Join-Path $InstallRoot $_.Name\n"
                "  if ($_.PSIsContainer) {\n"
                "    Copy-Item -Path $_.FullName -Destination $dest -Recurse -Force\n"
                "  } else {\n"
                "    Copy-Item -Path $_.FullName -Destination $dest -Force\n"
                "  }\n"
                "}\n"
                "Copy-Item -Path $NewExe -Destination $CurrentExe -Force\n"
                "Start-Process -FilePath $CurrentExe\n"
                "Remove-Item -Path $PSCommandPath -Force -ErrorAction SilentlyContinue\n"
            ),
            encoding="utf-8",
        )

        popen_args = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-CurrentExe",
            str(current_exe),
            "-NewExe",
            str(new_exe),
            "-SourceRoot",
            str(source_root),
            "-InstallRoot",
            str(current_exe.parent),
            "-OldPid",
            str(os.getpid()),
        ]
        creation_flags = 0
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creation_flags |= subprocess.CREATE_NEW_PROCESS_GROUP
        if hasattr(subprocess, "DETACHED_PROCESS"):
            creation_flags |= subprocess.DETACHED_PROCESS
        subprocess.Popen(popen_args, creationflags=creation_flags)
        return True

    def on_update_now(self) -> None:
        latest = self._latest_update_payload or {}
        version = latest.get("version", "latest")
        download_url = latest.get("download_url")

        if not download_url:
            QMessageBox.warning(self, "Update", "No download URL available.")
            return

        self.update_action_btn.setEnabled(False)
        self.update_action_btn.setText("Telechargement...")
        self.update_progress.setValue(0)
        self.update_progress.setVisible(True)

        try:
            update_dir = self.app_dir / "updates" / version
            zip_path = update_dir / f"desktop_client_{version}.zip"
            self.updater.download(download_url, zip_path, progress_cb=self.update_progress.setValue)
            payload_dir = self.updater.extract_package(zip_path, update_dir / "payload")
            self.updater.cleanup_old(self.app_dir / "updates")
            self.logger.info("Update package downloaded in %s", update_dir)
            preferred_executable_name = str(latest.get("entry_exe") or "").strip() or None
            auto_applied = self._start_windows_self_update(
                payload_dir=payload_dir,
                version=str(version),
                preferred_executable_name=preferred_executable_name,
            )
            if auto_applied:
                self.update_banner_title.setText(f"Mise a jour {version} en cours")
                self.update_banner_text.setText("L'application va se fermer puis se relancer automatiquement.")
                self.update_action_btn.setText("Application...")
                self.update_progress.setVisible(False)
                self._notify("Update", f"Version {version} en cours d'installation.")
                QMessageBox.information(
                    self,
                    "Update",
                    f"Update {version} downloaded.\nThe app will restart automatically.",
                )
                QTimer.singleShot(250, self.close)
                return

            self._notify("Update", f"Version {version} downloaded. Restart app to apply.")
            self.update_banner_title.setText(f"Mise a jour {version} telechargee")
            self.update_banner_text.setText("Redemarre l'application pour appliquer la mise a jour.")
            self.update_action_btn.setText("Telechargee")
            self.update_progress.setVisible(False)
            QMessageBox.information(
                self,
                "Update Downloaded",
                f"Update {version} downloaded successfully.\nRestart the app to apply.",
            )
        except Exception as exc:
            self.logger.exception("Update installation failed: %s", exc)
            self.update_action_btn.setEnabled(True)
            self.update_action_btn.setText("Mettre a jour")
            self.update_progress.setVisible(False)
            QMessageBox.critical(self, "Update", f"Update failed: {exc}")

    def on_export_logs(self) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Export logs",
            str(self.app_dir / f"logs_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"),
            "Text files (*.txt)",
        )
        if not target:
            return
        source = self.app_dir / "logs" / "app.log"
        if source.exists():
            Path(target).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            self.logger.info("Logs exported to %s", target)
            QMessageBox.information(self, "Logs", "Logs exported.")

    def validate_license_silent(self) -> None:
        try:
            state = self.license_manager.validate_current()
            self._apply_license_state(state, show_popup=False)
            if not state.is_valid:
                self.logger.warning("Background validation failed: %s", state.message)
        except Exception as exc:
            self.logger.warning("Background validation error: %s", exc)

    def _on_engine_runtime(self, value: str) -> None:
        self.runtime_label.setText(f"Runtime: {value}")
        self.kpi_runtime_value.setText(value)

    def _on_engine_model(self, value: str) -> None:
        self.model_label.setText(f"Active model: {value}")
        self.kpi_model_value.setText(value)

    def _extract_log_level(self, line: str) -> str:
        match = LOG_LEVEL_RE.search(line)
        if match:
            return match.group(1)
        stripped = line.strip()
        if stripped.startswith("{"):
            try:
                payload = json.loads(stripped)
                level = str(payload.get("level", "")).upper()
                if level in {"INFO", "WARNING", "ERROR", "DEBUG"}:
                    return level
            except Exception:
                pass
        return "INFO"

    def _append_log_line(self, line: str) -> None:
        self._all_log_lines.append(line)
        self._render_logs()

    def _render_logs(self) -> None:
        selected = self.log_filter_combo.currentText()
        self.logs_view.clear()
        for line in self._all_log_lines:
            if selected == "ALL" or self._extract_log_level(line) == selected:
                self.logs_view.append(line)

    def on_clear_logs(self) -> None:
        self._all_log_lines.clear()
        self.logs_view.clear()

    def _on_app_log_line(self, line: str) -> None:
        self._append_log_line(line)

    def _on_engine_status(self, status: str) -> None:
        self.status_label.setText(f"Status: {status}")
        if status == "Running":
            self.pause_btn.setText("Pause")
            self.status_label.setStyleSheet("color: #2fc56d; font-weight: 700;")
            self.kpi_engine_value.setText("RUNNING")
        elif status == "Paused":
            self.pause_btn.setText("Resume")
            self.status_label.setStyleSheet("color: #f6b73c; font-weight: 700;")
            self.kpi_engine_value.setText("PAUSED")
        elif status == "Error":
            self.pause_btn.setText("Pause")
            self.status_label.setStyleSheet("color: #ff4f4f; font-weight: 700;")
            self.kpi_engine_value.setText("ERROR")
        else:
            self.pause_btn.setText("Pause")
            self.status_label.setStyleSheet("color: #7f8aa3; font-weight: 700;")
            self.kpi_engine_value.setText("STOPPED")

    def _on_engine_output(self, line: str) -> None:
        if line.startswith("Screen Capture FPS:"):
            value = line.split(":", 1)[1].strip()
            self.kpi_capture_value.setText(value)
        self._append_log_line(line)

    def _notify(self, title: str, body: str) -> None:
        if self.tray.isVisible():
            self.tray.showMessage(title, body, QSystemTrayIcon.Information, 2500)

    def apply_theme(self, theme: str) -> None:
        if theme == "light":
            self.setStyleSheet(
                """
                QWidget { background: #eef3ff; color: #10233f; font-family: 'Rajdhani', 'Segoe UI'; font-size: 13px; }
                QFrame#SideRail { background: #ffffff; border: 1px solid #d2def5; border-radius: 16px; }
                QFrame#TopHeader { background: transparent; border: 1px solid #d2def5; border-radius: 12px; }
                QFrame#HeroPanel { background: transparent; border: 1px solid #c3d6fb; border-radius: 14px; }
                QFrame#UpdateBanner { background: #e3efff; border: 2px solid #2f74ff; border-radius: 14px; }
                QFrame#KpiCard { background: transparent; border: 1px solid #d2def5; border-radius: 12px; }
                QLabel#BrandTitle { color: #15335f; font-size: 20px; font-weight: 800; font-family: 'Orbitron', 'Rajdhani', 'Segoe UI'; }
                QLabel#BrandSubtitle { color: #4a6b99; font-size: 12px; }
                QLabel#PageName { color: #173f7b; font-size: 13px; font-weight: 700; }
                QLabel#HeroTitle { color: #13335d; font-size: 30px; font-weight: 800; font-family: 'Orbitron', 'Rajdhani', 'Segoe UI'; }
                QLabel#HeroSubtitle { color: #30507a; font-size: 14px; }
                QLabel#UpdateBannerTitle { color: #11356b; font-size: 24px; font-weight: 800; font-family: 'Orbitron', 'Rajdhani', 'Segoe UI'; }
                QLabel#UpdateBannerText { color: #244a84; font-size: 14px; }
                QLabel#KpiTitle { color: #4b6691; font-size: 11px; font-weight: 700; }
                QLabel#KpiValue { color: #10233f; font-size: 22px; font-weight: 800; }
                QLabel#KpiHint { color: #607ba8; font-size: 11px; }
                QGroupBox#CardGroup { border: 1px solid #d2def5; border-radius: 12px; margin-top: 12px; padding-top: 12px; background: transparent; }
                QGroupBox#CardGroup::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #244a84; font-weight: 700; }
                QLabel#InlineStatus { color: #244a84; font-weight: 700; }
                QLineEdit, QTextEdit, QComboBox { border: none; border-bottom: 1px solid #9fb8e1; border-radius: 0; padding: 7px 4px; background: transparent; color: #10233f; }
                QPushButton { background: #2f74ff; border: none; border-radius: 9px; color: white; padding: 8px 12px; font-weight: 600; }
                QPushButton#BtnPrimary { background: #ff6d1b; color: #ffffff; }
                QPushButton#BtnGhost { background: #dce8ff; color: #16355f; }
                QPushButton#BtnDiscord { background: #8fd0ff; color: #0f2a4d; border: 1px solid #5cb7ff; font-weight: 700; }
                QPushButton#NavButton, QPushButton#NavButtonActive { background: #ebf2ff; border: 1px solid #c6d6f6; border-radius: 10px; color: #355888; font-size: 16px; }
                QPushButton#NavButtonActive { background: #d8e8ff; border: 1px solid #2f74ff; color: #2f74ff; }
                QPushButton:disabled { background: #c8d8f5; color: #8ea7d2; }
                QTextEdit#LogsView { background: transparent; border: 1px solid #c9d9f5; color: #274776; font-family: 'JetBrains Mono', 'Consolas'; }
                QLabel#VersionLabel { color: #5977a9; }
                QProgressBar { border: 1px solid #c8d7ef; border-radius: 8px; background: transparent; text-align: center; color: #244a84; }
                QProgressBar::chunk { background-color: #2f74ff; border-radius: 8px; }
                """
            )
            return

        self.setStyleSheet(
            """
            QWidget { background: #080d16; color: #e7edf9; font-family: 'Rajdhani', 'Segoe UI'; font-size: 13px; }
            QFrame#SideRail { background: #0d131f; border: 1px solid #202f49; border-radius: 16px; }
            QFrame#TopHeader { background: transparent; border: 1px solid #21314e; border-radius: 12px; }
            QFrame#HeroPanel { background: transparent; border: 1px solid #27416a; border-radius: 14px; }
            QFrame#UpdateBanner { background: #12223a; border: 2px solid #ff6d1b; border-radius: 14px; }
            QFrame#KpiCard { background: transparent; border: 1px solid #253753; border-radius: 12px; }
            QLabel#BrandTitle { color: #f0f5ff; font-size: 20px; font-weight: 800; letter-spacing: 1px; font-family: 'Orbitron', 'Rajdhani', 'Segoe UI'; }
            QLabel#BrandSubtitle { color: #8ea5cd; font-size: 12px; }
            QLabel#PageName { color: #dbe8ff; font-size: 13px; font-weight: 700; }
            QLabel#HeroTitle { color: #f6f9ff; font-size: 30px; font-weight: 800; font-family: 'Orbitron', 'Rajdhani', 'Segoe UI'; }
            QLabel#HeroSubtitle { color: #b3c3df; font-size: 14px; }
            QLabel#UpdateBannerTitle { color: #ffd6b8; font-size: 24px; font-weight: 800; letter-spacing: 1px; font-family: 'Orbitron', 'Rajdhani', 'Segoe UI'; }
            QLabel#UpdateBannerText { color: #d4e3ff; font-size: 14px; }
            QLabel#KpiTitle { color: #8ea5cd; font-size: 11px; font-weight: 700; }
            QLabel#KpiValue { color: #f2f6ff; font-size: 22px; font-weight: 800; }
            QLabel#KpiHint { color: #738bad; font-size: 11px; }
            QGroupBox#CardGroup { border: 1px solid #243550; border-radius: 12px; margin-top: 12px; padding-top: 12px; background: transparent; }
            QGroupBox#CardGroup::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #c8d9f8; font-weight: 700; }
            QLabel#InlineStatus { color: #9ec0ff; font-weight: 700; }
            QLineEdit, QTextEdit, QComboBox { border: none; border-bottom: 1px solid #3f5680; border-radius: 0; padding: 7px 4px; background: transparent; color: #e8edfa; selection-background-color: #2f74ff; }
            QPushButton { background: #2f74ff; border: none; border-radius: 9px; color: white; padding: 8px 12px; font-weight: 600; }
            QPushButton#BtnPrimary { background: #ff6d1b; color: #ffffff; }
            QPushButton#BtnGhost { background: #1a2740; color: #d2def5; border: 1px solid #2f4469; }
            QPushButton#BtnDiscord { background: #5bb9ff; color: #081a33; border: 1px solid #8fd0ff; font-weight: 700; }
            QPushButton#NavButton, QPushButton#NavButtonActive { background: #131d30; border: 1px solid #243550; border-radius: 10px; color: #8ea5cd; font-size: 16px; }
            QPushButton#NavButtonActive { background: #1a2b4a; border: 1px solid #2f74ff; color: #dbe8ff; }
            QPushButton:hover { background: #3f83ff; }
            QPushButton#BtnGhost:hover { background: #243550; }
            QPushButton:disabled { background: #1b2640; color: #5e7398; }
            QTextEdit#LogsView { background: transparent; border: 1px solid #20314d; color: #9db3d8; font-family: 'JetBrains Mono', 'Consolas'; }
            QLabel#VersionLabel { color: #728bab; }
            QProgressBar { border: 1px solid #2a3d5f; border-radius: 8px; background: transparent; text-align: center; color: #cad8f6; }
            QProgressBar::chunk { background-color: #26c2a4; border-radius: 8px; }
            """
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        self.engine.stop()
        super().closeEvent(event)
