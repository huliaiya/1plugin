"""Expose the root fox_toolbox package under astrbot_plugin_fox_toolbox."""

from pathlib import Path

_ROOT_PACKAGE = Path(__file__).resolve().parents[2] / "fox_toolbox"
__path__ = [str(_ROOT_PACKAGE)]
