"""Tiny logger factory so every module gets a consistent format."""
import logging
import sys

from app.config import settings

_FMT = "%(asctime)s %(levelname)-7s %(name)s :: %(message)s"

_root = logging.getLogger()
if not _root.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FMT))
    _root.addHandler(handler)
_root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
