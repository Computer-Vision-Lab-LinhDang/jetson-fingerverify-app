"""Identify tab - 1:N fingerprint identification.

Displays probe image, identification results table with score
visualization, latency info, and auto-identify toggle.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QCheckBox, QSplitter,
    QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QColor, QFont, QImage, QPixmap

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROBE_DISPLAY_SIZE = 256
SCORE_BAR_WIDTH = 200
MAX_RESULT_ROWS = 20
AUTO_IDENTIFY_INTERVAL_MS = 3000

RESULT_COLUMNS = ["Rank", "User", "Employee ID", "Department", "Score", "Match"]

COLOR_MATCH = "#27AE60"
COLOR_NO_MATCH = "#E74C3C"
COLOR_THRESHOLD = "#F39C12"


@dataclass(frozen=True)
class IdentifyResult:
    """Immutable identification result entry."""

    rank: int
    user_name: str
    employee_id: str
    department: str
    score: float
    is_match: bool


class _ScoreBar(QWidget):
    """Horizontal bar visualizing a match score with threshold line."""

    def __init__(
        self,
        score: float,
        threshold: float = 0.5,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._score = max(0.0, min(1.0, score))
        self._threshold = max(0.0, min(1.0, threshold))
        self.setFixedHeight(20)
        self.setMinimumWidth(SCORE_BAR_WIDTH)
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(self._score * 100))
        bar.setTextVisible(True)
        bar.setFormat(f"{self._score:.3f}")

        if self._score >= self._threshold:
            bar.setStyleSheet(
                "QProgressBar { border: 1px solid #BDC3C7; border-radius: 4px; "
                "background: #ECF0F1; }"
                f"QProgressBar::chunk {{ background-color: {COLOR_MATCH}; "
                "border-radius: 3px; }"
            )
        else:
            bar.setStyleSheet(
                "QProgressBar { border: 1px solid #BDC3C7; border-radius: 4px; "
                "background: #ECF0F1; }"
                f"QProgressBar::chunk {{ background-color: {COLOR_NO_MATCH}; "
                "border-radius: 3px; }"
            )

        layout.addWidget(bar)


class IdentifyTab(QWidget):
    """1:N fingerprint identification interface."""

    # Signals
    identify_requested = pyqtSignal()
    auto_identify_toggled = pyqtSignal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._threshold = 0.5
        self._last_latency_ms = 0.0
        self._auto_identify_active = False
        self._identify_start_time = 0.0

        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._on_auto_identify_tick)
        self._auto_timer.setInterval(AUTO_IDENTIFY_INTERVAL_MS)

        self._init_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        root = QHBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # -- Left: probe image + controls --
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(8, 8, 8, 8)

        left_layout.addWidget(
            QLabel("Probe Image"),
            alignment=Qt.AlignmentFlag.AlignCenter,
        )

        self._probe_label = QLabel("No probe")
        self._probe_label.setFixedSize(PROBE_DISPLAY_SIZE, PROBE_DISPLAY_SIZE)
        self._probe_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._probe_label.setStyleSheet(
            "background-color: #1B2631; border: 2px solid #2C3E50; "
            "border-radius: 8px; color: #5D6D7E; font-size: 14px;"
        )
        left_layout.addWidget(
            self._probe_label, alignment=Qt.AlignmentFlag.AlignCenter
        )

        # Match / no-match indicator
        self._match_indicator = QLabel("--")
        self._match_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._match_indicator.setStyleSheet(
            "font-size: 24px; font-weight: bold; color: #7F8C8D; padding: 8px;"
        )
        left_layout.addWidget(self._match_indicator)

        # Latency
        self._latency_label = QLabel("Latency: -- ms")
        self._latency_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._latency_label.setStyleSheet(
            "font-size: 13px; color: #5D6D7E;"
        )
        left_layout.addWidget(self._latency_label)

        # Identify button
        self._identify_btn = QPushButton("IDENTIFY")
        self._identify_btn.setMinimumHeight(60)
        self._identify_btn.setStyleSheet(
            "QPushButton { background-color: #8E44AD; color: white; "
            "font-size: 20px; font-weight: bold; border-radius: 10px; }"
            "QPushButton:hover { background-color: #7D3C98; }"
            "QPushButton:pressed { background-color: #6C3483; }"
        )
        self._identify_btn.clicked.connect(self._on_identify_clicked)
        left_layout.addWidget(self._identify_btn)

        # Auto-identify toggle
        self._auto_chk = QCheckBox("Auto-Identify (continuous)")
        self._auto_chk.toggled.connect(self._on_auto_identify_toggled)
        left_layout.addWidget(self._auto_chk)

        left_layout.addStretch()
        splitter.addWidget(left_widget)

        # -- Right: results table --
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 8, 8, 8)

        right_layout.addWidget(QLabel("Identification Results"))

        self._results_table = QTableWidget()
        self._results_table.setColumnCount(len(RESULT_COLUMNS))
        self._results_table.setHorizontalHeaderLabels(RESULT_COLUMNS)
        self._results_table.horizontalHeader().setStretchLastSection(True)
        self._results_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._results_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._results_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._results_table.setAlternatingRowColors(True)
        right_layout.addWidget(self._results_table)

        # Score visualization area
        score_group = QGroupBox("Score Distribution")
        self._score_layout = QVBoxLayout()
        self._score_placeholder = QLabel("Run identification to see scores")
        self._score_placeholder.setStyleSheet(
            "color: #7F8C8D; padding: 12px;"
        )
        self._score_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._score_layout.addWidget(self._score_placeholder)
        score_group.setLayout(self._score_layout)
        right_layout.addWidget(score_group)

        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_identify_clicked(self) -> None:
        self._identify_btn.setEnabled(False)
        self._identify_btn.setText("Identifying...")
        self._identify_start_time = time.monotonic()
        self.identify_requested.emit()

    def start_identification(self) -> None:
        """Programmatic trigger (from toolbar)."""
        self._on_identify_clicked()

    def _on_auto_identify_toggled(self, checked: bool) -> None:
        self._auto_identify_active = checked
        if checked:
            self._auto_timer.start()
        else:
            self._auto_timer.stop()
        self.auto_identify_toggled.emit(checked)

    def _on_auto_identify_tick(self) -> None:
        if self._auto_identify_active and self._identify_btn.isEnabled():
            self._on_identify_clicked()

    # ------------------------------------------------------------------
    # Slots -- called externally
    # ------------------------------------------------------------------

    @pyqtSlot(bytes, int, int)
    def on_probe_image(
        self, image_data: bytes, width: int, height: int
    ) -> None:
        """Display the probe fingerprint image."""
        if not image_data:
            return

        qimg = QImage(
            image_data, width, height, width,
            QImage.Format.Format_Grayscale8,
        )
        pixmap = QPixmap.fromImage(qimg).scaled(
            PROBE_DISPLAY_SIZE, PROBE_DISPLAY_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._probe_label.setPixmap(pixmap)
        self._probe_label.setStyleSheet(
            "background-color: #1B2631; border: 2px solid #2980B9; "
            "border-radius: 8px;"
        )

    @pyqtSlot(list)
    def on_identify_results(self, results: list) -> None:
        """Display identification results.

        Parameters
        ----------
        results:
            List of IdentifyResult (or dicts with same keys).
        """
        elapsed = (time.monotonic() - self._identify_start_time) * 1000
        self._last_latency_ms = elapsed
        self._latency_label.setText(f"Latency: {elapsed:.0f} ms")

        self._identify_btn.setEnabled(True)
        self._identify_btn.setText("IDENTIFY")

        self._results_table.setRowCount(0)

        has_match = False

        for entry in results[:MAX_RESULT_ROWS]:
            if isinstance(entry, IdentifyResult):
                result = entry
            else:
                result = IdentifyResult(
                    rank=entry.get("rank", 0),
                    user_name=entry.get("user_name", ""),
                    employee_id=entry.get("employee_id", ""),
                    department=entry.get("department", ""),
                    score=entry.get("score", 0.0),
                    is_match=entry.get("is_match", False),
                )

            row = self._results_table.rowCount()
            self._results_table.insertRow(row)

            self._results_table.setItem(
                row, 0, QTableWidgetItem(str(result.rank))
            )
            self._results_table.setItem(
                row, 1, QTableWidgetItem(result.user_name)
            )
            self._results_table.setItem(
                row, 2, QTableWidgetItem(result.employee_id)
            )
            self._results_table.setItem(
                row, 3, QTableWidgetItem(result.department)
            )
            self._results_table.setItem(
                row, 4, QTableWidgetItem(f"{result.score:.4f}")
            )

            match_text = "YES" if result.is_match else "NO"
            match_item = QTableWidgetItem(match_text)
            match_color = QColor(COLOR_MATCH) if result.is_match else QColor(COLOR_NO_MATCH)
            match_item.setForeground(match_color)
            font = QFont()
            font.setBold(True)
            match_item.setFont(font)
            self._results_table.setItem(row, 5, match_item)

            if result.is_match:
                has_match = True

        # Update match indicator
        if not results:
            self._match_indicator.setText("NO MATCH")
            self._match_indicator.setStyleSheet(
                f"font-size: 24px; font-weight: bold; color: {COLOR_NO_MATCH}; "
                "padding: 8px;"
            )
        elif has_match:
            top = results[0]
            name = top.user_name if isinstance(top, IdentifyResult) else top.get("user_name", "")
            self._match_indicator.setText(f"MATCH: {name}")
            self._match_indicator.setStyleSheet(
                f"font-size: 24px; font-weight: bold; color: {COLOR_MATCH}; "
                "padding: 8px;"
            )
        else:
            self._match_indicator.setText("NO MATCH")
            self._match_indicator.setStyleSheet(
                f"font-size: 24px; font-weight: bold; color: {COLOR_NO_MATCH}; "
                "padding: 8px;"
            )

        # Update score bars
        self._update_score_bars(results)

    def _update_score_bars(self, results: list) -> None:
        """Rebuild score bar visualization."""
        # Clear existing
        while self._score_layout.count():
            item = self._score_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not results:
            placeholder = QLabel("No results")
            placeholder.setStyleSheet("color: #7F8C8D; padding: 12px;")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._score_layout.addWidget(placeholder)
            return

        for entry in results[:10]:
            if isinstance(entry, IdentifyResult):
                score = entry.score
                name = entry.user_name
            else:
                score = entry.get("score", 0.0)
                name = entry.get("user_name", "")

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(2, 1, 2, 1)

            name_lbl = QLabel(name)
            name_lbl.setFixedWidth(120)
            name_lbl.setStyleSheet("font-size: 12px; color: #2C3E50;")
            row_layout.addWidget(name_lbl)

            bar = _ScoreBar(score, self._threshold)
            row_layout.addWidget(bar)

            self._score_layout.addWidget(row_widget)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def set_threshold(self, threshold: float) -> None:
        """Update the identification threshold."""
        self._threshold = max(0.0, min(1.0, threshold))

    def clear_results(self) -> None:
        """Reset the results display."""
        self._results_table.setRowCount(0)
        self._probe_label.clear()
        self._probe_label.setText("No probe")
        self._match_indicator.setText("--")
        self._match_indicator.setStyleSheet(
            "font-size: 24px; font-weight: bold; color: #7F8C8D; padding: 8px;"
        )
        self._latency_label.setText("Latency: -- ms")
