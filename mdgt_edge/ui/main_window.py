"""MDGT Edge - Main Application Window (PyQt6).

Complete rewrite from PyQt5 to PyQt6 with tabbed interface,
dock panels, toolbar, and device monitoring.
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QMenuBar, QToolBar,
    QStatusBar, QDockWidget, QMessageBox, QApplication,
    QLabel, QWidget,
)
from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtGui import QAction, QIcon, QKeySequence

from mdgt_edge.ui.widgets.live_view import LiveViewTab
from mdgt_edge.ui.widgets.capture_tab import CaptureTab
from mdgt_edge.ui.widgets.enroll_tab import EnrollTab
from mdgt_edge.ui.widgets.identify_tab import IdentifyTab
from mdgt_edge.ui.widgets.database_tab import DatabaseTab
from mdgt_edge.ui.widgets.settings_tab import SettingsTab

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
APP_TITLE = "MDGT Edge - Fingerprint Verification System"
APP_ORG = "MDGT"
APP_NAME = "MDGTEdge"
MIN_WIDTH = 1280
MIN_HEIGHT = 800
DEVICE_POLL_INTERVAL_MS = 2000

TAB_LIVE_VIEW = 0
TAB_CAPTURE = 1
TAB_ENROLL = 2
TAB_IDENTIFY = 3
TAB_DATABASE = 4
TAB_SETTINGS = 5


class MDGTEdgeMainWindow(QMainWindow):
    """Main application window for MDGT Edge fingerprint verification system."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)

        self._settings = QSettings(APP_ORG, APP_NAME)

        # Track device connection state
        self._device_connected = False

        # Central widget -- tabbed interface
        self._tab_widget = QTabWidget()
        self._tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        self._tab_widget.setDocumentMode(True)
        self.setCentralWidget(self._tab_widget)

        # Build UI layers
        self._setup_tabs()
        self._setup_menu_bar()
        self._setup_toolbar()
        self._setup_dock_widgets()
        self._setup_status_bar()

        # Restore previous window geometry / state
        self._restore_state()

        # Periodic device health check
        self._device_timer = QTimer(self)
        self._device_timer.timeout.connect(self._check_device_status)
        self._device_timer.start(DEVICE_POLL_INTERVAL_MS)

        logger.info("Main window initialized")

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------

    def _setup_tabs(self) -> None:
        """Create and add all application tabs."""
        self._live_view_tab = LiveViewTab()
        self._capture_tab = CaptureTab()
        self._enroll_tab = EnrollTab()
        self._identify_tab = IdentifyTab()
        self._database_tab = DatabaseTab()
        self._settings_tab = SettingsTab()

        self._tab_widget.addTab(self._live_view_tab, "Live View")
        self._tab_widget.addTab(self._capture_tab, "Capture")
        self._tab_widget.addTab(self._enroll_tab, "Enroll")
        self._tab_widget.addTab(self._identify_tab, "Identify")
        self._tab_widget.addTab(self._database_tab, "Database")
        self._tab_widget.addTab(self._settings_tab, "Settings")

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _setup_menu_bar(self) -> None:
        """Build the application menu bar."""
        menu_bar = self.menuBar()

        # -- File menu --
        file_menu = menu_bar.addMenu("&File")

        self._act_export = QAction("&Export Data...", self)
        self._act_export.setShortcut(QKeySequence("Ctrl+E"))
        self._act_export.triggered.connect(self._on_export_data)
        file_menu.addAction(self._act_export)

        self._act_backup = QAction("&Backup Database...", self)
        self._act_backup.setShortcut(QKeySequence("Ctrl+B"))
        self._act_backup.triggered.connect(self._on_backup_database)
        file_menu.addAction(self._act_backup)

        file_menu.addSeparator()

        self._act_exit = QAction("E&xit", self)
        self._act_exit.setShortcut(QKeySequence("Ctrl+Q"))
        self._act_exit.triggered.connect(self.close)
        file_menu.addAction(self._act_exit)

        # -- Device menu --
        device_menu = menu_bar.addMenu("&Device")

        self._act_connect = QAction("&Connect", self)
        self._act_connect.setShortcut(QKeySequence("Ctrl+D"))
        self._act_connect.triggered.connect(self._on_device_connect)
        device_menu.addAction(self._act_connect)

        self._act_disconnect = QAction("D&isconnect", self)
        self._act_disconnect.triggered.connect(self._on_device_disconnect)
        self._act_disconnect.setEnabled(False)
        device_menu.addAction(self._act_disconnect)

        device_menu.addSeparator()

        self._act_device_props = QAction("&Properties...", self)
        self._act_device_props.triggered.connect(self._on_device_properties)
        device_menu.addAction(self._act_device_props)

        # -- View menu --
        self._view_menu = menu_bar.addMenu("&View")
        # Dock toggle actions added after dock widgets are created

        # -- Help menu --
        help_menu = menu_bar.addMenu("&Help")

        self._act_about = QAction("&About MDGT Edge", self)
        self._act_about.triggered.connect(self._on_about)
        help_menu.addAction(self._act_about)

        self._act_about_qt = QAction("About &Qt", self)
        self._act_about_qt.triggered.connect(
            lambda: QMessageBox.aboutQt(self, "About Qt")
        )
        help_menu.addAction(self._act_about_qt)

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------

    def _setup_toolbar(self) -> None:
        """Create the quick-action toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        self._tb_capture = QAction("Capture", self)
        self._tb_capture.setShortcut(QKeySequence("F5"))
        self._tb_capture.setToolTip("Single capture (F5)")
        self._tb_capture.triggered.connect(self._on_toolbar_capture)
        toolbar.addAction(self._tb_capture)

        self._tb_verify = QAction("Verify", self)
        self._tb_verify.setShortcut(QKeySequence("F6"))
        self._tb_verify.setToolTip("1:1 verification (F6)")
        self._tb_verify.triggered.connect(self._on_toolbar_verify)
        toolbar.addAction(self._tb_verify)

        self._tb_identify = QAction("Identify", self)
        self._tb_identify.setShortcut(QKeySequence("F7"))
        self._tb_identify.setToolTip("1:N identification (F7)")
        self._tb_identify.triggered.connect(self._on_toolbar_identify)
        toolbar.addAction(self._tb_identify)

        toolbar.addSeparator()

        self._tb_led_toggle = QAction("LED On/Off", self)
        self._tb_led_toggle.setShortcut(QKeySequence("F8"))
        self._tb_led_toggle.setToolTip("Toggle sensor LED (F8)")
        self._tb_led_toggle.setCheckable(True)
        self._tb_led_toggle.triggered.connect(self._on_toolbar_led_toggle)
        toolbar.addAction(self._tb_led_toggle)

    # ------------------------------------------------------------------
    # Dock widgets
    # ------------------------------------------------------------------

    def _setup_dock_widgets(self) -> None:
        """Create dockable panels on left / right / bottom."""
        # -- Device info dock (left) --
        self._device_dock = QDockWidget("Device Info", self)
        self._device_dock.setObjectName("device_info_dock")
        self._device_info_label = QLabel("No device connected")
        self._device_info_label.setWordWrap(True)
        self._device_info_label.setMargin(8)
        self._device_dock.setWidget(self._device_info_label)
        self.addDockWidget(
            Qt.DockWidgetArea.LeftDockWidgetArea, self._device_dock
        )

        # -- Log dock (bottom) --
        self._log_dock = QDockWidget("Log", self)
        self._log_dock.setObjectName("log_dock")
        self._log_label = QLabel("Ready.")
        self._log_label.setWordWrap(True)
        self._log_label.setMargin(8)
        self._log_dock.setWidget(self._log_label)
        self.addDockWidget(
            Qt.DockWidgetArea.BottomDockWidgetArea, self._log_dock
        )

        # -- Statistics dock (right) --
        self._stats_dock = QDockWidget("Statistics", self)
        self._stats_dock.setObjectName("stats_dock")
        self._stats_label = QLabel("Users: --\nTemplates: --")
        self._stats_label.setWordWrap(True)
        self._stats_label.setMargin(8)
        self._stats_dock.setWidget(self._stats_label)
        self.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea, self._stats_dock
        )

        # Add toggle actions to View menu
        self._view_menu.addAction(self._device_dock.toggleViewAction())
        self._view_menu.addAction(self._log_dock.toggleViewAction())
        self._view_menu.addAction(self._stats_dock.toggleViewAction())

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _setup_status_bar(self) -> None:
        """Create the status bar with device and model indicators."""
        status_bar = self.statusBar()

        self._status_device = QLabel("Device: Disconnected")
        self._status_device.setStyleSheet("color: #E74C3C; padding: 0 8px;")
        status_bar.addPermanentWidget(self._status_device)

        self._status_model = QLabel("Model: Not loaded")
        self._status_model.setStyleSheet("color: #7F8C8D; padding: 0 8px;")
        status_bar.addPermanentWidget(self._status_model)

        self._status_users = QLabel("Users: --")
        self._status_users.setStyleSheet("color: #7F8C8D; padding: 0 8px;")
        status_bar.addPermanentWidget(self._status_users)

        status_bar.showMessage("MDGT Edge ready", 3000)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _restore_state(self) -> None:
        """Restore window geometry and state from QSettings."""
        geometry = self._settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

        state = self._settings.value("window/state")
        if state is not None:
            self.restoreState(state)

        last_tab = self._settings.value("window/last_tab", 0, type=int)
        if 0 <= last_tab < self._tab_widget.count():
            self._tab_widget.setCurrentIndex(last_tab)

    def _save_state(self) -> None:
        """Persist window geometry and state to QSettings."""
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("window/state", self.saveState())
        self._settings.setValue(
            "window/last_tab", self._tab_widget.currentIndex()
        )

    # ------------------------------------------------------------------
    # Device monitoring
    # ------------------------------------------------------------------

    def _check_device_status(self) -> None:
        """Periodic health check for connected sensor device."""
        # Placeholder -- will be wired to IBScanService
        pass

    def _update_device_status(self, connected: bool, info: str = "") -> None:
        """Update all device-related UI elements."""
        self._device_connected = connected
        if connected:
            self._status_device.setText("Device: Connected")
            self._status_device.setStyleSheet(
                "color: #27AE60; padding: 0 8px;"
            )
            self._device_info_label.setText(info or "Connected")
            self._act_connect.setEnabled(False)
            self._act_disconnect.setEnabled(True)
        else:
            self._status_device.setText("Device: Disconnected")
            self._status_device.setStyleSheet(
                "color: #E74C3C; padding: 0 8px;"
            )
            self._device_info_label.setText("No device connected")
            self._act_connect.setEnabled(True)
            self._act_disconnect.setEnabled(False)

    # ------------------------------------------------------------------
    # Menu action handlers
    # ------------------------------------------------------------------

    def _on_export_data(self) -> None:
        """Export captured data to file."""
        self.statusBar().showMessage("Export not yet implemented", 3000)

    def _on_backup_database(self) -> None:
        """Create database backup."""
        self.statusBar().showMessage("Backup not yet implemented", 3000)

    def _on_device_connect(self) -> None:
        """Connect to fingerprint sensor."""
        self._update_device_status(True, "IBScanUltimate device")
        self.statusBar().showMessage("Connecting to device...", 2000)

    def _on_device_disconnect(self) -> None:
        """Disconnect from fingerprint sensor."""
        self._update_device_status(False)
        self.statusBar().showMessage("Device disconnected", 2000)

    def _on_device_properties(self) -> None:
        """Show device properties dialog."""
        if not self._device_connected:
            QMessageBox.information(
                self, "Device Properties", "No device connected."
            )
            return
        QMessageBox.information(
            self,
            "Device Properties",
            "Device: IBScanUltimate\nStatus: Connected",
        )

    def _on_about(self) -> None:
        """Show About dialog."""
        QMessageBox.about(
            self,
            "About MDGT Edge",
            "<h3>MDGT Edge</h3>"
            "<p>Fingerprint Verification System v1.0</p>"
            "<p>MDGTv2 deep learning model for 1:N identification "
            "on Jetson Nano.</p>"
            "<p>256-dim L2-normalized embeddings with FAISS cosine "
            "similarity matching.</p>",
        )

    # ------------------------------------------------------------------
    # Toolbar action handlers
    # ------------------------------------------------------------------

    def _on_toolbar_capture(self) -> None:
        """Switch to capture tab and trigger capture."""
        self._tab_widget.setCurrentIndex(TAB_CAPTURE)
        self._capture_tab.start_capture()

    def _on_toolbar_verify(self) -> None:
        """Switch to identify tab for 1:1 verification."""
        self._tab_widget.setCurrentIndex(TAB_IDENTIFY)

    def _on_toolbar_identify(self) -> None:
        """Switch to identify tab and start identification."""
        self._tab_widget.setCurrentIndex(TAB_IDENTIFY)
        self._identify_tab.start_identification()

    def _on_toolbar_led_toggle(self, checked: bool) -> None:
        """Toggle the sensor LED on or off."""
        self.statusBar().showMessage(
            f"LED {'enabled' if checked else 'disabled'}", 2000
        )

    # ------------------------------------------------------------------
    # Public API for external services
    # ------------------------------------------------------------------

    def update_model_status(self, model_name: str, backend: str) -> None:
        """Update model display in status bar."""
        self._status_model.setText(f"Model: {model_name} ({backend})")
        self._status_model.setStyleSheet("color: #27AE60; padding: 0 8px;")

    def update_user_count(self, count: int) -> None:
        """Update user count in status bar and stats dock."""
        self._status_users.setText(f"Users: {count}")
        self._stats_label.setText(f"Users: {count}\nTemplates: --")

    def append_log(self, message: str) -> None:
        """Append a message to the log dock."""
        current = self._log_label.text()
        lines = current.split("\n")
        lines.append(message)
        # Keep last 50 lines
        if len(lines) > 50:
            lines = lines[-50:]
        self._log_label.setText("\n".join(lines))

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802
        """Save state and confirm exit."""
        self._device_timer.stop()
        self._save_state()
        event.accept()
