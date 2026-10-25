from __future__ import annotations

import calendar
import datetime as dt
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib.axes import Axes
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.gridspec import GridSpec
from matplotlib.ticker import FuncFormatter
from PyQt6.QtCore import QDate, QDateTime, Qt
from PyQt6.QtWidgets import QTableWidgetItem, QWidget

from stempeluhr.config_handler import CONFIG_HANDLER
from stempeluhr.data_exporter import EXPORTER
from stempeluhr.database_controller import DB_CONTROLLER
from stempeluhr.datastore import store
from stempeluhr.filepath import REPORTS_PATH
from stempeluhr.icons import get_app_icon
from stempeluhr.ui import Ui_DataWindow
from stempeluhr.ui_controller import UI_CONTROLLER as UIC
from stempeluhr.utils import get_background_color, get_font_color

if TYPE_CHECKING:
    from stempeluhr.ui_mainwindow import MainWindow


logger = logging.getLogger(__name__)


@dataclass
class EventData:
    event_time: dt.datetime
    event: str


@dataclass
class PlotColors:
    red: str = "#ff4e26"
    green: str = "#25cf5e"
    blue: str = "#2693ff"
    light_blue: str = "#7db8ff"
    purple: str = "#a26eff"
    background: str = field(default_factory=get_background_color)
    text: str = field(default_factory=get_font_color)


class DataWindow(QWidget, Ui_DataWindow):
    def __init__(self, main_window: MainWindow) -> None:
        """Init the Data Window. Connect all the signals and slots."""
        super().__init__()
        self.setupUi(self)
        self.main_window = main_window
        self.setWindowIcon(get_app_icon())
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        # setting all the params
        self.date_edit.setDateTime(QDateTime.currentDateTime())
        self.colors = PlotColors()
        _set_plot_parameters(self.colors)
        self.figure = plt.figure(figsize=(13, 8), dpi=128, tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.container.addWidget(self.canvas)

        # keep track of prev date to only update the plot on month change
        self.prev_date = self.date_edit.date()
        self.save_button.clicked.connect(self.save_plot)
        self.plot_type_group.buttonClicked.connect(self.plot)
        self.date_edit.dateChanged.connect(self.update_date)

        self.update_project_selector()
        self.project_selector.currentIndexChanged.connect(self._on_project_change)

        self.export_button.clicked.connect(self.export_data)
        self.switch_button.clicked.connect(self.switch_data_view)
        self.delete_event_button.clicked.connect(self.delete_selected_event)
        self.button_month_prev.clicked.connect(lambda: self.change_month(-1))
        self.button_month_next.clicked.connect(lambda: self.change_month(1))

        # set the date to the selected date if click on table
        self.tableWidget.itemClicked.connect(self.on_item_click)

        self.delete_button = None
        # the window opens in month view, where events cannot be deleted
        self.delete_event_button.hide()
        # workaround to prevent the date change to trigger the plot
        self.programmatic_change = False

    @property
    def view_day(self) -> bool:
        return self.switch_button.isChecked()

    @property
    def selected_date(self) -> dt.date:
        return self.date_edit.date().toPyDate()

    @property
    def plot_month(self) -> bool:
        return self.radio_month.isChecked()

    @property
    def selected_project(self) -> str | None:
        """The project the view is filtered to, None for all projects."""
        if self.project_selector.currentIndex() <= 0:
            return None
        return self.project_selector.currentText()

    def update_project_selector(self) -> None:
        """Refresh the selector with the projects found in the events, keeping the current selection."""
        current = self.project_selector.currentText()
        self.project_selector.blockSignals(True)
        self.project_selector.clear()
        self.project_selector.addItems(["All Projects", *DB_CONTROLLER.get_event_projects()])
        index = self.project_selector.findText(current)
        if index >= 0:
            self.project_selector.setCurrentIndex(index)
        self.project_selector.blockSignals(False)

    def _on_project_change(self) -> None:
        self.plot()
        self.update_table_data()

    def update_date(self) -> None:
        """Update the date and plot the new data."""
        prev_date = self.prev_date
        self.prev_date = self.date_edit.date()
        if self.programmatic_change:
            return
        store.current_date = self.selected_date
        self.update_table_data()
        # do not change plot on day change
        month_changed = prev_date.month() != self.date_edit.date().month()
        year_changed = prev_date.year() != self.date_edit.date().year()
        if (month_changed and self.plot_month) or year_changed:
            self.plot()

    def _only_change_date(self, set_date: QDate | dt.date) -> None:
        """Change date while suppressing the on change event of the date edit."""
        self.programmatic_change = True
        self.date_edit.setDate(set_date)
        self.programmatic_change = False

    def plot(self) -> None:
        self.update_project_selector()
        # clears the old values before dispatching to the selected view
        self.figure.clear()
        # update the store before plotting
        store.update_data(self.selected_date)
        # get the store date -> this is needed to show the correct month in the dropdown
        # if the user did not change it there before
        self._only_change_date(store.current_date)
        project = self.selected_project
        if project is None:
            self._plot_all_projects()
        else:
            self._plot_single_project(project)
        self.canvas.draw()

    def _plot_all_projects(self) -> None:
        # Top: small plot with only the overtime
        # Bottom: main plot with the data
        gs = GridSpec(2, 1, height_ratios=[1, 4])
        ax1 = self.figure.add_subplot(gs[1])
        ax2 = self.figure.add_subplot(gs[0], sharex=ax1)

        df = store.df.copy() if self.plot_month else store.get_year_data(store.current_date.year)
        plot_df = self.adjust_df_for_plot(df)
        self._plot_work_time(ax1, plot_df)
        self._plot_overtime(ax2, plot_df)

        sum_overtime = plot_df.overtime.sum() + plot_df.overtime_adjustment.sum()
        sum_work = plot_df.work.sum()
        title = f"Working time for {self._period_name()} | Work: {sum_work:.0f} h | Overtime: {sum_overtime:.0f} h"
        self.figure.suptitle(title, weight="bold", fontsize=15)

    def _plot_single_project(self, project: str) -> None:
        """Booked hours of one project; pause, target and overtime do not exist at this grain."""
        ax = self.figure.add_subplot(111)
        frame = store.get_project_data(store.current_date, whole_year=not self.plot_month)
        hours = frame[project] if project in frame.columns else pd.Series(0.0, index=frame.index)

        ax.bar(range(len(hours)), hours, color=self.colors.blue, zorder=2, width=0.8)
        self._style_time_axis(ax, hours.index)
        # "booked", not "work": the day-level pause cannot be attributed to a project (ADR 0002)
        ax.set_ylabel("Booked Time (h)")
        max_value = hours.max()
        for i, value in enumerate(hours):
            if value <= 0.0:
                continue
            position = (i, value + max_value * 0.012)
            ax.annotate(f"{value:.1f}", position, ha="center", va="bottom", fontsize=8, weight="bold", zorder=5)

        title = f"{project} for {self._period_name()} | Booked: {hours.sum():.1f} h"
        self.figure.suptitle(title, weight="bold", fontsize=15)

    def _period_name(self) -> str:
        if self.plot_month:
            return store.current_date.strftime("%B %Y")
        return str(store.current_date.year)

    def _plot_work_time(self, ax: Axes, df: pd.DataFrame) -> None:
        sns.barplot(
            data=df,
            x=df.index,
            y="work",
            # color=self.colors.blue,
            ax=ax,
            zorder=2,
            width=0.8,
            hue=df["is_free_day"],
            palette={True: self.colors.purple, False: self.colors.blue},
            legend=False,
        )

        self._style_time_axis(ax, df.index)
        ax.set_ylabel("Work Time (h)")

        # Add numbers above the bars
        max_value = df.work.max()
        for i, (_, row) in enumerate(df.iterrows()):
            # target line for every day that has a target (future days carry target 0)
            target = row["target_time"]
            if target > 0:
                bar_width = 0.9
                ax.hlines(target, i - bar_width / 2, i + bar_width / 2, color=self.colors.text, lw=1, ls="--", zorder=3)
            total_time = row["work"]
            # days with a target still get their (0.0) annotation, work-free days stay blank
            if total_time <= 0.0 and target <= 0:
                continue
            position = (i, total_time + max_value * 0.012)
            ax.annotate(
                f"{total_time:.1f}",
                position,
                ha="center",
                va="bottom",
                fontsize=8,
                weight="bold",
                bbox={
                    "boxstyle": "round,pad=0.0",
                    "fc": self.colors.background,
                    "ec": self.colors.background,
                    "alpha": 0.8,
                },
                zorder=5,
            )

    def _style_time_axis(self, ax: Axes, index: pd.Index) -> None:
        """Grid and day/month tick labels shared by the work-time and project plots."""
        ax.yaxis.grid(True, lw=1, ls=":", color=self.colors.text, alpha=0.2, zorder=1)
        ax.xaxis.get_label().set_visible(False)

        if self.plot_month:
            tick_labels = [day.strftime("%a %d") for day in index]
            rotation = "vertical"
        else:
            tick_labels = [month.strftime("%b") for month in index]
            rotation = "horizontal"
        ax.set_xticks(range(len(tick_labels)))
        ax.set_xticklabels(tick_labels, rotation=rotation)
        # pin the limits: the adjustment markers on the shared overtime axis otherwise autoscale in extra margin
        ax.set_xlim(-0.5, len(tick_labels) - 0.5)
        ax.tick_params(axis="x", which="both", bottom=False, top=False)

    def _plot_overtime(self, ax: Axes, df: pd.DataFrame) -> None:
        sns.barplot(
            data=df,
            x=df.index,
            y="overtime",
            hue="color",
            palette={"positive": self.colors.green, "negative": self.colors.red},
            ax=ax,
            zorder=2,
            legend=False,
        )

        add_max = df.overtime.max() * 0.01
        # Min value needs more shift because of other va behavior
        add_min = df.overtime.min() * 0.05
        for i, (_, row) in enumerate(df.iterrows()):
            overtime = row["overtime"]
            if overtime == 0.0:
                continue
            add_value = add_max if overtime > 0 else add_min
            va = "bottom" if overtime >= 0 else "top"
            position = (i, overtime + add_value)
            ax.annotate(f"{abs(overtime):.1f}", position, ha="center", va=va, fontsize=6, weight="bold", zorder=5)

        ax.tick_params(axis="x", which="both", bottom=False, top=False, labelbottom=False)
        ax.xaxis.get_label().set_visible(False)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{int(x)}"))
        ax.spines["bottom"].set_position(("data", 0))
        ax.set_ylabel("Overtime (h)")
        self._plot_adjustments(ax, df)

    def _plot_adjustments(self, ax: Axes, df: pd.DataFrame) -> None:
        """Mark overtime adjustments on the zero line.

        They can be many times the daily overtime (e.g. a 20 h payout), so drawing them
        as bars would flatten the regular overtime bars.
        """
        for i, (_, row) in enumerate(df.iterrows()):
            adjustment = row["overtime_adjustment"]
            if adjustment == 0.0:
                continue
            ax.plot(i, 0, marker="D", color=self.colors.purple, markersize=4, zorder=6)
            # place the label opposite to the day's overtime bar to avoid overlapping its value
            place_below = row["overtime"] >= 0
            ax.annotate(
                f"{adjustment:+g} h",
                (i, 0),
                xytext=(0, -12 if place_below else 6),
                textcoords="offset points",
                ha="center",
                va="top" if place_below else "bottom",
                color=self.colors.purple,
                fontsize=7,
                weight="bold",
                zorder=6,
            )

    def adjust_df_for_plot(self, df: pd.DataFrame) -> pd.DataFrame:
        """Adjust the dataframe for plotting."""
        if df.empty:
            df = self._create_dummy_df()
        df["color"] = df["overtime"].apply(lambda x: "positive" if x >= 0 else "negative")
        if self.plot_month:
            free_days = store.get_free_days(self.selected_date.year)
            df["is_free_day"] = df.index.to_series().apply(lambda x: x.date() in free_days)
        else:
            df["is_free_day"] = False
        to_keep = ["work", "overtime", "overtime_adjustment", "color", "target_time", "is_free_day"]
        return df[to_keep]

    def _create_dummy_df(self) -> pd.DataFrame:
        """Create a dummy dataframe if no data is available."""
        date = store.current_date
        if self.plot_month:
            data_points = calendar.monthrange(date.year, date.month)[1]
            index = pd.date_range(start=date.replace(day=1), periods=data_points, freq="D")
        else:
            data_points = 12
            index = pd.date_range(start=date.replace(month=1, day=1), periods=data_points, freq="ME")
        zeros = [0] * data_points
        # month view still shows target lines for tracked-but-empty months; year view stays blank
        targets = store.get_month_targets(date) if self.plot_month else zeros
        data = {"work": zeros, "pause": zeros, "overtime": zeros, "overtime_adjustment": zeros, "target_time": targets}
        return pd.DataFrame(data, index=index)

    def save_plot(self) -> None:
        """Save the plot as png."""
        folder = Path(REPORTS_PATH)
        # only use the save path if it is set
        if CONFIG_HANDLER.config.save_path:
            folder = Path(CONFIG_HANDLER.config.save_path)
        # Generate Month or Year name for the file, with the project when the view is filtered
        period = store.current_date.strftime("%Y_%m" if self.plot_month else "%Y")
        project = self.selected_project
        infix = f"_{re.sub(r'[^\w-]', '_', project)}" if project else ""
        file_name = folder / f"{period}{infix}_plot.png"

        # check if the file already exists, if so, add a suffix until the file is unique
        suffix = 1
        save_file_name = file_name
        while True:
            if not save_file_name.exists():
                break
            save_file_name = folder / f"{file_name.stem}_{suffix}{file_name.suffix}"
            suffix += 1

        self.figure.savefig(save_file_name, transparent=False, dpi=300)
        UIC.show_message(f"Plot saved to {save_file_name}")

    # Data Things
    def update_table_data(self) -> None:
        UIC.clear_table(self.tableWidget)
        store.update_data(self.selected_date)
        if self.view_day:
            self.fill_daily_data()
        else:
            self.fill_monthly_data()
        prefix = "+" if store.total_overtime >= 0 else ""
        current_year = self.selected_date.year
        overtime_year = store.overtime_by_year.get(current_year, 0)
        prefix_year = "+" if overtime_year >= 0 else ""
        self.label_overtime.setText(
            f"Overtime: {prefix}{store.total_overtime:.0f} h ({current_year}: {prefix_year}{overtime_year:.0f} h) "
        )

    def export_data(self) -> None:
        if not UIC.ask_for_report_generation():
            return
        message = EXPORTER.export_data(store.df, self.selected_date)
        UIC.show_message(message)

    def switch_data_view(self) -> None:
        if self.view_day:
            self.fill_daily_data()
            self.switch_button.setText("Day")
            self.delete_event_button.show()
            return
        self.fill_monthly_data()
        self.switch_button.setText("Month")
        self.delete_event_button.hide()

    def fill_monthly_data(self) -> None:
        UIC.clear_table(self.tableWidget)
        project = self.selected_project
        UIC.set_header_names(self.tableWidget, "Date", "Time (h)" if project is None else "Booked (h)")
        if project is None:
            for index, entry in store.df.iterrows():
                needed_data = [index.strftime("%d/%m/%Y"), str(round(entry["work"], 1))]  # type: ignore
                UIC.fill_table(self.tableWidget, needed_data)
            self._fill_project_sums()
            return
        frame = store.get_project_data(self.selected_date)
        hours = frame[project] if project in frame.columns else pd.Series(0.0, index=frame.index)
        for index, value in hours.items():
            UIC.fill_table(self.tableWidget, [index.strftime("%d/%m/%Y"), str(round(value, 1))])  # type: ignore
        UIC.fill_table(self.tableWidget, [f"Σ {project}", str(round(hours.sum(), 1))])

    def _fill_project_sums(self) -> None:
        """Month totals per project below the day rows, to compare the projects at a glance."""
        totals = store.get_project_data(self.selected_date).sum()
        for project, hours in totals.items():
            if hours > 0:
                UIC.fill_table(self.tableWidget, [f"Σ {project}", str(round(hours, 1))])

    def fill_daily_data(self) -> None:
        UIC.clear_table(self.tableWidget)
        UIC.set_header_names(self.tableWidget, "Date / Type", "Event / Pause (min)")
        for entry in store.daily_data:
            UIC.fill_table(self.tableWidget, entry)

    def delete_selected_event(self) -> None:
        event_data = self.get_selected_event()
        if event_data is None:
            return
        if not UIC.user_okay(f"Do you want to delete event {event_data.event} at: {event_data.event_time}?"):
            return
        logger.info("Delete event %s at: %s", event_data.event, event_data.event_time)
        DB_CONTROLLER.delete_event(event_data.event_time)
        store.update_data(self.selected_date)
        self.update_table_data()
        self.plot()
        self.main_window.update_last_event_label()

    def get_selected_event(self) -> EventData | None:
        selection_model = self.tableWidget.selectionModel()
        indexes = selection_model.selectedRows() if selection_model else []
        if indexes:
            row = indexes[0].row()
            datetime_item = self.tableWidget.item(row, 0)
            event_item = self.tableWidget.item(row, 1)
            if datetime_item is None or event_item is None:
                return None
            try:
                return EventData(dt.datetime.fromisoformat(datetime_item.text()), event_item.text())
            except ValueError:
                # pause, date and summary rows carry no event timestamp
                return None
        return None

    def change_month(self, delta: int) -> None:
        """Change the month to the given month."""
        current_date = self.date_edit.date()
        new_date = current_date.addMonths(delta)
        self.date_edit.setDate(new_date)

    def on_item_click(self, item: QTableWidgetItem) -> None:
        """Set the date to the selected date in the table."""
        # only continue if this is not the day view
        if self.view_day:
            return
        row = item.row()
        date_item = self.tableWidget.item(row, 0)
        if date_item is None:
            return
        try:
            date = dt.datetime.strptime(date_item.text(), "%d/%m/%Y").date()
        except ValueError:
            # the project summary rows carry no date
            return
        self.date_edit.setDate(date)


def _set_plot_parameters(colors: PlotColors) -> None:
    plt.rcParams["date.autoformatter.day"] = "%d"
    plt.rcParams["date.autoformatter.month"] = "%b"
    plt.rcParams["figure.facecolor"] = colors.background
    plt.rcParams["axes.facecolor"] = colors.background
    plt.rcParams["text.color"] = colors.text
    plt.rcParams["axes.edgecolor"] = colors.text
    plt.rcParams["xtick.color"] = colors.text
    plt.rcParams["ytick.color"] = colors.text
    plt.rcParams["axes.labelcolor"] = colors.text
    plt.rcParams["axes.titlecolor"] = colors.text
    # Despine the plot right and top
    plt.rcParams["axes.spines.right"] = False
    plt.rcParams["axes.spines.top"] = False
    plt.rcParams["font.family"] = "DejaVu Sans Mono"
    plt.set_loglevel("WARNING")
