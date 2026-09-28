import sys
from collections.abc import Sequence

from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QInputDialog,
    QLayout,
    QMessageBox,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from stempeluhr import __version__
from stempeluhr.config_handler import CONFIG_HANDLER
from stempeluhr.filepath import HOME_PATH
from stempeluhr.icons import get_app_icon


class UiController:
    def __init__(self) -> None:
        """Class to abstract the UI from the main logic."""

    def show_message(self, message: str) -> None:
        """Prompt default messagebox, use a QMessageBox with OK-Button."""
        message_box = QMessageBox()
        message_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        message_box.setText(str(message))
        message_box.setWindowIcon(get_app_icon())
        message_box.setWindowTitle("Information")
        message_box.show()
        message_box.exec()

    def show_notification(self, tray_icon: QSystemTrayIcon, message: str, title: str, timeout: int = 3) -> None:
        # QT notification are prettier, but does not work properly on other than windows
        if sys.platform.startswith("win"):
            tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, timeout * 1000)
            return
        # use normal window notification on linux, note this is a fix, since this seem to crash the app on
        # C level, so we cannot even catch this error.
        self.show_message(message)

    def ask_for_report_generation(self) -> bool | None:
        message_box = QMessageBox()
        message_box.setText("Would you like to generate an Excel report?")
        message_box.setWindowTitle("Report Generation")
        message_box.setWindowIcon(get_app_icon())
        yes_button = message_box.addButton("Yes", QMessageBox.ButtonRole.YesRole)
        message_box.addButton("Cancel", QMessageBox.ButtonRole.NoRole)

        message_box.exec()
        return message_box.clickedButton() == yes_button

    def user_okay(self, text: str) -> bool:
        message_box = QMessageBox()
        message_box.setText(text)
        message_box.setWindowTitle("Confirmation required")
        message_box.setWindowIcon(get_app_icon())
        yes_button = message_box.addButton("Yes", QMessageBox.ButtonRole.YesRole)
        message_box.addButton("No", QMessageBox.ButtonRole.NoRole)
        message_box.exec()
        return message_box.clickedButton() == yes_button

    def display_about(self) -> None:
        message = (
            f"Version: {__version__}. This App was made with Python and Qt by Andre Wohnsland. "
            "Check https://github.com/AndreWohnsland/Stempeluhr for more information."
        )
        self.show_message(message)

    def get_text(self, attribute: str, parent: QWidget) -> tuple[str, bool]:
        text, ok = QInputDialog.getText(parent, "Getting data for config", f"Enter your {attribute}:")
        return (text, ok)

    def get_folder(self, current_path: str, parent: QWidget | None = None) -> str:
        if not current_path:
            current_path = str(HOME_PATH)

        dialog = QFileDialog(parent)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setDirectory(current_path)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.selectedFiles()[0]
        return ""

    def fill_table(self, table: QTableWidget, entry: Sequence) -> None:
        row_position = table.rowCount()
        table.insertRow(row_position)
        for i, data in enumerate(entry):
            table.setItem(row_position, i, QTableWidgetItem(data))

    def clear_table(self, table: QTableWidget) -> None:
        while table.rowCount() > 0:
            table.removeRow(0)

    def set_header_names(self, table: QTableWidget, name1: str, name2: str) -> None:
        header_1 = table.horizontalHeaderItem(0)
        if header_1 is not None:
            header_1.setText(name1)
        header_2 = table.horizontalHeaderItem(1)
        if header_2 is not None:
            header_2.setText(name2)

    def get_save_folder(self) -> None:
        user_path = CONFIG_HANDLER.config.save_path
        returned_path = self.get_folder(user_path)
        if returned_path:
            CONFIG_HANDLER.config.save_path = returned_path
        CONFIG_HANDLER.write_config_file()

    def delete_items_of_layout(self, layout: QLayout | None = None) -> None:
        """Recursively delete all items of the given layout."""
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                if item is None:
                    continue
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
                else:
                    self.delete_items_of_layout(item.layout())


UI_CONTROLLER = UiController()
