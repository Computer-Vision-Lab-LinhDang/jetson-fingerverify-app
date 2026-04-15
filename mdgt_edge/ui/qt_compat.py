"""Qt compatibility helpers for PyQt6/PyQt5 deployments.

The Jetson `fingerverify` environment ships with Qt5 on conda-forge, while
developer machines may use PyQt6. Import UI symbols from this module so the
same codebase runs on both stacks.
"""
from __future__ import annotations

from types import SimpleNamespace

QT_API = "PyQt6"

try:
    from PyQt6.QtCore import (
        QElapsedTimer,
        QMutex,
        QRect,
        QSettings,
        QThread,
        QTimer,
        Qt as _Qt,
        pyqtSignal,
        pyqtSlot,
    )
    from PyQt6.QtGui import (
        QAction,
        QBrush,
        QColor,
        QFont,
        QIcon,
        QImage,
        QKeySequence,
        QPainter,
        QPalette,
        QPen,
        QPixmap,
    )
    from PyQt6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QButtonGroup,
        QCheckBox,
        QComboBox,
        QDockWidget,
        QDoubleSpinBox,
        QFileDialog,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenuBar,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QRadioButton,
        QScrollArea,
        QSizePolicy,
        QSlider,
        QSpinBox,
        QSplitter,
        QStackedWidget,
        QStatusBar,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QToolBar,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    QT_API = "PyQt5"
    from PyQt5.QtCore import (  # type: ignore[no-redef]
        QElapsedTimer,
        QMutex,
        QRect,
        QSettings,
        QThread,
        QTimer,
        Qt as _Qt,
        pyqtSignal,
        pyqtSlot,
    )
    from PyQt5.QtGui import (  # type: ignore[no-redef]
        QBrush,
        QColor,
        QFont,
        QIcon,
        QImage,
        QKeySequence,
        QPainter,
        QPalette,
        QPen,
        QPixmap,
    )
    from PyQt5.QtWidgets import (  # type: ignore[no-redef]
        QAbstractItemView,
        QAction,
        QApplication,
        QButtonGroup,
        QCheckBox,
        QComboBox,
        QDockWidget,
        QDoubleSpinBox,
        QFileDialog,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenuBar,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QRadioButton,
        QScrollArea,
        QSizePolicy,
        QSlider,
        QSpinBox,
        QSplitter,
        QStackedWidget,
        QStatusBar,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QToolBar,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )


def _enum_value(source: object, name: str):
    if hasattr(source, name):
        return getattr(source, name)
    raise AttributeError(f"{source!r} has no enum value {name!r}")


def _enum_namespace(source: object, *names: str) -> SimpleNamespace:
    return SimpleNamespace(**{name: _enum_value(source, name) for name in names})


def _ensure_alias(target: object, alias_name: str, source: object, source_name: str | None = None) -> None:
    if hasattr(target, alias_name):
        return
    setattr(target, alias_name, _enum_value(source, source_name or alias_name))


def _ensure_namespace(target: object, namespace_name: str, source: object, *names: str) -> None:
    if hasattr(target, namespace_name):
        namespace = getattr(target, namespace_name)
    else:
        namespace = SimpleNamespace()
        setattr(target, namespace_name, namespace)

    for name in names:
        if not hasattr(namespace, name):
            setattr(namespace, name, _enum_value(source, name))


class _QtCompat:
    """Proxy exposing Qt5/Qt6 enum layouts under one interface."""

    AlignmentFlag = _enum_namespace(_Qt, "AlignCenter", "AlignTop", "AlignRight", "AlignVCenter")
    AspectRatioMode = _enum_namespace(_Qt, "KeepAspectRatio")
    DockWidgetArea = _enum_namespace(
        _Qt,
        "LeftDockWidgetArea",
        "RightDockWidgetArea",
        "BottomDockWidgetArea",
    )
    Orientation = _enum_namespace(_Qt, "Horizontal", "Vertical")
    ToolBarArea = _enum_namespace(_Qt, "TopToolBarArea")
    TransformationMode = _enum_namespace(_Qt, "SmoothTransformation")

    def __getattr__(self, name: str):
        if hasattr(_Qt, name):
            return getattr(_Qt, name)

        for namespace_name in (
            "AlignmentFlag",
            "AspectRatioMode",
            "DockWidgetArea",
            "Orientation",
            "ToolBarArea",
            "TransformationMode",
        ):
            namespace = getattr(type(self), namespace_name)
            if hasattr(namespace, name):
                return getattr(namespace, name)

        raise AttributeError(name)


Qt = _QtCompat()


_ensure_alias(QFrame, "StyledPanel", getattr(QFrame, "Shape", QFrame))
_ensure_alias(QFrame, "HLine", getattr(QFrame, "Shape", QFrame))
_ensure_alias(QFrame, "VLine", getattr(QFrame, "Shape", QFrame))
_ensure_alias(QPainter, "Antialiasing", getattr(QPainter, "RenderHint", QPainter))
_ensure_alias(QSizePolicy, "Expanding", getattr(QSizePolicy, "Policy", QSizePolicy))
_ensure_alias(QSizePolicy, "Fixed", getattr(QSizePolicy, "Policy", QSizePolicy))

_ensure_namespace(QHeaderView, "ResizeMode", QHeaderView, "ResizeToContents")
_ensure_namespace(QImage, "Format", QImage, "Format_Grayscale8")
_ensure_namespace(QMessageBox, "StandardButton", QMessageBox, "Yes", "No")
_ensure_namespace(QTabWidget, "TabPosition", QTabWidget, "North")
_ensure_namespace(QTableWidget, "EditTrigger", QAbstractItemView, "NoEditTriggers")
_ensure_namespace(QTableWidget, "SelectionBehavior", QAbstractItemView, "SelectRows")


__all__ = [
    "QAction",
    "QApplication",
    "QBrush",
    "QButtonGroup",
    "QCheckBox",
    "QColor",
    "QComboBox",
    "QDockWidget",
    "QDoubleSpinBox",
    "QElapsedTimer",
    "QFileDialog",
    "QFont",
    "QFrame",
    "QGridLayout",
    "QGroupBox",
    "QHeaderView",
    "QHBoxLayout",
    "QIcon",
    "QImage",
    "QKeySequence",
    "QLabel",
    "QLineEdit",
    "QListWidget",
    "QListWidgetItem",
    "QMainWindow",
    "QMenuBar",
    "QMessageBox",
    "QMutex",
    "QPainter",
    "QPalette",
    "QPen",
    "QPixmap",
    "QProgressBar",
    "QPushButton",
    "QRadioButton",
    "QRect",
    "QScrollArea",
    "QSettings",
    "QSizePolicy",
    "QSlider",
    "QSpinBox",
    "QSplitter",
    "QStackedWidget",
    "QStatusBar",
    "QTabWidget",
    "QTableWidget",
    "QTableWidgetItem",
    "QThread",
    "QTimer",
    "QToolBar",
    "QToolButton",
    "QVBoxLayout",
    "QWidget",
    "QT_API",
    "Qt",
    "pyqtSignal",
    "pyqtSlot",
]
