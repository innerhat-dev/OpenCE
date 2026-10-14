# Apple server discovery and protocol 28

Superseded for current builds by [protocol 29](apple-network-29.md). This record
describes the preceding integration and its validation.

The Apple baseline is innerhat `036b9fe609bdba518711464ce24d2a2d9a3d7caf` (protocol 26).
This targeted update uses OpenCommunityEdition/OpenCE `b1ef7f7e` (protocol 28),
with the original authors retained on cherry-picked commits. It does not merge
upstream wholesale. The old protocol-11 narrative in the inherited fidelity
policy predates this Apple migration; it is not the protocol of these builds.

## Changes and behavior

- iOS previously omitted `brokers.txt`. Bundle it and atomically refresh the
  default beside `save/config.toml` on launch. A separately named custom broker
  file is untouched.
- Adopt the required map-sharing protocol and downloading-player admission,
  multiplayer BSP/light behavior and reconnect fixes. Retain the original 30-Hz
  simulation and the existing Apple graphics settings.
- Rank open games with room and no previous join failure first, by player count.
  Sort the entire directory before truncating to a caller's visible rows, so a
  busy game outside the first eight received records is not lost.
- Empty results name the supported network version. Incompatible versions are
  still excluded; pretending to use their version would not be safe compatibility.
- Keep scenario music text suppressed, native Apple UI, personal branding split,
  importer isolation and existing local transport/PB capability fixes.

## Validation

- The source-derived wire manifest exactly matches upstream version 28, including
  the map-share structs and array dimensions (`tools/network_format.py`).
- Device guest and native Mac guest/host compile successfully.
- Isolated native Mac browser test joined the populated public "The Dude"
  Blood Gulch server, loaded into play and exchanged replicated gameplay updates;
  the process exited normally. No user saves were used, no automated shooting,
  no map seeding and no router UPnP changes. This is a short interoperability
  check, not full-match or physical-iPhone acceptance.
- Lobby ranking/truncation test under ASan/UBSan and both menu checks passed.
- Cache-format tests: 128 passed, four platform-dependent skips.
- Map-share filename/piece tests and their negative controls: 15 passed with
  the native Mac compiler. The original harness's `-m32` cannot link on Apple
  Silicon; this supplemental run omits that flag, so it is not a 32-bit ABI test.
  The actual ILP32 device build and source wire check cover separate ABI evidence.
- Broker probing found populated v28 listings alongside older versions; player
  counts are transient. Two of the four brokers answered the probe; discovery
  intentionally uses redundant brokers.

## Upstream decisions

These are the 62 non-merge upstream commits not ancestors of the inherited
Apple baseline. Some were already cherry-picked/adapted by that baseline. Only
the selected networking changes and their dependencies are integrated here;
remaining renderer/web/presentation work is explicitly deferred. The selected
patches were checked against retained Apple changes rather than replacing whole
network files. This ledger is not a claim of gameplay validation for deferred
changes.

| Commit | Purpose | Decision |
| --- | --- | --- |
| `d36c15c313dd96fbeb0f1a03431f000e18bd63e0` | Your own legs in first person, seen looking down (display.first_person_legs) | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `8664d2f24b2d855ea0369c27a5cb007f7757c570` | Your energy shield in a multiplayer armor color (display.shield_color) | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `2af955e1d6548e584066a4e68ce7431bb02c8994` | Space the campaign pause rows like the profile settings list. | Already equivalent in the inherited Apple baseline; no reapplication. |
| `1463c87090022950bc8b9e230fbaea4b0204e50b` | Energy shields glow as they flare, in their own color (display.shield_glow) | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `af7ad15d3c3bac0e459a719f6036f25db444b1e2` | Keep a respawned vehicle on the name its teleporter uses. | Already equivalent in the inherited Apple baseline; no reapplication. |
| `6ea142ceee1481eaf587b90a81f870e92da3fd94` | Fix co-op stale player handle crash | Already equivalent in the inherited Apple baseline; no reapplication. |
| `77794aa1b7a4dd70f20b4f2068a1a3a2482cd842` | Stand-in machines send the join request's hardware id | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `0f9a8904cd674e1cd3a5aad4a2a4c3eb69cc182c` | Test the stand-in machines' messages against network_messages.c | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `fb97e52663fde1c5a6b3bc116027113414fe1368` | Stale player handles forgotten in the port's loop (#250) | Already equivalent in the inherited Apple baseline; no reapplication. |
| `ebb1f093aed4ec7fac36dba81b7e37928b7f054f` | Campaign pause rows 30 apart, as the PC version's (#246) | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `21db5f906519d467c477309d56b18ccf7b751a06` | Vehicle homes: no other home's vehicle taken, no ridden one deleted (#249) | Already equivalent in the inherited Apple baseline; no reapplication. |
| `f735ca152d8a433245847b0a40b117d1ad3db26e` | First-person legs: one mesh kept, its waist forgotten on a new map (#243) | Already equivalent in the inherited Apple baseline; no reapplication. |
| `1f48f0555d0ec986af6cf4b012250f968a623677` | Shield glow: one light per unit in split screen, light show not clamped (#247) | Already equivalent in the inherited Apple baseline; no reapplication. |
| `095973133ee38e4d680fca9bff4138edc81abe43` | Shield color on the first-person arms too (#244) | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `acfa9a2a4ddcea41737d2f511fd15b819992f128` | Web build | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `a55a18208637c34bcd4ab49e94b222e0c1ed2dff` | Web deploy, tests, docs | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `532407588ed39392c091e716735016b6a76409ed` | Web loading indicator | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `4a9e515d54f9dac7e2de21f21ca49bc273989bba` | Web touch controls | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `47b7eac9a8911b879e236a067a48285f09df1f21` | Web rooms over WebRTC | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `887f40bd2c128b7b784193892c23ac41d8cae98c` | Web opaque canvas | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `6dc423fdbfadc2aaa0cf8a90de54075c73a46b2c` | Internet play with browsers | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `c89eb80d3abb404ecf283ea3650c87b74d1eddbc` | Web: no return addresses, SIMD page hash | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `19f1bd9f5dd27863ade762914b7a3ab5df73421c` | Web: pointer lock taken back on a click, wheel notches | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `248210cedbb731b628727d69212a12692ee71c35` | Keep first-person shield flares close to the arms | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `2e45259beafaced7c0d1cfca179d0e865a973ea5` | Delete tools/test_viewmodel_shield.py | Already equivalent in the inherited Apple baseline; no reapplication. |
| `0bfe2112892ec47aa6d78b5b5e8fc1da6434c1fa` | Web: stable pages hashed less often, fewer clock reads | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `01afcb654a1ce7f331ca500d6baeb881ccb0b1ce` | First-person shield flare kept close only with display.viewmodel_shield (#254) | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `6399ed9d4ab1e6bbcd6154d56703883dfcc17c22` | Text drawn a string at a time, web immediate draws packed | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `a3277d94dc51bfbeafd1cba52f279fa6da220f80` | Fewer draws and GL calls | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `5cd65a0cb0c3df69079e6c9af0bbd31d0df3dab9` | Web: meter blend in the shader | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `17a57832d8fc79867fc546eb2e5d3e5cb587d446` | Windows: tag block accessor builds again | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `e0b581b157999e90382668dbc5578528e85701cc` | Web: disclaimer footer | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `59a74b0c4b2975be46de751ee1818f514f4fd683` | The pregame screen opened through the port's menus everywhere | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `568f8c1fe7714423eb4a43843f50e98eac025e5f` | Web draws' uploads put in buffers no queued draw reads, so Metal does not wait | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `0a5a235f5e7813d4d6f6dae804352bc450d3173c` | Ask STUN and the brokers again after the p2p thread was stopped | Adopt: reconnect broker sockets and STUN after suspension. |
| `dc9b842ce2f155cf3274c3ce209231ac147c2920` | Draw with a base vertex on OpenGL ES 3.0 and 3.1 with the extension | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `1e7946659c5497c0448712bd1c3c60d1facc1da9` | config.toml with each section once, and a file with [display] twice read again | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `2059b6cef5339f4717b14c6cc98ec477aedfdd9e` | A player joining or leaving the lobby no longer restarts the countdown. | Adopt: do not restart the lobby countdown for playerless joining/leaving machines. |
| `71ceb363f19200d81b5ce71908577781487ccbc8` | Players who already have the map no longer wait for a machine that is still downloading it. | Adopt: a downloading machine does not hold up players with the map. |
| `a2aad18f65e6a5878bcb4daf553a2068e52897ee` | Custom Edition map sharing | Partial: protocol-27 map-transfer messages, verified pieces, peer reachability, cache support and settings. Retain native menu placement; exclude upstream AGENTS/web-only documentation changes. |
| `7a6fc70eb91078a1713cbf719114d48ceed4756f` | Fit the high-res text's fonts to the widths of a Custom Edition loc.map's letters | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `13ddcf802a0302291d534e9f75d50920d4e50483` | Keep a scenario's titles under the menus | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `67f22142197e40a35a36679751b5d794eeaba7bc` | A player still downloading the map no longer spawns until that player joins. | Adopt: hold downloading players out of simulation. |
| `05dd9ccdea94d8d3686ae55a9b71bc466d52b4e8` | Create the custom_maps folder on startup when it is missing. | Adopt: create the custom map directory before downloading. |
| `baab0780f6c230ef8a994e843057e6f1d1e16f16` | Adding a player after a map download uses the same checks as any other late join. | Adopt: admit downloaded players through the normal late-join queue. |
| `d6df944886a9e63807ef2af927ff07b8287df7be` | Bring a co-op team inside with a scripted teleport. | Adopt: host-authoritative co-op teleports to the script destination, including larger groups. |
| `5e5cb08820bbc422e199b4d88f82f90853d5d2cc` | Test that a scenario's titles stay under the menus | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `417de7e2ad0ad3b3b70f0502231db6b72d9db7df` | A multiplayer match keeps the flashlight past the Xbox player and vehicle limits. | Adopt: retain flashlights/lights beyond original player limits, required for version-28 agreement. |
| `c3365b1c6979b946c4a77cc274f75f9d8dd45650` | A multiplayer script that switches BSP to cycle the sky no longer reloads the level. | Adopt: prevent repeated multiplayer scripted BSP reloads. |
| `b71bd6a0faf5fa887eed3c22905afcbfe459facf` | Keep a multiplayer map's first scripted BSP switch so the host's game type chooses the sky. | Adopt: keep the first scripted multiplayer BSP chosen by the host game type. |
| `0b4a03561b004bc93e8a1178b01fad1463de9fab` | A large co-op fight respawns beside the group after ten seconds. | Already equivalent in the inherited Apple baseline; no reapplication. |
| `679bade466d55a49ebcaa818ae0d38e11f5a0f07` | Menu rows keep one vertical step. | Already equivalent in the inherited Apple baseline; no reapplication. |
| `2598dbe8b660ca5759a37e0a090a876179fd2e9b` | An overshield's drain is not a shield hit, and a second weapon is readied. | Already equivalent in the inherited Apple baseline; no reapplication. |
| `1068da0c3a98af143bdc7fb8b660aed5e7b0fe1b` | Compare shader keys and draw uniform inputs a word at a time | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `2c6c85cf38a7993d0a1740b04cc3e51ad754556e` | Raise the transparent geometry groups a frame from 384 to 2048 | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `9180bd37c81487218177fc5326d84a0361591c7a` | NETCODE.md: network versions 22 to 25 | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `fab098a7bd6f7d0a3114b5dd66c408016b37a24f` | Record the wire format of the network version | Partial: adopt the wire-format checker and manifest at their final upstream revisions. |
| `eea1c3641a2645330940effaeb8bc342601d5978` | Keep the debug model vertices off the stack | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `e791cf9ae08f5a139e8a1fadbcbc765b6b2a6f41` | Bodies the host moves are no longer drawn floating or in walls on clients. | Defer: no changes selected for this native discovery/protocol update; inherited adaptations remain. |
| `5a7c655a60555215864391433716ddd966ba3079` | Testing branch review fixes | Partial: protocol 28, map-download timeout/admission fixes and safe co-op spawn/teleport positions. Exclude unrelated menu-coordinate and shield-HUD edits. |
| `3d67397cdd3c9ee1515b62cf5a8168cf3def0730` | Record the wire format at network version 28 (#253) | Adopt: version-28 wire manifest. |
| `c6a2f9004bb182ac6c11fa0fe902d59f3a7cfcb4` | Record the map sharing messages and the sizes of the wire format's arrays (#253) | Adopt: include map-sharing structs and array-size definitions in the wire manifest/checker. |

## Menu integration correction (builds iOS 24 / macOS 17)

The first protocol-28 release contained `platform="desktop android"` on the
map-sharing widget. This branch's runtime XML reader accepts a single platform
name; the invalid value rejected the entire custom menu set and fell back to
Xbox menus, hiding the server browser. The live Mac network test bypassed this
menu path and therefore did not establish browser usability. Removing the
unnecessary platform attribute restores the shared widget on both platforms.
The XML validation now matches the runtime's single-value rule.

With the corrected guest image, an iPhone simulator loaded 1006 menu widgets.
Opening Multiplayer's Server Browser displayed 35 public servers, ordered by
joinable population (38 players on the first listing at capture time).
An XCTest-driven simulator check confirmed landscape application geometry
with portrait, landscape-left and landscape-right device orientations, plus
background/resume. The scene's launch-side lock was removed so the two supported
landscape orientations can follow rotation. Device and simulator builds passed;
physical-device rotation has not yet been retested. Screenshot pixel dimensions
alone are not an orientation assertion: XCTest image orientation metadata may
leave raw image dimensions portrait even when the app frame is landscape.
