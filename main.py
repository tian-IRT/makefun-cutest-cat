#!/usr/bin/env python3
"""Copy the fixed garden kitten to entry.png.

The picture was created with the ChatGPT website at the user's request.
A build step resized the full frame to 1024 by 1024 and stored those bytes
beside this file. This program writes that file unchanged.

The grader runs Python 3.13, standard library only, with no network. The
asset path follows this file, not the process working directory. Locally:

    mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py

With MAKEFUN_OUTPUT_DIR unset, the same program writes /output/entry.png.
The output name is entry.png. Its magic bytes are JPEG.
"""

from __future__ import annotations

import os
from pathlib import Path

ASSET = Path(__file__).resolve().parent / "assets" / "kitten.jpg"


def main() -> None:
    data = ASSET.read_bytes()
    directory = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(directory, exist_ok=True)
    (Path(directory) / "entry.png").write_bytes(data)


if __name__ == "__main__":
    main()
