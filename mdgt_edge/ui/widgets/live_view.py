"""LiveView tab - real-time sensor preview with quality overlays.

Displays the live fingerprint sensor feed, finger position indicators,
quality metrics, and FPS counter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QFrame, QSplitter, QPushButton,
    QSizePolicy, QGridLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer, QElapsedTimer
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QFont

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PREVIEW_WIDTH = 400
PREVIEW_HEIGHT = 400
DEFAULT_SENSOR_WIDTH = 192
DEFAULT_SENSOR_HEIGHT = 192
FPS_UPDATE_INTERVAL_MS = 1000
PREVIEW_POLL_INTERVAL_MS = 50

QUALITY_GOOD = "#27AE60"
QUALITY_FAIR = "#F39C12"
QUALITY_POOR = "#E74C3C"
QUALITY_UNKNOWN = "#7F8C8D"

FINGER_NAMES = [
    "Right Thumb", "Right Index", "Right Middle", "Right Ring", "Right Little",
    "Left Thumb", "Left Index", "Left Middle", "Left Ring", "Left Little",
]


@dataclass(frozen=True)
class FingerQuality:
    """Immutable quality state for a single finger."""

    index: int
    name: str
    detected: bool = False
    quality_score: int = 0

    @property
    def color(self) -> str:
        if not self.detected:
            return QUALITY_UNKNOWN
        if self.quality_score >= 70:
            return QUALITY_GOOD
        if self.quality_score >= 40:
            return QUALITY_FAIR
        return QUALITY_POOR


class QualityDot(QWidget):
    """Small colored circle indicating finger quality."""

    def __init__(self, size: int = 16, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._color = QUALITY_UNKNOWN
        self._update_style()

    def set_color(self, color: str) -> None:
        self._color = color
        self._update_style()

    def _update_style(self) -> None:
        radius = self.width() // 2
        self.setStyleSheet(
            f"background-color: {self._color}; "
            f"border-radius: {radius}px;"
        )


class LiveViewTab(QWidget):
    """Real-time fingerprint sensor preview with quality overlay."""

    # Signals
    preview_updated = pyqtSignal(object)   # QImage
    finger_detected = pyqtSignal(bool)
    quality_changed = pyqtSignal(list)     # list of FingerQuality

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._streaming = False
        self._frame_count = 0
        self._fps = 0.0
        self._finger_qualities: list[FingerQuality] = [
            FingerQuality(index=i, name=FINGER_NAMES[i])
            for i in range(len(FINGER_NAMES))
        ]

        self._fps_timer = QElapsedTimer()
        self._fps_update_timer = QTimer(self)
        self._fps_update_timer.timeout.connect(self._update_fps_display)
        self._fps_update_timer.setInterval(FPS_UPDATE_INTERVAL_MS)

        self._init_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        root_layout = QHBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(splitter)

        # -- Left panel: preview + controls --
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(8, 8, 8, 8)

        # Instruction label
        self._instruction_label = QLabel("Place finger on sensor to begin")
        self._instruction_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._instruction_label.setStyleSheet(
            "font-size: 16px; color: #5D6D7E; padding: 8px; "
            "background-color: #F8F9FA; border-radius: 6px;"
        )
        left_layout.addWidget(self._instruction_label)

        # Preview area
        self._preview_label = QLabel()
        self._preview_label.setFixedSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet(
            "background-color: #1B2631; border: 2px solid #2C3E50; "
            "border-radius: 8px; color: #5D6D7E; font-size: 14px;"
        )
        self._preview_label.setText("No Preview")
        left_layout.addWidget(
            self._preview_label, alignment=Qt.AlignmentFlag.AlignCenter
        )

        # FPS and finger count row
        info_row = QHBoxLayout()
        self._fps_label = QLabel("FPS: --")
        self._fps_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #2C3E50;"
        )
        info_row.addWidget(self._fps_label)

        info_row.addStretch()

        self._finger_count_label = QLabel("Fingers: 0")
        self._finger_count_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #2C3E50;"
        )
        info_row.addWidget(self._finger_count_label)
        left_layout.addLayout(info_row)

        # Control buttons
        btn_layout = QHBoxLayout()

        self._toggle_btn = QPushButton("Start Preview")
        self._toggle_btn.setStyleSheet(
            "QPushButton { background-color: #27AE60; color: white; "
            "font-size: 14px; font-weight: bold; padding: 10px 28px; "
            "border-radius: 6px; }"
            "QPushButton:hover { background-color: #229954; }"
        )
        self._toggle_btn.clicked.connect(self._on_toggle_preview)
        btn_layout.addWidget(self._toggle_btn)

        left_layout.addLayout(btn_layout)
        left_layout.addStretch()

        splitter.addWidget(left_widget)

        # -- Right panel: quality indicators + info --
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 8, 8, 8)

        # Finger quality group
        quality_group = QGroupBox("Finger Quality")
        quality_layout = QGridLayout()
        self._quality_dots: list[QualityDot] = []
        self._quality_labels: list[QLabel] = []

        for i, name in enumerate(FINGER_NAMES):
            row = i
            dot = QualityDot(16)
            label = QLabel(name)
            label.setStyleSheet("font-size: 12px; color: #2C3E50;")
            score_label = QLabel("--")
            score_label.setStyleSheet("font-size: 12px; color: #7F8C8D;")

            quality_layout.addWidget(dot, row, 0)
            quality_layout.addWidget(label, row, 1)
            quality_layout.addWidget(score_label, row, 2)

            self._quality_dots.append(dot)
            self._quality_labels.append(score_label)

        quality_group.setLayout(quality_layout)
        right_layout.addWidget(quality_group)

        # Sensor status group
        status_group = QGroupBox("Sensor Status")
        status_layout = QVBoxLayout()

        self._sensor_status_label = QLabel("Status: Idle")
        self._sensor_status_label.setStyleSheet(
            "font-size: 13px; color: #5D6D7E;"
        )
        status_layout.addWidget(self._sensor_status_label)

        self._resolution_label = QLabel("Resolution: --")
        self._resolution_label.setStyleSheet(
            "font-size: 13px; color: #5D6D7E;"
        )
        status_layout.addWidget(self._resolution_label)

        self._image_size_label = QLabel("Image Size: --")
        self._image_size_label.setStyleSheet(
            "font-size: 13px; color: #5D6D7E;"
        )
        status_layout.addWidget(self._image_size_label)

        status_group.setLayout(status_layout)
        right_layout.addWidget(status_group)

        right_layout.addStretch()
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

    # ------------------------------------------------------------------
    # Preview control
    # ------------------------------------------------------------------

    def _on_toggle_preview(self) -> None:
        if self._streaming:
            self.stop_preview()
        else:
            self.start_preview()

    def start_preview(self) -> None:
        """Start the live preview stream."""
        self._streaming = True
        self._frame_count = 0
        self._fps = 0.0
        self._fps_timer.start()
        self._fps_update_timer.start()
        self._toggle_btn.setText("Stop Preview")
        self._toggle_btn.setStyleSheet(
            "QPushButton { background-color: #E74C3C; color: white; "
            "font-size: 14px; font-weight: bold; padding: 10px 28px; "
            "border-radius: 6px; }"
            "QPushButton:hover { background-color: #C0392B; }"
        )
        self._sensor_status_label.setText("Status: Streaming")
        self._instruction_label.setText("Streaming -- place finger on sensor")
        logger.info("Preview started")

    def stop_preview(self) -> None:
        """Stop the live preview stream."""
        self._streaming = False
        self._fps_update_timer.stop()
        self._toggle_btn.setText("Start Preview")
        self._toggle_btn.setStyleSheet(
            "QPushButton { background-color: #27AE60; color: white; "
            "font-size: 14px; font-weight: bold; padding: 10px 28px; "
            "border-radius: 6px; }"
            "QPushButton:hover { background-color: #229954; }"
        )
        self._sensor_status_label.setText("Status: Idle")
        self._fps_label.setText("FPS: --")
        self._instruction_label.setText("Place finger on sensor to begin")
        logger.info("Preview stopped")

    @property
    def is_streaming(self) -> bool:
        return self._streaming

    # ------------------------------------------------------------------
    # Slots -- called by IBScanService signals
    # ------------------------------------------------------------------

    @pyqtSlot(bytes, int, int)
    def on_preview_frame(
        self, image_data: bytes, width: int, height: int
    ) -> None:
        """Receive a new preview frame from the sensor service."""
        if not self._streaming:
            return

        self._frame_count += 1

        qimg = QImage(
            image_data, width, height, width,
            QImage.Format.Format_Grayscale8,
        )
        pixmap = QPixmap.fromImage(qimg).scaled(
            PREVIEW_WIDTH, PREVIEW_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_label.setPixmap(pixmap)
        self._preview_label.setStyleSheet(
            "background-color: #1B2631; border: 2px solid #27AE60; "
            "border-radius: 8px;"
        )

        self.preview_updated.emit(qimg)

    @pyqtSlot(int)
    def on_finger_count_changed(self, count: int) -> None:
        """Update the finger count display."""
        self._finger_count_label.setText(f"Fingers: {count}")
        detected = count > 0
        self.finger_detected.emit(detected)
        if detected:
            self._instruction_label.setText(
                f"{count} finger(s) detected"
            )
        else:
            self._instruction_label.setText(
                "Place finger on sensor"
            )

    @pyqtSlot(list)
    def on_finger_quality_changed(self, qualities: list) -> None:
        """Update quality indicators from sensor quality data.

        Parameters
        ----------
        qualities:
            List of integer quality values per finger position.
        """
        new_qualities: list[FingerQuality] = []
        for i in range(min(len(qualities), len(FINGER_NAMES))):
            q_val = qualities[i] if i < len(qualities) else 0
            fq = FingerQuality(
                index=i,
                name=FINGER_NAMES[i],
                detected=q_val > 0,
                quality_score=q_val,
            )
            new_qualities.append(fq)

            if i < len(self._quality_dots):
                self._quality_dots[i].set_color(fq.color)
            if i < len(self._quality_labels):
                text = f"{q_val}" if q_val > 0 else "--"
                self._quality_labels[i].setText(text)

        self._finger_qualities = new_qualities
        self.quality_changed.emit(new_qualities)

    # ------------------------------------------------------------------
    # FPS tracking
    # ------------------------------------------------------------------

    def _update_fps_display(self) -> None:
        if not self._streaming:
            return
        elapsed_ms = self._fps_timer.elapsed()
        if elapsed_ms > 0:
            self._fps = (self._frame_count * 1000.0) / elapsed_ms
        self._fps_label.setText(f"FPS: {self._fps:.1f}")
        # Reset for next interval
        self._frame_count = 0
        self._fps_timer.restart()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def set_resolution_info(self, dpi: int, width: int, height: int) -> None:
        """Display sensor resolution info."""
        self._resolution_label.setText(f"Resolution: {dpi} DPI")
        self._image_size_label.setText(f"Image Size: {width}x{height}")

    def clear_preview(self) -> None:
        """Reset the preview to placeholder state."""
        self._preview_label.clear()
        self._preview_label.setText("No Preview")
        self._preview_label.setStyleSheet(
            "background-color: #1B2631; border: 2px solid #2C3E50; "
            "border-radius: 8px; color: #5D6D7E; font-size: 14px;"
        )
