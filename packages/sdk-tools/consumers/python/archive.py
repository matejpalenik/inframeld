"""Inspect a wheel's distribution boundary without importing its implementation."""

import sys
from zipfile import ZipFile

with ZipFile(sys.argv[1]) as archive:
    names = archive.namelist()
assert "inframeld_sdk/py.typed" in names
assert not any(
    any(
        marker in name
        for marker in [
            "__sdk_stale_probe__",
            "/docs/",
            "sdk-tools",
            "fixtures",
            ".gitlab",
            ".travis",
        ]
    )
    for name in names
), names
print("Runtime-only wheel:", len(names), "entries")
