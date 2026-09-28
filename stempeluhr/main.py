import logging
import sys
from importlib.metadata import PackageNotFoundError, version
from types import TracebackType

import typer

logger = logging.getLogger(__name__)

app = typer.Typer(add_completion=False)


def _version_callback(value: bool) -> None:
    if not value:
        return
    try:
        typer.echo(version("stempeluhr"))
    except PackageNotFoundError:
        typer.echo("unknown (source install)")
    raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    _: bool = typer.Option(False, "--version", callback=_version_callback, help="Show the version and exit."),
) -> None:
    """Stempeluhr - track your working time."""
    if ctx.invoked_subcommand is None:
        run_gui()


def _log_unhandled_exception(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
    logger.critical("Unhandled exception", exc_info=(exc_type, exc, tb))


def run_gui() -> None:
    """Start the Qt application."""
    from stempeluhr.utils import prepare_data_location_and_files, run_db_migrations, setup_logging

    # Prepare the data location and files. Needs to be done before importing the main application
    setup_logging()
    # Typer replaces the hook with its console printer, which the windowed build never shows. With a
    # non-default hook PyQt6 keeps running after a slot raises, so log it instead of losing it.
    sys.excepthook = _log_unhandled_exception
    prepare_data_location_and_files()
    run_db_migrations()

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    from stempeluhr.ui_mainwindow import MainWindow
    from stempeluhr.utils import sync_theme

    try:
        qt_app = QApplication(sys.argv[:1])
        # Qt 6.8+ hides menu icons on macOS by default (Apple HIG), we want them back
        qt_app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
        w = MainWindow()
        # still keep the app running, even if the main window is closed (we use tray for the app)
        QApplication.setQuitOnLastWindowClosed(False)
        sync_theme()
        w.show()
        sys.exit(qt_app.exec())
    except Exception as e:
        logger.exception(e)
        raise
