"""SQLAlchemy ORM models for the Stempeluhr database.

This module defines the database models using SQLAlchemy ORM for type-safe
database operations. The models mirror the existing SQLite database schema
to maintain backward compatibility while providing better developer experience.

The ORM provides:
- Type safety with proper Python type hints
- IDE autocompletion support
- Cleaner and more maintainable code
- Support for database migrations via Alembic (future)
"""

import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, create_engine
from sqlalchemy import Date as SqlDate
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class Event(Base):
    __tablename__ = "Events"

    ID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, name="Date")
    action: Mapped[str] = mapped_column(String, nullable=False, name="Action")
    project: Mapped[str | None] = mapped_column(String, nullable=True, name="Project")

    __table_args__ = (Index("idx_datetime", "Date"),)

    def __init__(self, date: datetime.datetime, action: str, project: str | None) -> None:  # noqa: D107
        self.date = date
        self.action = action
        self.project = project


class Pause(Base):
    __tablename__ = "Pause"

    ID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime.date] = mapped_column(SqlDate, nullable=False, unique=True, name="Date")
    time: Mapped[int] = mapped_column(Integer, nullable=False, name="Time")

    __table_args__ = (Index("idx_date", "Date", unique=True),)

    def __init__(self, date: datetime.date, time: int) -> None:  # noqa: D107
        self.date = date
        self.time = time


class TimeOff(Base):
    __tablename__ = "TimeOff"

    ID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime.date] = mapped_column(SqlDate, nullable=False, unique=True, name="Date")
    reason: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="Vacation",
        server_default="Vacation",
        name="Reason",
    )

    __table_args__ = (Index("idx_date_vacation", "Date", unique=True),)

    def __init__(self, date: datetime.date, reason: str = "Vacation") -> None:  # noqa: D107
        self.date = date
        self.reason = reason


class OvertimeAdjustment(Base):
    """Manual change to the overtime balance (e.g. payout or expiration), signed hours, one per date."""

    __tablename__ = "OvertimeAdjustment"

    ID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime.date] = mapped_column(SqlDate, nullable=False, unique=True, name="Date")
    hours: Mapped[float] = mapped_column(Float, nullable=False, name="Hours")

    __table_args__ = (Index("idx_date_adjustment", "Date", unique=True),)

    def __init__(self, date: datetime.date, hours: float) -> None:  # noqa: D107
        self.date = date
        self.hours = hours


class WorkSchedule(Base):
    """Work schedule effective from a date; the row with the greatest valid_from <= day applies to that day.

    The seeded baseline row uses date.min so every day resolves to a schedule.
    """

    __tablename__ = "WorkSchedule"

    ID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    valid_from: Mapped[datetime.date] = mapped_column(SqlDate, nullable=False, unique=True, name="ValidFrom")
    work_hours: Mapped[float] = mapped_column(Float, nullable=False, name="WorkHours")
    use_hours_per_week: Mapped[bool] = mapped_column(Boolean, nullable=False, name="UseHoursPerWeek")
    workdays: Mapped[list[int]] = mapped_column(JSON, nullable=False, name="Workdays")
    different_workdays: Mapped[bool] = mapped_column(Boolean, nullable=False, name="DifferentWorkdays")
    # 7 entries, Monday-Sunday
    time_per_day: Mapped[list[float]] = mapped_column(JSON, nullable=False, name="TimePerDay")

    __table_args__ = (Index("idx_valid_from", "ValidFrom", unique=True),)

    def __init__(  # noqa: D107, PLR0913, PLR0917
        self,
        valid_from: datetime.date,
        work_hours: float,
        use_hours_per_week: bool,
        workdays: list[int],
        different_workdays: bool,
        time_per_day: list[float],
    ) -> None:
        self.valid_from = valid_from
        self.work_hours = work_hours
        self.use_hours_per_week = use_hours_per_week
        self.workdays = workdays
        self.different_workdays = different_workdays
        self.time_per_day = time_per_day

    def get_daily_hours_at(self, day: int) -> float:
        """Get the work time for a specific day, 0-6, 0=Monday, 6=Sunday."""
        if day not in self.workdays:
            return 0.0
        if self.different_workdays:
            return self.time_per_day[day]
        number_work_days = len(self.workdays)
        if number_work_days == 0:
            return 0.0
        if not self.use_hours_per_week:
            return self.work_hours
        return self.work_hours / number_work_days

    def settings_key(self) -> tuple:
        """Hashable tuple of the schedule values, without the effective date."""
        return (
            self.work_hours,
            self.use_hours_per_week,
            tuple(self.workdays),
            self.different_workdays,
            tuple(self.time_per_day),
        )


def create_session_factory(db_url: str) -> sessionmaker:
    """Create a session factory for the given database URL.

    Args:
        db_url: SQLAlchemy database URL (e.g., 'sqlite:///path/to/db.db')

    Returns:
        A SQLAlchemy sessionmaker that can create new sessions

    """
    engine = create_engine(db_url, echo=False)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
