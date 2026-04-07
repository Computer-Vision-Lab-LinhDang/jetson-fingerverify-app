"""Spoof/PAD Detection Panel."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton, QRadioButton,
    QButtonGroup, QFrame, QGridLayout, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QFont, QColor, QPalette


# ---------------------------------------------------------------------------
# PAD result constants
# ---------------------------------------------------------------------------
PAD_UNKNOWN = 0
PAD_LIVE = 1
PAD_FAKE = 2


class ResultDisplay(QFrame):
    """Large status display for LIVE / FAKE DETECTED / UNKNOWN result."""

    _STATE_STYLES: dict[int, tuple[str, str, str]] = {
        PAD_UNKNOWN: ("#313244", "#a6adc8", "AWAITING SCAN"),
        PAD_LIVE:    ("#1a4731", "#a6e3a1", "LIVE"),
        PAD_FAKE:    ("#4a1a1a", "#f38ba8", "FAKE DETECTED"),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.setFrameShape(QFrame.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        self._lbl = QLabel("AWAITING SCAN")
        self._lbl.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        self._lbl.setFont(font)
        layout.addWidget(self._lbl)

        self._state: int = PAD_UNKNOWN
        self._blink_visible: bool = True
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._on_blink)

        self._apply_state(PAD_UNKNOWN)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply_state(self, state: int) -> None:
        bg, fg, text = self._STATE_STYLES.get(state, self._STATE_STYLES[PAD_UNKNOWN])
        self.setStyleSheet(
            f"ResultDisplay {{ background-color: {bg}; border-radius: 6px; border: 1px solid #45475a; }}"
        )
        self._lbl.setStyleSheet(f"color: {fg};")
        self._lbl.setText(text)
        self._fg_color = fg

    @pyqtSlot()
    def _on_blink(self) -> None:
        self._blink_visible = not self._blink_visible
        color = self._fg_color if self._blink_visible else "#4a1a1a"
        self._lbl.setStyleSheet(f"color: {color};")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_result(self, state: int) -> None:
        self._blink_timer.stop()
        self._state = state
        self._apply_state(state)
        if state == PAD_FAKE:
            self._blink_visible = True
            self._blink_timer.start()

    def reset(self) -> None:
        self._blink_timer.stop()
        self._state = PAD_UNKNOWN
        self._apply_state(PAD_UNKNOWN)


class SpoofPanel(QDockWidget):
    """PAD (Presentation Attack Detection) control and result display.

    Sections:
    1. PAD Enable/Disable toggle
    2. Sensitivity Level: 5 radio buttons (1=Lenient … 5=Strict), default=3
    3. Detection Result: Large LIVE / FAKE status display
    4. Statistics: Total scans, spoof count, live rate
    """

    # Signals
    spoof_enabled_changed = pyqtSignal(bool)
    spoof_level_changed = pyqtSignal(int)   # 1-5

    _LEVEL_DESCRIPTIONS: dict[int, str] = {
        1: "Very Lenient — Minimal false rejections",
        2: "Lenient — Fewer false rejections",
        3: "Balanced — Recommended default",
        4: "Strict — Fewer false accepts",
        5: "Very Strict — Maximum security",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("PAD / Spoof Detection", parent)
        self.setObjectName("SpoofPanel")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setMinimumWidth(240)

        self._pad_enabled: bool = False
        self._pad_level: int = 3
        self._total_scans: int = 0
        self._spoof_count: int = 0

        self._build_ui()
        self._connect_internal()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        layout.addWidget(self._build_toggle_section())
        layout.addWidget(self._build_sensitivity_section())
        layout.addWidget(self._build_result_section())
        layout.addWidget(self._build_stats_section())
        layout.addStretch()

        self.setWidget(root)

    def _build_toggle_section(self) -> QGroupBox:
        box = QGroupBox("PAD Status")
        layout = QHBoxLayout(box)

        self._btn_enable = QPushButton("Enable PAD")
        self._btn_enable.setProperty("cssClass", "primary")
        self._btn_enable.setMinimumHeight(36)
        self._btn_enable.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._btn_disable = QPushButton("Disable PAD")
        self._btn_disable.setProperty("cssClass", "danger")
        self._btn_disable.setMinimumHeight(36)
        self._btn_disable.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_disable.setEnabled(False)

        layout.addWidget(self._btn_enable)
        layout.addWidget(self._btn_disable)
        return box

    def _build_sensitivity_section(self) -> QGroupBox:
        box = QGroupBox("Sensitivity Level")
        box.setCheckable(True)
        box.setChecked(True)
        layout = QVBoxLayout(box)
        layout.setSpacing(4)

        radio_row = QHBoxLayout()
        self._level_group = QButtonGroup(box)

        for level in range(1, 6):
            radio = QRadioButton(str(level))
            if level == 3:
                radio.setChecked(True)
            self._level_group.addButton(radio, level)
            radio_row.addWidget(radio)

        layout.addLayout(radio_row)

        self._lbl_level_desc = QLabel(self._LEVEL_DESCRIPTIONS[3])
        self._lbl_level_desc.setWordWrap(True)
        self._lbl_level_desc.setStyleSheet("color: #a6adc8; font-size: 10px;")
        layout.addWidget(self._lbl_level_desc)

        return box

    def _build_result_section(self) -> QGroupBox:
        box = QGroupBox("Detection Result")
        layout = QVBoxLayout(box)
        layout.setSpacing(4)

        self._result_display = ResultDisplay()
        layout.addWidget(self._result_display)

        # Per-finger result labels (up to 4)
        self._finger_result_labels: list[QLabel] = []
        finger_grid = QGridLayout()
        finger_grid.setSpacing(3)

        for i in range(4):
            lbl = QLabel(f"F{i + 1}: —")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #a6adc8; font-size: 10px; border: 1px solid #45475a; border-radius: 3px; padding: 2px;")
            lbl.setVisible(False)
            self._finger_result_labels.append(lbl)
            finger_grid.addWidget(lbl, 0, i)

        layout.addLayout(finger_grid)
        return box

    def _build_stats_section(self) -> QGroupBox:
        box = QGroupBox("Statistics")
        box.setCheckable(True)
        box.setChecked(True)
        layout = QGridLayout(box)
        layout.setSpacing(4)

        stats_defs = [
            ("Total Scans:",   "_lbl_total"),
            ("Spoof Detected:", "_lbl_spoof"),
            ("Live Rate:",      "_lbl_live_rate"),
        ]

        for row, (key, attr) in enumerate(stats_defs):
            lbl_key = QLabel(key)
            lbl_key.setStyleSheet("color: #a6adc8; font-size: 11px;")
            lbl_val = QLabel("0")
            lbl_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl_val.setStyleSheet("color: #cdd6f4; font-size: 11px;")
            setattr(self, attr, lbl_val)
            layout.addWidget(lbl_key, row, 0)
            layout.addWidget(lbl_val, row, 1)

        self._btn_reset_stats = QPushButton("Reset Stats")
        self._btn_reset_stats.setFixedHeight(24)
        self._btn_reset_stats.clicked.connect(self._reset_stats)
        layout.addWidget(self._btn_reset_stats, len(stats_defs), 0, 1, 2)

        return box

    # ------------------------------------------------------------------
    # Internal connections
    # ------------------------------------------------------------------

    def _connect_internal(self) -> None:
        self._btn_enable.clicked.connect(self._on_enable_clicked)
        self._btn_disable.clicked.connect(self._on_disable_clicked)
        self._level_group.buttonClicked.connect(self._on_level_changed)

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_enable_clicked(self) -> None:
        self._pad_enabled = True
        self._btn_enable.setEnabled(False)
        self._btn_disable.setEnabled(True)
        self.spoof_enabled_changed.emit(True)

    @pyqtSlot()
    def _on_disable_clicked(self) -> None:
        self._pad_enabled = False
        self._btn_enable.setEnabled(True)
        self._btn_disable.setEnabled(False)
        self._result_display.reset()
        self.spoof_enabled_changed.emit(False)

    @pyqtSlot()
    def _on_level_changed(self) -> None:
        level = self._level_group.checkedId()
        self._pad_level = level
        self._lbl_level_desc.setText(self._LEVEL_DESCRIPTIONS.get(level, ""))
        self.spoof_level_changed.emit(level)

    @pyqtSlot()
    def _reset_stats(self) -> None:
        self._total_scans = 0
        self._spoof_count = 0
        self._refresh_stats()

    def _refresh_stats(self) -> None:
        self._lbl_total.setText(str(self._total_scans))
        self._lbl_spoof.setText(str(self._spoof_count))
        if self._total_scans > 0:
            live = self._total_scans - self._spoof_count
            rate = live / self._total_scans * 100.0
            self._lbl_live_rate.setText(f"{rate:.1f}%")
        else:
            self._lbl_live_rate.setText("—")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @pyqtSlot(int)
    def update_result(self, result: int) -> None:
        """Update overall PAD result.

        Args:
            result: PAD_UNKNOWN (0), PAD_LIVE (1), or PAD_FAKE (2)
        """
        self._result_display.set_result(result)
        self._total_scans += 1
        if result == PAD_FAKE:
            self._spoof_count += 1
        self._refresh_stats()

    @pyqtSlot(list)
    def update_finger_results(self, results: list[int]) -> None:
        """Update per-finger PAD results.

        Args:
            results: list of PAD_* values per finger (up to 4)
        """
        labels = {PAD_UNKNOWN: "—", PAD_LIVE: "LIVE", PAD_FAKE: "FAKE"}
        colors = {PAD_UNKNOWN: "#a6adc8", PAD_LIVE: "#a6e3a1", PAD_FAKE: "#f38ba8"}

        for i, lbl in enumerate(self._finger_result_labels):
            if i < len(results):
                state = results[i]
                lbl.setText(f"F{i + 1}: {labels.get(state, '—')}")
                lbl.setStyleSheet(
                    f"color: {colors.get(state, '#a6adc8')}; font-size: 10px; "
                    f"border: 1px solid #45475a; border-radius: 3px; padding: 2px;"
                )
                lbl.setVisible(True)
            else:
                lbl.setVisible(False)

    def reset(self) -> None:
        """Reset detection result display."""
        self._result_display.reset()
        for lbl in self._finger_result_labels:
            lbl.setVisible(False)

    @property
    def is_enabled(self) -> bool:
        return self._pad_enabled

    @property
    def level(self) -> int:
        return self._pad_level
