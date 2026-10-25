from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import holidays
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDoubleSpinBox, QRadioButton, QWidget

from stempeluhr.config_handler import CONFIG_HANDLER
from stempeluhr.database_controller import DB_CONTROLLER
from stempeluhr.datastore import store
from stempeluhr.icons import get_app_icon
from stempeluhr.models import WorkSchedule
from stempeluhr.ui import Ui_ConfigWindow
from stempeluhr.ui_schedule_window import ScheduleWindow

if TYPE_CHECKING:
    from stempeluhr.ui_mainwindow import MainWindow


class ConfigWindow(QWidget, Ui_ConfigWindow):
    def __init__(self, main_window: MainWindow) -> None:
        """Init. Many of the button and List connects are in pass_setup."""
        super().__init__()
        self.main_window = main_window
        self.setupUi(self)
        self.setWindowIcon(get_app_icon())
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.country_list = holidays.list_supported_countries()
        self._update_country_list()
        self.apply_button.clicked.connect(self.apply_config)
        self.filter_subdiv.textEdited.connect(self._apply_subdiv_filter)
        self.filter_country.textEdited.connect(self._apply_country_filter)
        self.input_country.currentTextChanged.connect(self._adjust_subdiv)
        for i in range(7):
            radio: QRadioButton = getattr(self, f"radio_weekday_{i}")
            radio.toggled.connect(lambda checked, day=i: self._handle_enable_state_of_specific_day(day, checked))
        self.input_different_times.toggled.connect(self._handle_enable_state_of_times_per_day)
        self.work_hours_button.toggled.connect(self._change_work_hours_button_text)
        self.past_settings_button.clicked.connect(self._open_schedule_window)
        self.set_config_values()

    def _handle_enable_state_of_times_per_day(self, isChecked: bool) -> None:
        """Enable or disable the input fields for each day based on the state of the 'different times' checkbox."""
        for i in range(7):
            input_box: QDoubleSpinBox = getattr(self, f"input_hours_day_{i}")
            radio: QRadioButton = getattr(self, f"radio_weekday_{i}")
            input_box.setEnabled(isChecked and radio.isChecked())
        self.work_hours_button.setEnabled(not isChecked)
        self.input_working_hours.setEnabled(not isChecked)

    def _change_work_hours_button_text(self, isChecked: bool) -> None:
        """Change the text of the work hours button based on whether it is checked or not."""
        text = "/ Week" if isChecked else "/ Day"
        self.work_hours_button.setText(text)

    def _handle_enable_state_of_specific_day(self, day: int, isChecked: bool) -> None:
        """Enable or disable the input field for a specific day based on the state of the corresponding radio button."""
        if not self.input_different_times.isChecked():
            return
        input_box: QDoubleSpinBox = getattr(self, f"input_hours_day_{day}")
        input_box.setEnabled(isChecked)

    def _update_country_list(self, country: str | None = None) -> None:
        """Update the country and subdiv list. If country is given, use this as the selected country."""
        # first choose which country to use, if selection, use this,
        # otherwise use the config country
        if country is None and self.input_country.currentText() != "":
            country = self.input_country.currentText()
        elif country is None:
            country = CONFIG_HANDLER.config.country
        subdiv_list = self.country_list.get(country, [])
        country_list = list(self.country_list.keys())
        # if there is a filter, apply it
        country_filter = self.filter_country.text()
        if country_filter:
            country_list = [c for c in country_list if country_filter.lower() in c.lower()]
        self.input_country.clear()
        self.input_country.addItems(country_list)
        self.input_country.setCurrentText(country)

        # clear filter, choose new subdiv
        self.filter_country.clear()
        self.input_subdiv.clear()
        self.input_subdiv.addItems(subdiv_list)
        self.input_subdiv.setCurrentText(CONFIG_HANDLER.config.subdiv or "")
        self.filter_subdiv.clear()

    def _adjust_subdiv(self) -> None:
        """Triggered when the country selection changes."""
        country = self.input_country.currentText()
        subdiv_list = self.country_list.get(country, [])
        self.input_subdiv.clear()
        self.input_subdiv.addItems(subdiv_list)
        if CONFIG_HANDLER.config.subdiv not in subdiv_list:
            return
        self.input_subdiv.setCurrentText(CONFIG_HANDLER.config.subdiv)

    def set_config_values(self) -> None:
        """Set config values to the input fields, other than country and subdiv."""
        self.input_name.setText(CONFIG_HANDLER.config.name)
        self.input_project_names.setText(";".join(CONFIG_HANDLER.config.project_names))
        self.set_schedule_values()

    def set_schedule_values(self) -> None:
        """Set the fields of the schedule effective today, e.g. on start or after a schedule change elsewhere."""
        schedule = DB_CONTROLLER.get_work_schedule_at(dt.date.today())
        self.input_working_hours.setValue(schedule.work_hours)
        self.work_hours_button.setChecked(schedule.use_hours_per_week)
        self.work_hours_button.setText("/ Week" if schedule.use_hours_per_week else "/ Day")
        for day in range(7):
            radio: QRadioButton = getattr(self, f"radio_weekday_{day}")
            radio.setChecked(day in schedule.workdays)
        self.input_different_times.setChecked(schedule.different_workdays)
        for i, time in enumerate(schedule.time_per_day):
            input_box: QDoubleSpinBox = getattr(self, f"input_hours_day_{i}")
            input_box.setValue(time)
            input_box.setEnabled(i in schedule.workdays and schedule.different_workdays)

    def apply_config(self) -> None:
        """Apply the config values to the config file and close the window."""
        CONFIG_HANDLER.config.country = self.input_country.currentText()
        CONFIG_HANDLER.config.subdiv = self.input_subdiv.currentText() or None
        CONFIG_HANDLER.config.name = self.input_name.text()
        CONFIG_HANDLER.config.project_names = [
            name.strip() for name in self.input_project_names.text().split(";") if name.strip()
        ]
        CONFIG_HANDLER.write_config_file()
        self._apply_schedule()
        self.main_window.update_data_window()
        self.main_window.update_project_names()
        self.close()

    def _apply_schedule(self) -> None:
        """Persist changed time settings as a new schedule effective today; past days keep their old schedule."""
        today = dt.date.today()
        current = DB_CONTROLLER.get_work_schedule_at(today)
        selected_days: list[int] = []
        for day in range(7):
            radio: QRadioButton = getattr(self, f"radio_weekday_{day}")
            if radio.isChecked():
                selected_days.append(day)
        time_per_day = current.time_per_day
        if self.input_different_times.isChecked():
            time_per_day = [getattr(self, f"input_hours_day_{i}").value() for i in range(7)]
        new_schedule = WorkSchedule(
            valid_from=today,
            work_hours=self.input_working_hours.value(),
            use_hours_per_week=self.work_hours_button.isChecked(),
            workdays=selected_days,
            different_workdays=self.input_different_times.isChecked(),
            time_per_day=time_per_day,
        )
        if new_schedule.settings_key() == current.settings_key():
            return
        DB_CONTROLLER.upsert_work_schedule(new_schedule)
        store.force_overtime_recalculation()
        # an open schedule management window would otherwise show a stale list
        schedule_window = self.main_window.schedule_window
        if schedule_window is not None and schedule_window.isVisible():
            schedule_window.refresh_list()

    def _open_schedule_window(self) -> None:
        """Open the window to manage schedules with other effective dates."""
        self.main_window.schedule_window = ScheduleWindow(self.main_window)
        self.main_window.schedule_window.show()

    def _apply_subdiv_filter(self) -> None:
        """Apply the filter to the subdiv list and update the list."""
        country = self.input_country.currentText()
        subdiv_list = self.country_list.get(country, [])
        filter_text = self.filter_subdiv.text()
        current_subdiv = self.input_subdiv.currentText()
        if filter_text:
            subdiv_list = [s for s in subdiv_list if filter_text.lower() in s.lower()]
        self.input_subdiv.clear()
        self.input_subdiv.addItems(subdiv_list)
        if current_subdiv in subdiv_list:
            self.input_subdiv.setCurrentText(current_subdiv)

    def _apply_country_filter(self) -> None:
        """Apply the filter to the country list and update the list."""
        country_list = list(self.country_list.keys())
        filter_text = self.filter_country.text()
        current_country = self.input_country.currentText()
        if filter_text:
            country_list = [c for c in country_list if filter_text.lower() in c.lower()]
        self.input_country.clear()
        self.input_country.addItems(country_list)
        if current_country in country_list:
            self.input_country.setCurrentText(current_country)
        self._adjust_subdiv()
