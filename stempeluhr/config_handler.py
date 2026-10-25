import datetime as dt
import json
from dataclasses import asdict, dataclass
from inspect import signature
from typing import Any, Literal

import holidays

from stempeluhr.filepath import CONFIG_PATH

# Fill data currently not in the config file,
# need at least all that config has
NEEDED_DATA = {
    "name": "",
    "project_names": ["Default"],
    "save_path": "",
    "country": "US",
    "subdiv": None,
}
CONFIG_NAMES = Literal[
    "name",
    "project_names",
    "save_path",
    "country",
    "subdiv",
]


@dataclass
class Config:
    name: str
    project_names: list[str]
    save_path: str
    country: str
    subdiv: str | None

    @classmethod
    def from_kwargs(cls, **kwargs: Any) -> "Config":
        cls_fields = set(signature(cls).parameters)

        class_args, other_args = {}, {}
        for name, val in kwargs.items():
            if name in cls_fields:
                class_args[name] = val
                continue
            other_args[name] = val

        c = cls(**class_args)
        for new_name, new_val in other_args.items():
            setattr(c, new_name, new_val)
        return c

    def __getitem__(self, item: CONFIG_NAMES) -> Any:
        return getattr(self, item)

    def get_holidays(self, year: int) -> list[dt.date]:
        available_holidays = holidays.country_holidays(self.country, subdiv=self.subdiv or None, years=year)
        return list(available_holidays.keys())


class ConfigHandler:
    def __init__(self) -> None:
        """Class for managing configuration file and settings ."""
        self.config = self._get_config()

    def _get_config(self) -> Config:
        config_file = self.read_config_file()
        return Config.from_kwargs(**config_file)

    def read_config_file(self) -> dict:
        if not CONFIG_PATH.exists():
            return NEEDED_DATA
        with CONFIG_PATH.open(encoding="utf-8") as f:
            config = json.load(f)
        for d in NEEDED_DATA.items():
            if d[0] not in config:
                config[d[0]] = d[1]
        return config

    def write_config_file(self) -> None:
        with CONFIG_PATH.open("w", encoding="utf-8") as write_file:
            json.dump(asdict(self.config), write_file)

    def set_config_value(self, key: CONFIG_NAMES, value: Any, write: bool = True) -> None:
        setattr(self.config, key, value)
        if not write:
            return
        self.write_config_file()

    def config_hash(self) -> int:
        """Get a hash of the current config."""
        return hash(json.dumps(asdict(self.config)))


CONFIG_HANDLER = ConfigHandler()
