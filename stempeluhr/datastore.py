import datetime as dt
import itertools
from dataclasses import dataclass, field

import pandas as pd
from dateutil.relativedelta import relativedelta

from stempeluhr.config_handler import CONFIG_HANDLER
from stempeluhr.database_controller import DB_CONTROLLER
from stempeluhr.models import WorkSchedule


@dataclass
class MonthData:
    df: pd.DataFrame
    data_hash: int
    config_hash: int = field(default_factory=CONFIG_HANDLER.config_hash)

    def is_same_data(self, data_hash: int) -> bool:
        """Compare the data hash of the current month with the stored hash."""
        return self.data_hash == data_hash and self.config_hash == CONFIG_HANDLER.config_hash()


@dataclass
class Store:
    """Data store for time tracking.

    The data frame contains total_time, start_time, end_time, pause, work, break_time, and overtime for days.
    """

    df: pd.DataFrame = field(default_factory=pd.DataFrame)
    daily_data: list[tuple[str, str]] = field(default_factory=list)
    current_date: dt.date = field(default_factory=dt.date.today)
    # dict with key: (year, month) and value: MonthData, which contains the needed hashes for data and config)
    all_data: dict[(tuple[int, int]), MonthData] = field(default_factory=dict)
    total_overtime: float = field(default=0.0)
    overtime_by_year: dict[int, float] = field(default_factory=dict)
    # workaround for not to not always recompute the overtime if fast changes are done
    last_overtime_calculation: dt.datetime = field(default_factory=lambda: dt.datetime.min)
    overtime_min_delta: dt.timedelta = field(default_factory=lambda: dt.timedelta(minutes=5))

    def __post_init__(self) -> None:
        self.generate_all_data()

    def update_data(self, selected_date: dt.date | None) -> None:
        if selected_date is None:
            selected_date = self.current_date
        self.current_date = selected_date
        self.generate_daily_data(selected_date)
        month_data = self.generate_month_data(selected_date)
        self.df = month_data.df
        if dt.datetime.now() - self.last_overtime_calculation > self.overtime_min_delta:
            self.calculate_overtime_totals()

    def get_free_days(self, year: int) -> list[dt.date]:
        vacation_days = DB_CONTROLLER.get_time_off_days(year)
        holiday_list = CONFIG_HANDLER.config.get_holidays(year)
        unique_days = list(set(vacation_days + holiday_list))
        schedules = DB_CONTROLLER.get_work_schedules()
        return [day for day in unique_days if day.weekday() in _schedule_at(schedules, day).workdays]

    def generate_all_data(self) -> None:
        months_with_data = DB_CONTROLLER.get_months_with_data()
        for year, month in months_with_data:
            self.all_data[(year, month)] = self.generate_month_data(dt.date(year, month, 1))

    def get_year_data(self, year: int) -> pd.DataFrame:
        year_data = []
        for month in range(1, 13):
            selected_date = dt.datetime(year, month, 1).date()
            month_data = self.generate_month_data(selected_date)
            year_data.append(month_data.df)
        year_data_df = pd.concat(year_data)

        if year_data_df.empty:
            return year_data_df

        # Only sum numeric columns, exclude time-based columns
        numeric_columns = [
            "total_time",
            "pause",
            "work",
            "break_time",
            "overtime",
            "overtime_adjustment",
            "target_time",
        ]
        columns_to_sum = [col for col in numeric_columns if col in year_data_df.columns]

        year_data_df = year_data_df[columns_to_sum].resample("ME").sum()
        year_data_df.index = year_data_df.index.to_period("M")
        return year_data_df

    def get_project_data(self, selected_date: dt.date, whole_year: bool = False) -> pd.DataFrame:
        """Booked hours per Project: day x project for the month, month x project for the year.

        Computed on demand from the raw events (see ADR 0002); pause, target and
        overtime do not exist at this grain. Projects without time show as 0.0.
        """
        if whole_year:
            start = dt.date(selected_date.year, 1, 1)
            end = dt.date(selected_date.year + 1, 1, 1)
            full_index = pd.date_range(start, periods=12, freq="MS")
        else:
            start = selected_date.replace(day=1)
            end = start + relativedelta(months=+1)
            full_index = pd.date_range(start, end - dt.timedelta(days=1), freq="D")
        work_data = DB_CONTROLLER.get_period_work(start, end)
        events = [(dt.datetime.fromisoformat(time), action, project) for time, action, project in work_data]
        rows = []
        for day, day_events in itertools.groupby(events, key=lambda event: event[0].date()):
            key = day.replace(day=1) if whole_year else day
            for interval_start, interval_end, project in _resolve_intervals(list(day_events)):
                rows.append((pd.Timestamp(key), project, (interval_end - interval_start).total_seconds() / 3600))
        frame = pd.DataFrame(rows, columns=["day", "project", "hours"])
        if frame.empty:
            return pd.DataFrame(index=full_index)
        pivot = frame.pivot_table(index="day", columns="project", values="hours", aggfunc="sum")
        return pivot.reindex(full_index).fillna(0.0).round(2)

    def get_month_targets(self, month: dt.date) -> list[float]:
        """Daily target hours for the month; all zeros if the month predates all tracked data.

        Lets the plot draw target lines for months without any data (gap months) while
        keeping months before tracking started blank.
        """
        start = month.replace(day=1)
        days = pd.date_range(start, start + relativedelta(months=+1) - dt.timedelta(days=1), freq="D")
        months_with_data = DB_CONTROLLER.get_months_with_data()
        if not months_with_data or (month.year, month.month) < months_with_data[0]:
            return [0.0] * len(days)
        schedules = DB_CONTROLLER.get_work_schedules()
        return [_target_time_at(day.date(), schedules) for day in days]

    def generate_daily_data(self, selected_date: dt.date) -> None:
        day_work, day_pause = DB_CONTROLLER.get_day_data(selected_date)
        daily = [(time, f"{action} ({project})") for time, action, project in day_work]
        if day_pause:
            daily.append(("Pause", str(day_pause[0][1])))
        self.daily_data = daily

    def generate_month_data(self, selected_date: dt.date) -> MonthData:
        work_data, pause_data = DB_CONTROLLER.get_month_data(selected_date)
        adjustment_data = self._get_month_adjustments(selected_date)
        free_days = self.get_free_days(selected_date.year)
        schedules = DB_CONTROLLER.get_work_schedules()
        schedule_key = tuple((s.valid_from, s.settings_key()) for s in schedules)
        data_hash = hash((tuple(work_data), tuple(pause_data), tuple(adjustment_data), tuple(free_days), schedule_key))
        # check if we already have the same data computes (no config or DB data changes)
        # skip for current month, since it constantly changes
        last_data = self.all_data.get((selected_date.year, selected_date.month))
        if last_data and last_data.is_same_data(data_hash) and not self.is_current_month(selected_date):
            return last_data
        if not work_data and not adjustment_data:
            return MonthData(df=pd.DataFrame([]), data_hash=data_hash)
        return MonthData(
            df=self._generate_month_report(work_data, selected_date, free_days, pause_data, adjustment_data, schedules),
            data_hash=data_hash,
        )

    def _get_month_adjustments(self, selected_date: dt.date) -> list[tuple[dt.date, float]]:
        start = dt.date(selected_date.year, selected_date.month, 1)
        end = start + relativedelta(months=+1)
        return [(a.date, a.hours) for a in DB_CONTROLLER.get_overtime_adjustments(start, end)]

    def _generate_month_report(  # noqa: PLR0913, PLR0917
        self,
        work_data: list[tuple[str, str, str]],
        selected_date: dt.date,
        free_days: list[dt.date],
        pause_data: list[tuple[str, int]],
        adjustment_data: list[tuple[dt.date, float]],
        schedules: list[WorkSchedule],
    ) -> pd.DataFrame:
        """Generate the complete monthly report DataFrame with all columns."""
        work_df = pd.DataFrame(work_data, columns=["datetime", "event", "project"])
        # not using .apply here, it would leave an empty frame (adjustment-only month) as non-datetime dtype
        work_df["datetime"] = pd.to_datetime(work_df["datetime"])
        work_df["time"] = work_df["datetime"].dt.time
        work_df["date"] = work_df["datetime"].dt.date

        start = dt.date(selected_date.year, selected_date.month, 1)
        end = start + relativedelta(months=+1)

        report_data = []

        for day in pd.date_range(start, end - dt.timedelta(days=1), freq="D"):
            days_data = work_df[work_df["date"] == day.date()]
            calculated_time = 0.0
            # Free days adds the daily target time to the total time (in case the user still worked to get overtime)
            if day.date() in free_days:
                calculated_time += _schedule_at(schedules, day.date()).get_daily_hours_at(day.weekday()) * 60

            day_work_time, start_time, end_time = self._calculate_day_time_with_times(days_data)
            calculated_time += day_work_time
            report_data.append(
                {
                    "day": day,
                    "total_time": calculated_time,
                    "start_time": start_time,
                    "end_time": end_time,
                }
            )

        combined_df = pd.DataFrame(report_data)
        combined_df.set_index("day", inplace=True)

        if pause_data:
            pause_df = pd.DataFrame(pause_data, columns=["day", "pause"])
            pause_df["day"] = pause_df["day"].apply(pd.to_datetime)
            pause_df.set_index("day", inplace=True)
            combined_df = pd.concat([combined_df, pause_df], axis=1, sort=False)
        else:
            combined_df["pause"] = 0.0

        combined_df["pause"] = combined_df["pause"].fillna(0.0).astype(float)
        combined_df["pause"] = combined_df["pause"].apply(lambda x: round(x / 60, 2))
        combined_df["total_time"] = combined_df["total_time"].apply(lambda x: round(x / 60, 2))
        combined_df["work"] = combined_df["total_time"] - combined_df["pause"]
        combined_df["work"] = combined_df["work"].apply(lambda x: max(x, 0)).round(2)
        combined_df["break_time"] = combined_df.apply(_calculate_break_time, axis=1)
        combined_df["target_time"] = combined_df.apply(lambda row: _calculate_target_time(row, schedules), axis=1)
        combined_df["overtime"] = combined_df.apply(_calculate_overtime, axis=1)
        combined_df["overtime"] = combined_df["overtime"].round(2)

        # adjustments only count once their date has arrived, same rule as overtime
        combined_df["overtime_adjustment"] = 0.0
        today = dt.date.today()
        for adjustment_date, hours in adjustment_data:
            if adjustment_date <= today:
                combined_df.loc[pd.Timestamp(adjustment_date), "overtime_adjustment"] = hours

        return combined_df

    def _calculate_day_time_with_times(self, df: pd.DataFrame) -> tuple[float, dt.time | None, dt.time | None]:
        """Calculate the total work time in minutes for a day, along with the start and end times."""
        events = list(df[["datetime", "event", "project"]].itertuples(index=False, name=None))
        intervals = _resolve_intervals(events)
        if not intervals:
            return 0.0, None, None
        total_time = sum((end - start).total_seconds() for start, end, _ in intervals)
        return round(total_time / 60, 2), intervals[0][0].time(), intervals[-1][1].time()

    def is_current_month(self, date: dt.date) -> bool:
        now = dt.date.today()
        return (date.year, date.month) == (now.year, now.month)

    def calculate_overtime_totals(self) -> None:
        """Calculate total overtime and overtime by year."""
        self.total_overtime = 0.0
        self.overtime_by_year = {}

        # re-calculate all data (caches might be invalid)
        self.generate_all_data()
        dfs = [month_data.df for month_data in self.all_data.values() if not month_data.df.empty]
        if not dfs:
            return
        merged_df = pd.concat(dfs)
        effective_overtime = merged_df["overtime"] + merged_df["overtime_adjustment"]
        overtime_by_year = effective_overtime.groupby(merged_df.index.year).sum()  # type: ignore
        for year, value in overtime_by_year.items():
            self.overtime_by_year[year] = round(value, 2)
        self.total_overtime = round(effective_overtime.sum(), 2)
        self.last_overtime_calculation = dt.datetime.now()

    def force_overtime_recalculation(self) -> None:
        """Make the next update_data bypass the recalculation throttle (e.g. after an adjustment change)."""
        self.last_overtime_calculation = dt.datetime.min


def _resolve_intervals(
    events: list[tuple[dt.datetime, str, str]],
) -> list[tuple[dt.datetime, dt.datetime, str]]:
    """Resolve one day's events into (start, end, project) work intervals.

    A start ends an open interval of another project (Project Switch, see ADR 0002);
    a repeated start on the same project and a stop without an open interval are
    ignored. An interval still open at the end runs until now (today) or midnight
    (the user forgot to stop on a past day).
    """
    intervals = []
    open_start: dt.datetime | None = None
    open_project = ""
    for event_time, action, project in events:
        if action == "start":
            if open_start is None:
                open_start, open_project = event_time, project
            # a repeated start on the same project does not end the interval
            elif project != open_project:
                intervals.append((open_start, event_time, open_project))
                open_start, open_project = event_time, project
        elif action == "stop" and open_start is not None:
            intervals.append((open_start, event_time, open_project))
            open_start = None
    if open_start is not None:
        end_of_day = dt.datetime.combine(open_start.date() + dt.timedelta(days=1), dt.time.min)
        cap = dt.datetime.now() if open_start.date() == dt.date.today() else end_of_day
        # a start booked ahead of now has no elapsed time yet
        if cap > open_start:
            intervals.append((open_start, cap, open_project))
    return intervals


def _calculate_break_time(row: pd.Series) -> float:
    start_time = row["start_time"]
    end_time = row["end_time"]

    if pd.isna(start_time) or pd.isna(end_time) or start_time is None or end_time is None:
        return 0.0
    if not isinstance(start_time, dt.time) or not isinstance(end_time, dt.time):
        return 0.0

    try:
        start_dt = dt.datetime.combine(dt.date.today(), start_time)
        end_dt = dt.datetime.combine(dt.date.today(), end_time)
        if end_dt < start_dt:
            end_dt += dt.timedelta(days=1)

        total_minutes = (end_dt - start_dt).total_seconds() / 60
        break_minutes = total_minutes - row["total_time"] * 60
        return round(max(break_minutes / 60, 0), 2)

    except (TypeError, ValueError, AttributeError):
        return 0.0


def _schedule_at(schedules: list[WorkSchedule], day: dt.date) -> WorkSchedule:
    """Resolve the schedule effective on a day; schedules are sorted by valid_from, oldest first."""
    return next(s for s in reversed(schedules) if s.valid_from <= day)


def _calculate_target_time(row: pd.Series, schedules: list[WorkSchedule]) -> float:
    """Calculate the target time for a given row."""
    day_date = row.name.date() if hasattr(row.name, "date") else row.name  # type: ignore
    # Make typing happy, should not happen here

    if not isinstance(day_date, dt.date):
        return 0.0
    return _target_time_at(day_date, schedules)


def _target_time_at(day: dt.date, schedules: list[WorkSchedule]) -> float:
    """Target hours for a day; future days have no target yet."""
    if day > dt.date.today():
        return 0.0
    return _schedule_at(schedules, day).get_daily_hours_at(day.weekday())


def _calculate_overtime(row: pd.Series) -> float:
    today = dt.date.today()
    daily_target: float = row["target_time"]
    day_date = row.name.date() if hasattr(row.name, "date") else row.name  # type: ignore
    work_hours: float = row["work"]

    # Make typing happy, should not happen here
    if not isinstance(day_date, dt.date):
        return 0.0
    # For future dates, we cannot calculate overtime yet since the day hasn't happened
    if day_date > today:
        return 0.0
    # For today, only show positive, since we can still work to get more hours
    overtime = work_hours - daily_target
    if day_date == today:
        return max(0.0, overtime)
    return overtime


store = Store()
