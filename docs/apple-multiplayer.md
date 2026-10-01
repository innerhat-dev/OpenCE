# Apple multiplayer and Mac invite links

Build both devices from the same revision with the same map set. Native builds
use protocol version 9 and changed player capacities, so original Xbox games
and older native builds cannot join. See the [shared System Link notes](../port/linux/README.md#system-link)
for protocol details and limits.

## Play on Mac using an invite

Open `build/macos/Halo CE Universal.app`. Allow local network access if macOS
asks. Internet play and clipboard invites are enabled in the default settings.

1. On the host, choose **Multiplayer → System Link**, select a player profile,
   then create a game with **Y / Tab**. Pick a map and mode.
2. Hosting copies a `halo://join/` link to the clipboard. Paste it into a message
   for the other players. The link is also in `halo.log` in the save directory.
3. On a joining Mac, open the link. Alternatively, copy the link and bring Halo
   to the front. Go to **Multiplayer → System Link**, select a profile, and join
   the advertised game.
4. Once everyone appears in the lobby, start the match on the host.

The app registers the `halo://` scheme. macOS delivers an opened link to the
running app; the host queues it in that instance's save directory. A development
launch can also take the link as an argument:

```sh
"build/macos/Halo CE Universal.app/Contents/MacOS/halo" 'halo://join/YOUR_64_HEX_DIGITS'
```

Invites last for the hosting game process. Treat the link as access to the room.
Keep the host running and send a new invite after restarting it.

Gameplay travels directly between players. Public MQTT brokers provide
signaling and public STUN services help discover network addresses; UPnP can
ask a compatible router to forward a port. There is no game server or relay
to pay for. These public services and some NAT/firewall combinations can still
prevent a connection. This build does not provide guaranteed connectivity,
host migration, or a browser client. See the
[upstream connection notes](../port/linux/README.md#connection).

The current integration keeps the Apple ARM64/Metal renderer and merges
cybersecurity upstream through `cdd0291a` (console log verbosity). This
includes repeated-match input and client-role fixes, map compatibility checks,
mouse aiming changes, compressed networking updates, stronger hit and movement
validation, score/death replication, and version-9 distributed netcode. Invite
codes now contain 64 hex digits, including a longer hash of the host's key.
Older Mac and iPhone builds must be rebuilt before joining a version-9 room;
older rooms still require a matching older build.

The updates since the September 30, 5 p.m. Panama review also fix sound-cache
cleanup between games and vehicles waking after a client's movement. Clients
use the host's game rules; hosts can detect sustained speed hacks and ban
players, and received player and machine names are cleaned before display.
See the [shared netcode notes](../port/linux/NETCODE.md) for these rules.

The console now shows important messages by default. Set `console_log` in
the `[game]` section of `config.toml` to `"all"`, `"important"`, or `"none"`;
command responses and stopping asserts remain visible. This setting is
config-only in this fork.

The original Xbox decompilation was reviewed through `901aee16`, including
the new text and circular-queue matching work. This port already implements
those routines and retains its portable Unicode handling and Apple ABI.

PR #22 was reviewed through `2e00e652`. Its clock/uptime fix (`5d18a367`)
and Darwin broken-pipe protection remain included. Its LP64/OpenGL conversion
is a separate port; this app keeps the rebased ARM guest and ANGLE/Metal.

PR #20 was reviewed through `79cbcb94`. Its reachable host advertisements
and replies to game searches from outside the LAN remain included. Upstream's
new socket-port tracking replaces the earlier invite-port restriction. The
latest ANGLE framebuffer/blit correction (`ea1015e1`) is also included.
The Command-W protection (`716338d8`) is adapted in the native SDL bridge.
The Discord socket-directory fix (`79cbcb94`) is already covered by this
port's native environment and Darwin temporary-directory lookup.
Automatic Tailscale lookup, alternate compilation and ray-traced lighting
remain separate. The Mac renderer streams geometry to avoid stale cached
walls after changing from Prisoner to Chill Out.

## Connect the devices

Put the Mac and iPhone on the same LAN. Find the Mac's Wi-Fi IPv4 address in
System Settings → Wi-Fi → Details → TCP/IP, and the phone's in Settings → Wi-Fi
→ the information button beside the connected network. Allow Halo's local
network access when prompted. Guest networks with client isolation prevent
devices from reaching each other.

The current iPhone build uses explicit peer addresses for discovery. It does
not request Apple's multicast entitlement, which iOS requires for UDP
broadcast/multicast; ordinary unicast to the other device avoids that requirement.
See Apple's [multicast entitlement documentation](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.networking.multicast).

Quit existing copies of Halo. From the repository root, replace the placeholder
values below with your devices' current addresses:

```sh
MAC_IP=YOUR_MAC_WIFI_IP
PHONE_IP=YOUR_IPHONE_WIFI_IP

open -n \
  --env "HALO_NET_ADDRESS=$MAC_IP" \
  --env "HALO_NET_BROADCAST=$PHONE_IP" \
  "build/macos/Halo CE Universal.app"
```

For the iPhone, set these environment variables in Xcode → Product → Scheme →
Edit Scheme → Run → Arguments, then run the app:

| Variable | Value |
| --- | --- |
| `HALO_NET_ADDRESS` | The iPhone's Wi-Fi IPv4 address |
| `HALO_NET_BROADCAST` | The Mac's Wi-Fi IPv4 address |

Alternatively, install using the [iPhone instructions](../port/ios/README.md#install-on-a-phone)
and launch from the same shell as the Mac command. Replace the device and bundle
identifiers with your own:

```sh
xcrun devicectl device process launch --terminate-existing \
  --device YOUR_DEVICE_ID \
  --environment-variables "{\"HALO_NET_ADDRESS\":\"$PHONE_IP\",\"HALO_NET_BROADCAST\":\"$MAC_IP\"}" \
  com.yourname.halo
```

These environment settings apply only to that launch. To retain them for normal
launches, edit the existing `[network]` section of each device's `config.toml`:
set `address` to that device's IP and `broadcast` to the other device's IP. The
[Mac guide](../port/macos/README.md#launch) and [iPhone guide](../port/ios/README.md#install-on-a-phone)
give the save locations. Update these values if Wi-Fi or DHCP changes the
addresses. Keep personal addresses and generated Xcode schemes out of commits.

## Start a match

1. On the Mac, choose **Multiplayer → System Link**, select a player profile,
   and create a game (Y / Tab). Choose a map and a mode such as Blood Gulch / Slayer.
2. On the iPhone, choose **Multiplayer → System Link**, select a profile and
   join the Mac's advertised game.
3. Wait until both players appear in the lobby, then start the match on the host.

The session should keep running after both maps load, and movement, shots and
damage should agree on both devices. This setup covers LAN multiplayer; it does
not establish campaign co-op, internet matchmaking or compatibility with every
other native platform.

## Diagnosing a disconnect

The Darwin adapter handles Halo's connected UDP sockets specially: Halo still
passes the server address to `sendto()` after connecting, which Apple rejects
with `EISCONN`. The adapter retries with `send()` only if the destination matches
the connected datagram peer. Without this fix, discovery and joining work, but
gameplay packets fail and the match closes shortly after loading. Rebuild both
apps if either predates the fix.

The socket regression probe uses loopback and needs no game data or SDK:

```sh
mkdir -p build/macos/tests
clang -arch arm64 -O2 -Wall -I. -Iport/linux/src \
  port/macos/tests/host_network.c port/macos/host/posix_net.c \
  -o build/macos/tests/host_network
build/macos/tests/host_network
```

It checks discovery sends, connected gameplay sends with explicit and omitted
destinations, empty datagrams, truncated datagrams, received
addresses and refusal to redirect a mismatched destination to the connected peer.
It also runs as part of `python3 tools/test_macos_runtime.py`.

The real-game smoke test uses separate saves and settings for two copies on one
Mac. It exercises either LAN discovery or an encrypted invite and records
movement and network updates. It requires game maps and a configured LAN IPv4
address, while keeping personal saves, clipboard and Discord activity untouched:

```sh
python3 tools/macos_multiplayer_smoke.py --mode invite --seconds 65 \
  --output build/macos/multiplayer/invite-test
python3 tools/macos_multiplayer_smoke.py --mode lan --seconds 65 \
  --output build/macos/multiplayer/lan-test
python3 tools/macos_multiplayer_smoke.py --mode invite --seconds 95 \
  --variants slayer,slayer --score 1 \
  --output build/macos/multiplayer/consecutive-test
```

Use a fresh output directory for each run. Two physical Macs on different
networks and 128-player capacity still need separate testing.
LAN mode also needs a second configured non-loopback IPv4 address on the Mac
(for example an existing VPN interface); it discovers that address automatically
or accepts `--client-address`. Invite mode works with LAN plus loopback.
The local invite test passed on the M5 Max. Direct discovery between its LAN
and VPN interfaces did not find the host; that path and LAN play between two
physical Macs remain unverified. Use the invite path for the current POC.

The protocol-9 candidate (build 6) passed a 95-second run with two consecutive
Slayer matches over an encrypted invite on the M5 Max. Both
instances exchanged updates and exited cleanly without a fault or unexpected
kick. The native runtime probes also
cover current invite lengths, Discord socket ownership, Command-W handling,
and occupied UDP ports used by UPnP cleanup. A private mock Discord RPC test
delivers the current join secret into the real game without changing Discord
activity:

Build 7 adds the console logging update. It passed the seven input-binding
checks, the private Discord invite test, and a 65-second encrypted two-instance
match. These tests use isolated saves; the installed app keeps existing player
profiles, controls and audio settings.

```sh
python3 tools/macos_discord_smoke.py
```
