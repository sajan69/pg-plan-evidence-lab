"""Strict JSON and explicit capture context. No database connections."""
from datetime import datetime, timezone
import hashlib
import json
import math
import re


class EvidenceError(ValueError):
    """Safe fixed error codes; never include record values."""


def fail(code):
    raise EvidenceError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def strict_json(raw, cap):
    if not isinstance(raw, bytes) or len(raw) > cap:
        fail("input_size")

    def pairs(items):
        obj = {}
        for key, val in items:
            if key in obj:
                fail("duplicate_key")
            obj[key] = val
        return obj

    def constant(_):
        fail("nonfinite_number")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, EvidenceError):
            raise
        fail("invalid_json")
    stack = [(value, 0)]
    count = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if depth > 64 or count > 50000:
            fail("json_budget")
        if isinstance(item, float) and not math.isfinite(item):
            fail("nonfinite_number")
        if isinstance(item, dict):
            stack.extend((val, depth + 1) for val in item.values())
        elif isinstance(item, list):
            stack.extend((val, depth + 1) for val in item)
    return value


HASH_FIELDS = ("query_sha256", "fixture_sha256", "workload_sha256", "settings_sha256")
MANIFEST_FIELDS = {"schema_version", "source", "server_version_num", "query_alias",
                   "captured_at", *HASH_FIELDS}


def manifest(raw):
    value = strict_json(raw, 16384)
    if not isinstance(value, dict) or set(value) != MANIFEST_FIELDS:
        fail("manifest_fields")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        fail("manifest_version")
    if value["source"] not in ("synthetic_fixture", "synthetic_lab", "manual_export"):
        fail("manifest_source")
    version = value["server_version_num"]
    if type(version) is not int or version // 10000 not in (16, 18) or version % 10000 > 999:
        fail("server_version")
    alias = value["query_alias"]
    if not isinstance(alias, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", alias):
        fail("query_alias")
    for key in HASH_FIELDS:
        if not isinstance(value[key], str) or not re.fullmatch(r"[0-9a-f]{64}", value[key]):
            fail("manifest_hash")
    stamp = value["captured_at"]
    try:
        if not isinstance(stamp, str) or len(stamp) > 40:
            fail("capture_time")
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if parsed.utcoffset() is None or not 2000 <= parsed.year <= 2100:
            fail("capture_time")
        normalized = parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError):
        fail("capture_time")
    return {**value, "captured_at": normalized}
