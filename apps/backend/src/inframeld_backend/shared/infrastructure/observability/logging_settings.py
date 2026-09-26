"""Define the supported diagnostic severity and rendering settings."""

from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["console", "json"]
