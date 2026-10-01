# Apple regression checks

The Apple workflow in `.github/workflows/apple.yml` checks pull requests,
relevant changes on main and manual runs on an ARM64 macOS 26 runner. It uses
public pinned dependencies and authored fixtures. It needs no Xbox SDK, maps,
Apple signing account or private environment files. The workflow must be pushed
before GitHub can execute it; local checks do not establish runner success.

## Source-only checks

From an Apple Silicon Mac with the public dependencies installed:

```sh
python3 tools/macos_build.py --plugin-only
python3 tools/ios_build.py --plugin-only
python3 tools/test_macos_runtime.py --standalone
python3 tools/test_ios_runtime.py
python3 -m unittest tools.test_input_bindings tools.test_visibility_queries tools.test_geometry_cache tools.test_presentation tools.test_macos_preflight tools.test_macos_benchmark
python3 tools/test_macos_menu.py
python3 tools/test_macos_menu.py --check-ui
```

The Mac probe exercises ILP32 layouts, varargs, memory routines, allocation and
write tracking, futexes, clocks, networking, invites and the SDL audio handoff.
The standalone option supplies authored guest memory routines; the default
option also checks the locally built game's musl routines.

The iOS check builds production device IR and compares it with the Mac test IR.
Only the arena address and its code-delta slot may differ. It then executes the
same signed-code, TLS and indirect-call lowering in a read-only signed Mach-O
image using the Mac arena. The device compiler and loader keep their existing
16 GB arena. This check does not establish physical iPhone gameplay or address
reservation on a device.

The native menu check packages the real AppKit menu and SDL bridge under a
unique test app identifier. Its loop calls SDL event polling, with a real UDP
round trip each iteration. It exercises Settings, folder/image sheets, an
authored disc import, missing-settings feedback, close and Quit. Runtime sheets
must not enter an application modal loop. This needs a WindowServer session;
headless or restricted GUI execution is insufficient.

Geometry checks compare actual cached GPU bytes after same-frame writes,
map-address reuse and 4 KB/16 KB boundary changes. They also exercise volatile
fallback, allocation failure and bounded storage across 200 address reuses.
The presentation test covers an FBO constructor changing both GL bindings, so
the first presentation cannot blit a render target into itself.

## Local game validation

Build the game with the user's own maps and SDK. Use a new output directory for
each run; the helper isolates saves, settings and private console traffic.

```sh
python3 tools/macos_benchmark.py --level a30 --seconds 900 --effects --interval .25 --checkpoints --output build/macos/tests/a30-soak-new
python3 tools/macos_benchmark.py --levels prisoner,chillout,a10,b30 --cycle-seconds 45 --seconds 230 --effects --screenshot-every 600 --output build/macos/tests/map-cycle-new
python3 tools/macos_multiplayer_smoke.py --help
```

Effect commands count only after a completed unique console output line; echoed
input does not count. Expressions must fit the engine's 127-byte input limit.
Each map change waits for the completed engine load and a player. Checkpoints
wait for completed writes, actual reads and a live player after revert. A normal
save may be refused in an unsafe scene; the test fails instead of forcing it.
Early process exit, missing work, assertions and GL faults also fail the run.

`validation.json` includes the guest SHA-256, acknowledged commands, completed
map changes/reverts and timings. Frame statistics include rendered loading and
startup frames. Vsync is enabled; driver draw time includes waits and is not a
GPU timestamp. Separate source-only menu/UDP checks and two-instance encrypted
gameplay checks do not establish Settings behavior across physical networks.

Local checks on 2026-09-30 passed 29 focused regressions, native preferences and
menu/UDP checks, the Mac ABI probes and the signed iOS instruction probe. Both
unsigned simulator and device apps compiled. The cache prototype's a30 soak completed
900 seconds with 2,480 acknowledged effect commands at a requested .25-second
interval, one verified safe save/revert, no GL/runtime fault and 692.75 MB peak
physical footprint. Console acknowledgement adds time to the requested cadence;
the actual count is reported rather than assuming four effects per second.
The 230-second map run completed four changes through Prisoner → Chill Out →
a10 → b30 → Prisoner and 84 effect commands. A separate 150-second run of two
real app instances passed encrypted invite gameplay with native menus enabled.
Settings was exercised in the separate native SDL/UDP test, not opened in the
two full-game instances during that run.

The final stable build keeps geometry streaming enabled. Its separate 70-second
a30 smoke run passed with 23 acknowledged effects, one completed save/revert,
3,049 rendered frames, no GL/runtime fault and 633.63 MB peak footprint. Its
guest SHA-256 is `7762915f06b77aa98d1212b64239df955967714e212e5dce6ab7b2be1c7f0aed`,
identical to the streamed reference below. Both final unsigned iOS builds also
passed. The iOS builds ran alongside this smoke run, so its frame timings are
not part of the sequential performance comparison.

## Upload measurements (2026-09-30)

The final a30 comparisons each lasted 70 seconds with 23 acknowledged effect
commands and one verified checkpoint revert. They used the same saved scene,
two-second cadence, hidden window and vsync, and ran sequentially after the soak
and builds finished. Other desktop apps remained open, so this is not a maximum
FPS measurement:

| Renderer | Upload bytes per rendered frame | Median / p95 frame | Peak physical footprint |
| --- | ---: | ---: | ---: |
| Streamed reference | 4,883,773 | 21.80 / 24.16 ms | 635.67 MB |
| Cache with guest libc byte comparison | 1,833,640 | 23.55 / 24.96 ms | 684.99 MB |
| Cache with alias-safe word comparison | 1,845,703 | 22.31 / 24.05 ms | 687.80 MB |

The word comparison reduced upload bytes by 62.2%, with about 52 MB additional
peak footprint. It eliminated most of the byte loop's cost, but median frame
time was still 2.3% slower than the streamed reference and p95 was comparable.
The measured benefit does not justify enabling the cache in the stable build.
`port/macos/renderer_config.h` therefore keeps `HALO_MACOS_GEOMETRY_CACHE` at 0;
set it to 1 and rebuild for a local experiment. This is a checked-in non-secret
build setting, not a new application environment variable. The CI probe checks
both the experimental cache and the streamed Mac/iOS defaults.

The existing misaligned-attribute expansion that avoids large ANGLE conversion
allocations is retained. Broader campaigns, other Macs, prolonged memory
pressure and physical-device multiplayer remain playtesting work.
