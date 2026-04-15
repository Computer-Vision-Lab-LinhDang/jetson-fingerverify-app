"""Splash screen widget displayed during application startup.

Shows the app title, subtitle, a progress bar, status message, and version
label on a dark-themed frameless window centered on screen.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from mdgt_edge.ui.qt_compat import (
    QApplication,
    QFont,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
    Qt,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SPLASH_WIDTH = 500
SPLASH_HEIGHT = 350

BG_COLOR = "#1B2631"
TEXT_COLOR = "#ECF0F1"
SUBTITLE_COLOR = "#7F8C8D"
ACCENT_COLOR = "#27AE60"
VERSION_COLOR = "#5D6D7E"

APP_TITLE = "MDGT Edge"
APP_SUBTITLE = "Fingerprint Verification System"
APP_VERSION = "v1.0"
INITIAL_STATUS = "Initializing..."


# ---------------------------------------------------------------------------
# State dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SplashState:
    """Immutable snapshot of splash screen progress state."""

    percent: int
    message: str


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class SplashScreen(QWidget):
    """Frameless startup splash screen with progress tracking.

    Parameters
    ----------
    parent:
        Optional parent widget (normally ``None`` for a top-level window).

    Usage
    -----
    ::

        splash = SplashScreen()
        splash.show()
        # ... during loading ...
        splash.update_progress(50, "Loading model...")
        splash.update_progress(100, "Ready.")
        splash.finish()
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._state = SplashState(percent=0, message=INITIAL_STATUS)
        self._init_window()
        self._init_ui()
        self._center_on_screen()

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _init_window(self) -> None:
        """Apply frameless, always-on-top window flags and fixed size."""
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setFixedSize(SPLASH_WIDTH, SPLASH_HEIGHT)
        self.setStyleSheet(f"background-color: {BG_COLOR};")

    def _init_ui(self) -> None:
        """Build the splash layout: title, subtitle, progress bar, labels."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(40, 40, 40, 24)
        root_layout.setSpacing(0)

        # -- App title --
        self._title_label = QLabel(APP_TITLE)
        title_font = QFont()
        title_font.setPointSize(24)
        title_font.setBold(True)
        self._title_label.setFont(title_font)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setStyleSheet(f"color: {TEXT_COLOR};")
        root_layout.addWidget(self._title_label)

        root_layout.addSpacing(8)

        # -- Subtitle --
        self._subtitle_label = QLabel(APP_SUBTITLE)
        subtitle_font = QFont()
        subtitle_font.setPointSize(14)
        self._subtitle_label.setFont(subtitle_font)
        self._subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle_label.setStyleSheet(f"color: {SUBTITLE_COLOR};")
        root_layout.addWidget(self._subtitle_label)

        # -- Spacer --
        root_layout.addStretch(1)

        # -- Progress bar --
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setStyleSheet(
            "QProgressBar {"
            f"    background-color: #2C3E50;"
            f"    border: none;"
            f"    border-radius: 4px;"
            "}"
            "QProgressBar::chunk {"
            f"    background-color: {ACCENT_COLOR};"
            f"    border-radius: 4px;"
            "}"
        )
        root_layout.addWidget(self._progress_bar)

        root_layout.addSpacing(10)

        # -- Status message --
        self._status_label = QLabel(INITIAL_STATUS)
        status_font = QFont()
        status_font.setPointSize(12)
        self._status_label.setFont(status_font)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(f"color: {TEXT_COLOR};")
        root_layout.addWidget(self._status_label)

        root_layout.addSpacing(16)

        # -- Version label --
        self._version_label = QLabel(APP_VERSION)
        version_font = QFont()
        version_font.setPointSize(9)
        self._version_label.setFont(version_font)
        self._version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._version_label.setStyleSheet(f"color: {VERSION_COLOR};")
        root_layout.addWidget(self._version_label)

    def _center_on_screen(self) -> None:
        """Move the window to the center of the primary screen."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        x = geometry.x() + (geometry.width() - SPLASH_WIDTH) // 2
        y = geometry.y() + (geometry.height() - SPLASH_HEIGHT) // 2
        self.move(x, y)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_progress(self, percent: int, message: str) -> None:
        """Update the progress bar value and status message.

        Parameters
        ----------
        percent:
            Completion percentage in the range 0–100.
        message:
            Short human-readable status string displayed below the bar.
        """
        clamped = max(0, min(100, percent))
        self._state = SplashState(percent=clamped, message=message)
        self._progress_bar.setValue(clamped)
        self._status_label.setText(message)
        logger.debug("Splash progress: %d%% — %s", clamped, message)

    def finish(self) -> None:
        """Close and destroy the splash screen."""
        logger.debug("Splash screen finished")
        self.close()
