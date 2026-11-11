# Validation

Status: **pass** on this machine for `MAKEFUN_OUTPUT_DIR` and for the default `/output/entry.png` path.

These runs are local measurements on CPython 3.12.3. They are not the make.fun grader and they are not a contest score.

Interpreter: `3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]`, zlib 1.3. This machine has no `python3.13` binary. `main.py` is unchanged from the supplied source. Its SHA-256 is `9be7ef55f223f7a44baae0fde4509269e69ea99d1293583804d505d3f6578784`.

Imports: `__future__`, `math`, `os`, `struct`, `zlib`.

## Local `MAKEFUN_OUTPUT_DIR` (full wall time)

```sh
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Two runs. Exit 0. Stdout and stderr empty.

| Run | Seconds | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| 1 | 4.622823877 | 295763 | `f343d0e35975c320ccc8405893cb63641a537318d9e07b8974bc49065d50abdd` |
| 2 | 4.669042481 | 295763 | `f343d0e35975c320ccc8405893cb63641a537318d9e07b8974bc49065d50abdd` |

Identical bytes: yes.

## `python3 validate.py`

The supplied checker passed. It prints wall time to three decimal places for its own two runs: **4.651** s and **4.633** s. Same length and SHA-256 as the table above.

- PNG signature, chunk CRCs, and IEND: checked
- 8-bit RGB, not interlaced, 1024×1024
- Inflated scanlines, including one filter byte per row: 3146752
- Decoded RGB samples: 3145728 (`1024*1024*3`)
- File size 295763 is under 1048576
- Both of those runs are under 60 seconds
- Face window dark pixels (luma < 90): 3996
- Face window bright pixels (luma > 240): 12258
- Problems: none

Running `python3 validate.py` again replaces this file with that checker's shorter report. This session did not call the competition API.

## Default `/output/entry.png`

`mkdir /output` on the host raised `PermissionError: [Errno 13] Permission denied`. After the test, `ls /output` was still `No such file or directory`.

The default path was exercised with `MAKEFUN_OUTPUT_DIR` unset, inside a user and mount namespace, so the process could create `/output` without adding it on the host. Two runs. Exit 0. Stdout and stderr empty.

| Run | Seconds | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| 1 | 4.749827562 | 295763 | `f343d0e35975c320ccc8405893cb63641a537318d9e07b8974bc49065d50abdd` |
| 2 | 4.658481708 | 295763 | `f343d0e35975c320ccc8405893cb63641a537318d9e07b8974bc49065d50abdd` |

## Earlier isolated CPython 3.13.18 record

Not re-run here. The supplied validation note records two runs of CPython 3.13.18, built without profile-guided optimization, writing `/output/entry.png`: **6.570** s and **6.475** s, 295763 bytes, SHA-256 `f343d0e35975c320ccc8405893cb63641a537318d9e07b8974bc49065d50abdd`, 1024×1024 8-bit RGB. That note says those wall times are not the grader image's times. Every PNG in this session has that same hash. The 6.570 s and 6.475 s figures were not measured on this machine.

## Preview

`preview.png` is a byte copy of the generated PNG. SHA-256 `f343d0e35975c320ccc8405893cb63641a537318d9e07b8974bc49065d50abdd`.

## Outside this check

No contest submission and no wallet signature. Transcript export is not part of this repository. The transcript policy is unresolved, and this source is not claimed ready for entry or accepted.
