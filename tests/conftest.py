import datetime as dt
import os
import tempfile
from collections.abc import Generator
from typing import Any

import pytest

# Isolate tests from the developer's real data: paths and the DB/config singletons
# resolve at import time, so the data dir must be redirected before any app import.
os.environ["STEMPELUHR_DATA_DIR"] = tempfile.mkdtemp(prefix="stempeluhr-tests-")

from stempeluhr.database_controller import DatabaseController


# Helper to check if a date is a working day (not weekend, not holiday, not vacation)
def _is_working_day(date: dt.date, holidays: set, vacations: set, workdays: set) -> bool:
    return date.weekday() in workdays and date not in holidays and date not in vacations


@pytest.fixture
def db_controller() -> Generator[DatabaseController, Any]:
    # Define the date range
    start_date = dt.date(2025, 1, 1)
    end_date = dt.date(2025, 12, 30)
    vacations_set = {dt.date(2025, 7, x) for x in range(1, 31)}  # Full vacation in July
    workdays_set = {0, 1, 2, 3, 4}

    current = start_date
    db_controller = DatabaseController(db_url=":memory:")
    while current <= end_date:
        if _is_working_day(current, set(), vacations_set, workdays_set):
            start_dt = dt.datetime.combine(current, dt.time(6, 0))
            end_dt = dt.datetime.combine(current, dt.time(14, 30))
            pause_start = dt.datetime.combine(current, dt.time(12, 0))
            pause_end = dt.datetime.combine(current, dt.time(13, 0))
            db_controller.add_event("start", start_dt, "default")
            if current.day % 2 == 0:
                db_controller.add_event("stop", pause_start, "default")
                db_controller.add_event("start", pause_end, "default")
            db_controller.add_event("stop", end_dt, "default")
        current += dt.timedelta(days=1)

    yield db_controller
