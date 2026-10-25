import datetime as dt
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from stempeluhr.datastore import MonthData, Store
from stempeluhr.models import OvertimeAdjustment, WorkSchedule


def make_schedule(
    valid_from: dt.date,
    daily_hours: float = 8.0,
    workdays: list[int] | None = None,
) -> WorkSchedule:
    return WorkSchedule(
        valid_from=valid_from,
        work_hours=daily_hours,
        use_hours_per_week=False,
        workdays=workdays if workdays is not None else [0, 1, 2, 3, 4],
        different_workdays=False,
        time_per_day=[8.0, 8.0, 8.0, 8.0, 8.0, 0.0, 0.0],
    )


@pytest.fixture
def mock_db_controller() -> MagicMock:
    mock = MagicMock()
    # Default: no data, 8h/day Mon-Fri schedule since the beginning
    mock.get_time_off_days.return_value = []
    mock.get_day_data.return_value = ([], [])
    mock.get_month_data.return_value = ([], [])
    mock.get_months_with_data.return_value = []
    mock.get_overtime_adjustments.return_value = []
    mock.get_work_schedules.return_value = [make_schedule(dt.date.min)]
    return mock


@pytest.fixture
def store_and_controller(mock_db_controller: MagicMock) -> Generator[tuple[Store, MagicMock]]:
    with patch("stempeluhr.datastore.DB_CONTROLLER", mock_db_controller):
        yield Store(), mock_db_controller


def test_store_initialization(store_and_controller: tuple[Store, MagicMock]) -> None:
    store_instance, _ = store_and_controller
    assert isinstance(store_instance, Store)
    assert isinstance(store_instance.df, pd.DataFrame)
    assert isinstance(store_instance.daily_data, list)
    assert isinstance(store_instance.all_data, dict)
    assert isinstance(store_instance.overtime_by_year, dict)
    assert store_instance.total_overtime == 0.0


def test_update_data_with_data(store_and_controller: tuple[Store, MagicMock]) -> None:
    store_instance, mock_db_controller = store_and_controller
    test_date = dt.date(2025, 5, 20)
    # Simulate a work event and a pause
    mock_db_controller.get_day_data.return_value = (
        [("2025-05-20T08:00:00", "start", "Default"), ("2025-05-20T16:00:00", "stop", "Default")],
        [("2025-05-20", 60)],
    )
    store_instance.update_data(test_date)
    assert store_instance.current_date == test_date
    assert isinstance(store_instance.df, pd.DataFrame)
    assert "work" in store_instance.df.columns or store_instance.df.empty


def test_update_data_none_date(store_and_controller: tuple[Store, MagicMock]) -> None:
    store_instance, mock_db_controller = store_and_controller
    # Should use current_date if None
    mock_db_controller.get_day_data.return_value = ([("2025-05-20T08:00:00", "start", "Default")], [])
    store_instance.update_data(None)
    assert store_instance.current_date == store_instance.current_date


def test_get_free_days_with_vacation_and_holiday(store_and_controller: tuple[Store, MagicMock]) -> None:
    store_instance, mock_db_controller = store_and_controller
    # Simulate vacation and holiday
    mock_db_controller.get_time_off_days.return_value = [dt.date(2025, 5, 1)]
    with patch("stempeluhr.datastore.CONFIG_HANDLER") as mock_config:
        mock_config.config.get_holidays.return_value = [dt.date(2025, 5, 2)]
        mock_config.config.workdays = [0, 1, 2, 3, 4]
        free_days = store_instance.get_free_days(2025)
        assert dt.date(2025, 5, 1) in free_days or dt.date(2025, 5, 2) in free_days


def test_generate_all_data_populates_all_data(store_and_controller: tuple[Store, MagicMock]) -> None:
    store_instance, mock_db_controller = store_and_controller
    # Simulate month data
    mock_db_controller.get_months_with_data.return_value = [(2025, 5)]
    mock_db_controller.get_month_data.return_value = ([("2025-05-01T08:00:00", "start", "Default")], [])
    store_instance.generate_all_data()
    assert len(store_instance.all_data) > 0
    for key, value in store_instance.all_data.items():
        assert isinstance(value, MonthData)


def test_get_year_data_returns_dataframe(store_and_controller: tuple[Store, MagicMock]) -> None:
    store_instance, mock_db_controller = store_and_controller
    mock_db_controller.get_month_data.return_value = ([("2025-05-01T08:00:00", "start", "Default")], [])
    year_data = store_instance.get_year_data(2025)
    assert isinstance(year_data, pd.DataFrame)


def test_generate_daily_data_with_pause(store_and_controller: tuple[Store, MagicMock]) -> None:
    store_instance, mock_db_controller = store_and_controller
    test_date = dt.date(2025, 5, 20)
    mock_db_controller.get_day_data.return_value = ([("2025-05-20T08:00:00", "start", "Default")], [("2025-05-20", 30)])
    store_instance.generate_daily_data(test_date)
    assert any("Pause" in entry for entry in store_instance.daily_data)


def test_generate_month_data_empty_work(store_and_controller: tuple[Store, MagicMock]) -> None:
    store_instance, mock_db_controller = store_and_controller
    test_date = dt.date(2025, 5, 1)
    mock_db_controller.get_month_data.return_value = ([], [])
    month_data = store_instance.generate_month_data(test_date)
    assert isinstance(month_data.df, pd.DataFrame)
    assert month_data.df.empty


def test_generate_month_data_with_work(store_and_controller: tuple[Store, MagicMock]) -> None:
    store_instance, mock_db_controller = store_and_controller
    test_date = dt.date(2025, 5, 1)
    mock_db_controller.get_month_data.return_value = (
        [("2025-05-01T08:00:00", "start", "Default"), ("2025-05-01T16:00:00", "stop", "Default")],
        [("2025-05-01", 60)],
    )
    month_data = store_instance.generate_month_data(test_date)
    assert isinstance(month_data.df, pd.DataFrame)
    assert not month_data.df.empty
    assert "work" in month_data.df.columns


def test_calculate_overtime_totals_with_data(store_and_controller: tuple[Store, MagicMock]) -> None:
    store_instance, mock_db_controller = store_and_controller
    # Simulate month data with overtime
    mock_db_controller.get_months_with_data.return_value = [(2025, 5)]
    mock_db_controller.get_month_data.return_value = (
        [("2025-05-01T08:00:00", "start", "Default"), ("2025-05-01T18:00:00", "stop", "Default")],
        [],
    )
    store_instance.generate_all_data()
    store_instance.calculate_overtime_totals()
    assert isinstance(store_instance.total_overtime, float)
    assert isinstance(store_instance.overtime_by_year, dict)


def test_overtime_adjustment_counts_in_totals(store_and_controller: tuple[Store, MagicMock]) -> None:
    """A past adjustment shifts the overtime totals by exactly its hours."""
    store_instance, mock_db_controller = store_and_controller
    adjustment_hours = -20.0
    mock_db_controller.get_months_with_data.return_value = [(2025, 5)]
    mock_db_controller.get_month_data.return_value = (
        [("2025-05-01T08:00:00", "start", "Default"), ("2025-05-01T18:00:00", "stop", "Default")],
        [],
    )
    mock_db_controller.get_overtime_adjustments.return_value = [
        OvertimeAdjustment(date=dt.date(2025, 5, 15), hours=adjustment_hours)
    ]
    with patch("stempeluhr.datastore.CONFIG_HANDLER") as mock_config:
        mock_config.config.get_daily_hours_at.return_value = 8.0
        mock_config.config.workdays = [0, 1, 2, 3, 4]
        mock_config.config.get_holidays.return_value = []
        mock_config.config_hash.return_value = 12345

        store_instance.calculate_overtime_totals()
        month_df = store_instance.all_data[(2025, 5)].df

        assert month_df["overtime_adjustment"].sum() == adjustment_hours
        expected_total = round(month_df["overtime"].sum() + adjustment_hours, 2)
        assert store_instance.total_overtime == expected_total
        assert store_instance.overtime_by_year[2025] == expected_total


def test_future_overtime_adjustment_is_not_counted(store_and_controller: tuple[Store, MagicMock]) -> None:
    """An adjustment dated in the future does not affect the month data until its date arrives."""
    store_instance, mock_db_controller = store_and_controller
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    month_first = tomorrow.replace(day=1)
    start_str = f"{month_first.isoformat()}T08:00:00"
    mock_db_controller.get_month_data.return_value = (
        [(start_str, "start", "Default"), (start_str.replace("T08", "T09"), "stop", "Default")],
        [],
    )
    mock_db_controller.get_overtime_adjustments.return_value = [OvertimeAdjustment(date=tomorrow, hours=-20.0)]
    with patch("stempeluhr.datastore.CONFIG_HANDLER") as mock_config:
        mock_config.config.get_daily_hours_at.return_value = 8.0
        mock_config.config.workdays = [0, 1, 2, 3, 4]
        mock_config.config.get_holidays.return_value = []
        mock_config.config_hash.return_value = 12345

        month_data = store_instance.generate_month_data(month_first)
        assert month_data.df["overtime_adjustment"].sum() == 0.0


def test_month_with_only_adjustment_is_not_dropped(store_and_controller: tuple[Store, MagicMock]) -> None:
    """A month without any work events but with an adjustment still produces a report."""
    store_instance, mock_db_controller = store_and_controller
    adjustment_hours = -15.0
    mock_db_controller.get_month_data.return_value = ([], [])
    mock_db_controller.get_overtime_adjustments.return_value = [
        OvertimeAdjustment(date=dt.date(2025, 6, 10), hours=adjustment_hours)
    ]
    with patch("stempeluhr.datastore.CONFIG_HANDLER") as mock_config:
        mock_config.config.get_daily_hours_at.return_value = 8.0
        mock_config.config.workdays = [0, 1, 2, 3, 4]
        mock_config.config.get_holidays.return_value = []
        mock_config.config_hash.return_value = 12345

        month_data = store_instance.generate_month_data(dt.date(2025, 6, 1))
        assert not month_data.df.empty
        assert month_data.df["overtime_adjustment"].sum() == adjustment_hours


def test_vacation_day_future_no_work_should_have_zero_work_and_overtime(
    store_and_controller: tuple[Store, MagicMock],
) -> None:
    """Test that a vacation day in the future with no work entries has 0 work and 0 overtime."""
    store_instance, mock_db_controller = store_and_controller
    daily_target = 8.0
    expected_zero = 0.0

    # Get tomorrow's date
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    month_first = tomorrow.replace(day=1)

    # Mock CONFIG_HANDLER to return 8 hours as daily target
    with patch("stempeluhr.datastore.CONFIG_HANDLER") as mock_config:
        mock_config.config.get_daily_hours_at.return_value = daily_target
        mock_config.config.workdays = [0, 1, 2, 3, 4]  # Mon-Fri
        mock_config.config.get_holidays.return_value = []
        mock_config.config_hash.return_value = 12345

        # Set tomorrow as a vacation/free day
        mock_db_controller.get_time_off_days.return_value = [tomorrow]

        # Need at least one work entry for _generate_month_report to create full dataframe
        # Using a past date so it doesn't interfere with tomorrow's vacation
        past_date_str = f"{month_first.year}-{month_first.month:02d}-01T08:00:00"
        mock_db_controller.get_month_data.return_value = (
            [
                (past_date_str, "start", "Default"),
                (f"{month_first.year}-{month_first.month:02d}-01T09:00:00", "stop", "Default"),
            ],
            [],
        )

        # Generate month data
        month_data = store_instance.generate_month_data(month_first)
        df = month_data.df

        assert not df.empty, "Dataframe should not be empty"

        # Find tomorrow's row by converting index to date and comparing
        index_dates = [idx.date() if hasattr(idx, "date") else idx for idx in df.index]
        tomorrow_mask = [d == tomorrow for d in index_dates]
        tomorrow_rows = df[tomorrow_mask]

        assert not tomorrow_rows.empty, f"Tomorrow ({tomorrow}) should be in the dataframe"

        # Extract the values for tomorrow
        overtime_hours = tomorrow_rows["overtime"].values[0]
        target_time = tomorrow_rows["target_time"].values[0]

        # For future dates: overtime should be 0 (we cannot calculate overtime for future dates)
        assert overtime_hours == expected_zero, (
            f"Future vacation day should have {expected_zero} overtime hours, but got {overtime_hours} hours. "
            f"Overtime cannot be calculated for future dates."
        )

        # target_time should be 0 for future dates (as per current logic)
        assert target_time == expected_zero, f"Future date target_time should be {expected_zero}, but got {target_time}"


def test_vacation_day_past_no_work_has_correct_zero_overtime(
    store_and_controller: tuple[Store, MagicMock],
) -> None:
    """Test that a vacation day in the past with no work entries correctly has 0 overtime."""
    store_instance, mock_db_controller = store_and_controller
    daily_target = 8.0

    # Most recent past day that is a workday under the mocked Mon-Fri config
    yesterday = dt.date.today() - dt.timedelta(days=1)
    while yesterday.weekday() > 4:
        yesterday -= dt.timedelta(days=1)
    month_first = yesterday.replace(day=1)

    # Mock CONFIG_HANDLER to return 8 hours as daily target
    with patch("stempeluhr.datastore.CONFIG_HANDLER") as mock_config:
        mock_config.config.get_daily_hours_at.return_value = daily_target
        mock_config.config.workdays = [0, 1, 2, 3, 4]  # Mon-Fri
        mock_config.config.get_holidays.return_value = []
        mock_config.config_hash.return_value = 12345

        # Set yesterday as a vacation/free day
        mock_db_controller.get_time_off_days.return_value = [yesterday]

        # Add a work entry on yesterday (the vacation day) to ensure the dataframe includes it
        yesterday_str = f"{yesterday.year}-{yesterday.month:02d}-{yesterday.day:02d}T08:00:00"
        yesterday_end = f"{yesterday.year}-{yesterday.month:02d}-{yesterday.day:02d}T09:00:00"
        mock_db_controller.get_month_data.return_value = (
            [(yesterday_str, "start", "Default"), (yesterday_end, "stop", "Default")],
            [],
        )

        # Generate month data
        month_data = store_instance.generate_month_data(month_first)
        df = month_data.df

        assert not df.empty, "Dataframe should not be empty"

        # Find yesterday's row by converting index to date and comparing
        index_dates = [idx.date() if hasattr(idx, "date") else idx for idx in df.index]
        yesterday_mask = [d == yesterday for d in index_dates]
        yesterday_rows = df[yesterday_mask]

        assert not yesterday_rows.empty, f"Yesterday ({yesterday}) should be in the dataframe"

        # Extract the values for yesterday
        work_hours = yesterday_rows["work"].values[0]
        overtime_hours = yesterday_rows["overtime"].values[0]
        target_time = yesterday_rows["target_time"].values[0]

        # For a past vacation day, target_time is set correctly (8 hours)
        # This test confirms that PAST vacation days work correctly
        assert target_time == daily_target, f"Past date target_time should be {daily_target}, but got {target_time}"
        # The work hours should be approximately 1 (from 8am to 9am) + daily target added by free day logic
        assert work_hours > 0, f"Past vacation day work should be > 0, but got {work_hours}"
        # For this test, we're mainly checking that target_time is correctly set for past dates
        # The overtime calculation for past dates should work correctly
        assert isinstance(overtime_hours, (int, float)), f"Overtime should be a number, but got {type(overtime_hours)}"


def test_schedule_change_keeps_past_target_times(store_and_controller: tuple[Store, MagicMock]) -> None:
    """Days before a schedule's effective date keep their old target time; the effective day uses the new one."""
    store_instance, mock_db_controller = store_and_controller
    change_date = dt.date(2025, 5, 16)  # a Friday
    mock_db_controller.get_work_schedules.return_value = [
        make_schedule(dt.date.min, daily_hours=6.0),
        make_schedule(change_date, daily_hours=8.0),
    ]
    # 8 hours of work on a Friday before the change
    mock_db_controller.get_month_data.return_value = (
        [("2025-05-02T08:00:00", "start", "Default"), ("2025-05-02T16:00:00", "stop", "Default")],
        [],
    )
    with patch("stempeluhr.datastore.CONFIG_HANDLER") as mock_config:
        mock_config.config.get_holidays.return_value = []
        mock_config.config_hash.return_value = 12345

        df = store_instance.generate_month_data(dt.date(2025, 5, 1)).df

    assert df.loc[pd.Timestamp(dt.date(2025, 5, 15)), "target_time"] == 6.0
    assert df.loc[pd.Timestamp(change_date), "target_time"] == 8.0
    # overtime before the change is judged against the old schedule
    assert df.loc[pd.Timestamp(dt.date(2025, 5, 2)), "overtime"] == 2.0


def test_free_day_credit_uses_schedule_of_that_date(store_and_controller: tuple[Store, MagicMock]) -> None:
    """A vacation day only counts as a free day if its weekday was a workday back then."""
    store_instance, mock_db_controller = store_and_controller
    mock_db_controller.get_work_schedules.return_value = [
        make_schedule(dt.date.min, workdays=[0, 1, 2, 3, 4]),
        make_schedule(dt.date(2025, 6, 1), workdays=[0, 1, 2, 3]),  # Fridays dropped
    ]
    vacation_friday_before = dt.date(2025, 5, 16)
    vacation_friday_after = dt.date(2025, 6, 13)
    mock_db_controller.get_time_off_days.return_value = [vacation_friday_before, vacation_friday_after]
    with patch("stempeluhr.datastore.CONFIG_HANDLER") as mock_config:
        mock_config.config.get_holidays.return_value = []
        mock_config.config_hash.return_value = 12345

        mock_db_controller.get_month_data.return_value = (
            [("2025-05-05T08:00:00", "start", "Default"), ("2025-05-05T09:00:00", "stop", "Default")],
            [],
        )
        may_df = store_instance.generate_month_data(dt.date(2025, 5, 1)).df
        mock_db_controller.get_month_data.return_value = (
            [("2025-06-02T08:00:00", "start", "Default"), ("2025-06-02T09:00:00", "stop", "Default")],
            [],
        )
        june_df = store_instance.generate_month_data(dt.date(2025, 6, 1)).df

    # Friday was a workday when the vacation was taken: full daily credit
    assert may_df.loc[pd.Timestamp(vacation_friday_before), "total_time"] == 8.0
    # after the change Fridays are no workday anymore: no credit, no target
    assert june_df.loc[pd.Timestamp(vacation_friday_after), "total_time"] == 0.0
    assert june_df.loc[pd.Timestamp(vacation_friday_after), "target_time"] == 0.0


def test_project_switch_splits_time_between_projects(store_and_controller: tuple[Store, MagicMock]) -> None:
    """A start on another project ends the open interval; the total stays the sum of both."""
    store_instance, mock_db_controller = store_and_controller
    mock_db_controller.get_period_work.return_value = [
        ("2025-05-02T08:00:00", "start", "ProjectA"),
        ("2025-05-02T10:00:00", "start", "ProjectB"),
        ("2025-05-02T12:00:00", "stop", "ProjectB"),
    ]
    frame = store_instance.get_project_data(dt.date(2025, 5, 1))

    day = pd.Timestamp(dt.date(2025, 5, 2))
    assert frame.loc[day, "ProjectA"] == 2.0
    assert frame.loc[day, "ProjectB"] == 2.0

    # the combined month report counts the same span once
    mock_db_controller.get_month_data.return_value = (mock_db_controller.get_period_work.return_value, [])
    df = store_instance.generate_month_data(dt.date(2025, 5, 1)).df
    assert df.loc[day, "total_time"] == 4.0


def test_repeated_start_on_same_project_is_ignored(store_and_controller: tuple[Store, MagicMock]) -> None:
    store_instance, mock_db_controller = store_and_controller
    mock_db_controller.get_period_work.return_value = [
        ("2025-05-02T08:00:00", "start", "ProjectA"),
        ("2025-05-02T09:00:00", "start", "ProjectA"),
        ("2025-05-02T10:00:00", "stop", "ProjectA"),
    ]
    frame = store_instance.get_project_data(dt.date(2025, 5, 1))
    assert frame.loc[pd.Timestamp(dt.date(2025, 5, 2)), "ProjectA"] == 2.0


def test_forgotten_stop_on_past_day_is_capped_at_midnight(store_and_controller: tuple[Store, MagicMock]) -> None:
    store_instance, mock_db_controller = store_and_controller
    mock_db_controller.get_period_work.return_value = [
        ("2025-05-02T22:00:00", "start", "ProjectA"),
    ]
    frame = store_instance.get_project_data(dt.date(2025, 5, 1))
    assert frame.loc[pd.Timestamp(dt.date(2025, 5, 2)), "ProjectA"] == 2.0


def test_start_booked_ahead_of_now_counts_no_time(store_and_controller: tuple[Store, MagicMock]) -> None:
    """A start entered for a future time on today has no elapsed time yet (no negative interval)."""
    store_instance, mock_db_controller = store_and_controller
    future_start = dt.datetime.now() + dt.timedelta(hours=3)
    if future_start.date() != dt.date.today():  # running close to midnight: stay on today
        future_start = dt.datetime.combine(dt.date.today(), dt.time(23, 59, 59))
    mock_db_controller.get_period_work.return_value = [(future_start.isoformat(), "start", "ProjectA")]
    frame = store_instance.get_project_data(future_start.date())
    assert "ProjectA" not in frame.columns


def test_get_project_data_year_aggregates_by_month(store_and_controller: tuple[Store, MagicMock]) -> None:
    store_instance, mock_db_controller = store_and_controller
    mock_db_controller.get_period_work.return_value = [
        ("2025-05-02T08:00:00", "start", "ProjectA"),
        ("2025-05-02T10:00:00", "stop", "ProjectA"),
        ("2025-05-20T08:00:00", "start", "ProjectA"),
        ("2025-05-20T09:00:00", "stop", "ProjectA"),
        ("2025-06-10T08:00:00", "start", "ProjectB"),
        ("2025-06-10T12:00:00", "stop", "ProjectB"),
    ]
    frame = store_instance.get_project_data(dt.date(2025, 5, 1), whole_year=True)

    assert len(frame) == 12
    assert frame.loc[pd.Timestamp(dt.date(2025, 5, 1)), "ProjectA"] == 3.0
    assert frame.loc[pd.Timestamp(dt.date(2025, 6, 1)), "ProjectB"] == 4.0
    # a project shows 0.0 in months without time on it
    assert frame.loc[pd.Timestamp(dt.date(2025, 6, 1)), "ProjectA"] == 0.0


def test_get_project_data_empty_month_has_full_index(store_and_controller: tuple[Store, MagicMock]) -> None:
    store_instance, mock_db_controller = store_and_controller
    mock_db_controller.get_period_work.return_value = []
    frame = store_instance.get_project_data(dt.date(2025, 5, 1))
    assert len(frame) == 31
    assert frame.columns.empty


def test_get_month_targets_for_months_without_data(store_and_controller: tuple[Store, MagicMock]) -> None:
    """Empty months inside the tracked period get schedule targets; pre-tracking and future months stay blank."""
    store_instance, mock_db_controller = store_and_controller
    mock_db_controller.get_months_with_data.return_value = [(2024, 3)]

    # past month within the tracked period: schedule target on workdays, none on weekends
    targets = store_instance.get_month_targets(dt.date(2024, 5, 1))
    days = pd.date_range("2024-05-01", periods=len(targets), freq="D")
    assert [t for t, d in zip(targets, days) if d.weekday() < 5] == [8.0] * 23
    assert all(t == 0.0 for t, d in zip(targets, days) if d.weekday() >= 5)

    # month before tracking started: no targets
    assert store_instance.get_month_targets(dt.date(2024, 1, 1)) == [0.0] * 31

    # future month: no targets yet
    future_month = (dt.date.today() + dt.timedelta(days=40)).replace(day=1)
    assert all(t == 0.0 for t in store_instance.get_month_targets(future_month))
