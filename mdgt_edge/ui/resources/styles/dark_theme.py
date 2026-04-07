"""Dark theme QSS stylesheet for MDGT Edge application.

Uses Catppuccin Mocha palette for a modern, eye-friendly dark UI.
"""

DARK_THEME_QSS = """
/* ===== Main Window ===== */
QMainWindow {
    background-color: #1e1e2e;
    color: #cdd6f4;
}

/* ===== Tab Widget ===== */
QTabWidget::pane {
    border: 1px solid #45475a;
    background-color: #1e1e2e;
    border-radius: 4px;
}
QTabBar::tab {
    background-color: #313244;
    color: #cdd6f4;
    padding: 8px 20px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    min-width: 100px;
}
QTabBar::tab:selected {
    background-color: #45475a;
    color: #cdd6f4;
    border-bottom: 2px solid #89b4fa;
}
QTabBar::tab:hover:!selected {
    background-color: #585b70;
}

/* ===== Buttons ===== */
QPushButton {
    background-color: #45475a;
    color: #cdd6f4;
    border: 1px solid #585b70;
    padding: 6px 16px;
    border-radius: 4px;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #585b70;
    border-color: #6c7086;
}
QPushButton:pressed {
    background-color: #313244;
}
QPushButton:disabled {
    background-color: #313244;
    color: #6c7086;
    border-color: #45475a;
}
QPushButton[cssClass="primary"] {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    font-weight: bold;
    padding: 8px 24px;
}
QPushButton[cssClass="primary"]:hover {
    background-color: #74c7ec;
}
QPushButton[cssClass="primary"]:pressed {
    background-color: #89dceb;
}
QPushButton[cssClass="danger"] {
    background-color: #f38ba8;
    color: #1e1e2e;
    border: none;
    font-weight: bold;
}
QPushButton[cssClass="danger"]:hover {
    background-color: #eba0ac;
}
QPushButton[cssClass="success"] {
    background-color: #a6e3a1;
    color: #1e1e2e;
    border: none;
    font-weight: bold;
}
QPushButton[cssClass="success"]:hover {
    background-color: #94e2d5;
}
QPushButton[cssClass="warning"] {
    background-color: #f9e2af;
    color: #1e1e2e;
    border: none;
    font-weight: bold;
}
QPushButton[cssClass="capture"] {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    font-size: 16px;
    font-weight: bold;
    padding: 12px 32px;
    border-radius: 8px;
    min-height: 48px;
}
QPushButton[cssClass="capture"]:hover {
    background-color: #74c7ec;
}

/* ===== Group Boxes ===== */
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 14px;
    padding: 12px 8px 8px 8px;
    font-weight: bold;
    color: #cdd6f4;
    font-size: 13px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #b4befe;
}

/* ===== Dock Widgets ===== */
QDockWidget {
    color: #cdd6f4;
    font-weight: bold;
}
QDockWidget::title {
    background-color: #313244;
    padding: 6px 8px;
    border-bottom: 1px solid #45475a;
    text-align: left;
}
QDockWidget::close-button, QDockWidget::float-button {
    background: transparent;
    border: none;
    padding: 2px;
}

/* ===== Tables ===== */
QTableWidget, QTableView {
    background-color: #1e1e2e;
    alternate-background-color: #181825;
    gridline-color: #313244;
    color: #cdd6f4;
    selection-background-color: #45475a;
    selection-color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
}
QHeaderView::section {
    background-color: #313244;
    color: #b4befe;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid #45475a;
    border-bottom: 1px solid #45475a;
    font-weight: bold;
    font-size: 12px;
}

/* ===== Inputs ===== */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    padding: 5px 10px;
    border-radius: 4px;
    font-size: 13px;
    min-height: 24px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #89b4fa;
}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
    background-color: #181825;
    color: #6c7086;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #313244;
    color: #cdd6f4;
    selection-background-color: #45475a;
    border: 1px solid #585b70;
}

/* ===== Progress Bars ===== */
QProgressBar {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    text-align: center;
    color: #cdd6f4;
    font-size: 12px;
    min-height: 20px;
}
QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 3px;
}
QProgressBar[cssClass="quality-excellent"]::chunk { background-color: #a6e3a1; }
QProgressBar[cssClass="quality-good"]::chunk { background-color: #a6e3a1; }
QProgressBar[cssClass="quality-adequate"]::chunk { background-color: #f9e2af; }
QProgressBar[cssClass="quality-fair"]::chunk { background-color: #fab387; }
QProgressBar[cssClass="quality-poor"]::chunk { background-color: #f38ba8; }

/* ===== Sliders ===== */
QSlider::groove:horizontal {
    background-color: #45475a;
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background-color: #89b4fa;
    width: 18px;
    height: 18px;
    margin: -6px 0;
    border-radius: 9px;
}
QSlider::handle:horizontal:hover {
    background-color: #74c7ec;
}

/* ===== Radio Buttons & Checkboxes ===== */
QRadioButton, QCheckBox {
    color: #cdd6f4;
    spacing: 8px;
    font-size: 13px;
}
QRadioButton::indicator, QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #585b70;
    border-radius: 4px;
    background-color: #313244;
}
QRadioButton::indicator {
    border-radius: 10px;
}
QRadioButton::indicator:checked, QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}

/* ===== Scroll Bars ===== */
QScrollBar:vertical {
    background-color: #1e1e2e;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 5px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background-color: #585b70;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background-color: #1e1e2e;
    height: 10px;
}
QScrollBar::handle:horizontal {
    background-color: #45475a;
    border-radius: 5px;
    min-width: 24px;
}

/* ===== Status Bar ===== */
QStatusBar {
    background-color: #181825;
    color: #a6adc8;
    font-size: 12px;
    border-top: 1px solid #313244;
}
QStatusBar::item {
    border: none;
}
QStatusBar QLabel {
    padding: 0 8px;
    color: #a6adc8;
}

/* ===== Menu Bar ===== */
QMenuBar {
    background-color: #181825;
    color: #cdd6f4;
    border-bottom: 1px solid #313244;
}
QMenuBar::item:selected {
    background-color: #45475a;
    border-radius: 4px;
}
QMenu {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    padding: 4px;
}
QMenu::item:selected {
    background-color: #45475a;
    border-radius: 2px;
}
QMenu::separator {
    height: 1px;
    background-color: #45475a;
    margin: 4px 8px;
}

/* ===== Toolbar ===== */
QToolBar {
    background-color: #181825;
    border-bottom: 1px solid #313244;
    spacing: 4px;
    padding: 2px;
}
QToolButton {
    background-color: transparent;
    color: #cdd6f4;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 8px;
}
QToolButton:hover {
    background-color: #45475a;
    border-color: #585b70;
}
QToolButton:checked {
    background-color: #45475a;
    border-color: #89b4fa;
}

/* ===== Labels ===== */
QLabel {
    color: #cdd6f4;
}
QLabel[cssClass="title"] {
    font-size: 18px;
    font-weight: bold;
    color: #cdd6f4;
}
QLabel[cssClass="subtitle"] {
    font-size: 14px;
    color: #a6adc8;
}
QLabel[cssClass="status-live"] {
    background-color: #a6e3a1;
    color: #1e1e2e;
    font-size: 18px;
    font-weight: bold;
    padding: 8px 16px;
    border-radius: 6px;
}
QLabel[cssClass="status-fake"] {
    background-color: #f38ba8;
    color: #1e1e2e;
    font-size: 18px;
    font-weight: bold;
    padding: 8px 16px;
    border-radius: 6px;
}
QLabel[cssClass="connected"] {
    color: #a6e3a1;
}
QLabel[cssClass="disconnected"] {
    color: #f38ba8;
}

/* ===== Frames ===== */
QFrame[cssClass="separator"] {
    background-color: #45475a;
    max-height: 1px;
}
QFrame[cssClass="preview"] {
    background-color: #181825;
    border: 2px solid #45475a;
    border-radius: 8px;
    min-height: 300px;
}

/* ===== Tooltips ===== */
QToolTip {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #585b70;
    padding: 6px;
    border-radius: 4px;
    font-size: 12px;
}

/* ===== Splitters ===== */
QSplitter::handle {
    background-color: #45475a;
}
QSplitter::handle:horizontal { width: 2px; }
QSplitter::handle:vertical { height: 2px; }
"""


LIGHT_THEME_QSS = """
/* ===== Light Theme (Catppuccin Latte) ===== */
QMainWindow {
    background-color: #eff1f5;
    color: #4c4f69;
}
QTabWidget::pane {
    border: 1px solid #ccd0da;
    background-color: #eff1f5;
}
QTabBar::tab {
    background-color: #e6e9ef;
    color: #4c4f69;
    padding: 8px 20px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background-color: #ccd0da;
    border-bottom: 2px solid #1e66f5;
}
QPushButton {
    background-color: #ccd0da;
    color: #4c4f69;
    border: 1px solid #bcc0cc;
    padding: 6px 16px;
    border-radius: 4px;
}
QPushButton:hover { background-color: #bcc0cc; }
QPushButton[cssClass="primary"] {
    background-color: #1e66f5;
    color: #eff1f5;
    border: none;
    font-weight: bold;
}
QPushButton[cssClass="danger"] {
    background-color: #d20f39;
    color: #eff1f5;
    border: none;
}
QPushButton[cssClass="success"] {
    background-color: #40a02b;
    color: #eff1f5;
    border: none;
}
QGroupBox {
    border: 1px solid #ccd0da;
    border-radius: 6px;
    margin-top: 14px;
    padding: 12px 8px 8px 8px;
    color: #4c4f69;
}
QGroupBox::title { color: #1e66f5; }
QDockWidget::title {
    background-color: #e6e9ef;
    border-bottom: 1px solid #ccd0da;
}
QTableWidget, QTableView {
    background-color: #eff1f5;
    alternate-background-color: #e6e9ef;
    gridline-color: #ccd0da;
    color: #4c4f69;
    selection-background-color: #ccd0da;
}
QHeaderView::section {
    background-color: #e6e9ef;
    color: #1e66f5;
    border: none;
    border-right: 1px solid #ccd0da;
    border-bottom: 1px solid #ccd0da;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #e6e9ef;
    color: #4c4f69;
    border: 1px solid #ccd0da;
    padding: 5px 10px;
    border-radius: 4px;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #1e66f5;
}
QProgressBar {
    background-color: #e6e9ef;
    border: 1px solid #ccd0da;
    border-radius: 4px;
    color: #4c4f69;
}
QProgressBar::chunk { background-color: #1e66f5; border-radius: 3px; }
QStatusBar {
    background-color: #dce0e8;
    color: #6c6f85;
    border-top: 1px solid #ccd0da;
}
QMenuBar {
    background-color: #dce0e8;
    color: #4c4f69;
}
QMenu {
    background-color: #e6e9ef;
    color: #4c4f69;
    border: 1px solid #ccd0da;
}
QMenu::item:selected { background-color: #ccd0da; }
QLabel[cssClass="status-live"] {
    background-color: #40a02b;
    color: #eff1f5;
}
QLabel[cssClass="status-fake"] {
    background-color: #d20f39;
    color: #eff1f5;
}
QRadioButton, QCheckBox { color: #4c4f69; }
QRadioButton::indicator:checked, QCheckBox::indicator:checked {
    background-color: #1e66f5;
    border-color: #1e66f5;
}
"""


class Colors:
    """Named color constants for programmatic use (Catppuccin Mocha)."""
    # Base
    BACKGROUND = "#1e1e2e"
    SURFACE = "#313244"
    OVERLAY = "#45475a"
    MUTED = "#585b70"

    # Text
    TEXT = "#cdd6f4"
    SUBTEXT = "#a6adc8"
    DIMMED = "#6c7086"

    # Accents
    BLUE = "#89b4fa"
    GREEN = "#a6e3a1"
    RED = "#f38ba8"
    YELLOW = "#f9e2af"
    ORANGE = "#fab387"
    TEAL = "#94e2d5"
    LAVENDER = "#b4befe"
    SKY = "#89dceb"
    PINK = "#f5c2e7"
    MAUVE = "#cba6f7"

    # Semantic
    QUALITY_EXCELLENT = GREEN
    QUALITY_GOOD = "#a6e3a1"
    QUALITY_ADEQUATE = YELLOW
    QUALITY_FAIR = ORANGE
    QUALITY_POOR = RED

    STATUS_CONNECTED = GREEN
    STATUS_DISCONNECTED = RED
    STATUS_LIVE = GREEN
    STATUS_FAKE = RED

    @staticmethod
    def nfiq2_color(score: int) -> str:
        """Return color hex for an NFIQ2 score (0-100)."""
        if score >= 81:
            return Colors.GREEN
        if score >= 61:
            return "#a6e3a1"
        if score >= 41:
            return Colors.YELLOW
        if score >= 21:
            return Colors.ORANGE
        return Colors.RED

    @staticmethod
    def quality_state_color(state: int) -> str:
        """Return color hex for IBSU_FingerQualityState."""
        mapping = {
            0: Colors.DIMMED,    # NOT_PRESENT
            1: Colors.GREEN,     # GOOD
            2: Colors.YELLOW,    # FAIR
            3: Colors.RED,       # POOR
        }
        return mapping.get(state, Colors.ORANGE)
