"""Bounded local files in trusted directories; no network or SQL."""
import json
import os
import stat
from .contract import fail


def read(path, cap):
    if not stat.S_ISREG(os.lstat(path).st_mode):
        fail("input_not_regular")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            fail("input_not_regular")
        raw = handle.read(cap + 1)
    if len(raw) > cap:
        fail("input_size")
    return raw


def write(path, result):
    raw = (json.dumps(result, indent=2, allow_nan=False) + "\n").encode()
    if len(raw) > 2 * 1024 * 1024:
        fail("output_size")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
