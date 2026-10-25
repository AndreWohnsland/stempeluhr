from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QListWidgetItem, QPushButton, QSizePolicy, QWidget

from stempeluhr.database_controller import DB_CONTROLLER
from stempeluhr.datastore import store
from stempeluhr.icons import get_app_icon, get_preset_icons
from stempeluhr.models import OvertimeAdjustment
from stempeluhr.ui import Ui_OvertimeWindow
from stempeluhr.ui_controller import UI_CONTROLLER

if TYPE_CHECKING:
    from stempeluhr.ui_mainwindow import MainWindow


class OvertimeWindow(QWidget, Ui_OvertimeWindow):
    def __init__(self, main_window: MainWindow) -> None:
        """Window to manage overtime adjustments (payouts, expiration or credits)."""
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

        self.date_edit.setDate(dt.date.today())
        self._generate_adjustment_list()
        self.save_button.clicked.connect(self._add_adjustment)

    def _generate_adjustment_list(self) -> None:
        """Read all the database entries and generate the list of adjustments."""
        self.list_widget_dates.clear()
        adjustments = DB_CONTROLLER.get_overtime_adjustments()
        adjustments.sort(reverse=True, key=lambda x: x.date)
        for adjustment in adjustments:
            self._add_adjustment_item(adjustment)

    def _add_adjustment_item(self, adjustment: OvertimeAdjustment) -> None:
        item = QListWidgetItem()
        item_widget = QWidget()
        prefix = "+" if adjustment.hours >= 0 else ""
        line_text = QLabel(f"{adjustment.date.strftime('%Y-%m-%d')}  |  {prefix}{adjustment.hours:g} h")
        line_text.setStyleSheet("font-size: 16px;")

        delete_button = QPushButton("")
        delete_button.clicked.connect(lambda: self._delete_adjustment_item(item, adjustment.date))
        delete_button.setIcon(get_preset_icons().delete_inverted)
        delete_button.setStyleSheet("border: 1px solid red; border-radius: 5px; padding: 5px; background-color: red;")
        delete_button.setMaximumWidth(30)
        delete_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)

        item_layout = QHBoxLayout()
        item_layout.setContentsMargins(0, 0, 0, 0)
        item_layout.addWidget(line_text)
        item_layout.addStretch()
        item_layout.addWidget(delete_button)
        item_widget.setLayout(item_layout)
        item.setSizeHint(item_widget.sizeHint())
        self.list_widget_dates.addItem(item)
        self.list_widget_dates.setItemWidget(item, item_widget)

    def _delete_adjustment_item(self, item: QListWidgetItem, date: dt.date) -> None:
        if not UI_CONTROLLER.user_okay(f"Do you want to remove the overtime adjustment on {date}?"):
            return
        DB_CONTROLLER.remove_overtime_adjustment(date)
        store.force_overtime_recalculation()
        row = self.list_widget_dates.row(item)
        self.list_widget_dates.takeItem(row)

    def _add_adjustment(self) -> None:
        """Add (or overwrite) the adjustment at the selected date."""
        hours = self.hours_select.value()
        if hours == 0:
            UI_CONTROLLER.show_message("Please enter a non-zero amount of hours.")
            return
        DB_CONTROLLER.add_overtime_adjustment(self.date_edit.date().toPyDate(), hours)
        store.force_overtime_recalculation()
        self._generate_adjustment_list()
