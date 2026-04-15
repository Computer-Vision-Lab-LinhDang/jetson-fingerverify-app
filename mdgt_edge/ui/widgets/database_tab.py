"""Database tab - user and fingerprint template management.

Provides user list, detail panel, finger template grid,
CRUD actions, statistics, and export/import controls.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from mdgt_edge.ui.qt_compat import (
    QColor,
    QComboBox,
    QFileDialog,
    QFont,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    Qt,
    pyqtSignal,
    pyqtSlot,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
USER_COLUMNS = ["ID", "Employee ID", "Full Name", "Department", "Status", "Templates"]
FINGER_NAMES = [
    "R. Thumb", "R. Index", "R. Middle", "R. Ring", "R. Little",
    "L. Thumb", "L. Index", "L. Middle", "L. Ring", "L. Little",
]

PAGE_SIZE_DEFAULT = 25
PAGE_SIZE_OPTIONS = [10, 25, 50, 100]

COLOR_ENROLLED = "#27AE60"
COLOR_EMPTY = "#BDC3C7"
COLOR_ACTIVE = "#27AE60"
COLOR_INACTIVE = "#E74C3C"


@dataclass(frozen=True)
class UserRecord:
    """Immutable user record for display."""

    user_id: int
    employee_id: str
    full_name: str
    department: str
    is_active: bool
    template_count: int


class _FingerCell(QLabel):
    """Small cell showing enrolled status for a single finger."""

    def __init__(
        self,
        finger_index: int,
        name: str,
        enrolled: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.finger_index = finger_index
        self.setText(name)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(80, 50)
        self.set_enrolled(enrolled)

    def set_enrolled(self, enrolled: bool) -> None:
        color = COLOR_ENROLLED if enrolled else COLOR_EMPTY
        self.setStyleSheet(
            f"background-color: {color}; color: white; "
            "font-size: 11px; font-weight: bold; "
            "border-radius: 6px; padding: 4px;"
        )


class DatabaseTab(QWidget):
    """User and fingerprint template management interface."""

    # Signals
    user_selected = pyqtSignal(int)              # user_id
    add_user_requested = pyqtSignal(str, str, str)  # emp_id, name, dept
    delete_user_requested = pyqtSignal(int)       # user_id
    deactivate_user_requested = pyqtSignal(int)   # user_id
    delete_template_requested = pyqtSignal(int, int)  # user_id, finger_index
    reenroll_requested = pyqtSignal(int, int)     # user_id, finger_index
    export_requested = pyqtSignal(str)            # file_path
    import_requested = pyqtSignal(str)            # file_path

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_page = 0
        self._page_size = PAGE_SIZE_DEFAULT
        self._total_users = 0
        self._selected_user_id: Optional[int] = None

        self._init_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        root = QHBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # -- Left: user list --
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(8, 8, 8, 8)

        # Search / filter row
        filter_row = QHBoxLayout()

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search by name or ID...")
        self._search_edit.textChanged.connect(self._on_search_changed)
        filter_row.addWidget(self._search_edit)

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["All", "Active", "Inactive"])
        self._filter_combo.currentTextChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._filter_combo)

        left_layout.addLayout(filter_row)

        # User table
        self._user_table = QTableWidget()
        self._user_table.setColumnCount(len(USER_COLUMNS))
        self._user_table.setHorizontalHeaderLabels(USER_COLUMNS)
        self._user_table.horizontalHeader().setStretchLastSection(True)
        self._user_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._user_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._user_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._user_table.setAlternatingRowColors(True)
        self._user_table.setSortingEnabled(True)
        self._user_table.currentCellChanged.connect(self._on_user_row_changed)
        left_layout.addWidget(self._user_table)

        # Pagination
        page_row = QHBoxLayout()

        self._btn_prev_page = QPushButton("< Prev")
        self._btn_prev_page.clicked.connect(self._on_prev_page)
        self._btn_prev_page.setEnabled(False)
        page_row.addWidget(self._btn_prev_page)

        self._page_label = QLabel("Page 1")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_row.addWidget(self._page_label)

        self._btn_next_page = QPushButton("Next >")
        self._btn_next_page.clicked.connect(self._on_next_page)
        page_row.addWidget(self._btn_next_page)

        page_row.addWidget(QLabel("Per page:"))
        self._page_size_spin = QSpinBox()
        self._page_size_spin.setRange(5, 200)
        self._page_size_spin.setValue(PAGE_SIZE_DEFAULT)
        self._page_size_spin.valueChanged.connect(self._on_page_size_changed)
        page_row.addWidget(self._page_size_spin)

        left_layout.addLayout(page_row)

        # Action buttons
        action_row = QHBoxLayout()

        self._btn_add = QPushButton("Add User")
        self._btn_add.setStyleSheet(
            "QPushButton { background-color: #27AE60; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #229954; }"
        )
        self._btn_add.clicked.connect(self._on_add_user)
        action_row.addWidget(self._btn_add)

        self._btn_edit = QPushButton("Edit")
        self._btn_edit.setEnabled(False)
        self._btn_edit.clicked.connect(self._on_edit_user)
        action_row.addWidget(self._btn_edit)

        self._btn_deactivate = QPushButton("Deactivate")
        self._btn_deactivate.setEnabled(False)
        self._btn_deactivate.clicked.connect(self._on_deactivate_user)
        action_row.addWidget(self._btn_deactivate)

        self._btn_delete = QPushButton("Delete")
        self._btn_delete.setEnabled(False)
        self._btn_delete.setStyleSheet(
            "QPushButton { color: #E74C3C; font-weight: bold; "
            "padding: 8px 16px; border-radius: 6px; }"
        )
        self._btn_delete.clicked.connect(self._on_delete_user)
        action_row.addWidget(self._btn_delete)

        left_layout.addLayout(action_row)

        # Statistics
        stats_group = QGroupBox("Statistics")
        stats_layout = QGridLayout()
        self._stat_labels: dict[str, QLabel] = {}
        stat_defs = [
            ("Total Users", "total_users"),
            ("Total Templates", "total_templates"),
            ("Avg Quality", "avg_quality"),
        ]
        for row, (display, key) in enumerate(stat_defs):
            lbl = QLabel(f"{display}:")
            lbl.setStyleSheet("font-weight: bold; color: #2C3E50;")
            val = QLabel("--")
            val.setStyleSheet("color: #5D6D7E;")
            stats_layout.addWidget(lbl, row, 0)
            stats_layout.addWidget(val, row, 1)
            self._stat_labels[key] = val
        stats_group.setLayout(stats_layout)
        left_layout.addWidget(stats_group)

        # Export / Import
        io_row = QHBoxLayout()
        self._btn_export = QPushButton("Export...")
        self._btn_export.clicked.connect(self._on_export)
        io_row.addWidget(self._btn_export)

        self._btn_import = QPushButton("Import...")
        self._btn_import.clicked.connect(self._on_import)
        io_row.addWidget(self._btn_import)
        left_layout.addLayout(io_row)

        splitter.addWidget(left_widget)

        # -- Right: user detail + finger grid --
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 8, 8, 8)

        # User detail
        detail_group = QGroupBox("User Detail")
        detail_layout = QGridLayout()
        self._detail_labels: dict[str, QLabel] = {}
        detail_defs = [
            ("User ID", "user_id"),
            ("Employee ID", "employee_id"),
            ("Full Name", "full_name"),
            ("Department", "department"),
            ("Status", "status"),
        ]
        for row, (display, key) in enumerate(detail_defs):
            lbl = QLabel(f"{display}:")
            lbl.setStyleSheet("font-weight: bold; color: #2C3E50;")
            val = QLabel("--")
            val.setStyleSheet("color: #5D6D7E;")
            detail_layout.addWidget(lbl, row, 0)
            detail_layout.addWidget(val, row, 1)
            self._detail_labels[key] = val
        detail_group.setLayout(detail_layout)
        right_layout.addWidget(detail_group)

        # Finger template grid
        finger_group = QGroupBox("Enrolled Fingers")
        finger_layout = QGridLayout()
        self._finger_cells: list[_FingerCell] = []

        # Row 0: Right hand (indices 0-4)
        finger_layout.addWidget(
            QLabel("Right Hand:"), 0, 0
        )
        for i in range(5):
            cell = _FingerCell(i, FINGER_NAMES[i])
            finger_layout.addWidget(cell, 0, i + 1)
            self._finger_cells.append(cell)

        # Row 1: Left hand (indices 5-9)
        finger_layout.addWidget(
            QLabel("Left Hand:"), 1, 0
        )
        for i in range(5, 10):
            cell = _FingerCell(i, FINGER_NAMES[i])
            finger_layout.addWidget(cell, 1, i - 5 + 1)
            self._finger_cells.append(cell)

        finger_group.setLayout(finger_layout)
        right_layout.addWidget(finger_group)

        # Fingerprint actions
        fp_action_row = QHBoxLayout()

        self._btn_view_template = QPushButton("View Template")
        self._btn_view_template.setEnabled(False)
        self._btn_view_template.clicked.connect(self._on_view_template)
        fp_action_row.addWidget(self._btn_view_template)

        self._btn_delete_template = QPushButton("Delete Template")
        self._btn_delete_template.setEnabled(False)
        self._btn_delete_template.setStyleSheet("color: #E74C3C;")
        self._btn_delete_template.clicked.connect(self._on_delete_template)
        fp_action_row.addWidget(self._btn_delete_template)

        self._btn_reenroll = QPushButton("Re-enroll")
        self._btn_reenroll.setEnabled(False)
        self._btn_reenroll.clicked.connect(self._on_reenroll)
        fp_action_row.addWidget(self._btn_reenroll)

        right_layout.addLayout(fp_action_row)
        right_layout.addStretch()

        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

    # ------------------------------------------------------------------
    # Table / selection
    # ------------------------------------------------------------------

    def _on_user_row_changed(
        self, current_row: int, _col: int, _prev_row: int, _prev_col: int
    ) -> None:
        has_selection = current_row >= 0
        self._btn_edit.setEnabled(has_selection)
        self._btn_deactivate.setEnabled(has_selection)
        self._btn_delete.setEnabled(has_selection)
        self._btn_view_template.setEnabled(has_selection)
        self._btn_delete_template.setEnabled(has_selection)
        self._btn_reenroll.setEnabled(has_selection)

        if has_selection:
            id_item = self._user_table.item(current_row, 0)
            if id_item:
                self._selected_user_id = int(id_item.text())
                self.user_selected.emit(self._selected_user_id)

    def _on_search_changed(self, text: str) -> None:
        """Filter table rows by search text (client-side)."""
        text_lower = text.lower()
        for row in range(self._user_table.rowCount()):
            match = False
            for col in range(self._user_table.columnCount()):
                item = self._user_table.item(row, col)
                if item and text_lower in item.text().lower():
                    match = True
                    break
            self._user_table.setRowHidden(row, not match)

    def _on_filter_changed(self, filter_text: str) -> None:
        """Filter by active/inactive status."""
        status_col = USER_COLUMNS.index("Status")
        for row in range(self._user_table.rowCount()):
            item = self._user_table.item(row, status_col)
            if not item:
                continue
            if filter_text == "All":
                self._user_table.setRowHidden(row, False)
            elif filter_text == "Active":
                self._user_table.setRowHidden(row, item.text() != "Active")
            elif filter_text == "Inactive":
                self._user_table.setRowHidden(row, item.text() != "Inactive")

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    def _on_prev_page(self) -> None:
        if self._current_page > 0:
            self._current_page -= 1
            self._update_page_label()

    def _on_next_page(self) -> None:
        max_page = max(0, (self._total_users - 1) // self._page_size)
        if self._current_page < max_page:
            self._current_page += 1
            self._update_page_label()

    def _on_page_size_changed(self, value: int) -> None:
        self._page_size = value
        self._current_page = 0
        self._update_page_label()

    def _update_page_label(self) -> None:
        total_pages = max(1, (self._total_users + self._page_size - 1) // self._page_size)
        self._page_label.setText(
            f"Page {self._current_page + 1} / {total_pages}"
        )
        self._btn_prev_page.setEnabled(self._current_page > 0)
        self._btn_next_page.setEnabled(
            self._current_page < total_pages - 1
        )

    # ------------------------------------------------------------------
    # CRUD actions
    # ------------------------------------------------------------------

    def _on_add_user(self) -> None:
        """Emit signal to add a new user (details entered elsewhere)."""
        self.add_user_requested.emit("", "", "")

    def _on_edit_user(self) -> None:
        """Placeholder for edit user dialog."""
        pass

    def _on_deactivate_user(self) -> None:
        if self._selected_user_id is None:
            return
        reply = QMessageBox.question(
            self,
            "Deactivate User",
            f"Deactivate user {self._selected_user_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.deactivate_user_requested.emit(self._selected_user_id)

    def _on_delete_user(self) -> None:
        if self._selected_user_id is None:
            return
        reply = QMessageBox.question(
            self,
            "Delete User",
            f"Permanently delete user {self._selected_user_id} "
            "and all templates?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_user_requested.emit(self._selected_user_id)

    def _on_view_template(self) -> None:
        pass

    def _on_delete_template(self) -> None:
        if self._selected_user_id is None:
            return
        self.delete_template_requested.emit(self._selected_user_id, 0)

    def _on_reenroll(self) -> None:
        if self._selected_user_id is None:
            return
        self.reenroll_requested.emit(self._selected_user_id, 0)

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Database", "users_export.csv",
            "CSV (*.csv);;JSON (*.json)",
        )
        if path:
            self.export_requested.emit(path)

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Data", "",
            "CSV (*.csv);;JSON (*.json)",
        )
        if path:
            self.import_requested.emit(path)

    # ------------------------------------------------------------------
    # Public API -- called by service layer
    # ------------------------------------------------------------------

    @pyqtSlot(list)
    def load_users(self, users: list) -> None:
        """Populate the user table.

        Parameters
        ----------
        users:
            List of UserRecord or dicts with matching keys.
        """
        self._user_table.setRowCount(0)

        for entry in users:
            if isinstance(entry, UserRecord):
                record = entry
            else:
                record = UserRecord(
                    user_id=entry.get("user_id", 0),
                    employee_id=entry.get("employee_id", ""),
                    full_name=entry.get("full_name", ""),
                    department=entry.get("department", ""),
                    is_active=entry.get("is_active", True),
                    template_count=entry.get("template_count", 0),
                )

            row = self._user_table.rowCount()
            self._user_table.insertRow(row)

            self._user_table.setItem(
                row, 0, QTableWidgetItem(str(record.user_id))
            )
            self._user_table.setItem(
                row, 1, QTableWidgetItem(record.employee_id)
            )
            self._user_table.setItem(
                row, 2, QTableWidgetItem(record.full_name)
            )
            self._user_table.setItem(
                row, 3, QTableWidgetItem(record.department)
            )

            status_text = "Active" if record.is_active else "Inactive"
            status_item = QTableWidgetItem(status_text)
            status_color = QColor(COLOR_ACTIVE) if record.is_active else QColor(COLOR_INACTIVE)
            status_item.setForeground(status_color)
            self._user_table.setItem(row, 4, status_item)

            self._user_table.setItem(
                row, 5, QTableWidgetItem(str(record.template_count))
            )

        self._total_users = len(users)
        self._update_page_label()

    @pyqtSlot(dict)
    def load_user_detail(self, detail: dict) -> None:
        """Populate the user detail panel.

        Parameters
        ----------
        detail:
            Dict with keys: user_id, employee_id, full_name, department,
            is_active, enrolled_fingers (list of int indices).
        """
        self._detail_labels["user_id"].setText(str(detail.get("user_id", "--")))
        self._detail_labels["employee_id"].setText(
            detail.get("employee_id", "--")
        )
        self._detail_labels["full_name"].setText(
            detail.get("full_name", "--")
        )
        self._detail_labels["department"].setText(
            detail.get("department", "--")
        )

        is_active = detail.get("is_active", True)
        status_text = "Active" if is_active else "Inactive"
        status_color = COLOR_ACTIVE if is_active else COLOR_INACTIVE
        self._detail_labels["status"].setText(status_text)
        self._detail_labels["status"].setStyleSheet(
            f"color: {status_color}; font-weight: bold;"
        )

        enrolled = set(detail.get("enrolled_fingers", []))
        for cell in self._finger_cells:
            cell.set_enrolled(cell.finger_index in enrolled)

    @pyqtSlot(int, int, int)
    def update_statistics(
        self, total_users: int, total_templates: int, avg_quality: int
    ) -> None:
        """Update the statistics panel."""
        self._stat_labels["total_users"].setText(str(total_users))
        self._stat_labels["total_templates"].setText(str(total_templates))
        self._stat_labels["avg_quality"].setText(
            f"{avg_quality}" if avg_quality else "--"
        )
