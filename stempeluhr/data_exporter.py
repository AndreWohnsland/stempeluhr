import datetime as dt
import logging
from pathlib import Path

import pandas as pd
import xlsxwriter
import xlsxwriter.format
from xlsxwriter.exceptions import XlsxWriterException

from stempeluhr.config_handler import CONFIG_HANDLER
from stempeluhr.database_controller import DB_CONTROLLER
from stempeluhr.filepath import REPORTS_PATH

logger = logging.getLogger(__name__)


class DataExporter:
    def export_data(self, df: pd.DataFrame, report_date: dt.date) -> str:
        if df.empty:
            message = "No data to export, will no generate file..."
            logger.warning(message)
            return message
        file_suffix = "time"
        file_name = f"{CONFIG_HANDLER.config.name.replace(' ', '_')}_{report_date.strftime('%m_%Y')}_{file_suffix}.xlsx"
        config_save_path = CONFIG_HANDLER.config.save_path
        save_path = REPORTS_PATH if not config_save_path else Path(config_save_path)
        file_path = save_path / file_name
        try:
            workbook = xlsxwriter.Workbook(file_path)
            bold = workbook.add_format({"bold": True})
            normal_color = workbook.add_format({"bg_color": "#4099FF", "align": "center"})
            vacation_color = workbook.add_format({"bg_color": "#00CC00", "align": "center"})
            worksheet = workbook.add_worksheet()
            cell_width = 20
            worksheet.set_column("A:G", cell_width)
            self._write_information(worksheet, bold, normal_color, vacation_color, report_date)
            self._write_times(worksheet, df, normal_color, vacation_color, report_date)
            workbook.close()
            return f"File saved at: {file_path}"
        except XlsxWriterException:
            message = f"Could not open Workbook: {file_name}, is it still opened?"
            logger.error(message)
            return message

    def _round_quarterly(self, number: float) -> float:
        return round(number * 4) / 4

    def _write_information(
        self,
        worksheet: xlsxwriter.Workbook.worksheet_class,
        bold: xlsxwriter.format.Format,
        normal_color: xlsxwriter.format.Format,
        vacation_color: xlsxwriter.format.Format,
        report_date: dt.date,
    ) -> None:
        worksheet.write("A1", "Name:", bold)
        worksheet.write("B1", CONFIG_HANDLER.config.name, normal_color)
        worksheet.write("A3", "Month:", bold)
        worksheet.write("B3", report_date.strftime("%B"), normal_color)
        worksheet.write("A4", "Year", bold)
        worksheet.write("B4", report_date.year, normal_color)
        worksheet.write("A6", "Day:")
        worksheet.write("B6", "Work Time")
        worksheet.write("C6", "Start Time")
        worksheet.write("D6", "End Time")
        worksheet.write("E6", "Break Time")
        worksheet.write("F6", "Total Time")
        worksheet.write("G6", "Overtime")

        worksheet.write("D1", "Normal Day", normal_color)
        worksheet.write("E1", "Free Day", vacation_color)

    def _write_times(
        self,
        worksheet: xlsxwriter.Workbook.worksheet_class,
        df: pd.DataFrame,
        normal_color: xlsxwriter.format.Format,
        vacation_color: xlsxwriter.format.Format,
        report_date: dt.date,
    ) -> None:
        free_days = set(
            CONFIG_HANDLER.config.get_holidays(report_date.year) + DB_CONTROLLER.get_time_off_days(report_date.year)
        )
        for i, (index, row) in enumerate(df.iterrows()):
            color = vacation_color if index.date() in free_days else normal_color  # type: ignore
            worksheet.write(f"A{7 + i}", index.strftime("%d.%m.%Y"))  # type: ignore
            _time = self._round_quarterly(max(row["work"], 0))
            worksheet.write(f"B{7 + i}", _time, color)

            self._write_time(worksheet, f"C{7 + i}", color, row.get("start_time"))
            self._write_time(worksheet, f"D{7 + i}", color, row.get("end_time"))

            self._write_value(worksheet, f"E{7 + i}", color, row.get("break_time", 0))
            self._write_value(worksheet, f"F{7 + i}", color, row.get("total_time", 0))
            self._write_value(worksheet, f"G{7 + i}", color, row.get("overtime", 0))

    def _write_value(
        self,
        worksheet: xlsxwriter.Workbook.worksheet_class,
        cell: str,
        color: xlsxwriter.format.Format,
        value: float | None = None,
    ) -> None:
        if value and not pd.isna(value):
            worksheet.write(cell, self._round_quarterly(value), color)
        else:
            worksheet.write(cell, 0, color)

    def _write_time(
        self,
        worksheet: xlsxwriter.Workbook.worksheet_class,
        cell: str,
        color: xlsxwriter.format.Format,
        value: dt.time | None = None,
    ) -> None:
        if value:
            worksheet.write(cell, value.strftime("%H:%M"), color)
        else:
            worksheet.write(cell, "-", color)


EXPORTER = DataExporter()
