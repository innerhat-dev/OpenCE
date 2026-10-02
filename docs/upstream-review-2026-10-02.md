# Selective upstream review: netcode version 10

Reviewed October 2, 2026 against cybersecurity's `main` at
`d1c7243cb20eab4488efa1266e259b1f4d5240f6`, starting from this fork's
`a6f242df` and the previous reviewed-through upstream revision
`f2ba71d9af4c6fc65d7419cc22e8f4899b16da88`.

The last full upstream integration remains `c55e4e2b` / Apple merge
`aabe44417431c36e46aaa385a69a89a3c9d685c0`. The protocol portion of `d1c7243c`
is a selective addition to that baseline, not a merge of intervening changes.
Local integration commit: `ea4dec3c28fcb4975ad36718c344bf5205b4c5eb`.
The [fidelity policy](xbox-fidelity.md) continues to govern future updates.

## Selected behavior

Version 10 adds host-reported ping telemetry to the existing version-9
distributed netcode. It does not replace movement prediction, hit detection,
authority, weapons, game rules or the 30 Hz simulation. There are no new
matchmaking, relay or account services.

The host sends each player's smoothed round-trip measurement every 60 simulation
ticks (two seconds), using the existing unreliable transport. The new message
type is appended as 19; existing message numbers are unchanged. Each record is
four bytes: player index, padding and a 16-bit millisecond value. A host's local
players have zero ping, unknown is `0xFFFF`, and known values are bounded to
`0xFFFE`. At 128 players, a full message is approximately 520 bytes before
transport overhead, per client every two seconds.

The original scoreboard and original font rendering remain in this fork; the
newly received ping values do not add a visible column. The point of this update
is version-10 protocol compatibility. Existing exact-version checks mean that
version-9 hosts and clients must update to join version-10 rooms. Other upstream
clients can still choose upstream's own presentation features.

## Per-commit decisions

All seven new commits' actual diffs and relevant dependencies were reviewed.

| Upstream commit | Actual change | Decision and reason | Validation / integration status |
| --- | --- | --- | --- |
| [`9f3e8c92de7569a577c3044d05288dbd6590c5bf`](https://github.com/cybersecurity/halo-ce-universal/commit/9f3e8c92de7569a577c3044d05288dbd6590c5bf) | Replacement high-resolution postgame title/panel and extra title-asset generator capabilities; depends on the excluded text/title pipeline. | **Exclude.** Presentation replacement, with no independent engine correction required for networking. | Source/assets/build dependency diff reviewed; not integrated. |
| [`f0dfb58c94fa1a8f0f46cbd7df97dfda91a3dcb3`](https://github.com/cybersecurity/halo-ce-universal/commit/f0dfb58c94fa1a8f0f46cbd7df97dfda91a3dcb3) | Optional vsync-off frame limiter; default caps presentation at twice display refresh, with a 120 FPS fallback. Intended to avoid some Intel GPU hangs. | **Defer.** Potentially useful stability feature, but independent of netcode and a new rendering/config choice. It does not impose a 30 FPS cap or change simulation timing. | Actual swap/config code reviewed; no runtime test because not integrated. Requires the following build fix and a deliberate Mac adaptation. |
| [`ab96597321eb50ccb499e5cec540cfdd5aca2d84`](https://github.com/cybersecurity/halo-ce-universal/commit/ab96597321eb50ccb499e5cec540cfdd5aca2d84) | Restricts that new limiter to desktop config and compiles it out under `HALO_ANDROID`. | **Defer with the limiter.** It fixes only the preceding commit's build regression. | Actual guest flags reviewed: Mac also defines `HALO_ANDROID`, but selects desktop config. Importing the pair unchanged would expose a Mac setting with no implementation. |
| [`634b4197f91534625bf99cb9ef0abe88975a7213`](https://github.com/cybersecurity/halo-ce-universal/commit/634b4197f91534625bf99cb9ef0abe88975a7213) | Restricts the added overhead enemy labels using weapon/zoom range and fades them at the edge. It does not change actual weapon aim assist. | **Exclude.** Refines the previously excluded overhead-name feature. | Diff reviewed; depends on excluded `f2ba71d9`; not integrated. |
| [`b438cea47946b2e6471ccc41c7d3da3542fca7f6`](https://github.com/cybersecurity/halo-ce-universal/commit/b438cea47946b2e6471ccc41c7d3da3542fca7f6) | Further caps enemy-label range and reduces label text size. | **Exclude.** Same non-original overhead-label dependency. | Diff reviewed; not integrated. |
| [`fd3d62f9602870b209b8e0e5cd38d9f90ced6029`](https://github.com/cybersecurity/halo-ce-universal/commit/fd3d62f9602870b209b8e0e5cd38d9f90ced6029) | Strengthens name/ban handling, transliterates Latin names for ASCII matching, numbers duplicate names, rejects ambiguous bans, and restricts local profile/virtual-keyboard input. | **Defer.** Independent moderation work. Its generic virtual-keyboard changes also affect variant names/descriptions and campaign profiles; names without ASCII/transliterable Latin characters can become `Player`. A narrower host-side change can be reviewed separately. | Full diff and callers reviewed. No protocol dependency; not integrated. Duplicate queued late joins need targeted validation before claiming unique names in every case. |
| [`d1c7243cb20eab4488efa1266e259b1f4d5240f6`](https://github.com/cybersecurity/halo-ce-universal/commit/d1c7243cb20eab4488efa1266e259b1f4d5240f6) | Adds version-10 ping telemetry alongside a redesigned/scaled scoreboard, ping column, pagination and scoreboard input capture. | **Partially adopt.** Take the protocol and protocol documentation; exclude the redesigned scoreboard, text scaling, settings and input capture. | Integrated as `ea4dec3c`. The four selected upstream files match this revision exactly. Native build, five protocol tests, consecutive-match gameplay and both mixed-version rejection checks passed; details below. |

The October 1 exclusions remain: `0182da817285b67eee8264663ca79f7c32d66b5e`
(replacement fonts / OpenCE titles) and
`f2ba71d9af4c6fc65d7419cc22e8f4899b16da88` (overhead player names). Neither is
reintroduced. Existing high-resolution HUD assets were already present in the
older baseline; this update does not enable them or alter the fork's original-HUD
defaults or existing user preferences.

## Exact integration boundary

Taken unchanged from `d1c7243c`:

- `port/linux/game/network_distributed.c`
- `port/linux/game/network_distributed.h`
- `port/linux/include/halo_port_limits.h`
- `port/linux/NETCODE.md`

These files were identical to that commit's parent before the update, so no
earlier presentation or name-policy commit is required. The sender, receiver,
length checks, stale-packet checks and network version are taken together;
changing only the version number would not implement the protocol.

Excluded from the mixed commit: `source/game/game_engine.c`,
`source/rasterizer/rasterizer_text.c`, scoreboard settings in `port_config.c`,
scoreboard key/wheel handling in `sdl_platform.c/.h`, and their README entries.
In particular, holding the original scoreboard does not acquire the upstream
change that consumes weapon-wheel input for scoreboard scrolling.

Local supporting changes are a protocol regression test, an Apple CI step to
run it, and documentation/version updates. No application environment variables
are introduced.

## Verification and limits

- The four selected files were checked byte-for-byte against upstream.
- The complete native Mac guest, host and asset-free app build passed using
  LLVM 22; the bundle was ad-hoc signed by the existing build pipeline.
- All five tests in `python3 -m unittest tools.test_network_pings` passed with
  AddressSanitizer and UndefinedBehaviorSanitizer. They exercise extracted
  production functions and packet validation, including the version/message
  layout, ping rounding and bounds, empty/sparse/full messages, receiver roles,
  malformed lengths/counts/indices, stale packets and batched packets. The
  fixture does not directly test live transport, tick scheduling or full reset.
- Two real version-10 instances on one Mac completed two consecutive Blood
  Gulch Slayer matches during a 95-second encrypted-invite smoke run. Both
  simulated multiple players, exchanged updates and exited cleanly without
  assertions or faults. This used the original-presentation reference profile.
  Evidence: `consecutive-v10-desktop/validation.json`.
- A saved version-9 guest and the new version-10 guest rejected each other
  correctly in both directions (host 9/client 10 and host 10/client 9). Neither
  client joined the incompatible game; all four processes exited cleanly
  without faults. Evidence: `mixed-version-validation.json`.

Local evidence is under `build/macos/netcode-v10-review-2026-10-02/` and remains
ignored. Do not commit private room invitations, runtime saves or game maps.
Real-game tests use isolated data links, saves and config with the original
presentation profile.

Current-commit Windows/Android gameplay and physical cross-platform internet/NAT
interoperability are not established by a Mac build or protocol fixture. The
wire implementation matches upstream, but device-level interoperability remains
a separate verification boundary.
