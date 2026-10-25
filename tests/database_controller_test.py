import datetime as dt

import pytest

from stempeluhr.database_controller import DatabaseController
from stempeluhr.models import Event, Pause, WorkSchedule


class TestController:
    def test_get_month_data(self, db_controller: DatabaseController) -> None:
        month_data, pause_data = db_controller.get_month_data(dt.date(2025, 1, 1))
        assert len(month_data) > 0
        assert len(pause_data) == 0
        assert len(month_data) > 0
        assert month_data[2] == ("2025-01-02T06:00:00", "start", "default")

    def test_get_day_data(self, db_controller: DatabaseController) -> None:
        day_data, pause_data = db_controller.get_day_data(dt.date(2025, 1, 3))
        assert len(day_data) > 0
        assert len(pause_data) == 0
        assert day_data == [("2025-01-03T06:00:00", "start", "default"), ("2025-01-03T14:30:00", "stop", "default")]

    def test_get_day_data_limits_to_selected_day(self, db_controller: DatabaseController) -> None:
        selected_day = dt.date(2025, 1, 2)
        day_data, _ = db_controller.get_day_data(selected_day)
        day_dates = {dt.datetime.fromisoformat(ts).date() for ts, *_ in day_data}
        assert day_dates == {selected_day}

    def test_insert_event(self, db_controller: DatabaseController) -> None:
        future_date = dt.datetime(2026, 1, 1, 10, 0, 0)
        db_controller.add_event("start", future_date, "default")
        day_data, _ = db_controller.get_day_data(future_date.date())
        assert any(future_date.isoformat() in item for item in day_data)
        assert day_data[0] == (future_date.isoformat(), "start", "default")

    def test_get_last_event_returns_latest_entry(self, db_controller: DatabaseController) -> None:
        earlier_event = dt.datetime(2026, 1, 6, 8, 0)
        latest_event = dt.datetime(2026, 1, 6, 18, 0)
        db_controller.add_event("start", earlier_event, "default")
        db_controller.add_event("stop", latest_event, "default")

        last_event = db_controller.get_last_event()
        assert last_event is not None
        assert last_event.date == latest_event
        assert last_event.action == "stop"

    def test_insert_pause(self, db_controller: DatabaseController) -> None:
        future_date = dt.date(2026, 1, 2)
        db_controller.add_pause(60, future_date)
        _, pause_data = db_controller.get_day_data(future_date)
        assert any(future_date.isoformat() in item for item in pause_data)
        assert pause_data[0] == (future_date.isoformat(), 60)

    def test_delete_event(self, db_controller: DatabaseController) -> None:
        future_date = dt.datetime(2026, 1, 3, 10, 0, 0)
        db_controller.add_event("start", future_date, "default")
        db_controller.delete_event(future_date)
        day_data, _ = db_controller.get_day_data(future_date.date())
        assert not any(future_date.isoformat() in item for item in day_data)

    def test_delete_pause(self, db_controller: DatabaseController) -> None:
        future_date = dt.date(2026, 1, 4)
        db_controller.add_pause(60, future_date)
        _, pause_data = db_controller.get_day_data(future_date)
        assert any(future_date.isoformat() in item for item in pause_data)
        db_controller.update_pause(-60, future_date)
        _, pause_data = db_controller.get_day_data(future_date)
        assert pause_data[0][1] == 0

    def test_update_pause(self, db_controller: DatabaseController) -> None:
        future_date = dt.date(2026, 1, 5)
        db_controller.add_pause(60, future_date)
        db_controller.update_pause(30, future_date)
        _, pause_data = db_controller.get_day_data(future_date)
        expected_time = 60 + 30
        assert any(str(expected_time) in str(item) for item in pause_data)

    def test_add_get_remove_vacation(self, db_controller: DatabaseController) -> None:
        vacation_date = dt.date(2026, 2, 1)
        db_controller.add_time_off(vacation_date, "Vacation")
        vacation_days = db_controller.get_time_off_days(2026)
        assert vacation_date in vacation_days
        db_controller.remove_time_off(vacation_date)
        vacation_days = db_controller.get_time_off_days(2026)
        assert vacation_date not in vacation_days

    def test_reason_on_vacation(self, db_controller: DatabaseController) -> None:
        vacation_date = dt.date(2026, 2, 2)
        reason = "Sick Leave"
        db_controller.add_time_off(vacation_date, reason)
        vacation_days = db_controller.get_time_off(2026)
        assert any(vacation.date == vacation_date and vacation.reason == reason for vacation in vacation_days)

    def test_change_time_off_reason(self, db_controller: DatabaseController) -> None:
        vacation_date = dt.date(2026, 2, 3)
        initial_reason = "Vacation"
        new_reason = "Sick Leave"
        db_controller.add_time_off(vacation_date, initial_reason)
        db_controller.change_time_off_reason(vacation_date, new_reason)
        vacation_days = db_controller.get_time_off(2026)
        assert any(vacation.date == vacation_date and vacation.reason == new_reason for vacation in vacation_days)

    def test_overtime_adjustment_add_upsert_remove(self, db_controller: DatabaseController) -> None:
        day = dt.date(2026, 3, 1)
        initial_hours = -20.0
        overwritten_hours = -10.0
        db_controller.add_overtime_adjustment(day, initial_hours)
        adjustments = db_controller.get_overtime_adjustments()
        assert any(a.date == day and a.hours == initial_hours for a in adjustments)

        # adding the same date again overwrites instead of duplicating
        db_controller.add_overtime_adjustment(day, overwritten_hours)
        matching = [a for a in db_controller.get_overtime_adjustments() if a.date == day]
        assert len(matching) == 1
        assert matching[0].hours == overwritten_hours

        db_controller.remove_overtime_adjustment(day)
        assert not any(a.date == day for a in db_controller.get_overtime_adjustments())

    def test_get_overtime_adjustments_period_is_half_open(self, db_controller: DatabaseController) -> None:
        db_controller.add_overtime_adjustment(dt.date(2026, 4, 1), 1.0)
        db_controller.add_overtime_adjustment(dt.date(2026, 4, 30), 2.0)
        db_controller.add_overtime_adjustment(dt.date(2026, 5, 1), 3.0)
        period = db_controller.get_overtime_adjustments(dt.date(2026, 4, 1), dt.date(2026, 5, 1))
        assert [a.hours for a in period] == [1.0, 2.0]

    def test_months_with_data_includes_adjustment_only_month(self, db_controller: DatabaseController) -> None:
        db_controller.add_overtime_adjustment(dt.date(2031, 6, 15), -5.0)
        assert (2031, 6) in db_controller.get_months_with_data()
        assert db_controller.get_months_with_data(2031) == [(2031, 6)]

    def test_get_period_work_orders_results(self, db_controller: DatabaseController) -> None:
        random_events = [
            Event(date=dt.datetime(2030, 5, 1, 15, 45), action="stop", project="default"),
            Event(date=dt.datetime(2030, 5, 1, 6, 15), action="start", project="default"),
            Event(date=dt.datetime(2030, 5, 1, 12, 0), action="coffee", project="default"),
            Event(date=dt.datetime(2030, 5, 1, 14, 0), action="resume", project="default"),
        ]

        with db_controller.session_scope() as session:
            session.add_all(random_events)

        period = db_controller.get_period_work(dt.date(2030, 5, 1), dt.date(2030, 5, 2))
        timestamps = [dt.datetime.fromisoformat(ts) for ts, *_ in period]

        assert timestamps == sorted(event.date for event in random_events)

    def test_get_event_projects_distinct_with_null_as_default(self, db_controller: DatabaseController) -> None:
        with db_controller.session_scope() as session:
            session.add(Event(date=dt.datetime(2030, 6, 1, 8, 0), action="start", project=None))
            session.add(Event(date=dt.datetime(2030, 6, 1, 9, 0), action="stop", project="ProjectX"))

        projects = db_controller.get_event_projects()
        assert projects == sorted(projects)
        assert {"Default", "ProjectX", "default"} <= set(projects)

    def test_get_period_work_reads_null_project_as_default(self, db_controller: DatabaseController) -> None:
        with db_controller.session_scope() as session:
            session.add(Event(date=dt.datetime(2030, 7, 1, 8, 0), action="start", project=None))

        period = db_controller.get_period_work(dt.date(2030, 7, 1), dt.date(2030, 7, 2))
        assert period == [("2030-07-01T08:00:00", "start", "Default")]

    def test_get_period_pause_orders_results(self, db_controller: DatabaseController) -> None:
        random_pauses = [
            Pause(date=dt.date(2030, 5, 3), time=45),
            Pause(date=dt.date(2030, 5, 1), time=15),
            Pause(date=dt.date(2030, 5, 2), time=30),
        ]

        with db_controller.session_scope() as session:
            session.add_all(random_pauses)

        period = db_controller.get_period_pause(dt.date(2030, 5, 1), dt.date(2030, 5, 3))
        pause_dates = [date for date, _ in period]

        # end is exclusive: the pause on May 3 must not leak into the period
        assert pause_dates == ["2030-05-01", "2030-05-02"]

    def test_get_months_with_data(self, db_controller: DatabaseController) -> None:
        months = db_controller.get_months_with_data()
        expected_months = {(2025, m) for m in range(1, 13)}
        assert months == sorted(expected_months)

    @pytest.mark.parametrize(
        "year, has_data",
        [(2025, True), (2024, False), (2026, False), (None, True)],
    )
    def test_get_months_with_data_for_specific_year(
        self, db_controller: DatabaseController, year: int | None, has_data: bool
    ) -> None:
        result = db_controller.get_months_with_data(year)
        assert (len(result) > 0) == has_data


def _schedule(valid_from: dt.date, work_hours: float = 40.0) -> WorkSchedule:
    return WorkSchedule(
        valid_from=valid_from,
        work_hours=work_hours,
        use_hours_per_week=True,
        workdays=[0, 1, 2, 3, 4],
        different_workdays=False,
        time_per_day=[8.0, 8.0, 8.0, 8.0, 8.0, 0.0, 0.0],
    )


class TestWorkSchedules:
    def test_controller_always_has_baseline_schedule(self, db_controller: DatabaseController) -> None:
        schedules = db_controller.get_work_schedules()
        assert len(schedules) == 1
        assert schedules[0].valid_from == dt.date.min
        # seeding is a no-op once any schedule exists
        db_controller.seed_work_schedule_if_empty(_schedule(dt.date(2025, 1, 1)))
        assert len(db_controller.get_work_schedules()) == 1

    def test_upsert_collapses_same_day_changes(self, db_controller: DatabaseController) -> None:
        change_date = dt.date(2025, 6, 1)
        db_controller.upsert_work_schedule(_schedule(dt.date.min, work_hours=99.0))
        db_controller.upsert_work_schedule(_schedule(change_date, work_hours=38.0))
        db_controller.upsert_work_schedule(_schedule(change_date, work_hours=35.0))
        schedules = db_controller.get_work_schedules()
        assert [s.valid_from for s in schedules] == [dt.date.min, change_date]
        assert db_controller.get_work_schedule_at(change_date).work_hours == 35.0

    def test_upsert_reverting_to_predecessor_removes_row(self, db_controller: DatabaseController) -> None:
        """Changing settings back to the previous schedule's values deletes the now-pointless row."""
        change_date = dt.date(2025, 6, 1)
        db_controller.upsert_work_schedule(_schedule(dt.date.min, work_hours=99.0))
        db_controller.upsert_work_schedule(_schedule(change_date, work_hours=38.0))
        db_controller.upsert_work_schedule(_schedule(change_date, work_hours=99.0))
        assert [s.valid_from for s in db_controller.get_work_schedules()] == [dt.date.min]

    def test_schedule_resolution_boundaries(self, db_controller: DatabaseController) -> None:
        change_date = dt.date(2025, 6, 1)
        db_controller.upsert_work_schedule(_schedule(dt.date.min, work_hours=38.0))
        db_controller.upsert_work_schedule(_schedule(change_date, work_hours=40.0))
        assert db_controller.get_work_schedule_at(change_date - dt.timedelta(days=1)).work_hours == 38.0
        assert db_controller.get_work_schedule_at(change_date).work_hours == 40.0

    def test_update_refuses_date_collision(self, db_controller: DatabaseController) -> None:
        june_date, july_date = dt.date(2025, 6, 1), dt.date(2025, 7, 1)
        db_controller.upsert_work_schedule(_schedule(dt.date.min, work_hours=99.0))
        db_controller.upsert_work_schedule(_schedule(june_date, work_hours=36.0))
        db_controller.upsert_work_schedule(_schedule(july_date))
        july = next(s for s in db_controller.get_work_schedules() if s.valid_from == july_date)
        assert db_controller.update_work_schedule(july.ID, _schedule(june_date)) is False
        moved = _schedule(dt.date(2025, 8, 1), work_hours=30.0)
        assert db_controller.update_work_schedule(july.ID, moved) is True
        schedules = db_controller.get_work_schedules()
        assert [s.valid_from for s in schedules] == [dt.date.min, june_date, dt.date(2025, 8, 1)]
        assert schedules[2].work_hours == 30.0

    def test_delete_work_schedule(self, db_controller: DatabaseController) -> None:
        change_date = dt.date(2025, 6, 1)
        db_controller.upsert_work_schedule(_schedule(dt.date.min, work_hours=99.0))
        db_controller.upsert_work_schedule(_schedule(change_date))
        schedule = next(s for s in db_controller.get_work_schedules() if s.valid_from == change_date)
        db_controller.delete_work_schedule(schedule.ID)
        assert [s.valid_from for s in db_controller.get_work_schedules()] == [dt.date.min]
