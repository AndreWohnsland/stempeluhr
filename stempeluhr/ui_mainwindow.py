import datetime as dt
import logging
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu, QSystemTrayIcon

from stempeluhr.config_handler import CONFIG_HANDLER
from stempeluhr.database_controller import DB_CONTROLLER
from stempeluhr.icons import get_preset_icons, get_tray_icon
from stempeluhr.ui import Ui_MainWindow
from stempeluhr.ui_config_window import ConfigWindow
from stempeluhr.ui_controller import UI_CONTROLLER as UIC
from stempeluhr.ui_data_window import DataWindow
from stempeluhr.ui_overtime_window import OvertimeWindow
from stempeluhr.ui_schedule_window import ScheduleWindow
from stempeluhr.ui_vacation_window import VacationWindow
from stempeluhr.updater import UPDATER
from stempeluhr.utils import open_folder_in_explorer

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self) -> None:
        """Init. Many of the button and List connects are in pass_setup."""
        super().__init__()
        self.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint)
        self.icons = get_preset_icons()
        self.clock_icon = self.icons.clock
        self.connect_buttons()
        self.connect_actions()
        self.set_tray()
        self.menubar.setNativeMenuBar(False)  # for macOS to show the menu bar in the app window
        self.setWindowIcon(self.clock_icon)
        self.update_project_names()
        # set manual here, since it does not recognize the hidden state at init somehow.
        # The default app shows the elements and got the additional height.
        self.past_datetime_edit.hide()
        self.past_datetime_edit.setDateTime(dt.datetime.now())
        self.back_button.hide()
        self.resize_mainwindow(0, -80)
        self.data_window = DataWindow(self)
        self.config_window: ConfigWindow | None = None
        self.vacation_window: VacationWindow | None = None
        self.overtime_window: OvertimeWindow | None = None
        self.schedule_window: ScheduleWindow | None = None
        self.update_last_event_label()

    def connect_buttons(self) -> None:
        # lambdas swallow the clicked(checked) bool, which would otherwise land in check_past_entry
        self.start_button.clicked.connect(lambda: self.add_start())  # noqa: PLW0108
        self.stop_button.clicked.connect(lambda: self.add_stop())  # noqa: PLW0108
        self.pause_button.clicked.connect(lambda: self.add_pause())  # noqa: PLW0108
        self.back_button.clicked.connect(self.hide_ui_elements)

    def set_tray(self) -> None:
        """Populate the tray icon and menu."""
        # Need to check if tray icon already exists
        existing_tray_icons = QApplication.instance().topLevelWidgets()  # type: ignore
        tray_icon_exists = any(isinstance(widget, QSystemTrayIcon) for widget in existing_tray_icons)
        if tray_icon_exists:
            return

        # Set the tray
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(self.clock_icon))
        self.tray_icon.setToolTip("Stempeluhr")
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.handle_tray_click)
        tray_menu = QMenu(self)
        self.tray_icon.setContextMenu(tray_menu)

        # Exit
        self.add_tray_menu_option(tray_menu, self.icons.exit, "Exit", self.close_app)
        # graph and data table
        self.add_tray_menu_option(tray_menu, self.icons.stats, "Data", self.show_data_window)
        # Mainwindow
        self.add_tray_menu_option(tray_menu, self.icons.setting, "Setup", self.restore_window)
        # Stop
        self.add_tray_menu_option(tray_menu, self.icons.stop, "Stop", lambda: self.add_stop(False))
        # Start
        self.add_tray_menu_option(tray_menu, self.icons.start, "Start", lambda: self.add_start(False))

    def add_tray_menu_option(self, tray_menu: QMenu, icon: QIcon, text: str, action: Callable[[], None]) -> None:
        start_action = QAction(icon, text, self)
        start_action.triggered.connect(action)
        tray_menu.addAction(start_action)

    def update_project_names(self) -> None:
        """Update the project names in the project input box."""
        self.input_project.clear()
        self.input_project.addItems(CONFIG_HANDLER.config.project_names)

    def close_app(self) -> None:
        """Close the app after asking the user."""
        if UIC.user_okay("Do you want to quit the application?"):
            QApplication.quit()

    def restore_window(self) -> None:
        # Show window when tray icon is clicked
        self.showNormal()
        self.activateWindow()

    def handle_tray_click(self, reason: Any) -> None:
        """Restore the window when the tray icon is clicked."""
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):  # type: ignore
            self.restore_window()

    def connect_actions(self) -> None:
        self.action_configuration.triggered.connect(self.show_config_window)
        self.action_report.triggered.connect(self.show_data_window)
        self.action_save_folder.triggered.connect(UIC.get_save_folder)
        # TODO: updater only works for git-clone installs; hidden until it handles pip/exe installs
        self.action_update.setVisible(False)
        self.action_update.triggered.connect(self.get_updates)
        self.action_past_entry.triggered.connect(self.show_ui_elements)
        self.action_about.triggered.connect(UIC.display_about)
        self.action_open_folder.triggered.connect(lambda _: open_folder_in_explorer())
        self.action_set_vacation.triggered.connect(self.show_vacation_window)
        self.action_overtime_adjustment.triggered.connect(self.show_overtime_window)

    def show_ui_elements(self) -> None:
        """Show the past time elements."""
        if self.is_past_time:
            return
        self.past_datetime_edit.show()
        self.past_datetime_edit.setDateTime(dt.datetime.now())
        self.back_button.show()
        self.resize_mainwindow(0, 80)

    def hide_ui_elements(self) -> None:
        """Hide the past time elements."""
        if not self.is_past_time:
            return
        self.past_datetime_edit.hide()
        self.back_button.hide()
        self.resize_mainwindow(0, -80)

    @property
    def is_past_time(self) -> bool:
        """Check if the past time elements are visible."""
        return self.past_datetime_edit.isVisible() and self.back_button.isVisible()

    def resize_mainwindow(self, width: int, height: int) -> None:
        """Resize the main window with a given width and height."""
        h = self.geometry().height()
        w = self.geometry().width()
        self.resize(w + width, h + height)

    @property
    def pause(self) -> int:
        """Value of the pause box."""
        return int(self.pause_box.text())

    def set_pause(self, value: int) -> None:
        """Update the pause box with a new value."""
        self.pause_box.setValue(value)

    def add_pause(self, check_past_entry: bool = True) -> None:
        """Add a pause to the database."""
        pause = self.pause
        entry_date = dt.date.today()
        if self.is_past_time and check_past_entry:
            entry_date = self.get_past_date()
        DB_CONTROLLER.add_pause(pause, entry_date)
        self.set_pause(0)
        UIC.show_notification(
            self.tray_icon, f"Added pause of {pause} minutes on date {entry_date.strftime('%d-%m-%Y')}", "Pause Added"
        )
        self.update_other_windows()

    def get_past_date(self) -> dt.date:
        """Return the date from the past datetime edit."""
        qt_object = self.past_datetime_edit.dateTime()
        qt_date = qt_object.date()
        return dt.date(qt_date.year(), qt_date.month(), qt_date.day())

    def get_past_datetime(self) -> dt.datetime:
        """Return the datetime from the past datetime edit."""
        qt_object = self.past_datetime_edit.dateTime()
        qt_date = qt_object.date()
        qt_time = qt_object.time()
        return dt.datetime(
            qt_date.year(), qt_date.month(), qt_date.day(), qt_time.hour(), qt_time.minute(), qt_time.second()
        )

    def add_event(self, event: str, check_past_entry: bool = True) -> None:
        """Add an event to the database."""
        entry_datetime = dt.datetime.now().replace(microsecond=0)
        if self.is_past_time and check_past_entry:
            entry_datetime = self.get_past_datetime()
        project = self.input_project.currentText()
        DB_CONTROLLER.add_event(event, entry_datetime, project)
        UIC.show_notification(
            self.tray_icon, f"Added event {event} at {entry_datetime.strftime('%d-%m-%Y - %H:%M:%S')}", "Event Added"
        )
        self.update_last_event_label()

    def add_start(self, check_past_entry: bool = True) -> None:
        """Add a start event."""
        self.add_event("start", check_past_entry)
        self.update_other_windows()

    def add_stop(self, check_past_entry: bool = True) -> None:
        """Add a stop event."""
        self.add_event("stop", check_past_entry)
        self.update_other_windows()

    def update_last_event_label(self) -> None:
        """Refresh the last-event label and tray status with the latest stored event."""
        last_event = DB_CONTROLLER.get_last_event()
        if last_event is None:
            label_text = "No Events Recorded"
            tooltip = "Stempeluhr"
        else:
            timestamp = last_event.date.strftime("%Y/%m/%d %H:%M")
            project = last_event.project or "Default"
            label_text = f"{project} | {timestamp} | {last_event.action.capitalize()}"
            tooltip = f"Stempeluhr - {last_event.action.capitalize()} {timestamp}"

        self.label_last_event.setText(label_text)
        # set_tray may skip creation when another instance already owns the tray
        if hasattr(self, "tray_icon"):
            self.tray_icon.setIcon(get_tray_icon(last_event.action if last_event else None))
            self.tray_icon.setToolTip(tooltip)

    def get_updates(self) -> None:
        """Ask the user if they want to update and then update."""
        message = "Want to search and get updates? This could take a short time."
        if UIC.user_okay(message):
            logger.info("Try to update ...")
            UPDATER.update()
            logger.info("Done updating")

    def show_data_window(self) -> None:
        """Trigger to update and show the data window."""
        self.data_window.plot()
        self.data_window.update_table_data()
        self.data_window.show()

    def update_other_windows(self) -> None:
        """Update the view of the other windows dependent on data."""
        self.update_data_window()

    def update_data_window(self) -> None:
        """Update the data window if it is visible."""
        if self.data_window.isVisible():
            self.data_window.plot()
            self.data_window.update_table_data()

    def show_config_window(self) -> None:
        """Show the configuration window."""
        self.config_window = ConfigWindow(self)
        self.config_window.show()

    def show_vacation_window(self) -> None:
        """Show the vacation window."""
        self.vacation_window = VacationWindow(self)
        self.vacation_window.show()

    def show_overtime_window(self) -> None:
        """Show the overtime adjustment window."""
        self.overtime_window = OvertimeWindow(self)
        self.overtime_window.show()
