"""Enhanced Status Bar with multiple permanent sections."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QStatusBar, QLabel, QWidget, QHBoxLayout,
    QProgressBar, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSlot, QTimer
from PyQt6.QtGui import QFont, QColor


class _SectionLabel(QLabel):
    """Thin wrapper that adds a right-side separator frame."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setStyleSheet("color: #a6adc8; font-size: 11px; padding: 0 6px;")


class EnhancedStatusBar(QStatusBar):
    """Custom status bar with permanent labeled sections.

    Sections (left to right):
    1. Connection status: "● Connected: IB Kojak" or "○ Disconnected"
    2. Capture mode: "Mode: Flat 1-Finger @ 500 DPI"
    3. FPS: "Preview: 30 FPS"
    4. Finger count: "Fingers: 2/4"
    5. PAD status: "PAD: ON (Level 3)" or "PAD: OFF"
    6. Model: "Model: mdgtv2_fp16.engine (TRT)"
    7. Memory: "RAM: 1.2/4.0 GB"
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizeGripEnabled(False)
        self.setStyleSheet(
            "QStatusBar { background-color: #181825; border-top: 1px solid #313244; }"
            "QStatusBar::item { border: none; }"
        )
        self._build_sections()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_sections(self) -> None:
        sections: list[QWidget] = [
            self._make_separator(),
            self._build_connection_section(),
            self._make_separator(),
            self._build_mode_section(),
            self._make_separator(),
            self._build_fps_section(),
            self._make_separator(),
            self._build_finger_count_section(),
            self._make_separator(),
            self._build_pad_section(),
            self._make_separator(),
            self._build_model_section(),
            self._make_separator(),
            self._build_memory_section(),
            self._make_separator(),
        ]
        for widget in sections:
            self.addPermanentWidget(widget)

    def _make_separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #313244;")
        sep.setFixedWidth(1)
        return sep

    def _build_connection_section(self) -> QLabel:
        self._lbl_connection = _SectionLabel("○ Disconnected")
        self._lbl_connection.setStyleSheet("color: #f38ba8; font-size: 11px; padding: 0 6px;")
        return self._lbl_connection

    def _build_mode_section(self) -> QLabel:
        self._lbl_mode = _SectionLabel("Mode: —")
        return self._lbl_mode

    def _build_fps_section(self) -> QLabel:
        self._lbl_fps = _SectionLabel("Preview: — FPS")
        return self._lbl_fps

    def _build_finger_count_section(self) -> QLabel:
        self._lbl_fingers = _SectionLabel("Fingers: —")
        return self._lbl_fingers

    def _build_pad_section(self) -> QLabel:
        self._lbl_pad = _SectionLabel("PAD: OFF")
        return self._lbl_pad

    def _build_model_section(self) -> QLabel:
        self._lbl_model = _SectionLabel("Model: —")
        return self._lbl_model

    def _build_memory_section(self) -> QLabel:
        self._lbl_memory = _SectionLabel("RAM: —")
        return self._lbl_memory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @pyqtSlot(bool, str)
    def set_connection(self, connected: bool, device_name: str = "") -> None:
        """Update connection indicator.

        Args:
            connected: True if device is connected.
            device_name: Human-readable device name (e.g. "IB Kojak").
        """
        if connected:
            text = f"● Connected: {device_name}" if device_name else "● Connected"
            self._lbl_connection.setText(text)
            self._lbl_connection.setStyleSheet(
                "color: #a6e3a1; font-size: 11px; padding: 0 6px;"
            )
        else:
            self._lbl_connection.setText("○ Disconnected")
            self._lbl_connection.setStyleSheet(
                "color: #f38ba8; font-size: 11px; padding: 0 6px;"
            )

    @pyqtSlot(str, int)
    def set_capture_mode(self, mode_label: str, dpi: int) -> None:
        """Update capture mode section.

        Args:
            mode_label: e.g. "Flat 1-Finger"
            dpi: 500 or 1000
        """
        self._lbl_mode.setText(f"Mode: {mode_label} @ {dpi} DPI")

    @pyqtSlot(float)
    def set_fps(self, fps: float) -> None:
        """Update live preview FPS."""
        self._lbl_fps.setText(f"Preview: {fps:.0f} FPS")

    @pyqtSlot(int, int)
    def set_finger_count(self, detected: int, expected: int) -> None:
        """Update finger count section."""
        self._lbl_fingers.setText(f"Fingers: {detected}/{expected}")
        if detected == expected and expected > 0:
            self._lbl_fingers.setStyleSheet(
                "color: #a6e3a1; font-size: 11px; padding: 0 6px;"
            )
        else:
            self._lbl_fingers.setStyleSheet(
                "color: #f9e2af; font-size: 11px; padding: 0 6px;"
            )

    @pyqtSlot(bool, int)
    def set_pad_status(self, enabled: bool, level: int = 3) -> None:
        """Update PAD/spoof detection status."""
        if enabled:
            self._lbl_pad.setText(f"PAD: ON (Level {level})")
            self._lbl_pad.setStyleSheet(
                "color: #a6e3a1; font-size: 11px; padding: 0 6px;"
            )
        else:
            self._lbl_pad.setText("PAD: OFF")
            self._lbl_pad.setStyleSheet(
                "color: #a6adc8; font-size: 11px; padding: 0 6px;"
            )

    @pyqtSlot(str)
    def set_model(self, model_name: str) -> None:
        """Update active model display.

        Args:
            model_name: e.g. "mdgtv2_fp16.engine (TRT)" or "model.onnx (ONNX)"
        """
        if model_name:
            self._lbl_model.setText(f"Model: {model_name}")
            self._lbl_model.setStyleSheet(
                "color: #89b4fa; font-size: 11px; padding: 0 6px;"
            )
        else:
            self._lbl_model.setText("Model: —")
            self._lbl_model.setStyleSheet(
                "color: #a6adc8; font-size: 11px; padding: 0 6px;"
            )

    @pyqtSlot(float, float)
    def set_memory(self, used_gb: float, total_gb: float) -> None:
        """Update RAM usage display.

        Args:
            used_gb: Used RAM in GB.
            total_gb: Total RAM in GB.
        """
        self._lbl_memory.setText(f"RAM: {used_gb:.1f}/{total_gb:.1f} GB")
        ratio = used_gb / total_gb if total_gb > 0 else 0.0
        if ratio > 0.85:
            color = "#f38ba8"
        elif ratio > 0.70:
            color = "#f9e2af"
        else:
            color = "#a6adc8"
        self._lbl_memory.setStyleSheet(
            f"color: {color}; font-size: 11px; padding: 0 6px;"
        )

    def show_temporary_message(self, message: str, timeout_ms: int = 3000) -> None:
        """Display a temporary message in the left area."""
        self.showMessage(message, timeout_ms)
