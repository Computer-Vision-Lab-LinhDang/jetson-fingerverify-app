"""Settings tab - device and system configuration.

Provides controls for device connection, thresholds, quality gates,
PAD configuration, model selection, database, and logging settings.
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QGridLayout, QPushButton, QLineEdit,
    QComboBox, QSlider, QSpinBox, QDoubleSpinBox,
    QCheckBox, QRadioButton, QButtonGroup,
    QScrollArea, QFileDialog, QMessageBox, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
THRESHOLD_MIN = 0.0
THRESHOLD_MAX = 1.0
THRESHOLD_STEP = 0.01
THRESHOLD_DECIMALS = 2

NFIQ2_MIN = 0
NFIQ2_MAX = 100

MINUTIAE_MIN = 0
MINUTIAE_MAX = 200

SPOOF_LEVELS = [1, 2, 3, 4, 5]

LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

BACKEND_OPTIONS = ["ONNX", "TensorRT"]

TOP_K_MIN = 1
TOP_K_MAX = 100


class SettingsTab(QWidget):
    """Device and system configuration interface."""

    # Signals
    settings_applied = pyqtSignal(dict)   # full settings dict
    settings_reset = pyqtSignal()
    database_backup_requested = pyqtSignal(str)  # backup path

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._init_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)

        # -- Device section --
        device_group = QGroupBox("Device")
        device_layout = QGridLayout()

        device_layout.addWidget(QLabel("Connection:"), 0, 0)
        self._device_status_label = QLabel("Disconnected")
        self._device_status_label.setStyleSheet("color: #E74C3C; font-weight: bold;")
        device_layout.addWidget(self._device_status_label, 0, 1)

        device_layout.addWidget(QLabel("Device Info:"), 1, 0)
        self._device_info_label = QLabel("--")
        self._device_info_label.setStyleSheet("color: #5D6D7E;")
        device_layout.addWidget(self._device_info_label, 1, 1)

        device_layout.addWidget(QLabel("Serial Number:"), 2, 0)
        self._device_serial_label = QLabel("--")
        self._device_serial_label.setStyleSheet("color: #5D6D7E;")
        device_layout.addWidget(self._device_serial_label, 2, 1)

        device_group.setLayout(device_layout)
        layout.addWidget(device_group)

        # -- Thresholds section --
        threshold_group = QGroupBox("Thresholds")
        threshold_layout = QGridLayout()

        # Verify threshold
        threshold_layout.addWidget(QLabel("Verify Threshold:"), 0, 0)
        self._verify_slider = QSlider(Qt.Orientation.Horizontal)
        self._verify_slider.setRange(0, 100)
        self._verify_slider.setValue(50)
        self._verify_slider.valueChanged.connect(self._on_verify_slider_changed)
        threshold_layout.addWidget(self._verify_slider, 0, 1)
        self._verify_value_label = QLabel("0.50")
        self._verify_value_label.setFixedWidth(50)
        threshold_layout.addWidget(self._verify_value_label, 0, 2)

        # Identify threshold
        threshold_layout.addWidget(QLabel("Identify Threshold:"), 1, 0)
        self._identify_slider = QSlider(Qt.Orientation.Horizontal)
        self._identify_slider.setRange(0, 100)
        self._identify_slider.setValue(50)
        self._identify_slider.valueChanged.connect(self._on_identify_slider_changed)
        threshold_layout.addWidget(self._identify_slider, 1, 1)
        self._identify_value_label = QLabel("0.50")
        self._identify_value_label.setFixedWidth(50)
        threshold_layout.addWidget(self._identify_value_label, 1, 2)

        # Top-K
        threshold_layout.addWidget(QLabel("Top-K Results:"), 2, 0)
        self._topk_spin = QSpinBox()
        self._topk_spin.setRange(TOP_K_MIN, TOP_K_MAX)
        self._topk_spin.setValue(10)
        threshold_layout.addWidget(self._topk_spin, 2, 1)

        threshold_group.setLayout(threshold_layout)
        layout.addWidget(threshold_group)

        # -- Quality section --
        quality_group = QGroupBox("Quality Gates")
        quality_layout = QGridLayout()

        quality_layout.addWidget(QLabel("Min NFIQ2 Score:"), 0, 0)
        self._nfiq2_spin = QSpinBox()
        self._nfiq2_spin.setRange(NFIQ2_MIN, NFIQ2_MAX)
        self._nfiq2_spin.setValue(30)
        quality_layout.addWidget(self._nfiq2_spin, 0, 1)

        quality_layout.addWidget(QLabel("Min Minutiae Count:"), 1, 0)
        self._minutiae_spin = QSpinBox()
        self._minutiae_spin.setRange(MINUTIAE_MIN, MINUTIAE_MAX)
        self._minutiae_spin.setValue(12)
        quality_layout.addWidget(self._minutiae_spin, 1, 1)

        quality_group.setLayout(quality_layout)
        layout.addWidget(quality_group)

        # -- PAD section --
        pad_group = QGroupBox("Presentation Attack Detection (PAD)")
        pad_layout = QVBoxLayout()

        self._pad_enabled_chk = QCheckBox("Enable PAD / Spoof Detection")
        self._pad_enabled_chk.setChecked(True)
        pad_layout.addWidget(self._pad_enabled_chk)

        spoof_row = QHBoxLayout()
        spoof_row.addWidget(QLabel("Spoof Detection Level:"))
        self._spoof_group = QButtonGroup(self)
        self._spoof_radios: list[QRadioButton] = []
        for level in SPOOF_LEVELS:
            radio = QRadioButton(str(level))
            self._spoof_group.addButton(radio, level)
            self._spoof_radios.append(radio)
            spoof_row.addWidget(radio)
        self._spoof_radios[2].setChecked(True)  # default level 3
        pad_layout.addLayout(spoof_row)

        pad_group.setLayout(pad_layout)
        layout.addWidget(pad_group)

        # -- Model section --
        model_group = QGroupBox("AI Model")
        model_layout = QGridLayout()

        model_layout.addWidget(QLabel("Active Model:"), 0, 0)
        self._model_name_label = QLabel("MDGTv2")
        self._model_name_label.setStyleSheet(
            "font-weight: bold; color: #2C3E50;"
        )
        model_layout.addWidget(self._model_name_label, 0, 1)

        model_layout.addWidget(QLabel("Model Path:"), 1, 0)
        model_path_row = QHBoxLayout()
        self._model_path_edit = QLineEdit()
        self._model_path_edit.setPlaceholderText("models/model_fp16.engine")
        model_path_row.addWidget(self._model_path_edit)
        self._btn_browse_model = QPushButton("Browse...")
        self._btn_browse_model.clicked.connect(self._on_browse_model)
        model_path_row.addWidget(self._btn_browse_model)
        model_layout.addLayout(model_path_row, 1, 1)

        model_layout.addWidget(QLabel("Backend:"), 2, 0)
        self._backend_combo = QComboBox()
        self._backend_combo.addItems(BACKEND_OPTIONS)
        model_layout.addWidget(self._backend_combo, 2, 1)

        model_group.setLayout(model_layout)
        layout.addWidget(model_group)

        # -- Database section --
        db_group = QGroupBox("Database")
        db_layout = QGridLayout()

        db_layout.addWidget(QLabel("DB Path:"), 0, 0)
        db_path_row = QHBoxLayout()
        self._db_path_edit = QLineEdit()
        self._db_path_edit.setPlaceholderText("data/mdgt_edge.db")
        db_path_row.addWidget(self._db_path_edit)
        self._btn_browse_db = QPushButton("Browse...")
        self._btn_browse_db.clicked.connect(self._on_browse_db)
        db_path_row.addWidget(self._btn_browse_db)
        db_layout.addLayout(db_path_row, 0, 1)

        self._wal_chk = QCheckBox("WAL Mode (recommended)")
        self._wal_chk.setChecked(True)
        db_layout.addWidget(self._wal_chk, 1, 0, 1, 2)

        self._btn_backup_db = QPushButton("Backup Database")
        self._btn_backup_db.clicked.connect(self._on_backup_db)
        db_layout.addWidget(self._btn_backup_db, 2, 0, 1, 2)

        db_group.setLayout(db_layout)
        layout.addWidget(db_group)

        # -- Logging section --
        log_group = QGroupBox("Logging")
        log_layout = QGridLayout()

        log_layout.addWidget(QLabel("Log Level:"), 0, 0)
        self._log_level_combo = QComboBox()
        self._log_level_combo.addItems(LOG_LEVELS)
        self._log_level_combo.setCurrentText("INFO")
        log_layout.addWidget(self._log_level_combo, 0, 1)

        log_layout.addWidget(QLabel("Log File:"), 1, 0)
        log_path_row = QHBoxLayout()
        self._log_path_edit = QLineEdit()
        self._log_path_edit.setPlaceholderText("logs/mdgt_edge.log")
        log_path_row.addWidget(self._log_path_edit)
        self._btn_browse_log = QPushButton("Browse...")
        self._btn_browse_log.clicked.connect(self._on_browse_log)
        log_path_row.addWidget(self._btn_browse_log)
        log_layout.addLayout(log_path_row, 1, 1)

        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        # -- Apply / Reset buttons --
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._btn_reset = QPushButton("Reset to Defaults")
        self._btn_reset.clicked.connect(self._on_reset)
        btn_row.addWidget(self._btn_reset)

        self._btn_apply = QPushButton("Apply")
        self._btn_apply.setStyleSheet(
            "QPushButton { background-color: #2980B9; color: white; "
            "font-weight: bold; padding: 10px 28px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #2471A3; }"
        )
        self._btn_apply.clicked.connect(self._on_apply)
        btn_row.addWidget(self._btn_apply)

        layout.addLayout(btn_row)
        layout.addStretch()

        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------
    # Slider callbacks
    # ------------------------------------------------------------------

    def _on_verify_slider_changed(self, value: int) -> None:
        self._verify_value_label.setText(f"{value / 100:.2f}")

    def _on_identify_slider_changed(self, value: int) -> None:
        self._identify_value_label.setText(f"{value / 100:.2f}")

    # ------------------------------------------------------------------
    # Browse dialogs
    # ------------------------------------------------------------------

    def _on_browse_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Model File", "",
            "Engine (*.engine);;ONNX (*.onnx);;All (*)",
        )
        if path:
            self._model_path_edit.setText(path)

    def _on_browse_db(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Database", "",
            "SQLite (*.db);;All (*)",
        )
        if path:
            self._db_path_edit.setText(path)

    def _on_browse_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Select Log File", "",
            "Log (*.log);;Text (*.txt);;All (*)",
        )
        if path:
            self._log_path_edit.setText(path)

    def _on_backup_db(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Backup Database", "mdgt_edge_backup.db",
            "SQLite (*.db);;All (*)",
        )
        if path:
            self.database_backup_requested.emit(path)

    # ------------------------------------------------------------------
    # Apply / Reset
    # ------------------------------------------------------------------

    def _on_apply(self) -> None:
        settings = self.get_current_settings()
        self.settings_applied.emit(settings)
        QMessageBox.information(
            self, "Settings", "Settings applied successfully."
        )

    def _on_reset(self) -> None:
        reply = QMessageBox.question(
            self,
            "Reset Settings",
            "Reset all settings to defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._set_defaults()
            self.settings_reset.emit()

    def _set_defaults(self) -> None:
        """Restore all controls to default values."""
        self._verify_slider.setValue(50)
        self._identify_slider.setValue(50)
        self._topk_spin.setValue(10)
        self._nfiq2_spin.setValue(30)
        self._minutiae_spin.setValue(12)
        self._pad_enabled_chk.setChecked(True)
        self._spoof_radios[2].setChecked(True)
        self._backend_combo.setCurrentIndex(0)
        self._wal_chk.setChecked(True)
        self._log_level_combo.setCurrentText("INFO")
        self._model_path_edit.clear()
        self._db_path_edit.clear()
        self._log_path_edit.clear()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_current_settings(self) -> dict:
        """Collect all current settings into a dictionary."""
        spoof_level = self._spoof_group.checkedId()
        if spoof_level < 0:
            spoof_level = 3

        return {
            "verify_threshold": self._verify_slider.value() / 100.0,
            "identify_threshold": self._identify_slider.value() / 100.0,
            "top_k": self._topk_spin.value(),
            "min_nfiq2": self._nfiq2_spin.value(),
            "min_minutiae": self._minutiae_spin.value(),
            "pad_enabled": self._pad_enabled_chk.isChecked(),
            "spoof_level": spoof_level,
            "model_path": self._model_path_edit.text(),
            "backend": self._backend_combo.currentText(),
            "db_path": self._db_path_edit.text(),
            "wal_mode": self._wal_chk.isChecked(),
            "log_level": self._log_level_combo.currentText(),
            "log_file": self._log_path_edit.text(),
        }

    @pyqtSlot(dict)
    def load_settings(self, settings: dict) -> None:
        """Populate controls from a settings dictionary.

        Parameters
        ----------
        settings:
            Dict with keys matching get_current_settings() output.
        """
        if "verify_threshold" in settings:
            self._verify_slider.setValue(
                int(settings["verify_threshold"] * 100)
            )
        if "identify_threshold" in settings:
            self._identify_slider.setValue(
                int(settings["identify_threshold"] * 100)
            )
        if "top_k" in settings:
            self._topk_spin.setValue(settings["top_k"])
        if "min_nfiq2" in settings:
            self._nfiq2_spin.setValue(settings["min_nfiq2"])
        if "min_minutiae" in settings:
            self._minutiae_spin.setValue(settings["min_minutiae"])
        if "pad_enabled" in settings:
            self._pad_enabled_chk.setChecked(settings["pad_enabled"])
        if "spoof_level" in settings:
            level = settings["spoof_level"]
            idx = level - 1
            if 0 <= idx < len(self._spoof_radios):
                self._spoof_radios[idx].setChecked(True)
        if "model_path" in settings:
            self._model_path_edit.setText(settings["model_path"])
        if "backend" in settings:
            self._backend_combo.setCurrentText(settings["backend"])
        if "db_path" in settings:
            self._db_path_edit.setText(settings["db_path"])
        if "wal_mode" in settings:
            self._wal_chk.setChecked(settings["wal_mode"])
        if "log_level" in settings:
            self._log_level_combo.setCurrentText(settings["log_level"])
        if "log_file" in settings:
            self._log_path_edit.setText(settings["log_file"])

    def update_device_info(
        self, connected: bool, info: str = "", serial: str = ""
    ) -> None:
        """Update device status display."""
        if connected:
            self._device_status_label.setText("Connected")
            self._device_status_label.setStyleSheet(
                "color: #27AE60; font-weight: bold;"
            )
        else:
            self._device_status_label.setText("Disconnected")
            self._device_status_label.setStyleSheet(
                "color: #E74C3C; font-weight: bold;"
            )
        self._device_info_label.setText(info or "--")
        self._device_serial_label.setText(serial or "--")
