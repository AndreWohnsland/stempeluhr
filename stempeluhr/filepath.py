import os
import sys
from pathlib import Path

APP_NAME = "stempeluhr"
# data dir of installs from before the rename to stempeluhr; never migrated
LEGACY_APP_NAME = "time_tracker"


def _sanitize_name(name: str) -> str:
    """Convert spaces to underscores and converts to lowercase."""
    return name.replace(" ", "_").lower()


def get_app_dir(app_name: str = APP_NAME) -> Path:
    """Get the application directory for the current platform."""
    app_name = _sanitize_name(app_name)
    # Windows
    if sys.platform.startswith("win"):
        app_folder = os.environ.get("APPDATA")
        if app_folder is None:
            app_folder = os.path.expanduser("~")  # noqa: PTH111
        return Path(app_folder) / app_name
    # MacOS
    if sys.platform == "darwin":
        return Path("~/Library/Application Support").expanduser() / app_name
    # Linux
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path("~/.config").expanduser()))) / app_name


# Repo root for git-based installs (points into site-packages for pip installs)
ROOT_PATH = Path(__file__).resolve().parents[1]
PACKAGE_PATH = Path(__file__).resolve().parent
HOME_PATH = Path.home()


def _data_folder() -> Path:
    # STEMPELUHR_DATA_DIR redirects all app data (db, config, logs, reports), e.g. for tests or a sandbox
    if override := os.environ.get("STEMPELUHR_DATA_DIR"):
        return Path(override)
    # keep the pre-rename dir if it already exists
    legacy = get_app_dir(LEGACY_APP_NAME)
    return legacy if legacy.exists() else get_app_dir()


# Data folder (app data)
SAVE_FOLDER = _data_folder()

# DB
OLD_DATABASE_PATH = ROOT_PATH / "data" / "timedata.db"
DATABASE_PATH = SAVE_FOLDER / "time_data.db"

# config
OLD_CONFIG_PATH = ROOT_PATH / "config" / "config.json"
CONFIG_PATH = SAVE_FOLDER / "config.json"

# saved reports (default one)
REPORTS_PATH = SAVE_FOLDER / "reports"

# Logs
LOG_FILE_PATH = SAVE_FOLDER / "app.log"

# Alembic
MIGRATIONS_PATH = PACKAGE_PATH / "migrations"
