#!/usr/bin/env python3
"""Run the prescribed command twice and check the PNG contract.

    python3 validate.py

Writes VALIDATION.md next to this file. Does not claim a contest score.
"""

from __future__ import annotations

import ast
import hashlib
import platform
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIMIT_BYTES = 1048576
LIMIT_EDGE = 1024
RUN = "mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py"
ALLOWED_IMPORTS = {"__future__", "math", "os", "struct", "zlib"}


def paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def decode_png(data: bytes) -> tuple[int, int, bytearray]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit("not a PNG")
    pos = 8
    width = height = None
    bit = color = inter = None
    idat = b""
    saw_iend = False
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        tag = data[pos + 4 : pos + 8]
        start = pos + 8
        end = start + length
        if end + 4 > len(data):
            raise SystemExit("truncated chunk")
        chunk = data[start:end]
        crc = struct.unpack(">I", data[end : end + 4])[0]
        expect = zlib.crc32(chunk, zlib.crc32(tag)) & 0xFFFFFFFF
        if crc != expect:
            raise SystemExit(f"bad crc on {tag!r}")
        pos = end + 4
        if tag == b"IHDR":
            width, height, bit, color, comp, filt, inter = struct.unpack(">IIBBBBB", chunk)
            if comp != 0 or filt != 0:
                raise SystemExit("unsupported PNG compression or filter method")
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            saw_iend = True
            if pos != len(data):
                raise SystemExit("bytes after IEND")
            break
    if not saw_iend or width is None or height is None:
        raise SystemExit("incomplete PNG")
    if bit != 8 or color != 2 or inter != 0:
        raise SystemExit(f"expected 8-bit RGB, got bit={bit} color={color} inter={inter}")
    raw = zlib.decompress(idat)
    stride = width * 3
    if len(raw) != height * (stride + 1):
        raise SystemExit("image data length does not match the header")
    out = bytearray(height * stride)
    prev = bytearray(stride)
    index = 0
    for _y in range(height):
        filt = raw[index]
        index += 1
        row = bytearray(raw[index : index + stride])
        index += stride
        if filt == 1:
            for x in range(stride):
                left = row[x - 3] if x >= 3 else 0
                row[x] = (row[x] + left) & 255
        elif filt == 2:
            for x in range(stride):
                row[x] = (row[x] + prev[x]) & 255
        elif filt == 3:
            for x in range(stride):
                left = row[x - 3] if x >= 3 else 0
                row[x] = (row[x] + ((left + prev[x]) // 2)) & 255
        elif filt == 4:
            for x in range(stride):
                a = row[x - 3] if x >= 3 else 0
                b = prev[x]
                c = prev[x - 3] if x >= 3 else 0
                row[x] = (row[x] + paeth(a, b, c)) & 255
        elif filt != 0:
            raise SystemExit(f"bad filter {filt}")
        out[_y * stride : (_y + 1) * stride] = row
        prev = row
    return width, height, out


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def run_prescribed() -> tuple[float, bytes]:
    started = time.perf_counter()
    proc = subprocess.run(
        RUN,
        cwd=ROOT,
        shell=True,
        capture_output=True,
    )
    elapsed = time.perf_counter() - started
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.decode() or f"exit {proc.returncode}")
    if proc.stdout or proc.stderr:
        raise SystemExit("main.py wrote to stdout or stderr")
    data = (ROOT / "out" / "entry.png").read_bytes()
    return elapsed, data


def luma(rgb: bytearray, width: int, x: int, y: int) -> int:
    i = (y * width + x) * 3
    return (rgb[i] * 3 + rgb[i + 1] * 6 + rgb[i + 2]) // 10


def main() -> None:
    mods = imports_of(ROOT / "main.py")
    extra = mods - ALLOWED_IMPORTS
    if extra:
        raise SystemExit(f"non-stdlib imports: {sorted(extra)}")

    first_s, first = run_prescribed()
    second_s, second = run_prescribed()
    digest = hashlib.sha256(first).hexdigest()
    same = first == second
    width, height, rgb = decode_png(first)
    problems: list[str] = []
    if not same:
        problems.append("two runs differed")
    if len(first) > LIMIT_BYTES:
        problems.append(f"file is {len(first)} bytes")
    if width > LIMIT_EDGE or height > LIMIT_EDGE:
        problems.append(f"dimensions {width}x{height}")
    if first_s > 60 or second_s > 60:
        problems.append("run exceeded 60 seconds")
    # Corners stay the pale backdrop; the face holds both a dark pupil and a catchlight.
    for x, y in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        if luma(rgb, width, x, y) < 180:
            problems.append(f"dark corner at {x},{y}")
    dark = bright = 0
    x0, x1 = width // 2 - 180, width // 2 + 180
    y0, y1 = height // 2 - 220, height // 2 + 40
    for y in range(y0, y1):
        for x in range(x0, x1):
            value = luma(rgb, width, x, y)
            if value < 90:
                dark += 1
            elif value > 240:
                bright += 1
    if dark < 50 or bright < 20:
        problems.append(f"face contrast weak (dark={dark}, bright={bright})")

    status = "pass" if not problems else "fail"
    inflated = height * (width * 3 + 1)
    problem_lines = "\n".join("- " + item for item in problems) if problems else "None."
    report = f"""# Validation

Status: **{status}**

Local interpreter: {sys.version.split()[0]} ({platform.python_implementation()})
Published grader runtime: Python 3.13, standard library only. This machine has no `python3.13` binary, so the hash below is for {sys.version.split()[0]}.

## Command

```sh
{RUN}
```

The same command was run twice. `main.py` was silent on both runs.

| Run | Seconds | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| 1 | {first_s:.3f} | {len(first)} | `{digest}` |
| 2 | {second_s:.3f} | {len(second)} | `{hashlib.sha256(second).hexdigest()}` |

Identical bytes: {same}

## Image

- PNG signature, chunk CRCs, and IEND: checked
- Inflated scanlines match the header: {inflated} bytes
- Dimensions: {width} x {height} (limit {LIMIT_EDGE} x {LIMIT_EDGE})
- Color: 8-bit RGB, not interlaced
- File size: {len(first)} bytes (limit {LIMIT_BYTES})
- Face window dark pixels (luma < 90): {dark}
- Face window bright pixels (luma > 240): {bright}
- Imports: {", ".join(sorted(mods))}

## Spec notes

- Output path follows the public starter: `MAKEFUN_OUTPUT_DIR` or `/output`, file name `entry.png`. This environment cannot create `/output` (permission denied), so only the `MAKEFUN_OUTPUT_DIR` command was executed.
- Wall budget published for the sandbox: 60 seconds, 1 CPU, 512 MB, 64 processes. These local runs only measure wall time.
- `GET /api/competitions/cutest-cat-01` reports `reproduce: null` (scored on the server). This script does not call the judge and does not report a win rate.
- A public repository, a signed entry, and transcripts are not part of this check.

## Problems

{problem_lines}
"""
    (ROOT / "VALIDATION.md").write_text(report, encoding="utf-8")
    if problems:
        raise SystemExit(report)
    print(report)


if __name__ == "__main__":
    main()
