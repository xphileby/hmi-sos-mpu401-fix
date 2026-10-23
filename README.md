# hmi-sos-mpu401-fix

A patch for the HMI Sound Operating System MPU-401 MIDI driver that ships with **Descent** and **Descent II**.
With it, both games play their General MIDI music through an MPU-401 port (Roland Sound Canvas, Yamaha MU-series
or any other external module) on real DOS hardware.

## The problem

Set Descent's music to *General MIDI / MPU-401* (`MidiDeviceID=0xa001`, `MidiPort=0x330` in `DESCENT.CFG`) and start
the game on a real PC. The screen fades out and the machine hangs: no keyboard, no Ctrl+Alt+Del, only a reset
helps. With `-nomusic`, `-nosound`, or FM music (`0xa009`), the game runs fine. Under DOSBox everything works, so
the bug went unnoticed in most modern setups.

The hang does not depend on the sound hardware or emulation. It reproduced with a Sound Blaster Live! under
Creative's SBEINIT (native MPU emulation and hardware UART), and under SBEMU, on a Core 2 machine.

## Root cause

HMI SOS does not compile its MIDI drivers into the game. It loads them at run time from `HMIMDRV.386`, which is a
container of small 32-bit drivers (`fmmidi.com`, `mpu401.com`, `mt32.com`, `gusmidi.com`, ...). The `mpu401.com`
driver in the Descent build of that file has a "reset all controllers" filter added to its send routine, and that
change introduced two bugs:

1. **Write to the code segment.** The filter keeps its state in two bytes inside the driver image and addresses
   them with `push cs` / `pop es` followed by writes such as `mov byte ptr es:[0x31c], 1`. Writing through a code
   selector raises a general protection fault on a real 386+ in protected mode. DOSBox does not enforce this. The
   first MIDI message the game sends hangs it.
2. **Stale jump targets.** The send routine has two early exits: `jne` when the driver's init failed, and `je` for
   a zero-length message. Their displacements were not updated when the filter call was inserted. Both now land in
   the middle of the byte-send loop, with the saved registers still on the stack and a garbage counter.

Daggerfall ships a different build of `HMIMDRV.386` without the filter, so its `mpu401.com` is not affected.

## The fix

The fix changes 3 bytes in the `mpu401.com` driver (image offsets are relative to the driver image, which starts
0x2c bytes after the `mpu401.com` name in the file):

| Image offset | File offset | Original | Patched | Meaning |
|---|---|---|---|---|
| 0x266 | 0x12AE3 | `0f 85 33 00 00 00` | `0f 85 20 00 00 00` | `jne` on init error → routine exit (0x28c) |
| 0x27c | 0x12AF9 | `0f 84 1d 00 00 00` | `0f 84 0a 00 00 00` | `je` on zero length → routine exit (0x28c) |
| 0x2b9 | 0x12B34 | `0e` (`push cs`) | `1e` (`push ds`) | flags are written through the driver's data alias |

When the filter runs, DS already holds the driver's data selector, which maps the same image. With the fix, the
flags end up exactly where HMI intended.

| File | Size | MD5 |
|---|---|---|
| `HMIMDRV.386` as shipped with Descent 1.5 / Descent II | 112060 | `593ddf8cd1db2c1894d83cf341bd3b3c` |
| after the patch | 112060 | `d25dc961feb49a7caa35224c8a98b843` |

## Usage

```
python3 patch_hmimdrv.py HMIMDRV.386            # patches in place, keeps HMIMDRV.386.bak
python3 patch_hmimdrv.py HMIMDRV.386 FIXED.386  # writes a new file
```

The script finds the driver by name, checks its size and the exact bytes, and refuses to touch any other build.
Running it again on a patched file changes nothing. Copy the result over `HMIMDRV.386` in the game folder
(`DESCENT\` or `DESCENT2\`), then set the music to General MIDI / MPU-401 with `SETUP.EXE` or in `DESCENT.CFG`.

If Python is not available, the three bytes in the table can be changed with any hex editor.

## Tested

- Descent 1.5 (registered), DOS/4GW 1.97, real hardware: Core 2 Extreme X6800, Sound Blaster Live! with Creative
  SBEINIT 5.00 under JemmEx. Music plays on a Roland SC-8850 through the gameport MIDI out; sound effects play
  through the SB16 emulation. Before the patch the same setup hung right after the intro fade.
