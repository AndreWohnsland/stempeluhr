"""Database controller using SQLAlchemy ORM for type-safe database operations.

This module provides the main database interface for the Stempeluhr application.
It uses SQLAlchemy ORM to provide type-safe database operations with proper Python
type hints and better developer experience.

The DatabaseController class provides high-level methods for:
- Event tracking (start/stop events)
- Pause time management
- Vacation day management
- Data retrieval for daily and monthly reports
"""

import datetime
import logging
from collections.abc import Generator
from contextlib import contextmanager

from dateutil.relativedelta import relativedelta
from sqlalchemy import create_engine, delete, func, select, update
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from stempeluhr.config_handler import CONFIG_HANDLER
from stempeluhr.filepath import DATABASE_PATH
from stempeluhr.models import Base, Event, OvertimeAdjustment, Pause, TimeOff, WorkSchedule

logger = logging.getLogger(__name__)


def _baseline_work_schedule() -> WorkSchedule:
    """Baseline schedule covering all days before the first change.

    Older versions kept these values in the config file, so they are taken over from
    there (or the former defaults) the first time the schedule table is created.
    """
    legacy = CONFIG_HANDLER.read_config_file()
    return WorkSchedule(
        valid_from=datetime.date.min,
        work_hours=legacy.get("work_hours", 40.0),
        use_hours_per_week=legacy.get("use_hours_per_week", True),
        workdays=legacy.get("workdays", [0, 1, 2, 3, 4]),
        different_workdays=legacy.get("different_workdays", False),
        time_per_day=legacy.get("time_per_day", [8.0, 8.0, 8.0, 8.0, 8.0, 0.0, 0.0]),
    )


class DatabaseController:
    """Controller Class to execute all DB queries and return results as Values / Lists / Dictionaries."""

    database_path = DATABASE_PATH

    def __init__(self, db_url: str | None = None) -> None:
        """Initialize the database controller with SQLAlchemy ORM."""
        self.call_count = 0
        if db_url is None:
            # Ensure parent directory exists
            DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{DATABASE_PATH}"
        elif not db_url.startswith("sqlite://"):
            # Handle :memory: case and other direct paths
            db_url = f"sqlite:///{db_url}"

        self.db_url = db_url
        if not self.database_path.exists():
            logger.debug("No database detected, creating Database at %s", self.database_path)

        self.engine = create_engine(self.db_url, echo=False)
        Base.metadata.create_all(self.engine)
        self.Session = scoped_session(sessionmaker(bind=self.engine, expire_on_commit=False))
        # every consumer may rely on the schedule table always resolving any date
        self.seed_work_schedule_if_empty(_baseline_work_schedule())

    def __del__(self) -> None:
        """Close the session when the object is deleted."""
        self.Session.remove()
        self.engine.dispose()

    @contextmanager
    def session_scope(self) -> Generator[Session]:
        """Provide a transactional scope around a series of operations."""
        self.call_count += 1
        # print(f"DB Call count: {self.call_count}")
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def add_event(self, event: str, entry_datetime: datetime.datetime, project: str) -> None:
        datetime_string = entry_datetime.isoformat()
        logger.info("Add Event: %s, timestamp: %s", event, datetime_string)
        with self.session_scope() as session:
            new_event = Event(date=entry_datetime, action=event, project=project)
            session.add(new_event)

    def get_last_event(self) -> Event | None:
        with self.session_scope() as session:
            stmt = select(Event).order_by(Event.date.desc()).limit(1)
            return session.execute(stmt).scalar_one_or_none()

    def add_pause(self, pause_time: int, entry_date: datetime.date) -> None:
        if self.day_exists(entry_date):
            self.update_pause(pause_time, entry_date)
        else:
            self.insert_pause(pause_time, entry_date)

    def update_pause(self, pause_time: int, date: datetime.date) -> None:
        logger.info("Updating pause time by %s at %s", pause_time, date.isoformat())
        with self.session_scope() as session:
            stmt = update(Pause).where(Pause.date == date).values(time=Pause.time + pause_time)
            session.execute(stmt)

    def insert_pause(self, pause_time: int, date: datetime.date) -> None:
        logger.info("Inserting pause time by %s at %s", pause_time, date.isoformat())
        with self.session_scope() as session:
            new_pause = Pause(date=date, time=pause_time)
            session.add(new_pause)

    def day_exists(self, date: datetime.date) -> int:
        with self.session_scope() as session:
            stmt = select(Pause).where(Pause.date == date)
            result = session.execute(stmt).scalar_one_or_none()
            return 1 if result else 0

    def get_month_data(self, search_date: datetime.date) -> tuple[list[tuple[str, str, str]], list[tuple[str, int]]]:
        start = datetime.date(search_date.year, search_date.month, 1)
        end = start + relativedelta(months=+1)
        work = self.get_period_work(start, end)
        pause = self.get_period_pause(start, end)
        return work, pause

    def get_day_data(self, day: datetime.date) -> tuple[list[tuple[str, str, str]], list[tuple[str, int]]]:
        start = day
        end = start + relativedelta(days=+1)
        work = self.get_period_work(start, end)
        pause = self.get_period_pause(start, end)
        return work, pause

    def get_period_work(self, start: datetime.date, end: datetime.date) -> list[tuple[str, str, str]]:
        with self.session_scope() as session:
            start_dt = datetime.datetime.combine(start, datetime.time.min)
            end_dt = datetime.datetime.combine(end, datetime.time.min)
            stmt = select(Event).where(Event.date >= start_dt, Event.date < end_dt).order_by(Event.date)
            results = session.execute(stmt).scalars().all()
            # events from before the project column existed read as "Default"
            return [(event.date.isoformat(), event.action, event.project or "Default") for event in results]

    def get_event_projects(self) -> list[str]:
        """Distinct project names present in the events, sorted alphabetically."""
        with self.session_scope() as session:
            stmt = select(Event.project).distinct()
            return sorted({project or "Default" for project in session.execute(stmt).scalars()})

    def get_period_pause(self, start: datetime.date, end: datetime.date) -> list[tuple[str, int]]:
        with self.session_scope() as session:
            # end-exclusive like get_period_work, else the first day of the next month leaks into the month df
            stmt = select(Pause).where(Pause.date >= start, Pause.date < end).order_by(Pause.date)
            results = session.execute(stmt).scalars().all()
            return [(pause.date.isoformat(), pause.time) for pause in results]

    def get_months_with_data(self, year: int | None = None) -> list[tuple[int, int]]:
        """Return distinct year/month combinations that have recorded events or overtime adjustments."""
        with self.session_scope() as session:
            months: set[tuple[int, int]] = set()
            for date_column in (Event.date, OvertimeAdjustment.date):
                year_col = func.strftime("%Y", date_column)
                month_col = func.strftime("%m", date_column)
                stmt = select(year_col, month_col).group_by(year_col, month_col)
                if year is not None:
                    stmt = stmt.where(year_col == str(year))
                months.update((int(y), int(m)) for y, m in session.execute(stmt).all())
            return sorted(months)

    def delete_event(self, delete_datetime: datetime.datetime) -> None:
        with self.session_scope() as session:
            stmt = delete(Event).where(Event.date == delete_datetime)
            session.execute(stmt)

    def add_time_off(self, day: datetime.date, reason: str) -> None:
        date_string = day.isoformat()
        logger.info("Adding Time Off on %s", date_string)
        with self.session_scope() as session:
            # only enter if the date does not exist
            existing = session.execute(select(TimeOff).where(TimeOff.date == day)).scalar_one_or_none()
            if not existing:
                new_vacation = TimeOff(date=day, reason=reason)
                session.add(new_vacation)

    def get_time_off_days(self, year: int) -> list[datetime.date]:
        return [vacation.date for vacation in self.get_time_off(year)]

    def get_time_off(self, year: int) -> list[TimeOff]:
        with self.session_scope() as session:
            stmt = select(TimeOff).where(
                TimeOff.date >= datetime.date(year, 1, 1),
                TimeOff.date <= datetime.date(year, 12, 31),
            )
            results = session.execute(stmt).scalars().all()
            return list(results)

    def remove_time_off(self, vacation_date: datetime.date) -> None:
        logger.info("Removing Time Off on %s", vacation_date.isoformat())
        with self.session_scope() as session:
            stmt = delete(TimeOff).where(TimeOff.date == vacation_date)
            session.execute(stmt)

    def add_overtime_adjustment(self, day: datetime.date, hours: float) -> None:
        """Add an overtime adjustment, overwriting the value if the date already has one."""
        logger.info("Adding overtime adjustment of %s h on %s", hours, day.isoformat())
        with self.session_scope() as session:
            existing = session.execute(
                select(OvertimeAdjustment).where(OvertimeAdjustment.date == day)
            ).scalar_one_or_none()
            if existing:
                existing.hours = hours
            else:
                session.add(OvertimeAdjustment(date=day, hours=hours))

    def get_overtime_adjustments(
        self, start: datetime.date | None = None, end: datetime.date | None = None
    ) -> list[OvertimeAdjustment]:
        """Return adjustments within [start, end), or all if no period is given."""
        with self.session_scope() as session:
            stmt = select(OvertimeAdjustment).order_by(OvertimeAdjustment.date)
            if start is not None:
                stmt = stmt.where(OvertimeAdjustment.date >= start)
            if end is not None:
                stmt = stmt.where(OvertimeAdjustment.date < end)
            return list(session.execute(stmt).scalars().all())

    def remove_overtime_adjustment(self, day: datetime.date) -> None:
        logger.info("Removing overtime adjustment on %s", day.isoformat())
        with self.session_scope() as session:
            stmt = delete(OvertimeAdjustment).where(OvertimeAdjustment.date == day)
            session.execute(stmt)

    def get_work_schedules(self) -> list[WorkSchedule]:
        """Return all work schedules, oldest first."""
        with self.session_scope() as session:
            stmt = select(WorkSchedule).order_by(WorkSchedule.valid_from)
            return list(session.execute(stmt).scalars().all())

    def get_work_schedule_at(self, day: datetime.date) -> WorkSchedule:
        """Return the schedule effective on the given day (the seeded baseline guarantees one exists)."""
        with self.session_scope() as session:
            stmt = (
                select(WorkSchedule)
                .where(WorkSchedule.valid_from <= day)
                .order_by(WorkSchedule.valid_from.desc())
                .limit(1)
            )
            return session.execute(stmt).scalar_one()

    def upsert_work_schedule(self, schedule: WorkSchedule) -> None:
        """Insert the schedule, or overwrite the values of the row sharing its valid_from.

        A row identical to its predecessor resolves every day the same as the predecessor,
        so it is deleted instead of stored (e.g. a change that got reverted the same day).
        """
        logger.info("Setting work schedule effective %s", schedule.valid_from.isoformat())
        with self.session_scope() as session:
            existing = session.execute(
                select(WorkSchedule).where(WorkSchedule.valid_from == schedule.valid_from)
            ).scalar_one_or_none()
            predecessor = session.execute(
                select(WorkSchedule)
                .where(WorkSchedule.valid_from < schedule.valid_from)
                .order_by(WorkSchedule.valid_from.desc())
                .limit(1)
            ).scalar_one_or_none()
            if predecessor is not None and predecessor.settings_key() == schedule.settings_key():
                if existing is not None:
                    session.delete(existing)
                return
            if existing is None:
                session.add(schedule)
                return
            self._copy_schedule_values(schedule, existing)

    def update_work_schedule(self, schedule_id: int, schedule: WorkSchedule) -> bool:
        """Update the row with the given values; False if another row already owns the valid_from."""
        with self.session_scope() as session:
            clash = session.execute(
                select(WorkSchedule).where(
                    WorkSchedule.valid_from == schedule.valid_from,
                    WorkSchedule.ID != schedule_id,  # noqa: SIM300
                )
            ).scalar_one_or_none()
            if clash is not None:
                return False
            existing = session.get_one(WorkSchedule, schedule_id)
            existing.valid_from = schedule.valid_from
            self._copy_schedule_values(schedule, existing)
            return True

    def delete_work_schedule(self, schedule_id: int) -> None:
        logger.info("Removing work schedule with id %s", schedule_id)
        with self.session_scope() as session:
            stmt = delete(WorkSchedule).where(WorkSchedule.ID == schedule_id)  # noqa: SIM300
            session.execute(stmt)

    def seed_work_schedule_if_empty(self, schedule: WorkSchedule) -> None:
        """Create the baseline schedule once; no-op if any schedule exists."""
        with self.session_scope() as session:
            if session.execute(select(WorkSchedule).limit(1)).scalar_one_or_none() is None:
                session.add(schedule)

    @staticmethod
    def _copy_schedule_values(source: WorkSchedule, target: WorkSchedule) -> None:
        target.work_hours = source.work_hours
        target.use_hours_per_week = source.use_hours_per_week
        target.workdays = source.workdays
        target.different_workdays = source.different_workdays
        target.time_per_day = source.time_per_day

    def change_time_off_reason(self, vacation_date: datetime.date, new_reason: str) -> None:
        logger.info("Changing Time Off reason on %s to %s", vacation_date.isoformat(), new_reason)
        with self.session_scope() as session:
            stmt = update(TimeOff).where(TimeOff.date == vacation_date).values(reason=new_reason)
            session.execute(stmt)


DB_CONTROLLER = DatabaseController()
