import logging
import logging.config
import os
import platform
import subprocess
from pathlib import Path

import qdarktheme
from alembic import command
from alembic.config import Config
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication
from sqlalchemy import create_engine, inspect

from stempeluhr.filepath import (
    CONFIG_PATH,
    DATABASE_PATH,
    LOG_FILE_PATH,
    MIGRATIONS_PATH,
    OLD_CONFIG_PATH,
    OLD_DATABASE_PATH,
    REPORTS_PATH,
    SAVE_FOLDER,
)
from stempeluhr.models import Base

logger = logging.getLogger(__name__)


def is_light() -> bool:
    """Return if the system uses dark or light mode."""
    hints = QGuiApplication.styleHints()  # None before the app instance exists
    return hints is None or hints.colorScheme() != Qt.ColorScheme.Dark


def get_background_color() -> str:
    """Return the icon color based on the light mode."""
    return "#f8f9fa" if is_light() else "#202124"


def get_font_color() -> str:
    """Return the font color based on the light mode."""
    return "#4d5157" if is_light() else "#e4e7eb"


def sync_theme() -> None:
    """Apply the qdarktheme stylesheet matching the OS color scheme."""
    stylesheet = qdarktheme.load_stylesheet("light" if is_light() else "dark")
    QApplication.instance().setStyleSheet(stylesheet)  # type: ignore


def prepare_data_location_and_files() -> None:
    """Create the app folder if not exists.

    Move the old config and database files to the new location.
    """
    # need to create the folder once
    if not SAVE_FOLDER.exists():
        SAVE_FOLDER.mkdir(parents=True)
    if not REPORTS_PATH.exists():
        REPORTS_PATH.mkdir(parents=True)
    # move config file
    if OLD_CONFIG_PATH.exists():
        logger.debug("Old Config found at %s, moving to new location to %s", OLD_DATABASE_PATH, DATABASE_PATH)
        OLD_CONFIG_PATH.rename(CONFIG_PATH)
    # move database file
    if OLD_DATABASE_PATH.exists():
        logger.debug("Old Database found at %s, moving to new location to %s", OLD_DATABASE_PATH, DATABASE_PATH)
        OLD_DATABASE_PATH.rename(DATABASE_PATH)


def open_folder_in_explorer(p: Path = SAVE_FOLDER) -> None:
    system = platform.system()
    resolved_path = str(p.resolve())
    if system == "Windows":
        os.startfile(resolved_path)  # type: ignore
    elif system == "Darwin":  # Mac
        subprocess.run(["open", resolved_path], check=False)
    elif system == "Linux":
        subprocess.run(["xdg-open", resolved_path], check=False)


def setup_logging(log_file_path: Path = LOG_FILE_PATH) -> None:
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "simple": {
                "format": "%(asctime)s - %(levelname)s | %(name)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "stout": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "simple",
                "stream": "ext://sys.stdout",
            },
            "stderr": {
                "class": "logging.StreamHandler",
                "level": "ERROR",
                "formatter": "simple",
                "stream": "ext://sys.stderr",
            },
            "file": {
                "class": "logging.FileHandler",
                "level": "DEBUG",
                "formatter": "simple",
                "filename": log_file_path,
            },
        },
        # third-party chatter: alembic startup notes, matplotlib font cache scan
        "loggers": {
            "alembic": {"level": "WARNING"},
            "matplotlib": {"level": "WARNING"},
        },
        "root": {
            "level": "INFO",
            "handlers": ["stout", "stderr", "file"],
        },
    }
    if not log_file_path.parent.exists():
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(logging_config)


def run_db_migrations() -> None:
    """Run the alembic migrations to update the database schema."""
    db_url = f"sqlite:///{DATABASE_PATH}"
    # no ini file: everything alembic needs at runtime is set programmatically
    alembic_cfg = Config()
    alembic_cfg.attributes["configure_logger"] = False
    alembic_cfg.set_main_option("script_location", str(MIGRATIONS_PATH))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    # the migration chain starts from the pre-alembic schema, so it cannot build a
    # fresh database: create the current schema directly and mark it as up to date
    engine = create_engine(db_url)
    if not inspect(engine).has_table("Events"):
        Base.metadata.create_all(engine)
        command.stamp(alembic_cfg, "head")
        return
    command.upgrade(alembic_cfg, "head")
