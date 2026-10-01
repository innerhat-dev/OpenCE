# punpckhdq main review, 2026-09-30

Fetched `origin` in `/Users/pfista/src/halo/punpckhdq-halo`. Its clean main and
origin/main both point to `901aee16f4424b6d5921226e03a6570ccb515f06`.
Compared the source with our Apple main at
`b2f5cc8717c3d0d09c3a81e830e1c6c68f413798`, including the current local Apple
stability changes. There are 11 commits in the preceding 48 hours, six in the
preceding 24 hours, as of 2026-10-01 03:30 UTC. No punpckhdq source was imported.

These changes advance reconstruction of Xbox build 2342. They are useful as
reference implementations; they do not add a Mac renderer, ray tracing,
portable runtime or our networking protocol. Our branch already implements
the queue, CRC, text, collision, device and small-object functions added here.

| Commit | Area | Assessment for our branch |
| --- | --- | --- |
| [901aee1](https://github.com/punpckhdq/halo/commit/901aee16f4424b6d5921226e03a6570ccb515f06) | Circular queue | Existing wraparound, peek, size and free-space behavior is equivalent. No runtime improvement identified. |
| [0bd21e7](https://github.com/punpckhdq/halo/commit/0bd21e74b1c9694f9cbd02b6e45aceed4a8ee8d0) | Text and Unicode | Useful named types and reference for font parsing, bounds and character handling. Our draw-string and Unicode files already have the same 28 and 73 function names respectively. Most inspected differences are names, signatures or equivalent control flow. |
| [3c3fa9f](https://github.com/punpckhdq/halo/commit/3c3fa9fc839b2386b6531a891c9ca240d8b558d5) | Equipment, garbage, sound scenery | Our pickup, placement, lifetime and sound behavior is already implemented. Types and flag names are clearer, but renaming them is not a demonstrated gameplay fix. |
| [4e33d5e](https://github.com/punpckhdq/halo/commit/4e33d5edac6f519265ce3b73ed6f3195df7e160b) | Xbox input | Highest-value reference for future controller tests: presets, unplug behavior, aircraft inversion and stick snapping. Do not replace SDL/touch paths or authenticated layouts. |
| [d614318](https://github.com/punpckhdq/halo/commit/d6143181c913de3db203d81919a897c00c460915) | Collision and physics | Useful comparison material for movement, vehicle impacts and water collisions. The project still marks collisions.c and physics.c NonMatching, so this is not sufficient evidence for changing our numerical behavior. |
| [67c5186](https://github.com/punpckhdq/halo/commit/67c51867e7e35ec8c72803fc76be43051ecb5e25) | Doors, controls and lights | Already implemented here. Its desired_value field is our actual_value field at offset 4 in the same eight-byte device group; this apparent difference is a rename. |
| [9d335c5](https://github.com/punpckhdq/halo/commit/9d335c56b3934625ec6695e60f6876b8e79eb47b) | CRC | Same polynomial, initial state and byte update behavior. Its cast-lvalue pointer increment targets the original compiler; our explicit pointer advance is portable. |
| [d2cfbaf](https://github.com/punpckhdq/halo/commit/d2cfbafa84d8dc9c153445edcf0318431e5b71da) | String search | Equivalent to our existing stristr, including case-sensitive first-byte selection and case-insensitive remaining comparison. No new string-search fix. |
| [171bcb1](https://github.com/punpckhdq/halo/commit/171bcb17fb623c5977d002598e55ad5a25ff0021) | Object reconstruction | Useful reference, but preserve our expanded object pool and player-scaled garbage limits. A direct import would restore Xbox capacities and fixed active-garbage limits. |
| [5d7fddc](https://github.com/punpckhdq/halo/commit/5d7fddc37f76194e5d151ce829a1cf25ca821ce8) | Geometry authoring tools | Targets developer geometry conversion/error reporting; no immediate improvement identified for playing the Apple build. |
| [66738be](https://github.com/punpckhdq/halo/commit/66738be8dd1c054a836c3fe5263300914aab0033) | objdiff version | Reconstruction tooling, not runtime behavior. Keep separate from the stable app work. |

## Recommended use

Prioritize controller regression coverage using the now-matched input functions
as an independent reference, then text parsing and device lifetime checks. The
upstream config marks input, draw-string and devices Matching; this review did
not independently rebuild their original Xbox binary or certify those matches.

Keep collision/physics changes as comparison candidates until a specific
difference is established against the original build and exercised locally.
For example, their stick-snap constants use float subtraction and a float
reciprocal; our current code deliberately preserves wider intermediate math.
Their collision helpers call external math routines where ours preserves
original scalar expansion. These differences need numerical evidence, not a
whole-file replacement.

No confirmed missing gameplay or networking fix emerged from this review.
Retain our Apple runtime, rendering adapter, expanded capacities and modern
networking. The latest source is valuable for correctness work, but merging its
11 commits directly is not justified by an identified stable-build benefit.

## Latest Cyber main

A fresh upstream fetch during this review found
[8fb1647e](https://github.com/cybersecurity/halo-ce-universal/commit/8fb1647e18a68e164529321bdcbe24557801f23b),
committed at 2026-10-01 03:20 UTC. It is absent from our main. This is a higher
priority candidate than the punpckhdq reconstruction changes: first-person
effects can request a deleted weapon's matrices, and the sound message path
passes a weapon slot instead of the actual weapon object. It also limits
missing-mouth-data and ignored-advertisement logging. Our current source still
has the affected weapon lookup and sound call.

Recommend a focused import of the weapon lifetime/sound fixes and logging
throttles with weapon-pickup/swap regression coverage. Its Linux/Windows crash
reports need separate Apple adaptation; the full commit also adds a debug
weapon selector. No part of this new commit was applied in this round.
The other missing upstream commit, 943abae1, fixes Windows update unpacking.
