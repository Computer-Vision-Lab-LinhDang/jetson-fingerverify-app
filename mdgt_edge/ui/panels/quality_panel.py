"""Quality Assessment Panel - NFIQ2 score and per-finger quality display."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QProgressBar, QFrame, QGridLayout,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QRect
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush


# ---------------------------------------------------------------------------
# Quality state constants (match IBScanUltimate IBSU_FingerQualityState)
# ---------------------------------------------------------------------------
QUALITY_NOT_PRESENT = 0
QUALITY_GOOD = 1
QUALITY_FAIR = 2
QUALITY_POOR = 3
QUALITY_INVALID_AREA_TOP = 4
QUALITY_INVALID_AREA_BOTTOM = 5
QUALITY_INVALID_AREA_LEFT = 6
QUALITY_INVALID_AREA_RIGHT = 7


class QualityIndicator(QWidget):
    """Custom widget showing a single finger's quality as colored circle + label."""

    _STATE_COLORS: dict[int, tuple[str, str]] = {
        QUALITY_NOT_PRESENT:       ("#45475a", "—"),
        QUALITY_GOOD:              ("#a6e3a1", "Good"),
        QUALITY_FAIR:              ("#fab387", "Fair"),
        QUALITY_POOR:              ("#f38ba8", "Poor"),
        QUALITY_INVALID_AREA_TOP:    ("#f9e2af", "Inv↑"),
        QUALITY_INVALID_AREA_BOTTOM: ("#f9e2af", "Inv↓"),
        QUALITY_INVALID_AREA_LEFT:   ("#f9e2af", "Inv←"),
        QUALITY_INVALID_AREA_RIGHT:  ("#f9e2af", "Inv→"),
    }

    def __init__(self, finger_name: str = "F1", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(52, 72)
        self._quality: int = QUALITY_NOT_PRESENT
        self._finger_name: str = finger_name

    def set_quality(self, quality_state: int) -> None:
        """Update quality state and repaint."""
        self._quality = quality_state
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        hex_color, _ = self._STATE_COLORS.get(self._quality, ("#45475a", "—"))
        circle_color = QColor(hex_color)

        # Draw circle
        radius = 18
        cx = self.width() // 2
        cy = radius + 6
        painter.setPen(QPen(QColor("#585b70"), 1))
        painter.setBrush(QBrush(circle_color))
        painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

        # Finger name above circle center
        name_font = QFont()
        name_font.setPointSize(8)
        name_font.setBold(True)
        painter.setFont(name_font)
        painter.setPen(QPen(QColor("#1e1e2e")))
        painter.drawText(QRect(0, cy - radius, self.width(), radius * 2),
                         Qt.AlignCenter, self._finger_name)

        # State label below circle
        _, state_text = self._STATE_COLORS.get(self._quality, ("#45475a", "—"))
        label_font = QFont()
        label_font.setPointSize(7)
        painter.setFont(label_font)
        painter.setPen(QPen(QColor("#a6adc8")))
        painter.drawText(QRect(0, cy + radius + 2, self.width(), 16),
                         Qt.AlignCenter, state_text)

        painter.end()


class NfiqBar(QProgressBar):
    """NFIQ2 score bar with dynamic color coding."""

    _THRESHOLDS = [
        (20,  "#f38ba8"),   # Poor       0-20
        (40,  "#fab387"),   # Fair      21-40
        (60,  "#f9e2af"),   # Adequate  41-60
        (80,  "#a6e3a1"),   # Good      61-80
        (100, "#a6e3a1"),   # Excellent 81-100
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setRange(0, 100)
        self.setValue(0)
        self.setMinimumHeight(24)
        self.setFormat("%v / 100")
        self._apply_color(0)

    def set_score(self, score: int) -> None:
        """Set NFIQ2 score (0–100) and update bar color."""
        clamped = max(0, min(100, score))
        self.setValue(clamped)
        self._apply_color(clamped)

    def _apply_color(self, score: int) -> None:
        for threshold, color in self._THRESHOLDS:
            if score <= threshold:
                self.setStyleSheet(
                    f"QProgressBar::chunk {{ background-color: {color}; border-radius: 3px; }}"
                )
                break


class QualityPanel(QDockWidget):
    """NFIQ2 quality score and per-finger quality assessment display.

    Sections:
    1. NFIQ2 Score: Large progress bar (0-100) with color coding
    2. Per-Finger Quality: Grid of QualityIndicator widgets (up to 4 fingers)
    3. Finger Count: "X/Y fingers detected"
    4. Image Quality Metrics: StdDev, Contrast, Sharpness
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Quality Assessment", parent)
        self.setObjectName("QualityPanel")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setMinimumWidth(240)

        self._finger_count: int = 0
        self._finger_max: int = 1

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        layout.addWidget(self._build_nfiq2_section())
        layout.addWidget(self._build_finger_quality_section())
        layout.addWidget(self._build_finger_count_section())
        layout.addWidget(self._build_metrics_section())
        layout.addStretch()

        self.setWidget(root)

    def _build_nfiq2_section(self) -> QGroupBox:
        box = QGroupBox("NFIQ2 Score")
        box.setCheckable(True)
        box.setChecked(True)
        layout = QVBoxLayout(box)

        self._nfiq_bar = NfiqBar()
        layout.addWidget(self._nfiq_bar)

        self._lbl_nfiq_rating = QLabel("No sample")
        self._lbl_nfiq_rating.setAlignment(Qt.AlignCenter)
        self._lbl_nfiq_rating.setStyleSheet("color: #a6adc8; font-size: 11px;")
        layout.addWidget(self._lbl_nfiq_rating)

        return box

    def _build_finger_quality_section(self) -> QGroupBox:
        box = QGroupBox("Finger Quality")
        box.setCheckable(True)
        box.setChecked(True)
        layout = QGridLayout(box)
        layout.setSpacing(4)

        finger_labels = ["Index L", "Middle L", "Index R", "Middle R"]
        self._quality_indicators: list[QualityIndicator] = []

        for i, name in enumerate(finger_labels):
            row, col = divmod(i, 2)
            indicator = QualityIndicator(finger_name=f"F{i + 1}", parent=box)
            indicator.setToolTip(name)
            self._quality_indicators.append(indicator)
            layout.addWidget(indicator, row, col, Qt.AlignCenter)

        return box

    def _build_finger_count_section(self) -> QGroupBox:
        box = QGroupBox("Finger Count")
        box.setCheckable(True)
        box.setChecked(True)
        layout = QHBoxLayout(box)

        self._lbl_finger_count = QLabel("0 / 1 fingers detected")
        self._lbl_finger_count.setAlignment(Qt.AlignCenter)
        count_font = QFont()
        count_font.setPointSize(11)
        count_font.setBold(True)
        self._lbl_finger_count.setFont(count_font)
        layout.addWidget(self._lbl_finger_count)

        return box

    def _build_metrics_section(self) -> QGroupBox:
        box = QGroupBox("Image Metrics")
        box.setCheckable(True)
        box.setChecked(True)
        layout = QGridLayout(box)
        layout.setSpacing(4)

        metrics = [
            ("StdDev",    "_lbl_stddev"),
            ("Contrast",  "_lbl_contrast"),
            ("Sharpness", "_lbl_sharpness"),
        ]

        for row, (label, attr) in enumerate(metrics):
            lbl_key = QLabel(f"{label}:")
            lbl_key.setStyleSheet("color: #a6adc8; font-size: 11px;")
            lbl_val = QLabel("—")
            lbl_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl_val.setStyleSheet("color: #cdd6f4; font-size: 11px;")
            setattr(self, attr, lbl_val)
            layout.addWidget(lbl_key, row, 0)
            layout.addWidget(lbl_val, row, 1)

        return box

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @pyqtSlot(int)
    def update_nfiq2(self, score: int) -> None:
        """Update NFIQ2 score display (0–100)."""
        self._nfiq_bar.set_score(score)
        if score <= 20:
            rating = "Poor"
            color = "#f38ba8"
        elif score <= 40:
            rating = "Fair"
            color = "#fab387"
        elif score <= 60:
            rating = "Adequate"
            color = "#f9e2af"
        elif score <= 80:
            rating = "Good"
            color = "#a6e3a1"
        else:
            rating = "Excellent"
            color = "#a6e3a1"
        self._lbl_nfiq_rating.setText(f"{rating} ({score})")
        self._lbl_nfiq_rating.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold;")

    @pyqtSlot(list)
    def update_finger_qualities(self, qualities: list[int]) -> None:
        """Update per-finger quality indicators.

        Args:
            qualities: list of quality states (up to 4), using QUALITY_* constants.
        """
        for i, indicator in enumerate(self._quality_indicators):
            state = qualities[i] if i < len(qualities) else QUALITY_NOT_PRESENT
            indicator.set_quality(state)

    @pyqtSlot(int, int)
    def update_finger_count(self, detected: int, expected: int) -> None:
        """Update finger count label."""
        self._finger_count = detected
        self._finger_max = expected
        word = "finger" if expected == 1 else "fingers"
        self._lbl_finger_count.setText(f"{detected} / {expected} {word} detected")
        color = "#a6e3a1" if detected == expected else "#f9e2af"
        self._lbl_finger_count.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: bold;"
        )

    @pyqtSlot(float, float, float)
    def update_metrics(self, stddev: float, contrast: float, sharpness: float) -> None:
        """Update image quality metrics."""
        self._lbl_stddev.setText(f"{stddev:.2f}")
        self._lbl_contrast.setText(f"{contrast:.2f}")
        self._lbl_sharpness.setText(f"{sharpness:.2f}")

    def reset(self) -> None:
        """Reset all quality displays to idle state."""
        self._nfiq_bar.set_score(0)
        self._lbl_nfiq_rating.setText("No sample")
        self._lbl_nfiq_rating.setStyleSheet("color: #a6adc8; font-size: 11px;")
        for indicator in self._quality_indicators:
            indicator.set_quality(QUALITY_NOT_PRESENT)
        self._lbl_finger_count.setText("0 / 1 fingers detected")
        self._lbl_finger_count.setStyleSheet("color: #a6adc8; font-size: 11px;")
        self._lbl_stddev.setText("—")
        self._lbl_contrast.setText("—")
        self._lbl_sharpness.setText("—")
