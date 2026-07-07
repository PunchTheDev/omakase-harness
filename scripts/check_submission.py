#!/usr/bin/env python3
"""Gates 1–3 self-check for OC-H: payload shape, locked-file integrity, harness sanity.

Exit 0 = submit; nonzero = the printed reason is what Peggy would reject with.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "..", "oc-eval"))
sys.path.insert(0, ROOT)


def fail(msg: str) -> int:
    print(f"REJECT: {msg}")
    return 1


def check_payload(path: str) -> str | None:
    with open(path) as f:
        payload = json.load(f)
    with open(os.path.join(ROOT, "payload-schema.json")) as f:
        schema = json.load(f)
    missing = [k for k in schema["required"] if k not in payload]
    if missing:
        return f"payload missing required fields: {missing}"
    extra = [k for k in payload if k not in schema["properties"]]
    if extra:
        return f"payload has unknown fields: {extra}"
    return None


def check_locked_files() -> str | None:
    with open(os.path.join(ROOT, "manifest.json")) as f:
        locked = json.load(f)["locked"]
    for path, expected in locked.items():
        full = os.path.join(ROOT, path)
        if not os.path.exists(full):
            return f"locked file deleted: {path}"
        with open(full, "rb") as f:
            if hashlib.sha256(f.read()).hexdigest() != expected:
                return f"locked file modified: {path}"
    return None


def check_harness() -> str | None:
    # static pass — two families of banned primitives in the mutable package:
    # network/process (workers only via the injected pool) and answer
    # reconstruction (suites generators, mock internals, file/dynamic-import
    # escapes). A speed bump, not a wall: production containment is the sealed
    # runtime that simply doesn't contain answer material.
    banned = re.compile(
        r"\b(socket|subprocess|urllib|requests|httpx|http\.client"
        r"|suites|mockpool|task_by_id|generate_split|knows"
        r"|importlib|__import__|eval|exec|open|globals|vars)\b"
    )
    for dirpath, _, files in os.walk(os.path.join(ROOT, "harness")):
        for name in files:
            if name.endswith(".py"):
                with open(os.path.join(dirpath, name)) as f:
                    if banned.search(f.read()):
                        return f"banned network/process primitive in harness/{name}"
    try:
        import harness  # noqa: F401
    except Exception as e:  # noqa: BLE001
        return f"harness package failed to import: {e}"
    if not callable(getattr(harness, "run_task", None)):
        return "harness.run_task missing — the contract in harness/__init__.py"
    return None


def main() -> int:
    payload_path = sys.argv[1] if len(sys.argv) > 1 else None
    checks = [
        ("gate-2 locked files", check_locked_files()),
        ("gate-3 harness", check_harness()),
    ]
    if payload_path:
        checks.insert(0, ("gate-1 payload", check_payload(payload_path)))
    for name, err in checks:
        if err:
            return fail(f"[{name}] {err}")
        print(f"ok: {name}")
    print("submission passes gates 1-3 self-check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
