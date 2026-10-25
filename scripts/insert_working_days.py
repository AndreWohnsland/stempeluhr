import datetime as dt
import random
import sys
from pathlib import Path

import holidays
import typer

parent_path = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(parent_path))

from stempeluhr.config_handler import CONFIG_HANDLER  # noqa: E402
from stempeluhr.database_controller import DB_CONTROLLER  # noqa: E402
from stempeluhr.filepath import DATABASE_PATH  # noqa: E402


# Helper to check if a date is a working day (not weekend, not holiday, not vacation)
def is_working_day(date: dt.date, holidays: set, vacations: set, workdays: set) -> bool:
    return date.weekday() in workdays and date not in holidays and date not in vacations


def main() -> None:
    """Insert random 2025 working-day events into the real app database (not a test copy)."""
    typer.confirm(f"Insert random 2025 events into {DATABASE_PATH}?", abort=True)
    # Define the date range
    start_date = dt.date(2025, 1, 1)
    end_date = dt.date(2025, 12, 30)

    # Get holidays and vacations for 2025
    country = CONFIG_HANDLER.config.country
    subdiv = CONFIG_HANDLER.config.subdiv or None
    holidays_set = set(holidays.country_holidays(country, subdiv=subdiv, years=2025).keys())
    vacations_set = set(DB_CONTROLLER.get_time_off_days(2025))
    workdays_set = set(DB_CONTROLLER.get_work_schedule_at(dt.date.today()).workdays)

    current = start_date
    while current <= end_date:
        if is_working_day(current, holidays_set, vacations_set, workdays_set):
            # Random start between 6:00 and 7:00
            start_hour = random.randint(6, 6)
            start_minute = random.randint(0, 59)
            start_dt = dt.datetime.combine(current, dt.time(start_hour, start_minute))
            # Random end between 15:00 and 16:00
            end_hour = random.randint(15, 15)
            end_minute = random.randint(0, 59)
            end_dt = dt.datetime.combine(current, dt.time(end_hour, end_minute))
            # Insert start event
            DB_CONTROLLER.add_event("start", start_dt, "default")
            # 40% chance for a break from 12:00 to 13:00
            pause_chance = 0.8
            if random.random() < pause_chance:
                pause_start = dt.datetime.combine(current, dt.time(12, 0))
                pause_end = dt.datetime.combine(current, dt.time(13, 0))
                DB_CONTROLLER.add_event("stop", pause_start, "default")
                DB_CONTROLLER.add_event("start", pause_end, "default")
                # Add pause (60 minutes)
            # Insert end event
            DB_CONTROLLER.add_event("stop", end_dt, "default")
        current += dt.timedelta(days=1)


if __name__ == "__main__":
    typer.run(main)
