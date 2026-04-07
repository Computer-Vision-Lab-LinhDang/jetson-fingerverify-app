"""Capture tab - manual fingerprint capture with export options.

Provides capture mode selection, resolution settings, result display,
segment grid, export controls, and capture history.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QGridLayout, QPushButton, QComboBox,
    QCheckBox, QFileDialog, QListWidget, QListWidgetItem,
    QSplitter, QScrollArea, QSizePolicy, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QImage, QPixmap

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CAPTURE_MODES = [
    "Flat - 1 Finger",
    "Flat - 2 Fingers",
    "Flat - 4 Fingers",
    "Roll - Single Finger",
    "Roll - Two Thumbs",
]

RESOLUTIONS = ["500 DPI", "1000 DPI"]

EXPORT_FORMATS = {
    "WSQ (*.wsq)": "wsq",
    "PNG (*.png)": "png",
    "JPEG 2000 (*.jp2)": "jp2",
    "RAW (*.raw)": "raw",
}

RESULT_DISPLAY_SIZE = 300
SEGMENT_THUMB_SIZE = 120
MAX_HISTORY_ITEMS = 20


@dataclass(frozen=True)
class CaptureRecord:
    """Immutable record of a single capture event."""

    timestamp: str
    mode: str
    resolution: str
    width: int
    height: int
    quality_score: int
    nfiq2_score: int
    image_data: bytes


class CaptureTab(QWidget):
    """Manual fingerprint capture with export options."""

    # Signals
    capture_requested = pyqtSignal(str, str)      # mode, resolution
    export_requested = pyqtSignal(str, str)        # file_path, format

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._last_image_data: Optional[bytes] = None
        self._last_width = 0
        self._last_height = 0
        self._capture_history: list[CaptureRecord] = []

        self._init_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        root_layout = QHBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(splitter)

        # -- Left column: options + capture --
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(8, 8, 8, 8)

        # Capture mode
        mode_group = QGroupBox("Capture Mode")
        mode_layout = QVBoxLayout()

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(CAPTURE_MODES)
        mode_layout.addWidget(self._mode_combo)

        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("Resolution:"))
        self._resolution_combo = QComboBox()
        self._resolution_combo.addItems(RESOLUTIONS)
        res_row.addWidget(self._resolution_combo)
        mode_layout.addLayout(res_row)

        mode_group.setLayout(mode_layout)
        left_layout.addWidget(mode_group)

        # Capture options
        opts_group = QGroupBox("Options")
        opts_layout = QVBoxLayout()

        self._chk_auto_contrast = QCheckBox("Auto Contrast")
        self._chk_auto_contrast.setChecked(True)
        opts_layout.addWidget(self._chk_auto_contrast)

        self._chk_auto_capture = QCheckBox("Auto Capture")
        opts_layout.addWidget(self._chk_auto_capture)

        self._chk_ignore_count = QCheckBox("Ignore Finger Count")
        opts_layout.addWidget(self._chk_ignore_count)

        opts_group.setLayout(opts_layout)
        left_layout.addWidget(opts_group)

        # Capture button
        self._capture_btn = QPushButton("CAPTURE")
        self._capture_btn.setMinimumHeight(60)
        self._capture_btn.setStyleSheet(
            "QPushButton { background-color: #2980B9; color: white; "
            "font-size: 18px; font-weight: bold; border-radius: 8px; }"
            "QPushButton:hover { background-color: #2471A3; }"
            "QPushButton:pressed { background-color: #1A5276; }"
        )
        self._capture_btn.clicked.connect(self._on_capture_clicked)
        left_layout.addWidget(self._capture_btn)

        # Export panel
        export_group = QGroupBox("Export")
        export_layout = QVBoxLayout()

        self._export_format_combo = QComboBox()
        self._export_format_combo.addItems(EXPORT_FORMATS.keys())
        export_layout.addWidget(self._export_format_combo)

        self._export_btn = QPushButton("Save As...")
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._on_export_clicked)
        export_layout.addWidget(self._export_btn)

        export_group.setLayout(export_layout)
        left_layout.addWidget(export_group)

        left_layout.addStretch()
        splitter.addWidget(left_widget)

        # -- Center column: result display --
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(8, 8, 8, 8)

        center_layout.addWidget(
            QLabel("Captured Image"),
            alignment=Qt.AlignmentFlag.AlignCenter,
        )

        self._result_label = QLabel("No capture yet")
        self._result_label.setFixedSize(RESULT_DISPLAY_SIZE, RESULT_DISPLAY_SIZE)
        self._result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._result_label.setStyleSheet(
            "background-color: #1B2631; border: 2px solid #2C3E50; "
            "border-radius: 8px; color: #5D6D7E; font-size: 14px;"
        )
        center_layout.addWidget(
            self._result_label, alignment=Qt.AlignmentFlag.AlignCenter
        )

        # Image info
        info_group = QGroupBox("Image Info")
        info_layout = QGridLayout()
        self._info_fields: dict[str, QLabel] = {}
        field_names = [
            ("Width", "width"),
            ("Height", "height"),
            ("Resolution", "resolution"),
            ("Quality", "quality"),
            ("NFIQ2", "nfiq2"),
        ]
        for row, (display_name, key) in enumerate(field_names):
            lbl = QLabel(f"{display_name}:")
            lbl.setStyleSheet("font-weight: bold; color: #2C3E50;")
            val = QLabel("--")
            val.setStyleSheet("color: #5D6D7E;")
            info_layout.addWidget(lbl, row, 0)
            info_layout.addWidget(val, row, 1)
            self._info_fields[key] = val
        info_group.setLayout(info_layout)
        center_layout.addWidget(info_group)

        # Segment images grid
        seg_group = QGroupBox("Segments")
        seg_scroll = QScrollArea()
        seg_scroll.setWidgetResizable(True)
        seg_inner = QWidget()
        self._segment_layout = QGridLayout(seg_inner)
        self._segment_labels: list[QLabel] = []
        for i in range(4):
            lbl = QLabel("--")
            lbl.setFixedSize(SEGMENT_THUMB_SIZE, SEGMENT_THUMB_SIZE)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                "background-color: #2C3E50; border: 1px solid #5D6D7E; "
                "border-radius: 4px; color: #7F8C8D; font-size: 11px;"
            )
            self._segment_layout.addWidget(lbl, i // 2, i % 2)
            self._segment_labels.append(lbl)
        seg_scroll.setWidget(seg_inner)
        seg_box_layout = QVBoxLayout()
        seg_box_layout.addWidget(seg_scroll)
        seg_group.setLayout(seg_box_layout)
        center_layout.addWidget(seg_group)

        center_layout.addStretch()
        splitter.addWidget(center_widget)

        # -- Right column: capture history --
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 8, 8, 8)

        right_layout.addWidget(QLabel("Capture History"))

        self._history_list = QListWidget()
        self._history_list.currentRowChanged.connect(
            self._on_history_selected
        )
        right_layout.addWidget(self._history_list)

        self._clear_history_btn = QPushButton("Clear History")
        self._clear_history_btn.clicked.connect(self._on_clear_history)
        right_layout.addWidget(self._clear_history_btn)

        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 1)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_capture_clicked(self) -> None:
        mode = self._mode_combo.currentText()
        resolution = self._resolution_combo.currentText()
        self._capture_btn.setEnabled(False)
        self._capture_btn.setText("Capturing...")
        self.capture_requested.emit(mode, resolution)

    def start_capture(self) -> None:
        """Programmatic trigger (from toolbar)."""
        self._on_capture_clicked()

    def _on_export_clicked(self) -> None:
        if self._last_image_data is None:
            return

        fmt_key = self._export_format_combo.currentText()
        fmt_ext = EXPORT_FORMATS.get(fmt_key, "png")

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Fingerprint",
            f"fingerprint.{fmt_ext}",
            fmt_key,
        )
        if file_path:
            self.export_requested.emit(file_path, fmt_ext)

    def _on_clear_history(self) -> None:
        self._capture_history.clear()
        self._history_list.clear()

    def _on_history_selected(self, row: int) -> None:
        if 0 <= row < len(self._capture_history):
            record = self._capture_history[row]
            self._display_capture_result(
                record.image_data,
                record.width,
                record.height,
                record.quality_score,
                record.nfiq2_score,
            )

    # ------------------------------------------------------------------
    # Slots -- called externally via signals
    # ------------------------------------------------------------------

    @pyqtSlot(object)
    def on_capture_complete(self, result: object) -> None:
        """Handle capture completion from IBScanService.

        Parameters
        ----------
        result:
            Capture result object with image_data, width, height, etc.
        """
        self._capture_btn.setEnabled(True)
        self._capture_btn.setText("CAPTURE")

        image_data = getattr(result, "image_data", b"")
        width = getattr(result, "width", 192)
        height = getattr(result, "height", 192)
        quality = getattr(result, "quality_score", 0)
        nfiq2 = getattr(result, "nfiq2_score", 0)

        if not image_data:
            return

        self._last_image_data = image_data
        self._last_width = width
        self._last_height = height
        self._export_btn.setEnabled(True)

        self._display_capture_result(image_data, width, height, quality, nfiq2)
        self._add_history_entry(image_data, width, height, quality, nfiq2)

    def _display_capture_result(
        self,
        image_data: bytes,
        width: int,
        height: int,
        quality: int,
        nfiq2: int,
    ) -> None:
        """Render capture result in the UI."""
        qimg = QImage(
            image_data, width, height, width,
            QImage.Format.Format_Grayscale8,
        )
        pixmap = QPixmap.fromImage(qimg).scaled(
            RESULT_DISPLAY_SIZE, RESULT_DISPLAY_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._result_label.setPixmap(pixmap)
        self._result_label.setStyleSheet(
            "background-color: #1B2631; border: 2px solid #27AE60; "
            "border-radius: 8px;"
        )

        res_text = self._resolution_combo.currentText()
        self._info_fields["width"].setText(str(width))
        self._info_fields["height"].setText(str(height))
        self._info_fields["resolution"].setText(res_text)
        self._info_fields["quality"].setText(str(quality) if quality else "--")
        self._info_fields["nfiq2"].setText(str(nfiq2) if nfiq2 else "--")

    def _add_history_entry(
        self,
        image_data: bytes,
        width: int,
        height: int,
        quality: int,
        nfiq2: int,
    ) -> None:
        """Add a capture record to the history list."""
        now = datetime.now().strftime("%H:%M:%S")
        record = CaptureRecord(
            timestamp=now,
            mode=self._mode_combo.currentText(),
            resolution=self._resolution_combo.currentText(),
            width=width,
            height=height,
            quality_score=quality,
            nfiq2_score=nfiq2,
            image_data=image_data,
        )
        self._capture_history.insert(0, record)
        if len(self._capture_history) > MAX_HISTORY_ITEMS:
            self._capture_history = self._capture_history[:MAX_HISTORY_ITEMS]

        item = QListWidgetItem(f"[{now}] {record.mode} Q:{quality}")
        self._history_list.insertItem(0, item)
        if self._history_list.count() > MAX_HISTORY_ITEMS:
            self._history_list.takeItem(self._history_list.count() - 1)

    # ------------------------------------------------------------------
    # Segment display
    # ------------------------------------------------------------------

    @pyqtSlot(list)
    def on_segments_received(self, segments: list) -> None:
        """Display individual finger segment images.

        Parameters
        ----------
        segments:
            List of (image_data, width, height) tuples.
        """
        for i, seg_label in enumerate(self._segment_labels):
            if i < len(segments):
                img_data, w, h = segments[i]
                qimg = QImage(
                    img_data, w, h, w,
                    QImage.Format.Format_Grayscale8,
                )
                pixmap = QPixmap.fromImage(qimg).scaled(
                    SEGMENT_THUMB_SIZE, SEGMENT_THUMB_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                seg_label.setPixmap(pixmap)
            else:
                seg_label.clear()
                seg_label.setText("--")
