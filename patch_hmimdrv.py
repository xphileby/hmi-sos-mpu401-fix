#!/usr/bin/env python3
"""Fix the HMI SOS MPU-401 MIDI driver in HMIMDRV.386 so Descent / Descent II play MIDI music on real hardware.

The "mpu401.com" driver inside the Descent build of HMIMDRV.386 (112060 bytes, MD5 593ddf8cd1db2c1894d83cf341bd3b3c)
has two bugs, both introduced when HMI inserted a controller-reset filter into the send routine:

  1. The filter does `push cs / pop es` and then writes its state flags through ES, i.e. into the code segment.
     DOSBox does not care; a real CPU in protected mode raises #GP at the first MIDI message -> the game hangs.
     Fix: `push ds` (the driver's data alias of the same image) instead of `push cs`.
  2. Two early exits of the send routine (`jne` on the init-error flag, `je` on a zero-length message) still carry
     their pre-insertion displacements and now land in the middle of the send loop with a broken stack.
     Fix: point both at the routine's real exit.

Other HMIMDRV.386 builds (e.g. Daggerfall's, 117852 bytes) do not have the filter and are left untouched.

Usage:  python3 patch_hmimdrv.py HMIMDRV.386 [OUTPUT]     (default: patch in place, keeping HMIMDRV.386.bak)
"""
import shutil
import struct
import sys

BROKEN_SIZE = 0x329      # size of the affected mpu401.com driver image
ENTRY_HDR = 0x2c         # directory entry (name + offsets) that precedes each driver image
JUMPS = [                # (offset in image, opcode, original rel32, correct target)
    (0x266, b'\x0f\x85', 0x33, 0x28c),   # jne exit  - init error flag set
    (0x27c, b'\x0f\x84', 0x1d, 0x28c),   # je  exit  - message length 0
]
PUSH_CS = 0x2b9          # push cs ; pop es  ->  push ds ; pop es


def patch(b: bytearray) -> list[str]:
    e = b.find(b'mpu401.com\x00')
    if e < 0:
        raise SystemExit('no mpu401.com driver in this file')
    size = struct.unpack_from('<I', b, e + 0x24)[0]
    if size != BROKEN_SIZE:
        raise SystemExit(f'mpu401 driver size {size:#x}: not the affected build ({BROKEN_SIZE:#x}), nothing to do')
    img = e + ENTRY_HDR
    log = []
    for at, op, old, target in JUMPS:
        o = img + at
        if bytes(b[o:o + 2]) != op:
            raise SystemExit(f'{at:#x}: unexpected opcode {b[o:o + 2].hex()}')
        cur, new = struct.unpack_from('<i', b, o + 2)[0], target - (at + 6)
        if cur == new:
            log.append(f'{at:#x}: already patched')
            continue
        if cur != old:
            raise SystemExit(f'{at:#x}: unexpected displacement {cur:#x}')
        struct.pack_into('<i', b, o + 2, new)
        log.append(f'{at:#x} (file {o + 2:#x}): jump displacement {old:#x} -> {new:#x}')
    o = img + PUSH_CS
    ctx = bytes(b[o - 3:o + 2])
    if ctx not in (b'\x06\x0f\xa1\x0e\x07', b'\x06\x0f\xa1\x1e\x07'):
        raise SystemExit(f'{PUSH_CS:#x}: unexpected code {ctx.hex()}')
    if b[o] == 0x0e:
        b[o] = 0x1e
        log.append(f'{PUSH_CS:#x} (file {o:#x}): push cs -> push ds')
    else:
        log.append(f'{PUSH_CS:#x}: already patched')
    return log


def main() -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) == 3 else src
    b = bytearray(open(src, 'rb').read())
    print('\n'.join(patch(b)))
    if dst == src:
        shutil.copyfile(src, src + '.bak')
    open(dst, 'wb').write(b)
    print(f'written {dst}')


if __name__ == '__main__':
    main()
