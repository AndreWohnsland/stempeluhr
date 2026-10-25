from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from stempeluhr.database_controller import DB_CONTROLLER
from stempeluhr.datastore import store
from stempeluhr.icons import get_app_icon, get_preset_icons
from stempeluhr.models import WorkSchedule
from stempeluhr.ui_controller import UI_CONTROLLER

if TYPE_CHECKING:
    from stempeluhr.ui_mainwindow import MainWindow

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class ScheduleWindow(QWidget):
    """Manage past and future work schedules (time settings with an effective date)."""

    def __init__(self, main_window: MainWindow) -> None:  # noqa: D107
        super().__init__()
        self.main_window = main_window
        self.setWindowTitle("Past Time Settings")
        self.setWindowIcon(get_app_icon())
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        layout = QVBoxLayout(self)
        header = QLabel("Time settings and the date they apply from. Newest first, each applies until the next one.")
        header.setWordWrap(True)
        layout.addWidget(header)
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)
        self.resize(760, 480)
        self.refresh_list()

    def refresh_list(self) -> None:
        self.list_widget.clear()
        schedules = DB_CONTROLLER.get_work_schedules()
        baseline_id = schedules[0].ID
        for schedule in reversed(schedules):
            item = QListWidgetItem()
            widget = ScheduleEntryWidget(self, schedule, is_baseline=baseline_id == schedule.ID)
            item.setSizeHint(widget.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, widget)

    def schedule_data_changed(self) -> None:
        """Rebuild the list and refresh dependent views after any schedule write."""
        store.force_overtime_recalculation()
        self.main_window.update_data_window()
        self.refresh_list()
        # an open config window would otherwise show stale values and re-apply them as a new change
        config_window = self.main_window.config_window
        if config_window is not None and config_window.isVisible():
            config_window.set_schedule_values()


class ScheduleEntryWidget(QWidget):
    """Editor for one work schedule row, mirroring the config window's time settings."""

    def __init__(self, schedule_window: ScheduleWindow, schedule: WorkSchedule, is_baseline: bool) -> None:  # noqa: D107
        super().__init__()
        self.schedule_window = schedule_window
        self.schedule = schedule
        self.is_baseline = is_baseline
        self._build_ui()
        self._set_values()
        self._connect_signals()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Since:"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        top_row.addWidget(self.date_edit)
        if self.is_baseline:
            # the baseline covers everything before the first change, its date is fixed
            self.date_edit.hide()
            top_row.addWidget(QLabel("the beginning"))
        top_row.addStretch()
        self.input_working_hours = QDoubleSpinBox()
        self.input_working_hours.setMaximum(168.0)
        top_row.addWidget(self.input_working_hours)
        self.work_hours_button = QPushButton()
        self.work_hours_button.setCheckable(True)
        self.work_hours_button.setStyleSheet("padding: 4px 12px;")
        top_row.addWidget(self.work_hours_button)
        self.input_different_times = QCheckBox("Different times per day")
        top_row.addWidget(self.input_different_times)

        self.apply_button = QPushButton("Apply")
        self.apply_button.setEnabled(False)
        self.apply_button.setStyleSheet("padding: 4px 12px;")
        top_row.addWidget(self.apply_button)
        self.delete_button = QPushButton("")
        self.delete_button.setIcon(get_preset_icons().delete_inverted)
        self.delete_button.setStyleSheet(
            "border: 1px solid red; border-radius: 5px; padding: 5px; background-color: red;"
        )
        self.delete_button.setMaximumWidth(30)
        self.delete_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        if self.is_baseline:
            self.delete_button.hide()
        top_row.addWidget(self.delete_button)
        layout.addLayout(top_row)

        day_row = QHBoxLayout()
        self.day_radios: list[QRadioButton] = []
        self.day_spinboxes: list[QDoubleSpinBox] = []
        for name in DAY_NAMES:
            day_column = QVBoxLayout()
            radio = QRadioButton(name)
            # like the config window: radios as independent toggles, one per weekday
            radio.setAutoExclusive(False)
            spinbox = QDoubleSpinBox()
            spinbox.setMaximum(24.0)
            day_column.addWidget(radio)
            day_column.addWidget(spinbox)
            day_row.addLayout(day_column)
            self.day_radios.append(radio)
            self.day_spinboxes.append(spinbox)
        layout.addLayout(day_row)

    def _set_values(self) -> None:
        schedule = self.schedule
        self.date_edit.setDate(schedule.valid_from)
        self.input_working_hours.setValue(schedule.work_hours)
        self.work_hours_button.setChecked(schedule.use_hours_per_week)
        self.work_hours_button.setText("/ Week" if schedule.use_hours_per_week else "/ Day")
        self.input_different_times.setChecked(schedule.different_workdays)
        for day in range(7):
            self.day_radios[day].setChecked(day in schedule.workdays)
            self.day_spinboxes[day].setValue(schedule.time_per_day[day])
        self._update_enable_states()

    def _connect_signals(self) -> None:
        self.date_edit.dateChanged.connect(self._mark_dirty)
        self.input_working_hours.valueChanged.connect(self._mark_dirty)
        self.work_hours_button.toggled.connect(self._on_hours_mode_toggled)
        self.input_different_times.toggled.connect(self._on_structure_changed)
        for day in range(7):
            self.day_radios[day].toggled.connect(self._on_structure_changed)
            self.day_spinboxes[day].valueChanged.connect(self._mark_dirty)
        self.apply_button.clicked.connect(self._apply)
        self.delete_button.clicked.connect(self._delete)

    def _mark_dirty(self) -> None:
        self.apply_button.setEnabled(True)

    def _on_hours_mode_toggled(self, is_checked: bool) -> None:
        self.work_hours_button.setText("/ Week" if is_checked else "/ Day")
        self._mark_dirty()

    def _on_structure_changed(self) -> None:
        self._update_enable_states()
        self._mark_dirty()

    def _update_enable_states(self) -> None:
        different_times = self.input_different_times.isChecked()
        self.input_working_hours.setEnabled(not different_times)
        self.work_hours_button.setEnabled(not different_times)
        for day in range(7):
            self.day_spinboxes[day].setEnabled(different_times and self.day_radios[day].isChecked())

    def _current_values(self) -> WorkSchedule:
        valid_from = dt.date.min if self.is_baseline else self.date_edit.date().toPyDate()
        time_per_day = self.schedule.time_per_day
        if self.input_different_times.isChecked():
            time_per_day = [self.day_spinboxes[day].value() for day in range(7)]
        return WorkSchedule(
            valid_from=valid_from,
            work_hours=self.input_working_hours.value(),
            use_hours_per_week=self.work_hours_button.isChecked(),
            workdays=[day for day in range(7) if self.day_radios[day].isChecked()],
            different_workdays=self.input_different_times.isChecked(),
            time_per_day=time_per_day,
        )

    def _apply(self) -> None:
        updated = self._current_values()
        if not DB_CONTROLLER.update_work_schedule(self.schedule.ID, updated):
            UI_CONTROLLER.show_message(
                f"Another time setting already starts on {updated.valid_from}, please pick a different date."
            )
            return
        self.schedule_window.schedule_data_changed()

    def _delete(self) -> None:
        if not UI_CONTROLLER.user_okay(f"Do you want to remove the time settings from {self.schedule.valid_from}?"):
            return
        DB_CONTROLLER.delete_work_schedule(self.schedule.ID)
        self.schedule_window.schedule_data_changed()
