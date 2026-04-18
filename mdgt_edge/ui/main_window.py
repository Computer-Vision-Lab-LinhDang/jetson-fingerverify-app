"""MDGT Edge - Main Application Window (PyQt6).

Complete rewrite from PyQt5 to PyQt6 with tabbed interface,
dock panels, toolbar, and device monitoring.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np

from mdgt_edge.ui.qt_compat import (
    QAction,
    QApplication,
    QDockWidget,
    QIcon,
    QKeySequence,
    QLabel,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QSettings,
    QStatusBar,
    QTabWidget,
    QTimer,
    QToolBar,
    QWidget,
    Qt,
)

from mdgt_edge.ui.widgets.live_view import LiveViewTab
from mdgt_edge.ui.widgets.capture_tab import CaptureTab
from mdgt_edge.ui.widgets.enroll_tab import EnrollTab
from mdgt_edge.ui.widgets.identify_tab import IdentifyTab
from mdgt_edge.ui.widgets.database_tab import DatabaseTab
from mdgt_edge.ui.widgets.settings_tab import SettingsTab
from mdgt_edge.ui.services.ibscan_service import IBScanService
from mdgt_edge.ui.panels.device_control import DeviceControlPanel
from mdgt_edge.ui.panels.quality_panel import QualityPanel
from mdgt_edge.ui.panels.spoof_panel import SpoofPanel

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

GALLERY_DIR = os.path.expanduser("~/.mdgt_edge")
IMAGES_DIR = os.path.join(GALLERY_DIR, "images")
INDEX_PATH = os.path.join(GALLERY_DIR, "gallery.faiss")
USERS_PATH = os.path.join(GALLERY_DIR, "enrolled_users.json")
MATCH_THRESHOLD = 0.5

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

        # IBScan sensor service (background thread)
        self._sensor_service = IBScanService(parent=self)
        self._connect_sensor_signals()
        self._sensor_service.start()

        # Periodic device health check
        self._device_timer = QTimer(self)
        self._device_timer.timeout.connect(self._check_device_status)
        self._device_timer.start(DEVICE_POLL_INTERVAL_MS)

        # Inference engine placeholder
        self._inference = None
        self._auto_led = True
        self._auto_beep = True

        # FAISS gallery for identification
        # Database + FAISS gallery
        from mdgt_edge.pipeline.faiss_index import FAISSIndexManager
        from mdgt_edge.database.database import DatabaseManager
        from mdgt_edge.database.repository import UserRepository, FingerprintRepository
        self._db = DatabaseManager("data/mdgt_edge.db")
        self._user_repo = UserRepository(self._db)
        self._fp_repo = FingerprintRepository(self._db)
        self._faiss_index = FAISSIndexManager(dim=256)
        self._enrolled_users: dict[int, dict] = {}
        self._next_fp_id = 1
        self._load_gallery()

        # Background embedding worker (async enrollment)
        from mdgt_edge.pipeline.embedding_worker import EmbeddingWorker
        self._embed_worker = EmbeddingWorker(
            inference_provider=lambda: self._inference,
            fp_repo=self._fp_repo,
            faiss_index=self._faiss_index,
            preprocess_fn=self._preprocess_for_model,
            on_done=self._on_embedding_done,
            on_error=self._on_embedding_error,
        )
        self._embed_worker.start()
        self._last_pending: int = 0
        self._embed_poll_timer = QTimer(self)
        self._embed_poll_timer.timeout.connect(self._poll_embed_queue)
        self._embed_poll_timer.start(1000)

        # Ordered startup sequence
        QTimer.singleShot(500, self._run_startup_sequence)

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
        # -- Device control dock (left) --
        self._device_control = DeviceControlPanel(self)
        self.addDockWidget(
            Qt.DockWidgetArea.LeftDockWidgetArea, self._device_control
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

        # -- Quality dock (right, tabbed with stats) --
        self._quality_panel = QualityPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._quality_panel)
        self.tabifyDockWidget(self._stats_dock, self._quality_panel)

        # -- Spoof/PAD dock (right) --
        self._spoof_panel = SpoofPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._spoof_panel)
        self.tabifyDockWidget(self._quality_panel, self._spoof_panel)

        # Add toggle actions to View menu
        self._view_menu.addAction(self._device_control.toggleViewAction())
        self._view_menu.addAction(self._log_dock.toggleViewAction())
        self._view_menu.addAction(self._stats_dock.toggleViewAction())
        self._view_menu.addAction(self._quality_panel.toggleViewAction())
        self._view_menu.addAction(self._spoof_panel.toggleViewAction())

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

    def _connect_sensor_signals(self) -> None:
        """Wire IBScanService signals to UI update slots."""
        svc = self._sensor_service

        # Service -> UI status
        svc.device_connected.connect(self._on_sensor_connected)
        svc.device_disconnected.connect(self._on_sensor_disconnected)
        svc.device_count_changed.connect(self._on_device_count_changed)
        svc.error_occurred.connect(self._on_sensor_error)
        svc.status_message.connect(
            lambda msg: self.statusBar().showMessage(msg, 3000)
        )

        # Service -> LiveView preview + Enroll + Identify live preview
        svc.preview_frame.connect(self._live_view_tab.on_preview_frame)
        svc.preview_frame.connect(self._enroll_tab.on_preview_frame)
        svc.preview_frame.connect(self._identify_tab.on_preview_frame)
        svc.finger_count_changed.connect(self._live_view_tab.on_finger_count_changed)
        svc.finger_count_changed.connect(self._enroll_tab.on_finger_status)
        svc.finger_count_changed.connect(self._on_finger_count_for_enroll)
        svc.finger_quality_changed.connect(self._live_view_tab.on_finger_quality_changed)

        # DeviceControlPanel -> Service
        ctrl = self._device_control
        ctrl.connect_requested.connect(lambda: svc.open_device(0))
        ctrl.disconnect_requested.connect(svc.close_device)
        ctrl.led_changed.connect(svc.set_leds)
        ctrl.beep_requested.connect(svc.beep)
        ctrl.capture_mode_changed.connect(self._on_capture_mode_changed)

        # LiveView toggle -> begin/cancel capture on service
        # Disconnect the original internal handler and replace with ours
        self._live_view_tab._toggle_btn.clicked.disconnect(
            self._live_view_tab._on_toggle_preview
        )
        self._live_view_tab._toggle_btn.clicked.connect(self._on_preview_toggle)

        # Enroll tab -> capture from sensor
        self._enroll_tab.enroll_capture_requested.connect(self._on_enroll_capture)

        # Enroll tab -> save to database when done
        self._enroll_tab.enrollment_complete.connect(self._on_enrollment_complete)

        # Capture complete -> dispatch to enroll or identify
        svc.capture_complete.connect(self._on_capture_complete_dispatch)

        # Identify tab -> capture + match
        self._identify_tab.identify_requested.connect(self._on_identify_requested)

        # Quality signals
        svc.nfiq2_score_ready.connect(self._on_nfiq2_score)
        svc.finger_quality_changed.connect(self._quality_panel.update_finger_qualities)

        # Spoof signals
        svc.spoof_result.connect(self._on_spoof_result)

        # Duplicate + geometry
        svc.duplicate_result.connect(self._on_duplicate_result)
        svc.geometry_result.connect(self._on_geometry_result)

        # Settings
        self._settings_tab.settings_applied.connect(self._on_settings_applied)

        # Database tab CRUD
        db = self._database_tab
        db.add_user_requested.connect(self._on_db_add_user)
        db.delete_user_requested.connect(self._on_db_delete_user)
        db.deactivate_user_requested.connect(self._on_db_deactivate_user)
        db.user_selected.connect(self._on_db_user_selected)

    def _auto_detect_sensor(self) -> None:
        """Try to open the first available sensor on startup."""
        if self._sensor_service.is_device_open:
            return
        self._sensor_service.open_device(0)
        logger.info("Auto-detect: requesting sensor open")

    def _run_startup_sequence(self) -> None:
        """Ordered startup: sensor -> NFIQ2 -> model -> gallery -> DB -> settings."""
        from mdgt_edge.ui.widgets.splash_screen import SplashScreen
        self._splash = SplashScreen()
        self._splash.show()

        steps = [
            (10, "Detecting sensor...", self._auto_detect_sensor),
            (30, "Initializing NFIQ2...", lambda: self._sensor_service.request_nfiq2_init()),
            (50, "Loading AI model...", self._load_model),
            (70, "Loading gallery...", self._load_gallery),
            (85, "Loading database...", self._refresh_database_tab),
            (100, "Ready!", lambda: None),
        ]

        delay = 0
        for pct, msg, func in steps:
            delay += 500
            QTimer.singleShot(delay, lambda p=pct, m=msg, f=func: self._startup_step(p, m, f))

        # Close splash after all steps
        QTimer.singleShot(delay + 500, self._finish_startup)

    def _startup_step(self, percent: int, message: str, func) -> None:
        """Execute one startup step and update splash."""
        if hasattr(self, "_splash") and self._splash is not None:
            self._splash.update_progress(percent, message)
        try:
            func()
        except Exception as exc:
            print(f"[STARTUP] {message} failed: {exc}", flush=True)

    def _finish_startup(self) -> None:
        """Close splash and show main window."""
        if hasattr(self, "_splash") and self._splash is not None:
            self._splash.finish()
            self._splash = None
        self.statusBar().showMessage("MDGT Edge ready", 3000)
        print("[STARTUP] complete", flush=True)

    def _load_model(self) -> None:
        """Auto-load ONNX model on startup (ONNX first, then TRT)."""
        model_search_paths = [
            "/home/binhan2/jetson-fingerverify-app/models/model.onnx",
            os.path.expanduser("~/models/model.onnx"),
            "/home/binhan2/jetson-fingerverify-app/models/model_fp16.engine",
        ]
        for path in model_search_paths:
            if os.path.isfile(path):
                try:
                    if path.endswith(".engine"):
                        self._status_model.setText(
                            f"Model: {os.path.basename(path)} (TRT)"
                        )
                        self._status_model.setStyleSheet(
                            "color: #27AE60; padding: 0 8px;"
                        )
                    else:
                        from mdgt_edge.pipeline.inference_engine import ONNXBackend
                        self._inference = ONNXBackend()
                        if self._inference.load(path):
                            print(f"[MODEL] loaded {path}", flush=True)
                            self._status_model.setText(
                                f"Model: {os.path.basename(path)} (ONNX)"
                            )
                            self._status_model.setStyleSheet(
                                "color: #27AE60; padding: 0 8px;"
                            )
                        else:
                            print(f"[MODEL] failed to load {path}", flush=True)
                            self._inference = None
                            continue
                    logger.info("Model loaded: %s", path)
                    return
                except Exception as exc:
                    logger.warning("Failed to load model %s: %s", path, exc)
                    continue
        logger.info("No model found in search paths")

    def _check_device_status(self) -> None:
        """Periodic health check for connected sensor device."""
        if self._device_connected and not self._sensor_service.is_device_open:
            self._update_device_status(False)

    def _on_preview_toggle(self) -> None:
        """Start or stop preview capture on sensor."""
        if self._live_view_tab.is_streaming:
            # Stopping
            self._sensor_service.cancel_capture()
            self._live_view_tab.stop_preview()
        else:
            # Starting — FLAT_TWO=1, 500dpi, AUTO_CONTRAST only (no AUTO_CAPTURE)
            if not self._sensor_service.is_device_open:
                self._sensor_service.open_device(0)
            self._sensor_service.begin_capture(1, 500, 1)
            self._live_view_tab.start_preview()

    def _on_capture_mode_changed(self, image_type: int, resolution: int) -> None:
        """Restart capture with new mode/resolution if streaming."""
        if not self._live_view_tab.is_streaming:
            return
        print(f"[MODE] changing to type={image_type} res={resolution}", flush=True)
        self._sensor_service.cancel_capture()
        self._sensor_service.begin_capture(image_type, resolution, 1)

    def _on_enroll_capture(self, finger_index: int) -> None:
        """Capture current preview frame immediately for enrollment."""
        from dataclasses import dataclass
        print(f"[ENROLL] capture finger={finger_index}", flush=True)
        self._pending_enroll_finger = finger_index

        # Ensure device open + streaming
        if not self._sensor_service.is_device_open:
            self._sensor_service.open_device(0)
            self.statusBar().showMessage("Opening sensor...", 3000)
            QTimer.singleShot(2000, lambda: self._do_enroll_grab(finger_index))
            return
        if not self._live_view_tab.is_streaming:
            self._sensor_service.begin_capture(1, 500, 1)
            self._live_view_tab.start_preview()
            self.statusBar().showMessage("Starting preview... try again in 2s", 3000)
            self._enroll_tab._capture_btn.setEnabled(True)
            self._enroll_tab._capture_btn.setText("Capture Sample")
            return

        self._do_enroll_grab(finger_index)

    def _do_enroll_grab(self, finger_index: int) -> None:
        """Grab the current live preview frame for enrollment."""
        from dataclasses import dataclass

        last_data = getattr(self._live_view_tab, "_last_frame_data", None)
        last_w = getattr(self._live_view_tab, "_last_frame_width", 0)
        last_h = getattr(self._live_view_tab, "_last_frame_height", 0)

        if not last_data or last_w <= 0 or last_h <= 0:
            print(f"[ENROLL] no frame (data={bool(last_data)} w={last_w} h={last_h})", flush=True)
            self.statusBar().showMessage("No image available. Start preview first.", 3000)
            self._enroll_tab._capture_btn.setEnabled(True)
            self._enroll_tab._capture_btn.setText("Capture Sample")
            return

        @dataclass
        class _SnapResult:
            success: bool = True
            image_data: bytes = b""
            width: int = 0
            height: int = 0
            quality_score: int = 50
            nfiq2_score: int = 50
            spoof_detected: bool = False

        raw = bytes(last_data)
        # Reject blank/white frames (mean > 240 = mostly white)
        arr = np.frombuffer(raw, dtype=np.uint8)
        mean_val = float(arr.mean())
        std_val = float(arr.std())
        print(f"[ENROLL] grabbed {len(raw)} bytes {last_w}x{last_h} mean={mean_val:.0f} std={std_val:.0f}", flush=True)
        if mean_val > 252 and std_val < 8:
            self.statusBar().showMessage(
                "Image too bright/blank. Place finger properly and try again.", 5000
            )
            self._enroll_tab._capture_btn.setEnabled(True)
            self._enroll_tab._capture_btn.setText("Capture Sample")
            self._auto_led_feedback("capture_fail")
            return

        result = _SnapResult(image_data=raw, width=last_w, height=last_h)
        self._enroll_tab.on_enroll_capture_result(result)

    def _on_finger_count_for_enroll(self, count: int) -> None:
        """Update enroll tab finger status (display only)."""
        pass

    def _on_capture_complete_dispatch(self, result: object) -> None:
        """Route capture_complete to the correct tab based on pending mode."""
        mode = getattr(self, "_pending_capture_mode", None)
        img_data = getattr(result, "image_data", b"")
        w = getattr(result, "width", 0)
        h = getattr(result, "height", 0)
        print(f"[DISPATCH] capture_complete mode={mode} {len(img_data)}bytes {w}x{h}", flush=True)
        if mode == "enroll":
            self._pending_capture_mode = None
            self._enroll_tab.on_enroll_capture_result(result)
            # Restart capture for next sample (SDK ends capture after result)
            print("[DISPATCH] restarting capture for next enroll sample", flush=True)
            self._sensor_service.begin_capture(1, 500, 1)
            self._auto_led_feedback("capture_success")
        elif mode == "identify":
            self._pending_capture_mode = None
            self._on_identify_capture_result(result)
            self._auto_led_feedback("capture_success")

    def _on_identify_requested(self) -> None:
        """Handle identify tab requesting 1:N identification."""
        if not self._sensor_service.is_device_open:
            self._identify_tab.on_identify_results([])
            self.statusBar().showMessage("No sensor connected", 3000)
            return
        # Auto-start preview if not streaming
        if not self._live_view_tab.is_streaming:
            self._sensor_service.begin_capture(1, 500, 3)
            self._live_view_tab.start_preview()
        self.statusBar().showMessage(
            "Place finger on sensor... identifying in 2s", 5000
        )
        QTimer.singleShot(2000, self._do_identify_snapshot)

    def _do_identify_snapshot(self) -> None:
        """Take a snapshot, extract embedding, and run FAISS search."""
        last_data = getattr(self._live_view_tab, "_last_frame_data", None)
        last_w = getattr(self._live_view_tab, "_last_frame_width", 0)
        last_h = getattr(self._live_view_tab, "_last_frame_height", 0)
        if not last_data or last_w <= 0 or last_h <= 0:
            self.statusBar().showMessage("No finger on sensor. Try again.", 3000)
            self._identify_tab.on_identify_results([])
            return

        raw = bytes(last_data)
        print(f"[IDENTIFY] snapshot {len(raw)} bytes {last_w}x{last_h}", flush=True)
        self._identify_tab.on_probe_image(raw, last_w, last_h)

        if self._inference is None:
            print("[IDENTIFY] no model loaded", flush=True)
            self.statusBar().showMessage("No model loaded for identification", 3000)
            self._identify_tab.on_identify_results([])
            return

        if self._faiss_index.count == 0:
            print("[IDENTIFY] gallery empty", flush=True)
            self.statusBar().showMessage("Gallery empty — enroll fingerprints first", 3000)
            self._identify_tab.on_identify_results([])
            return

        try:
            tensor = self._preprocess_for_model(raw, last_w, last_h)
            embedding = self._inference.infer_image(tensor)
            hits = self._faiss_index.search(embedding, top_k=5)
            print(f"[IDENTIFY] {len(hits)} hits: {hits}", flush=True)

            results = []
            for rank, (fp_id, score) in enumerate(hits, 1):
                info = self._enrolled_users.get(fp_id, {})
                emp_id = info.get("employee_id", "")
                # FVC benchmark data = auto unmatch
                is_fvc = emp_id.startswith("FVC-")
                results.append({
                    "rank": rank,
                    "user_name": info.get("name", "Unknown"),
                    "employee_id": emp_id,
                    "department": info.get("department", ""),
                    "score": float(score),
                    "is_match": False if is_fvc else float(score) >= MATCH_THRESHOLD,
                })
            self._identify_tab.on_identify_results(results)

            # Show best match image
            if hits:
                best_fp_id = hits[0][0]
                img_data, img_w, img_h = self._load_fp_image(best_fp_id)
                if img_data:
                    self._identify_tab.on_match_image(img_data, img_w, img_h)
                else:
                    self._identify_tab.on_match_image(b"", 0, 0)
        except Exception as exc:
            print(f"[IDENTIFY] error: {exc}", flush=True)
            self.statusBar().showMessage(f"Identification error: {exc}", 5000)
            self._identify_tab.on_identify_results([])

    def _on_enrollment_complete(self, employee_id: str, samples: list) -> None:
        """Save image + DB row synchronously, queue embedding extraction in background."""
        import hashlib
        from mdgt_edge.database.models import User, Fingerprint, UserRole
        print(f"[ENROLL] complete emp={employee_id} samples={len(samples)}", flush=True)

        name = self._enroll_tab._edit_full_name.text().strip()
        dept = self._enroll_tab._combo_department.currentText()

        # Find or create user in SQLite
        db_user = self._user_repo.get_by_employee_id(employee_id)
        if db_user is None:
            db_user = self._user_repo.create(User(
                employee_id=employee_id,
                full_name=name,
                department=dept,
                role=UserRole.USER,
            ))
            print(f"[ENROLL] created user id={db_user.id}", flush=True)
        else:
            print(f"[ENROLL] found existing user id={db_user.id}", flush=True)

        added = 0
        queued = 0
        for sample in samples:
            raw = getattr(sample, "image_data", b"")
            w = getattr(sample, "width", 0)
            h = getattr(sample, "height", 0)
            finger_idx = getattr(sample, "finger_index", 0)
            quality = getattr(sample, "quality_score", 50.0)
            if not raw or w <= 0 or h <= 0:
                continue

            img_hash = hashlib.sha256(raw).hexdigest()[:16]

            # Fast path: save image + pending DB row, no inference here.
            try:
                db_fp = self._fp_repo.create(Fingerprint(
                    user_id=db_user.id,
                    finger_index=finger_idx,
                    embedding_enc=None,
                    quality_score=float(quality),
                    image_hash=img_hash,
                ))
                fp_id = db_fp.id
                print(f"[ENROLL] pending row fp_id={fp_id}", flush=True)
                self._save_fp_image(fp_id, raw, w, h)
            except Exception as exc:
                print(f"[ENROLL] DB save error: {exc}", flush=True)
                continue

            self._enrolled_users[fp_id] = {
                "employee_id": employee_id,
                "name": name,
                "department": dept,
                "finger": finger_idx,
            }

            # Queue async embedding extraction (non-blocking)
            if self._inference is not None:
                self._embed_worker.enqueue(fp_id, raw, w, h)
                queued += 1
            added += 1

        user_count = self._user_repo.count(active_only=True)
        fp_count = self._fp_repo.count(active_only=True)
        self.update_user_count(user_count)
        self.statusBar().showMessage(
            f"Enrolled {employee_id}: {added} sample(s) saved, "
            f"{queued} queued for embedding",
            5000,
        )
        self.append_log(
            f"Enrolled: {employee_id} ({added} samples, {queued} queued)"
        )

        self._auto_led_feedback("enrollment_complete")

        # Auto-refresh database tab (gallery size will grow as worker finishes)
        self._refresh_database_tab()

    def _refresh_database_tab(self) -> None:
        """Reload database tab with current data from SQLite."""
        try:
            users = self._user_repo.get_all()
            records = []
            for u in users:
                fp_count = self._fp_repo.count_by_user(u.id)
                records.append({
                    "user_id": u.id,
                    "employee_id": u.employee_id,
                    "full_name": u.full_name,
                    "department": u.department,
                    "is_active": u.is_active,
                    "template_count": fp_count,
                })
            self._database_tab.load_users(records)
            total_users = self._user_repo.count(active_only=True)
            total_fps = self._fp_repo.count(active_only=True)
            self._database_tab.update_statistics(total_users, total_fps, 50)
            print(f"[DB] refreshed: {total_users} users, {total_fps} fingerprints", flush=True)
        except Exception as exc:
            print(f"[DB] refresh error: {exc}", flush=True)

    # ------------------------------------------------------------------
    # Advanced API handlers
    # ------------------------------------------------------------------

    def _on_nfiq2_score(self, score: int) -> None:
        """Update quality panel with NFIQ2 score."""
        self._quality_panel.update_nfiq2(score)
        self.append_log(f"NFIQ2: {score}")

    def _on_spoof_result(self, is_spoof: bool, details: list) -> None:
        """Handle spoof detection result."""
        from mdgt_edge.ui.panels.spoof_panel import PAD_LIVE, PAD_FAKE
        self._spoof_panel.update_result(PAD_FAKE if is_spoof else PAD_LIVE)
        if is_spoof:
            self.statusBar().showMessage("WARNING: Spoof finger detected!", 5000)
            self._auto_led_feedback("spoof_detected")

    def _on_duplicate_result(self, is_dup: bool, matched_pos: int) -> None:
        """Handle duplicate detection result."""
        if is_dup:
            print(f"[DUPLICATE] finger matches position {matched_pos}", flush=True)
            QMessageBox.warning(
                self, "Duplicate Finger",
                f"This finger matches an already enrolled position ({matched_pos}).\n"
                "Capture rejected. Please use a different finger."
            )
        else:
            print("[DUPLICATE] no duplicate found", flush=True)

    def _on_geometry_result(self, is_valid: bool) -> None:
        """Handle finger geometry validation."""
        if not is_valid:
            self.statusBar().showMessage("Poor finger positioning — adjust placement", 5000)
            self._enroll_tab._finger_status_label.setText("Reposition finger")
            self._enroll_tab._finger_status_label.setStyleSheet(
                "font-size: 13px; color: #E74C3C; font-weight: bold;"
            )

    def _on_settings_applied(self, settings: dict) -> None:
        """Apply settings to sensor service."""
        svc = self._sensor_service
        print(f"[SETTINGS] applying: {list(settings.keys())}", flush=True)

        # PAD settings
        if "pad_enabled" in settings:
            svc.enable_spoof(settings["pad_enabled"])
        if "spoof_level" in settings:
            svc.set_spoof_level(settings["spoof_level"])

        # Device properties via set_property
        prop_map = {
            "super_dry_mode": (30, lambda v: "TRUE" if v else "FALSE"),  # ENUM_IBSU_PROPERTY_SUPER_DRY_MODE
            "wet_finger_detect": (32, lambda v: "TRUE" if v else "FALSE"),
            "wet_finger_level": (33, lambda v: str(v)),
            "enhanced_result": (34, lambda v: "TRUE" if v else "FALSE"),
            "enhanced_result_level": (35, lambda v: str(v)),
            "adaptive_capture": (36, lambda v: "TRUE" if v else "FALSE"),
        }
        applied = 0
        for key, (prop_id, converter) in prop_map.items():
            if key in settings:
                try:
                    svc.set_property(prop_id, converter(settings[key]))
                    applied += 1
                except Exception as exc:
                    print(f"[SETTINGS] property {key} failed: {exc}", flush=True)

        # Store LED/beep preferences
        self._auto_led = settings.get("auto_led_feedback", True)
        self._auto_beep = settings.get("auto_beep", True)

        self.statusBar().showMessage(f"Settings applied ({applied} device properties)", 3000)

    def _auto_led_feedback(self, event: str) -> None:
        """Automatic LED + beeper feedback on events."""
        if not getattr(self, "_auto_led", True):
            return
        svc = self._sensor_service
        if event == "capture_success":
            svc.set_leds(0x00FF00)  # green
            if getattr(self, "_auto_beep", True):
                svc.beep(50)
        elif event == "capture_fail":
            svc.set_leds(0xFF0000)  # red
        elif event == "spoof_detected":
            svc.set_leds(0xFF0000)  # red
            if getattr(self, "_auto_beep", True):
                svc.beep(200)
        elif event == "enrollment_complete":
            svc.set_leds(0x00FF00)  # green
            if getattr(self, "_auto_beep", True):
                svc.beep(100)

    # ------------------------------------------------------------------
    # Preprocessing & gallery persistence
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Database CRUD handlers
    # ------------------------------------------------------------------

    def _on_db_add_user(self, emp_id: str, name: str, dept: str) -> None:
        """Show dialog to add a new user."""
        from mdgt_edge.ui.qt_compat import (
            QDialog, QDialogButtonBox, QFormLayout, QLineEdit as _QLineEdit,
        )
        dialog = QDialog(self)
        dialog.setWindowTitle("Add User")
        form = QFormLayout(dialog)
        emp_edit = _QLineEdit()
        name_edit = _QLineEdit()
        dept_edit = _QLineEdit()
        emp_edit.setPlaceholderText("e.g. EMP-001")
        name_edit.setPlaceholderText("Full Name")
        dept_edit.setPlaceholderText("Department")
        form.addRow("Employee ID:", emp_edit)
        form.addRow("Full Name:", name_edit)
        form.addRow("Department:", dept_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            eid = emp_edit.text().strip()
            nm = name_edit.text().strip()
            dp = dept_edit.text().strip()
            if not eid or not nm:
                QMessageBox.warning(self, "Error", "Employee ID and Name are required.")
                return
            try:
                from mdgt_edge.database.models import User, UserRole
                self._user_repo.create(User(
                    employee_id=eid, full_name=nm, department=dp, role=UserRole.USER,
                ))
                self._refresh_database_tab()
                self.statusBar().showMessage(f"User {eid} created", 3000)
            except Exception as exc:
                QMessageBox.warning(self, "Error", f"Failed to add user: {exc}")

    def _on_db_delete_user(self, user_id: int) -> None:
        """Delete a user and their fingerprints, rebuild FAISS."""
        try:
            self._fp_repo.deactivate_by_user(user_id)
            self._user_repo.delete(user_id)
            self._rebuild_faiss_index()
            self._refresh_database_tab()
            self.statusBar().showMessage(f"User {user_id} deleted", 3000)
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"Delete failed: {exc}")

    def _on_db_deactivate_user(self, user_id: int) -> None:
        """Deactivate a user and rebuild FAISS index."""
        try:
            self._user_repo.deactivate(user_id)
            self._fp_repo.deactivate_by_user(user_id)
            self._rebuild_faiss_index()
            self._refresh_database_tab()
            self.statusBar().showMessage(f"User {user_id} deactivated", 3000)
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"Deactivate failed: {exc}")

    def _rebuild_faiss_index(self) -> None:
        """Rebuild FAISS index from active DB embeddings only."""
        from mdgt_edge.pipeline.faiss_index import FAISSIndexManager
        self._faiss_index = FAISSIndexManager(dim=256)
        self._enrolled_users.clear()
        self._load_gallery()
        print(f"[GALLERY] rebuilt: {self._faiss_index.count} active embeddings", flush=True)

    def _on_db_user_selected(self, user_id: int) -> None:
        """Load user detail and enrolled fingers for display."""
        try:
            user = self._user_repo.get_by_id(user_id)
            if user is None:
                return
            fps = self._fp_repo.get_by_user_id(user_id)
            enrolled_fingers = list({fp.finger_index for fp in fps})
            self._database_tab.load_user_detail({
                "user_id": user.id,
                "employee_id": user.employee_id,
                "full_name": user.full_name,
                "department": user.department,
                "is_active": user.is_active,
                "enrolled_fingers": enrolled_fingers,
            })
        except Exception as exc:
            print(f"[DB] user detail error: {exc}", flush=True)

    # ------------------------------------------------------------------
    # Image persistence for identify visualization
    # ------------------------------------------------------------------

    @staticmethod
    def _save_fp_image(fp_id: int, raw: bytes, width: int, height: int) -> None:
        """Save raw fingerprint image to disk for later visualization."""
        os.makedirs(IMAGES_DIR, exist_ok=True)
        meta_path = os.path.join(IMAGES_DIR, f"{fp_id}.meta")
        img_path = os.path.join(IMAGES_DIR, f"{fp_id}.raw")
        try:
            with open(img_path, "wb") as f:
                f.write(raw)
            with open(meta_path, "w") as f:
                f.write(f"{width},{height}")
        except Exception as exc:
            print(f"[IMAGE] save error fp_id={fp_id}: {exc}", flush=True)

    @staticmethod
    def _load_fp_image(fp_id: int) -> tuple:
        """Load a saved fingerprint image. Returns (bytes, width, height) or (None, 0, 0)."""
        meta_path = os.path.join(IMAGES_DIR, f"{fp_id}.meta")
        img_path = os.path.join(IMAGES_DIR, f"{fp_id}.raw")
        if not os.path.exists(img_path) or not os.path.exists(meta_path):
            return None, 0, 0
        try:
            with open(meta_path, "r") as f:
                w, h = f.read().strip().split(",")
            with open(img_path, "rb") as f:
                data = f.read()
            return data, int(w), int(h)
        except Exception:
            return None, 0, 0

    @staticmethod
    def _preprocess_for_model(
        raw_bytes: bytes, width: int, height: int, model_size: int = 224,
    ) -> np.ndarray:
        """Convert raw grayscale sensor bytes to (1, 3, 224, 224) float32 tensor.

        Applies gradient-based ridge deskew before CLAHE so enroll and identify
        images are rotation-normalised.
        """
        import cv2
        from mdgt_edge.pipeline.orientation import deskew
        gray = np.frombuffer(raw_bytes, dtype=np.uint8).copy().reshape((height, width))
        deskewed, angle = deskew(gray)
        if abs(angle) > 0:
            logger.debug("deskew applied: %.2f deg", angle)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(deskewed)
        resized = cv2.resize(enhanced, (model_size, model_size), interpolation=cv2.INTER_LINEAR)
        rgb = np.stack([resized, resized, resized], axis=0).astype(np.float32) / 255.0
        return np.expand_dims(rgb, axis=0)

    def _load_gallery(self) -> None:
        """Load FAISS gallery from SQLite — batch mode to save RAM."""
        try:
            rows = self._fp_repo.get_active_embeddings()
            # Pre-filter valid embeddings
            valid = []
            for fp_id, user_id, emb_bytes in rows:
                if emb_bytes is None or len(emb_bytes) != 1024:
                    continue
                valid.append((fp_id, user_id, emb_bytes))

            if not valid:
                print("[GALLERY] loaded 0 embeddings from DB", flush=True)
                return

            # Batch build: stack all embeddings into one array
            ids = np.array([fp_id for fp_id, _, _ in valid], dtype=np.int64)
            embs = np.zeros((len(valid), 256), dtype=np.float32)
            for i, (_, _, emb_bytes) in enumerate(valid):
                embs[i] = np.frombuffer(emb_bytes, dtype=np.float32)
            self._faiss_index.build_index(embs, ids)

            # Build user lookup — batch query users
            user_ids = list({uid for _, uid, _ in valid})
            user_cache: dict[int, tuple] = {}
            for uid in user_ids:
                u = self._user_repo.get_by_id(uid)
                if u:
                    user_cache[uid] = (u.employee_id, u.full_name, u.department)
            for fp_id, user_id, _ in valid:
                info = user_cache.get(user_id, ("", "Unknown", ""))
                self._enrolled_users[fp_id] = {
                    "employee_id": info[0], "name": info[1], "department": info[2],
                }

            print(f"[GALLERY] loaded {len(valid)} embeddings from DB", flush=True)
        except Exception as exc:
            print(f"[GALLERY] load error: {exc}", flush=True)

    def _save_gallery(self) -> None:
        """Persist FAISS index and enrolled user metadata to disk."""
        os.makedirs(GALLERY_DIR, exist_ok=True)
        try:
            self._faiss_index.save(INDEX_PATH)
        except Exception as exc:
            print(f"[GALLERY] index save error: {exc}", flush=True)
        try:
            with open(USERS_PATH, "w") as f:
                json.dump(
                    {"users": {str(k): v for k, v in self._enrolled_users.items()},
                     "next_fp_id": self._next_fp_id},
                    f, indent=2,
                )
        except Exception as exc:
            print(f"[GALLERY] users save error: {exc}", flush=True)

    def _on_sensor_connected(self, info: dict) -> None:
        """Handle successful device connection."""
        product = info.get("product_name", "Unknown")
        serial = info.get("serial_number", "N/A")
        fw = info.get("firmware_version", "")
        detail = (
            f"Product: {product}\n"
            f"Serial: {serial}\n"
            f"Firmware: {fw}"
        )
        self._update_device_status(True, detail)
        self._device_control.set_connected(True)
        self._device_control.set_device_info(product, serial, fw)
        logger.info("Sensor connected: %s (%s)", product, serial)

    def _on_sensor_disconnected(self) -> None:
        """Handle device disconnection."""
        self._update_device_status(False)
        self._device_control.set_connected(False)
        self._live_view_tab.stop_preview()
        self._live_view_tab.clear_preview()
        logger.info("Sensor disconnected")

    def _on_device_count_changed(self, count: int) -> None:
        """Handle USB hotplug events."""
        if count > 0 and not self._device_connected:
            self._sensor_service.open_device(0)
        elif count == 0 and self._device_connected:
            self._update_device_status(False)

    def _on_sensor_error(self, message: str, code: int) -> None:
        """Handle sensor errors without crashing."""
        logger.warning("Sensor error: %s (code=%d)", message, code)
        self.statusBar().showMessage(f"Sensor error: {message}", 5000)

    def _update_device_status(self, connected: bool, info: str = "") -> None:
        """Update all device-related UI elements."""
        self._device_connected = connected
        if connected:
            self._status_device.setText("Device: Connected")
            self._status_device.setStyleSheet(
                "color: #27AE60; padding: 0 8px;"
            )
            self._act_connect.setEnabled(False)
            self._act_disconnect.setEnabled(True)
        else:
            self._status_device.setText("Device: Disconnected")
            self._status_device.setStyleSheet(
                "color: #E74C3C; padding: 0 8px;"
            )
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
        self.statusBar().showMessage("Connecting to device...", 2000)
        self._sensor_service.open_device(0)

    def _on_device_disconnect(self) -> None:
        """Disconnect from fingerprint sensor."""
        self._sensor_service.close_device()

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
        self._embed_poll_timer.stop()
        self._embed_worker.stop(timeout=3.0)
        self._sensor_service.stop()
        self._sensor_service.wait(3000)
        self._save_gallery()
        self._save_state()
        event.accept()

    # ------------------------------------------------------------------
    # Async embedding worker glue
    # ------------------------------------------------------------------

    def _poll_embed_queue(self) -> None:
        """Periodic UI update: show pending count, refresh when queue drains."""
        pending = self._embed_worker.pending
        if pending > 0:
            self._stats_label.setText(
                f"Users: {self._user_repo.count(active_only=True)}\n"
                f"Templates pending: {pending}"
            )
        elif self._last_pending > 0 and pending == 0:
            # Queue just drained — refresh gallery stats
            try:
                fp_count = self._fp_repo.count(active_only=True)
                self.statusBar().showMessage(
                    f"All embeddings ready ({fp_count} fingerprints in gallery)", 3000
                )
                self._refresh_database_tab()
                self._save_gallery()
            except Exception as exc:
                logger.warning("post-drain refresh failed: %s", exc)
        self._last_pending = pending

    def _on_embedding_done(self, fp_id: int, embedding: np.ndarray) -> None:
        """Worker-thread callback when a single embedding completes.

        Runs in the worker thread — do NOT touch Qt widgets directly here.
        """
        logger.debug("embedding done fp_id=%s norm=%.4f",
                     fp_id, float(np.linalg.norm(embedding)))

    def _on_embedding_error(self, fp_id: int, exc: Exception) -> None:
        """Worker-thread callback on failure (still no Qt widgets here)."""
        logger.warning("embedding failed fp_id=%s: %s", fp_id, exc)


def main() -> int:
    """Launch the desktop application."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = MDGTEdgeMainWindow()
    window.show()

    exec_app = getattr(app, "exec", None)
    if exec_app is None:
        exec_app = app.exec_
    return exec_app()


if __name__ == "__main__":
    raise SystemExit(main())
