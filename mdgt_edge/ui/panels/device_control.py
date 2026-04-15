"""Device Control Panel - QDockWidget for sensor control."""
from __future__ import annotations

from mdgt_edge.ui.qt_compat import (
    QButtonGroup,
    QCheckBox,
    QColor,
    QComboBox,
    QDockWidget,
    QFont,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
    Qt,
    pyqtSignal,
    pyqtSlot,
)


class DeviceControlPanel(QDockWidget):
    """Dockable panel for IBScanUltimate device control.

    Sections:
    1. Device Info: product name, serial, firmware, connection status
    2. Capture Mode: image type selector (Flat 1/2/3/4, Roll 1/2)
    3. Resolution: 500/1000 DPI radio buttons
    4. Capture Options: Auto-Contrast, Auto-Capture, Ignore Finger Count
    5. LED Control: Color buttons + custom pattern
    6. Beep Control: Short / Long / Custom duration
    """

    # Signals
    capture_mode_changed = pyqtSignal(int, int)   # image_type, resolution
    capture_options_changed = pyqtSignal(int)      # bitflags
    led_changed = pyqtSignal(int)                  # LED mask
    beep_requested = pyqtSignal(int)               # duration_ms
    connect_requested = pyqtSignal()
    disconnect_requested = pyqtSignal()

    # Capture option bitflags
    OPT_AUTO_CONTRAST = 0x01
    OPT_AUTO_CAPTURE = 0x02
    OPT_IGNORE_FINGER_COUNT = 0x04

    # LED masks
    LED_OFF = 0x00
    LED_GREEN = 0x01
    LED_RED = 0x02
    LED_BLUE = 0x04
    LED_WHITE = 0x07

    _CAPTURE_MODES = [
        ("Flat - Single Finger",   0),
        ("Flat - Two Fingers",     1),
        ("Flat - Three Fingers",   2),
        ("Flat - Four Fingers",    3),
        ("Roll - Single Finger",   4),
        ("Roll - Two Fingers",     5),
    ]

    _LED_BUTTONS = [
        ("Green",  LED_GREEN,  "#a6e3a1", "#1e1e2e"),
        ("Red",    LED_RED,    "#f38ba8", "#1e1e2e"),
        ("Blue",   LED_BLUE,   "#89b4fa", "#1e1e2e"),
        ("White",  LED_WHITE,  "#cdd6f4", "#1e1e2e"),
        ("Off",    LED_OFF,    "#45475a", "#cdd6f4"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Device Control", parent)
        self.setObjectName("DeviceControlPanel")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setMinimumWidth(240)

        self._options_flags: int = 0
        self._resolution: int = 500

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

        layout.addWidget(self._build_device_info())
        layout.addWidget(self._build_capture_mode())
        layout.addWidget(self._build_resolution())
        layout.addWidget(self._build_capture_options())
        layout.addWidget(self._build_led_control())
        layout.addWidget(self._build_beep_control())
        layout.addStretch()

        self.setWidget(root)

    def _build_device_info(self) -> QGroupBox:
        box = QGroupBox("Device Info")
        box.setCheckable(True)
        box.setChecked(True)
        layout = QVBoxLayout(box)
        layout.setSpacing(4)

        # Status row
        status_row = QHBoxLayout()
        self._status_dot = QLabel("●")
        self._status_dot.setFixedWidth(18)
        self._status_dot.setProperty("cssClass", "dot-disconnected")
        self._status_label = QLabel("Disconnected")
        status_row.addWidget(self._status_dot)
        status_row.addWidget(self._status_label)
        status_row.addStretch()
        layout.addLayout(status_row)

        # Info labels
        self._lbl_product = QLabel("Product: —")
        self._lbl_serial = QLabel("Serial: —")
        self._lbl_firmware = QLabel("Firmware: —")
        for lbl in (self._lbl_product, self._lbl_serial, self._lbl_firmware):
            lbl.setStyleSheet("color: #a6adc8; font-size: 11px;")
            layout.addWidget(lbl)

        _sep = QFrame()
        _sep.setFrameShape(QFrame.HLine)
        _sep.setStyleSheet("color: #45475a;")
        layout.addWidget(_sep)

        # Connect / Disconnect buttons
        btn_row = QHBoxLayout()
        self._btn_connect = QPushButton("Connect")
        self._btn_connect.setProperty("cssClass", "primary")
        self._btn_disconnect = QPushButton("Disconnect")
        self._btn_disconnect.setProperty("cssClass", "danger")
        self._btn_disconnect.setEnabled(False)
        btn_row.addWidget(self._btn_connect)
        btn_row.addWidget(self._btn_disconnect)
        layout.addLayout(btn_row)

        return box

    def _build_capture_mode(self) -> QGroupBox:
        box = QGroupBox("Capture Mode")
        box.setCheckable(True)
        box.setChecked(True)
        layout = QVBoxLayout(box)

        self._combo_mode = QComboBox()
        for label, _ in self._CAPTURE_MODES:
            self._combo_mode.addItem(label)
        layout.addWidget(self._combo_mode)

        return box

    def _build_resolution(self) -> QGroupBox:
        box = QGroupBox("Resolution")
        box.setCheckable(True)
        box.setChecked(True)
        layout = QHBoxLayout(box)

        self._btn_group_res = QButtonGroup(box)
        self._radio_500 = QRadioButton("500 DPI")
        self._radio_1000 = QRadioButton("1000 DPI")
        self._radio_500.setChecked(True)
        self._btn_group_res.addButton(self._radio_500, 500)
        self._btn_group_res.addButton(self._radio_1000, 1000)
        layout.addWidget(self._radio_500)
        layout.addWidget(self._radio_1000)
        layout.addStretch()

        return box

    def _build_capture_options(self) -> QGroupBox:
        box = QGroupBox("Capture Options")
        box.setCheckable(True)
        box.setChecked(True)
        layout = QVBoxLayout(box)
        layout.setSpacing(4)

        self._chk_auto_contrast = QCheckBox("Auto-Contrast")
        self._chk_auto_capture = QCheckBox("Auto-Capture")
        self._chk_ignore_finger_count = QCheckBox("Ignore Finger Count")

        for chk in (self._chk_auto_contrast, self._chk_auto_capture, self._chk_ignore_finger_count):
            layout.addWidget(chk)

        return box

    def _build_led_control(self) -> QGroupBox:
        box = QGroupBox("LED Control")
        box.setCheckable(True)
        box.setChecked(True)
        layout = QVBoxLayout(box)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self._led_buttons: dict[int, QToolButton] = {}

        for label, mask, bg, fg in self._LED_BUTTONS:
            btn = QToolButton()
            btn.setText(label)
            btn.setFixedHeight(28)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet(
                f"QToolButton {{ background-color: {bg}; color: {fg}; "
                f"border-radius: 4px; border: 1px solid #45475a; font-size: 11px; }}"
                f"QToolButton:hover {{ opacity: 0.85; border: 1px solid #89b4fa; }}"
                f"QToolButton:pressed {{ border: 2px solid #89b4fa; }}"
            )
            btn.setProperty("led_mask", mask)
            btn.clicked.connect(lambda checked, m=mask: self.led_changed.emit(m))
            self._led_buttons[mask] = btn
            btn_row.addWidget(btn)

        layout.addLayout(btn_row)

        # Custom pattern row
        custom_row = QHBoxLayout()
        custom_row.addWidget(QLabel("Custom:"))
        self._spin_led_pattern = QSpinBox()
        self._spin_led_pattern.setRange(0, 255)
        self._spin_led_pattern.setToolTip("LED bitmask (0–255)")
        self._btn_led_custom = QPushButton("Apply")
        self._btn_led_custom.setFixedWidth(56)
        self._btn_led_custom.clicked.connect(
            lambda: self.led_changed.emit(self._spin_led_pattern.value())
        )
        custom_row.addWidget(self._spin_led_pattern)
        custom_row.addWidget(self._btn_led_custom)
        layout.addLayout(custom_row)

        return box

    def _build_beep_control(self) -> QGroupBox:
        box = QGroupBox("Beep Control")
        box.setCheckable(True)
        box.setChecked(True)
        layout = QVBoxLayout(box)

        preset_row = QHBoxLayout()
        self._btn_beep_short = QPushButton("Short")
        self._btn_beep_long = QPushButton("Long")
        self._btn_beep_short.clicked.connect(lambda: self.beep_requested.emit(100))
        self._btn_beep_long.clicked.connect(lambda: self.beep_requested.emit(500))
        preset_row.addWidget(self._btn_beep_short)
        preset_row.addWidget(self._btn_beep_long)
        layout.addLayout(preset_row)

        custom_row = QHBoxLayout()
        custom_row.addWidget(QLabel("Custom (ms):"))
        self._spin_beep_ms = QSpinBox()
        self._spin_beep_ms.setRange(50, 5000)
        self._spin_beep_ms.setValue(200)
        self._spin_beep_ms.setSingleStep(50)
        self._btn_beep_custom = QPushButton("Beep")
        self._btn_beep_custom.setFixedWidth(56)
        self._btn_beep_custom.clicked.connect(
            lambda: self.beep_requested.emit(self._spin_beep_ms.value())
        )
        custom_row.addWidget(self._spin_beep_ms)
        custom_row.addWidget(self._btn_beep_custom)
        layout.addLayout(custom_row)

        return box

    # ------------------------------------------------------------------
    # Internal signal connections
    # ------------------------------------------------------------------

    def _connect_internal(self) -> None:
        self._btn_connect.clicked.connect(self._on_connect_clicked)
        self._btn_disconnect.clicked.connect(self._on_disconnect_clicked)
        self._combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        self._btn_group_res.buttonClicked.connect(self._on_resolution_changed)

        for chk in (self._chk_auto_contrast, self._chk_auto_capture, self._chk_ignore_finger_count):
            chk.stateChanged.connect(self._on_options_changed)

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_connect_clicked(self) -> None:
        self.connect_requested.emit()

    @pyqtSlot()
    def _on_disconnect_clicked(self) -> None:
        self.disconnect_requested.emit()

    @pyqtSlot(int)
    def _on_mode_changed(self, index: int) -> None:
        _, image_type = self._CAPTURE_MODES[index]
        self.capture_mode_changed.emit(image_type, self._resolution)

    @pyqtSlot()
    def _on_resolution_changed(self) -> None:
        self._resolution = self._btn_group_res.checkedId()
        index = self._combo_mode.currentIndex()
        _, image_type = self._CAPTURE_MODES[index]
        self.capture_mode_changed.emit(image_type, self._resolution)

    @pyqtSlot(int)
    def _on_options_changed(self, _state: int) -> None:
        flags = 0
        if self._chk_auto_contrast.isChecked():
            flags |= self.OPT_AUTO_CONTRAST
        if self._chk_auto_capture.isChecked():
            flags |= self.OPT_AUTO_CAPTURE
        if self._chk_ignore_finger_count.isChecked():
            flags |= self.OPT_IGNORE_FINGER_COUNT
        self._options_flags = flags
        self.capture_options_changed.emit(flags)

    # ------------------------------------------------------------------
    # Public API (called by main window / controller)
    # ------------------------------------------------------------------

    @pyqtSlot(bool)
    def set_connected(self, connected: bool) -> None:
        """Update UI to reflect connection state."""
        if connected:
            self._status_dot.setStyleSheet("color: #a6e3a1; font-size: 14px;")
            self._status_label.setText("Connected")
            self._btn_connect.setEnabled(False)
            self._btn_disconnect.setEnabled(True)
        else:
            self._status_dot.setStyleSheet("color: #f38ba8; font-size: 14px;")
            self._status_label.setText("Disconnected")
            self._btn_connect.setEnabled(True)
            self._btn_disconnect.setEnabled(False)

    @pyqtSlot(str, str, str)
    def set_device_info(self, product: str, serial: str, firmware: str) -> None:
        """Populate device info labels."""
        self._lbl_product.setText(f"Product: {product}")
        self._lbl_serial.setText(f"Serial:  {serial}")
        self._lbl_firmware.setText(f"Firmware: {firmware}")
