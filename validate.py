#!/usr/bin/env python3
"""Check that main.py copies the fixed kitten, independent of cwd.

    python3 validate.py

Uses the standard library only. Prints this machine's wall times.
Does not claim a contest score and does not rewrite VALIDATION.md.
"""

from __future__ import annotations

import ast
import hashlib
import os
import platform
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSET = ROOT / "assets" / "kitten.jpg"
PREVIEW = ROOT / "preview.jpg"
MAIN = ROOT / "main.py"
LIMIT_BYTES = 1048576
LIMIT_EDGE = 1024
ALLOWED_IMPORTS = {"__future__", "os", "pathlib"}


def jpeg_size(data: bytes) -> tuple[int, int]:
    if data[:2] != b"\xff\xd8":
        raise SystemExit("asset is not a JPEG")
    pos = 2
    while pos + 4 < len(data):
        if data[pos] != 0xFF:
            raise SystemExit("truncated JPEG marker")
        while data[pos] == 0xFF:
            pos += 1
        marker = data[pos]
        pos += 1
        if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
            continue
        if pos + 2 > len(data):
            break
        length = struct.unpack(">H", data[pos : pos + 2])[0]
        if marker in (0xC0, 0xC1, 0xC2):
            payload = data[pos + 2 : pos + length]
            height, width = struct.unpack(">HH", payload[1:5])
            return width, height
        if marker == 0xDA:
            break
        pos += length
    raise SystemExit("JPEG has no start-of-frame marker")


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def run_copy(cwd: Path, output_dir: str | None) -> tuple[float, bytes]:
    env = os.environ.copy()
    env.pop("MAKEFUN_OUTPUT_DIR", None)
    if output_dir is not None:
        env["MAKEFUN_OUTPUT_DIR"] = output_dir
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(MAIN)],
        cwd=cwd,
        env=env,
        capture_output=True,
    )
    elapsed = time.perf_counter() - started
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.decode() or f"exit {proc.returncode}")
    if proc.stdout or proc.stderr:
        raise SystemExit("main.py wrote to stdout or stderr")
    if output_dir is None:
        target = Path("/output") / "entry.png"
    else:
        target = Path(output_dir)
        if not target.is_absolute():
            target = cwd / target
        target = target / "entry.png"
    return elapsed, target.read_bytes()


def require(condition: bool, message: str, problems: list[str]) -> None:
    if not condition:
        problems.append(message)


def main() -> None:
    problems: list[str] = []
    extra = imports_of(MAIN) - ALLOWED_IMPORTS
    require(not extra, f"non-stdlib imports: {sorted(extra)}", problems)
    asset = ASSET.read_bytes()
    preview = PREVIEW.read_bytes()
    width, height = jpeg_size(asset)
    digest = hashlib.sha256(asset).hexdigest()
    require(preview == asset, "preview.jpg differs from assets/kitten.jpg", problems)
    require(len(asset) <= LIMIT_BYTES, f"asset is {len(asset)} bytes", problems)
    require(width <= LIMIT_EDGE and height <= LIMIT_EDGE, f"dimensions {width}x{height}", problems)
    require(width == 1024 and height == 1024, f"expected 1024x1024, got {width}x{height}", problems)

    runs: list[tuple[str, float, str]] = []
    with tempfile.TemporaryDirectory(prefix="cat-val-") as tmp:
        work = Path(tmp)
        decoy = work / "assets"
        decoy.mkdir()
        (decoy / "kitten.jpg").write_bytes(b"decoy-not-the-asset")
        cases = (
            ("repo-relative", ROOT, "out"),
            ("repo-relative-repeat", ROOT, "out"),
            ("other-cwd-absolute", work, str(work / "abs-out")),
            ("other-cwd-absolute-repeat", work, str(work / "abs-out")),
            ("other-cwd-relative", work, "rel-out"),
            ("other-cwd-relative-repeat", work, "rel-out"),
        )
        for name, cwd, output_dir in cases:
            elapsed, data = run_copy(cwd, output_dir)
            runs.append((name, elapsed, hashlib.sha256(data).hexdigest()))
            require(data == asset, f"{name} bytes differ from the asset", problems)
            require(elapsed <= 60, f"{name} exceeded 60 seconds", problems)

    lines = [
        f"interpreter: {sys.version}",
        f"implementation: {platform.python_implementation()}",
        f"asset: {ASSET.relative_to(ROOT)}",
        f"bytes: {len(asset)}",
        f"sha256: {digest}",
        f"jpeg: {width}x{height}",
        f"imports: {', '.join(sorted(imports_of(MAIN)))}",
        "runs:",
    ]
    for name, elapsed, run_digest in runs:
        lines.append(f"  {name}: {elapsed:.9f}s {run_digest}")
    status = "pass" if not problems else "fail"
    lines.append(f"status: {status}")
    if problems:
        lines.extend(f"problem: {item}" for item in problems)
    report = "\n".join(lines)
    print(report)
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
