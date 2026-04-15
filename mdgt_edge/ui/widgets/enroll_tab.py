"""Enroll tab - multi-step fingerprint enrollment wizard.

Guides the operator through user selection, finger selection,
capture with quality/PAD gates, review, and confirmation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from mdgt_edge.ui.qt_compat import (
    QComboBox,
    QFont,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QImage,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPixmap,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
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
STEP_USER = 0
STEP_FINGERS = 1
STEP_CAPTURE = 2
STEP_REVIEW = 3
STEP_SUMMARY = 4

STEP_TITLES = [
    "Step 1: Select / Create User",
    "Step 2: Select Finger(s) to Enroll",
    "Step 3: Capture Fingerprint(s)",
    "Step 4: Review & Confirm",
    "Step 5: Enrollment Summary",
]

FINGER_NAMES = [
    "R. Thumb", "R. Index", "R. Middle", "R. Ring", "R. Little",
    "L. Thumb", "L. Index", "L. Middle", "L. Ring", "L. Little",
]

MIN_SAMPLES_PER_FINGER = 3
CAPTURE_THUMB_SIZE = 128
QUALITY_THRESHOLD_DEFAULT = 40
NFIQ2_THRESHOLD_DEFAULT = 30


@dataclass(frozen=True)
class EnrollSample:
    """Immutable capture sample for enrollment."""

    finger_index: int
    sample_number: int
    image_data: bytes
    width: int
    height: int
    quality_score: int
    nfiq2_score: int
    spoof_detected: bool


class _FingerButton(QPushButton):
    """Toggle button representing a single finger for selection."""

    def __init__(self, index: int, name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(name, parent)
        self.finger_index = index
        self.setCheckable(True)
        self.setMinimumSize(80, 36)
        self._update_style()
        self.toggled.connect(lambda _: self._update_style())

    def _update_style(self) -> None:
        if self.isChecked():
            self.setStyleSheet(
                "QPushButton { background-color: #27AE60; color: white; "
                "font-weight: bold; border-radius: 6px; padding: 6px; }"
            )
        else:
            self.setStyleSheet(
                "QPushButton { background-color: #ECF0F1; color: #2C3E50; "
                "border-radius: 6px; padding: 6px; }"
                "QPushButton:hover { background-color: #D5DBDB; }"
            )


class _HandDiagram(QWidget):
    """2D hand diagram showing which finger is being enrolled."""

    # Finger positions: (x_pct, y_pct, label) for right hand (0-4) and left hand (5-9)
    _RIGHT_FINGERS = [
        (0.50, 0.85, "Thumb"),   # 0: R.Thumb
        (0.35, 0.15, "Index"),   # 1: R.Index
        (0.50, 0.05, "Middle"),  # 2: R.Middle
        (0.65, 0.15, "Ring"),    # 3: R.Ring
        (0.80, 0.30, "Little"),  # 4: R.Little
    ]
    _LEFT_FINGERS = [
        (0.50, 0.85, "Thumb"),   # 5: L.Thumb
        (0.65, 0.15, "Index"),   # 6: L.Index
        (0.50, 0.05, "Middle"),  # 7: L.Middle
        (0.35, 0.15, "Ring"),    # 8: L.Ring
        (0.20, 0.30, "Little"),  # 9: L.Little
    ]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._active_finger: int = -1
        self._enrolled_fingers: set[int] = set()
        self.setFixedSize(320, 200)

    def set_active_finger(self, finger_index: int) -> None:
        self._active_finger = finger_index
        self.update()

    def set_enrolled(self, enrolled: set[int]) -> None:
        self._enrolled_fingers = enrolled
        self.update()

    def paintEvent(self, event) -> None:
        from mdgt_edge.ui.qt_compat import QPainter, QPen, QColor, QFont, QRect
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        half = w // 2

        # Draw hand labels
        p.setPen(QPen(QColor("#2C3E50")))
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        p.setFont(font)
        p.drawText(QRect(0, h - 22, half, 20), Qt.AlignmentFlag.AlignCenter, "Right Hand")
        p.drawText(QRect(half, h - 22, half, 20), Qt.AlignmentFlag.AlignCenter, "Left Hand")

        font.setPointSize(8)
        font.setBold(False)
        p.setFont(font)

        # Draw fingers
        for base_idx, fingers, x_off in [
            (0, self._RIGHT_FINGERS, 0),
            (5, self._LEFT_FINGERS, half),
        ]:
            for i, (xp, yp, label) in enumerate(fingers):
                fi = base_idx + i
                cx = int(x_off + xp * half)
                cy = int(yp * (h - 30)) + 5
                radius = 16

                # Color: active=purple, enrolled=green, default=gray
                if fi == self._active_finger:
                    p.setBrush(QColor("#8E44AD"))
                    p.setPen(QPen(QColor("#6C3483"), 3))
                elif fi in self._enrolled_fingers:
                    p.setBrush(QColor("#27AE60"))
                    p.setPen(QPen(QColor("#1E8449"), 2))
                else:
                    p.setBrush(QColor("#BDC3C7"))
                    p.setPen(QPen(QColor("#95A5A6"), 1))

                p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

                # Label
                p.setPen(QPen(QColor("white" if fi == self._active_finger or fi in self._enrolled_fingers else "#2C3E50")))
                p.drawText(QRect(cx - 25, cy - 8, 50, 16), Qt.AlignmentFlag.AlignCenter, label)

        p.end()


class EnrollTab(QWidget):
    """Multi-step fingerprint enrollment wizard."""

    # Signals
    enroll_capture_requested = pyqtSignal(int)           # finger_index
    enrollment_complete = pyqtSignal(str, list)           # employee_id, samples
    enrollment_cancelled = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_step = STEP_USER
        self._selected_fingers: list[int] = []
        self._samples: list[EnrollSample] = []
        self._current_finger_idx = 0
        self._current_sample_num = 0

        self._init_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)

        # Step title
        self._step_title = QLabel(STEP_TITLES[STEP_USER])
        self._step_title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #2C3E50; padding: 8px;"
        )
        self._step_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._step_title)

        # Progress indicators
        progress_row = QHBoxLayout()
        self._step_indicators: list[QLabel] = []
        for i in range(5):
            lbl = QLabel(f" {i + 1} ")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedSize(32, 32)
            lbl.setStyleSheet(
                "background-color: #BDC3C7; color: white; "
                "border-radius: 16px; font-weight: bold;"
            )
            self._step_indicators.append(lbl)
            progress_row.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addLayout(progress_row)

        # Stacked pages
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_user_page())
        self._stack.addWidget(self._build_finger_page())
        self._stack.addWidget(self._build_capture_page())
        self._stack.addWidget(self._build_review_page())
        self._stack.addWidget(self._build_summary_page())
        root.addWidget(self._stack, stretch=1)

        # Navigation
        nav_row = QHBoxLayout()

        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.setStyleSheet(
            "QPushButton { padding: 8px 20px; border-radius: 6px; }"
        )
        self._btn_cancel.clicked.connect(self._on_cancel)
        nav_row.addWidget(self._btn_cancel)

        nav_row.addStretch()

        self._btn_prev = QPushButton("Previous")
        self._btn_prev.setStyleSheet(
            "QPushButton { padding: 8px 20px; border-radius: 6px; }"
        )
        self._btn_prev.setEnabled(False)
        self._btn_prev.clicked.connect(self._go_previous)
        nav_row.addWidget(self._btn_prev)

        self._btn_next = QPushButton("Next")
        self._btn_next.setStyleSheet(
            "QPushButton { background-color: #2980B9; color: white; "
            "font-weight: bold; padding: 8px 20px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #2471A3; }"
        )
        self._btn_next.clicked.connect(self._go_next)
        nav_row.addWidget(self._btn_next)

        root.addLayout(nav_row)

        self._update_step_indicators()

    # ------------------------------------------------------------------
    # Page builders
    # ------------------------------------------------------------------

    def _build_user_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        group = QGroupBox("User Information")
        form = QGridLayout()

        form.addWidget(QLabel("Employee ID:"), 0, 0)
        self._edit_employee_id = QLineEdit()
        self._edit_employee_id.setPlaceholderText("e.g. EMP-001")
        form.addWidget(self._edit_employee_id, 0, 1)

        form.addWidget(QLabel("Full Name:"), 1, 0)
        self._edit_full_name = QLineEdit()
        self._edit_full_name.setPlaceholderText("e.g. Nguyen Van A")
        form.addWidget(self._edit_full_name, 1, 1)

        form.addWidget(QLabel("Department:"), 2, 0)
        self._combo_department = QComboBox()
        self._combo_department.addItems([
            "Engineering", "Operations", "Security",
            "Administration", "Research", "Other",
        ])
        self._combo_department.setEditable(True)
        form.addWidget(self._combo_department, 2, 1)

        group.setLayout(form)
        layout.addWidget(group)
        layout.addStretch()
        return page

    def _build_finger_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(
            QLabel("Select fingers to enroll (click to toggle):"),
        )

        # Right hand
        rh_group = QGroupBox("Right Hand")
        rh_layout = QHBoxLayout()
        self._finger_buttons: list[_FingerButton] = []
        for i in range(5):
            btn = _FingerButton(i, FINGER_NAMES[i])
            rh_layout.addWidget(btn)
            self._finger_buttons.append(btn)
        rh_group.setLayout(rh_layout)
        layout.addWidget(rh_group)

        # Left hand
        lh_group = QGroupBox("Left Hand")
        lh_layout = QHBoxLayout()
        for i in range(5, 10):
            btn = _FingerButton(i, FINGER_NAMES[i])
            lh_layout.addWidget(btn)
            self._finger_buttons.append(btn)
        lh_group.setLayout(lh_layout)
        layout.addWidget(lh_group)

        self._finger_count_label = QLabel("Selected: 0 finger(s)")
        self._finger_count_label.setStyleSheet(
            "font-size: 14px; color: #5D6D7E; padding: 8px;"
        )
        for btn in self._finger_buttons:
            btn.toggled.connect(self._on_finger_selection_changed)
        layout.addWidget(self._finger_count_label)

        layout.addStretch()
        return page

    def _build_capture_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        # Current finger being captured
        self._capture_finger_label = QLabel("Finger: --")
        self._capture_finger_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #2C3E50; padding: 4px;"
        )
        self._capture_finger_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._capture_finger_label)

        # Hand diagram showing current finger
        self._hand_diagram = _HandDiagram()
        layout.addWidget(self._hand_diagram, alignment=Qt.AlignmentFlag.AlignCenter)

        # Preview row: live feed (left) + last captured (right)
        preview_row = QHBoxLayout()

        # Live preview from sensor
        live_group = QGroupBox("Live Preview")
        live_layout = QVBoxLayout()
        self._live_preview = QLabel("Waiting for sensor...")
        self._live_preview.setFixedSize(300, 300)
        self._live_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._live_preview.setStyleSheet(
            "background-color: #1B2631; border: 2px solid #2C3E50; "
            "border-radius: 8px; color: #5D6D7E; font-size: 14px;"
        )
        live_layout.addWidget(self._live_preview)
        self._finger_status_label = QLabel("No finger detected")
        self._finger_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._finger_status_label.setStyleSheet("font-size: 13px; color: #E74C3C;")
        live_layout.addWidget(self._finger_status_label)
        live_group.setLayout(live_layout)
        preview_row.addWidget(live_group)

        # Last captured sample
        captured_group = QGroupBox("Last Captured")
        captured_layout = QVBoxLayout()
        self._capture_preview = QLabel("Place finger on sensor")
        self._capture_preview.setFixedSize(CAPTURE_THUMB_SIZE * 2, CAPTURE_THUMB_SIZE * 2)
        self._capture_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._capture_preview.setStyleSheet(
            "background-color: #1B2631; border: 2px solid #2C3E50; "
            "border-radius: 8px; color: #5D6D7E; font-size: 14px;"
        )
        captured_layout.addWidget(self._capture_preview)
        captured_group.setLayout(captured_layout)
        preview_row.addWidget(captured_group)

        layout.addLayout(preview_row)

        # Quality / PAD feedback
        feedback_row = QHBoxLayout()

        self._quality_feedback = QLabel("Quality: --")
        self._quality_feedback.setStyleSheet("font-size: 13px; color: #5D6D7E;")
        feedback_row.addWidget(self._quality_feedback)

        self._pad_feedback = QLabel("PAD: --")
        self._pad_feedback.setStyleSheet("font-size: 13px; color: #5D6D7E;")
        feedback_row.addWidget(self._pad_feedback)

        layout.addLayout(feedback_row)

        # Per-finger progress bar
        self._capture_progress = QProgressBar()
        self._capture_progress.setRange(0, MIN_SAMPLES_PER_FINGER)
        self._capture_progress.setValue(0)
        self._capture_progress.setFormat("Sample %v / %m")
        layout.addWidget(self._capture_progress)

        # Overall progress
        self._overall_progress_label = QLabel("Overall: 0 / 0 fingers done")
        self._overall_progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._overall_progress_label.setStyleSheet(
            "font-size: 13px; color: #5D6D7E; padding: 4px;"
        )
        layout.addWidget(self._overall_progress_label)

        # Buttons row: Capture + Retake
        btn_row = QHBoxLayout()

        self._capture_btn = QPushButton("Capture Sample")
        self._capture_btn.setMinimumHeight(50)
        self._capture_btn.setStyleSheet(
            "QPushButton { background-color: #27AE60; color: white; "
            "font-size: 16px; font-weight: bold; border-radius: 8px; }"
            "QPushButton:hover { background-color: #229954; }"
        )
        self._capture_btn.clicked.connect(self._on_capture_sample)
        btn_row.addWidget(self._capture_btn)

        self._retake_btn = QPushButton("Retake Last")
        self._retake_btn.setMinimumHeight(50)
        self._retake_btn.setEnabled(False)
        self._retake_btn.setStyleSheet(
            "QPushButton { background-color: #E67E22; color: white; "
            "font-size: 14px; font-weight: bold; border-radius: 8px; }"
            "QPushButton:hover { background-color: #D35400; }"
        )
        self._retake_btn.clicked.connect(self._on_retake_last)
        btn_row.addWidget(self._retake_btn)

        layout.addLayout(btn_row)

        layout.addStretch()
        return page

    def _build_review_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        layout.addWidget(QLabel("Review enrolled samples:"))

        self._review_grid_widget = QWidget()
        self._review_grid = QGridLayout(self._review_grid_widget)
        layout.addWidget(self._review_grid_widget)

        self._review_summary = QLabel("")
        self._review_summary.setStyleSheet(
            "font-size: 14px; color: #2C3E50; padding: 8px;"
        )
        self._review_summary.setWordWrap(True)
        layout.addWidget(self._review_summary)

        layout.addStretch()
        return page

    def _build_summary_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._summary_icon = QLabel()
        self._summary_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary_icon.setStyleSheet("font-size: 48px;")
        layout.addWidget(self._summary_icon)

        self._summary_label = QLabel("Enrollment complete")
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary_label.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #27AE60; padding: 12px;"
        )
        layout.addWidget(self._summary_label)

        self._summary_detail = QLabel("")
        self._summary_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary_detail.setStyleSheet(
            "font-size: 14px; color: #5D6D7E;"
        )
        self._summary_detail.setWordWrap(True)
        layout.addWidget(self._summary_detail)

        self._btn_new_enroll = QPushButton("Start New Enrollment")
        self._btn_new_enroll.setStyleSheet(
            "QPushButton { background-color: #2980B9; color: white; "
            "font-weight: bold; padding: 10px 24px; border-radius: 6px; }"
        )
        self._btn_new_enroll.clicked.connect(self._reset_wizard)
        layout.addWidget(
            self._btn_new_enroll, alignment=Qt.AlignmentFlag.AlignCenter
        )

        return page

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _go_next(self) -> None:
        if not self._validate_current_step():
            return

        if self._current_step == STEP_FINGERS:
            self._prepare_capture_step()

        if self._current_step == STEP_CAPTURE:
            self._prepare_review_step()

        if self._current_step == STEP_REVIEW:
            self._finalize_enrollment()

        if self._current_step < STEP_SUMMARY:
            self._current_step += 1
            self._stack.setCurrentIndex(self._current_step)
            self._step_title.setText(STEP_TITLES[self._current_step])
            self._update_navigation_state()
            self._update_step_indicators()

    def _go_previous(self) -> None:
        if self._current_step > STEP_USER:
            self._current_step -= 1
            self._stack.setCurrentIndex(self._current_step)
            self._step_title.setText(STEP_TITLES[self._current_step])
            self._update_navigation_state()
            self._update_step_indicators()

    def _update_navigation_state(self) -> None:
        self._btn_prev.setEnabled(self._current_step > STEP_USER)
        if self._current_step == STEP_REVIEW:
            self._btn_next.setText("Confirm")
        elif self._current_step == STEP_SUMMARY:
            self._btn_next.setEnabled(False)
            self._btn_prev.setEnabled(False)
        else:
            self._btn_next.setText("Next")
            self._btn_next.setEnabled(True)

    def _update_step_indicators(self) -> None:
        for i, lbl in enumerate(self._step_indicators):
            if i < self._current_step:
                lbl.setStyleSheet(
                    "background-color: #27AE60; color: white; "
                    "border-radius: 16px; font-weight: bold;"
                )
            elif i == self._current_step:
                lbl.setStyleSheet(
                    "background-color: #2980B9; color: white; "
                    "border-radius: 16px; font-weight: bold;"
                )
            else:
                lbl.setStyleSheet(
                    "background-color: #BDC3C7; color: white; "
                    "border-radius: 16px; font-weight: bold;"
                )

    def _validate_current_step(self) -> bool:
        if self._current_step == STEP_USER:
            if not self._edit_employee_id.text().strip():
                QMessageBox.warning(
                    self, "Validation", "Employee ID is required."
                )
                return False
            if not self._edit_full_name.text().strip():
                QMessageBox.warning(
                    self, "Validation", "Full name is required."
                )
                return False
            return True

        if self._current_step == STEP_FINGERS:
            selected = [
                b for b in self._finger_buttons if b.isChecked()
            ]
            if not selected:
                QMessageBox.warning(
                    self, "Validation",
                    "Select at least one finger to enroll.",
                )
                return False
            self._selected_fingers = [b.finger_index for b in selected]
            return True

        if self._current_step == STEP_CAPTURE:
            finger_ids_captured = {
                s.finger_index for s in self._samples
            }
            if not all(f in finger_ids_captured for f in self._selected_fingers):
                QMessageBox.warning(
                    self, "Validation",
                    "Not all selected fingers have been captured.",
                )
                return False
            return True

        return True

    # ------------------------------------------------------------------
    # Finger selection
    # ------------------------------------------------------------------

    def _on_finger_selection_changed(self) -> None:
        count = sum(1 for b in self._finger_buttons if b.isChecked())
        self._finger_count_label.setText(f"Selected: {count} finger(s)")

    # ------------------------------------------------------------------
    # Capture step
    # ------------------------------------------------------------------

    def _prepare_capture_step(self) -> None:
        self._samples.clear()
        self._current_finger_idx = 0
        self._current_sample_num = 0
        self._update_capture_display()

    def _update_capture_display(self) -> None:
        # Track which fingers are fully enrolled
        enrolled = {
            s.finger_index for s in self._samples
            if sum(1 for x in self._samples if x.finger_index == s.finger_index) >= MIN_SAMPLES_PER_FINGER
        }

        if self._current_finger_idx < len(self._selected_fingers):
            finger_id = self._selected_fingers[self._current_finger_idx]
            name = FINGER_NAMES[finger_id] if finger_id < len(FINGER_NAMES) else f"Finger {finger_id}"
            self._capture_finger_label.setText(f"Finger: {name}")
            self._capture_progress.setValue(self._current_sample_num)
            done_count = self._current_finger_idx
            total_count = len(self._selected_fingers)
            self._overall_progress_label.setText(
                f"Overall: {done_count} / {total_count} fingers done"
            )
            # Update hand diagram
            self._hand_diagram.set_active_finger(finger_id)
            self._hand_diagram.set_enrolled(enrolled)
        else:
            self._capture_finger_label.setText("All fingers captured!")
            self._capture_btn.setEnabled(False)
            self._hand_diagram.set_active_finger(-1)
            self._hand_diagram.set_enrolled(enrolled)

    def _on_capture_sample(self) -> None:
        if self._current_finger_idx >= len(self._selected_fingers):
            return
        finger_id = self._selected_fingers[self._current_finger_idx]
        self._capture_btn.setEnabled(False)
        self._capture_btn.setText("Place finger on sensor...")
        self.enroll_capture_requested.emit(finger_id)

    def _on_retake_last(self) -> None:
        """Remove the last captured sample and allow re-capture."""
        if not self._samples:
            return
        removed = self._samples.pop()
        # If we just moved to next finger, go back
        if self._current_sample_num == 0 and self._current_finger_idx > 0:
            self._current_finger_idx -= 1
            self._current_sample_num = MIN_SAMPLES_PER_FINGER - 1
        elif self._current_sample_num > 0:
            self._current_sample_num -= 1
        self._capture_progress.setValue(self._current_sample_num)
        self._capture_btn.setEnabled(True)
        self._capture_btn.setText("Capture Sample")
        self._retake_btn.setEnabled(len(self._samples) > 0)
        self._capture_preview.clear()
        self._capture_preview.setText("Retake — place finger")
        self._update_capture_display()

    @pyqtSlot(bytes, int, int)
    def on_preview_frame(self, image_data: bytes, width: int, height: int) -> None:
        """Update live preview during capture step."""
        if self._current_step != STEP_CAPTURE:
            return
        if not image_data or width <= 0 or height <= 0:
            return
        qimg = QImage(image_data, width, height, width, QImage.Format_Grayscale8)
        if qimg.isNull():
            return
        pixmap = QPixmap.fromImage(qimg).scaled(
            300, 300,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._live_preview.setPixmap(pixmap)
        self._live_preview.setStyleSheet(
            "background-color: #1B2631; border: 2px solid #27AE60; border-radius: 8px;"
        )

    @pyqtSlot(int)
    def on_finger_status(self, count: int) -> None:
        """Update finger detection status label."""
        if count > 0:
            self._finger_status_label.setText(f"{count} finger(s) detected")
            self._finger_status_label.setStyleSheet("font-size: 13px; color: #27AE60; font-weight: bold;")
        else:
            self._finger_status_label.setText("No finger detected")
            self._finger_status_label.setStyleSheet("font-size: 13px; color: #E74C3C;")

    @pyqtSlot(object)
    def on_enroll_capture_result(self, result: object) -> None:
        """Handle a capture result during enrollment.

        Parameters
        ----------
        result:
            Object with image_data, width, height, quality_score,
            nfiq2_score, spoof_detected attributes.
        """
        self._capture_btn.setEnabled(True)
        self._capture_btn.setText("Capture Sample")

        image_data = getattr(result, "image_data", b"")
        width = getattr(result, "width", 192)
        height = getattr(result, "height", 192)
        quality = getattr(result, "quality_score", 0)
        nfiq2 = getattr(result, "nfiq2_score", 0)
        spoof = getattr(result, "spoof_detected", False)

        # Update feedback labels
        self._quality_feedback.setText(f"Quality: {quality}")
        pad_text = "SPOOF DETECTED" if spoof else "Live"
        pad_color = "#E74C3C" if spoof else "#27AE60"
        self._pad_feedback.setText(f"PAD: {pad_text}")
        self._pad_feedback.setStyleSheet(f"font-size: 13px; color: {pad_color};")

        # Quality gate
        if quality < QUALITY_THRESHOLD_DEFAULT:
            self._quality_feedback.setStyleSheet("font-size: 13px; color: #E74C3C;")
            QMessageBox.warning(
                self, "Quality Too Low",
                f"Quality {quality} is below threshold {QUALITY_THRESHOLD_DEFAULT}. "
                "Please try again.",
            )
            return

        # PAD gate
        if spoof:
            QMessageBox.warning(
                self, "Spoof Detected",
                "Presentation attack detected. Please use a real finger.",
            )
            return

        # Update preview
        if image_data:
            qimg = QImage(
                image_data, width, height, width,
                QImage.Format_Grayscale8,
            )
            pixmap = QPixmap.fromImage(qimg).scaled(
                CAPTURE_THUMB_SIZE * 2, CAPTURE_THUMB_SIZE * 2,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._capture_preview.setPixmap(pixmap)

        # Accept sample
        finger_id = self._selected_fingers[self._current_finger_idx]
        sample = EnrollSample(
            finger_index=finger_id,
            sample_number=self._current_sample_num,
            image_data=image_data,
            width=width,
            height=height,
            quality_score=quality,
            nfiq2_score=nfiq2,
            spoof_detected=spoof,
        )
        self._samples.append(sample)
        self._current_sample_num += 1
        self._capture_progress.setValue(self._current_sample_num)
        self._quality_feedback.setStyleSheet("font-size: 13px; color: #27AE60;")
        self._retake_btn.setEnabled(True)

        # Move to next finger if enough samples
        if self._current_sample_num >= MIN_SAMPLES_PER_FINGER:
            self._current_finger_idx += 1
            self._current_sample_num = 0
            self._capture_progress.setValue(0)

        self._update_capture_display()

    # ------------------------------------------------------------------
    # Review step
    # ------------------------------------------------------------------

    def _prepare_review_step(self) -> None:
        # Clear existing review grid
        while self._review_grid.count():
            item = self._review_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        col = 0
        for finger_id in self._selected_fingers:
            finger_samples = [
                s for s in self._samples if s.finger_index == finger_id
            ]
            name = FINGER_NAMES[finger_id] if finger_id < len(FINGER_NAMES) else f"Finger {finger_id}"

            header = QLabel(name)
            header.setStyleSheet("font-weight: bold; color: #2C3E50;")
            self._review_grid.addWidget(header, 0, col)

            for row, sample in enumerate(finger_samples, start=1):
                thumb = QLabel()
                thumb.setFixedSize(CAPTURE_THUMB_SIZE, CAPTURE_THUMB_SIZE)
                if sample.image_data:
                    qimg = QImage(
                        sample.image_data,
                        sample.width, sample.height, sample.width,
                        QImage.Format_Grayscale8,
                    )
                    pixmap = QPixmap.fromImage(qimg).scaled(
                        CAPTURE_THUMB_SIZE, CAPTURE_THUMB_SIZE,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    thumb.setPixmap(pixmap)
                else:
                    thumb.setText("No data")
                thumb.setStyleSheet(
                    "border: 1px solid #BDC3C7; border-radius: 4px;"
                )
                self._review_grid.addWidget(thumb, row, col)

            col += 1

        emp = self._edit_employee_id.text().strip()
        name = self._edit_full_name.text().strip()
        dept = self._combo_department.currentText()
        n_fingers = len(self._selected_fingers)
        n_samples = len(self._samples)
        self._review_summary.setText(
            f"Employee: {emp} ({name})\n"
            f"Department: {dept}\n"
            f"Fingers: {n_fingers}, Total samples: {n_samples}"
        )

    # ------------------------------------------------------------------
    # Finalization
    # ------------------------------------------------------------------

    def _finalize_enrollment(self) -> None:
        emp = self._edit_employee_id.text().strip()
        self._summary_icon.setText("OK")
        self._summary_label.setText("Enrollment Successful")
        self._summary_label.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #27AE60; padding: 12px;"
        )
        self._summary_detail.setText(
            f"Employee {emp} enrolled with "
            f"{len(self._selected_fingers)} finger(s) "
            f"({len(self._samples)} samples total)."
        )
        self.enrollment_complete.emit(emp, list(self._samples))

    def _on_cancel(self) -> None:
        reply = QMessageBox.question(
            self,
            "Cancel Enrollment",
            "Are you sure you want to cancel?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._reset_wizard()
            self.enrollment_cancelled.emit()

    def _reset_wizard(self) -> None:
        """Reset wizard to initial state."""
        self._current_step = STEP_USER
        self._selected_fingers.clear()
        self._samples.clear()
        self._current_finger_idx = 0
        self._current_sample_num = 0

        self._edit_employee_id.clear()
        self._edit_full_name.clear()
        self._combo_department.setCurrentIndex(0)

        for btn in self._finger_buttons:
            btn.setChecked(False)

        self._capture_preview.clear()
        self._capture_preview.setText("Place finger on sensor")
        self._capture_progress.setValue(0)
        self._capture_btn.setEnabled(True)
        self._capture_btn.setText("Capture Sample")

        self._stack.setCurrentIndex(STEP_USER)
        self._step_title.setText(STEP_TITLES[STEP_USER])
        self._btn_next.setEnabled(True)
        self._btn_next.setText("Next")
        self._btn_prev.setEnabled(False)
        self._update_step_indicators()
