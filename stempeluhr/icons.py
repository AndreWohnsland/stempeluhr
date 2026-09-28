from dataclasses import dataclass

import qtawesome as qta
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from stempeluhr.filepath import PACKAGE_PATH
from stempeluhr.utils import get_background_color, get_font_color

# read at import: in the onefile build the file lives in a temp dir that macOS purges after 3 days
_APP_ICON_SVG = (PACKAGE_PATH / "ui" / "stempeluhr.svg").read_text()
# stroke color the SVG is authored with, swapped for the theme color at runtime
_SVG_SOURCE_COLOR = "#4d5157"


@dataclass
class PresetIconNames:
    start = "fa5s.play"
    stop = "fa5.pause-circle"
    exit = "mdi.close-box-outline"
    stats = "fa5s.chart-line"
    table = "fa5s.table"
    setting = "fa6s.gear"
    delete = "fa5.trash-alt"
    edit = "fa5.edit"


@dataclass
class PresetIcon:
    start: QIcon
    stop: QIcon
    exit: QIcon
    stats: QIcon
    table: QIcon
    setting: QIcon
    clock: QIcon
    delete: QIcon
    delete_inverted: QIcon
    edit: QIcon
    edit_inverted: QIcon


def generate_icon(icon_name: str, color: str = "white") -> QIcon:
    return qta.icon(icon_name, color=color)


# solid glyphs (not the menu's pause-circle) so the badge stays legible at tray size
_BADGE_ICONS = {"start": ("fa5s.play", "green"), "stop": ("fa5s.pause", "orange")}


def generate_app_icon(color: str, badge: str | None = None) -> QIcon:
    """Render the Stempeluhr SVG in the given color at the common icon sizes.

    With badge ("start"/"stop"), overlay the matching glyph in the bottom-left corner.
    """
    svg = _APP_ICON_SVG.replace(_SVG_SOURCE_COLOR, color)
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    badge_icon = generate_icon(*_BADGE_ICONS[badge]) if badge in _BADGE_ICONS else None
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        if badge_icon is not None:
            badge_size = size // 2
            painter.drawPixmap(0, size - badge_size, badge_icon.pixmap(badge_size, badge_size))
        painter.end()
        icon.addPixmap(QPixmap.fromImage(image))
    return icon


def get_tray_icon(last_action: str | None) -> QIcon:
    """App icon mirroring the last event as a corner badge."""
    return generate_app_icon(get_font_color(), badge=last_action)


def get_preset_icons() -> PresetIcon:
    default_color = get_font_color()
    bg_color = get_background_color()
    return PresetIcon(
        start=generate_icon(PresetIconNames.start, "green"),
        stop=generate_icon(PresetIconNames.stop, "orange"),
        exit=generate_icon(PresetIconNames.exit, "red"),
        stats=generate_icon(PresetIconNames.stats, "#0F84FF"),
        table=generate_icon(PresetIconNames.table, default_color),
        setting=generate_icon(PresetIconNames.setting, "gray"),
        clock=generate_app_icon(default_color),
        delete=generate_icon(PresetIconNames.delete, "red"),
        delete_inverted=generate_icon(PresetIconNames.delete, bg_color),
        edit=generate_icon(PresetIconNames.edit, "#0F84FF"),
        edit_inverted=generate_icon(PresetIconNames.edit, bg_color),
    )


def get_app_icon() -> QIcon:
    return generate_app_icon(get_font_color())
