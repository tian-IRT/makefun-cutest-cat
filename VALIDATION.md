# Validation

Status: **pass** on this machine for the fixed-image copy.

These runs are local measurements on CPython 3.12.3. This machine has no `python3.13` binary, so none of the times below are a Python 3.13 run or a make.fun grade. No contest score is claimed.

Interpreter: `3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]`.

`main.py` imports `__future__`, `os`, and `pathlib`. It reads `assets/kitten.jpg` through `__file__` and writes those bytes to `entry.png`.

## Asset

| | |
| --- | --- |
| Path | `assets/kitten.jpg` |
| Format | baseline JPEG (SOF0), 8-bit, 4:4:4, JFIF only |
| Dimensions | 1024×1024 |
| Bytes | 950123 (limit 1048576) |
| SHA-256 | `b66ebcb5f991c9edfc565ca873936868aa8ac701fde4f8bc7aaffb20bea0c320` |

`preview.jpg` is the same bytes.

The accepted source picture is a 1254×1254 8-bit RGB PNG, 2395470 bytes, SHA-256 `7f295fbc68352a990c71da0ffed22570d277db8bc4c81bafd0b963ad763c5c75`. It was created with the ChatGPT website at the user's request. That file contained a `caBX` metadata chunk. The chunk was left out of this repository. Pillow 13.0.0 resized the full frame with Lanczos to 1024×1024, with no crop. A lossless PNG of that resize is 1570633 bytes, which is over 1048576, so the stored file is a JPEG at quality 99, subsampling 4:4:4, optimized, not progressive. Against the resized PNG, mean squared error is 1.0083 and PSNR is 48.10 dB.

## `python3 validate.py`

Status: **pass**. A decoy `assets/kitten.jpg` in the other working directory was not read. Every output matched the asset SHA-256 above. Stdout and stderr were empty.

| Run | Seconds |
| --- | ---: |
| Repo directory, `MAKEFUN_OUTPUT_DIR=out` | 0.022363659 |
| Same command again | 0.024015224 |
| Other working directory, absolute output directory | 0.018063816 |
| Same command again | 0.021346112 |
| Other working directory, relative output directory | 0.017984141 |
| Same command again | 0.019766361 |

## Prescribed shell command

```sh
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
```

| Run | Seconds | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| 1 | 0.024892231 | 950123 | `b66ebcb5f991c9edfc565ca873936868aa8ac701fde4f8bc7aaffb20bea0c320` |
| 2 | 0.022985575 | 950123 | `b66ebcb5f991c9edfc565ca873936868aa8ac701fde4f8bc7aaffb20bea0c320` |

Exit 0. Stdout and stderr empty. Identical to the asset: yes.

## Default `/output/entry.png`

`mkdir /output` on the host is `PermissionError: [Errno 13] Permission denied`. After the test, `ls /output` was still `No such file or directory`.

The default path was run with `MAKEFUN_OUTPUT_DIR` unset and the working directory `/`, inside a user and mount namespace. The process could create `/output` there without creating it on the host.

| Run | Seconds | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| 1 | 0.018508792 | 950123 | `b66ebcb5f991c9edfc565ca873936868aa8ac701fde4f8bc7aaffb20bea0c320` |
| 2 | 0.020319231 | 950123 | `b66ebcb5f991c9edfc565ca873936868aa8ac701fde4f8bc7aaffb20bea0c320` |

Exit 0. Stdout and stderr empty. Identical to the asset: yes. Both runs are under 60 seconds.

## Archived procedural entry

Git history still has the previous drawn kitten at commit `71957f36adae07e388c5fcc491723283cfa8941d`. That program is not this entry. Its `VALIDATION.md` records a different picture, SHA-256 `f343d0e35975c320ccc8405893cb63641a537318d9e07b8974bc49065d50abdd`, 295763 bytes, 1024×1024 RGB PNG. Those local 3.12.3 times, and the earlier isolated CPython 3.13.18 times of 6.570 s and 6.475 s, belong to that drawing. They were not re-measured for this image.

## Outside this check

No contest submission and no wallet signature. Transcript export is not part of this repository. The transcript policy is unresolved. This entry is not submitted and is not accepted.
