# Follow-up to the original Apple PR review

Reviewed [OpenCommunityEdition/OpenCE #64](https://github.com/OpenCommunityEdition/OpenCE/pull/64)
on 2026-10-12. GitHub returned two discussion comments and no inline review
comments or submitted reviews. This follow-up targets
[innerhat-dev/OpenCE #1](https://github.com/innerhat-dev/OpenCE/pull/1).

## Gameplay and controls

Source: [UEMxMDE's six-part report](https://github.com/OpenCommunityEdition/OpenCE/pull/64#issuecomment-6028960061).

| Feedback | Current disposition |
| --- | --- |
| No ordinary split-screen multiplayer or co-op entry | The innerhat base supplies multiplayer lobby **Add Player** / controller **Start** joining and **Co-op Campaign**. The menu fallback bug that hid the current menus is fixed. This revision also removes the desktop single-gamepad reassignment rule on iOS, where touch already occupies player one's port. Physical multi-controller gameplay still needs testing. |
| Cannot use touch and a controller as separate players | Added opt-in **Touch as a separate player** to the shake settings, persisted across launches. After relaunch, touch stays visible on player one and hardware controllers have separate slots. The default remains automatic touch hiding and shared player one, as requested by this fork's owner. No hide-controls switch is offered when touch is the only input. |
| SWAP G and LIGHT swapped | Already corrected in the migrated iOS controls: LIGHT → SDL left shoulder → Xbox white → flashlight; SWAP G → SDL right shoulder → Xbox black → switch grenades, with the default profile bindings. This is not a new upstream fix in this revision. |
| Pause-menu navigation moves the player | Already addressed by upstream [129d3483](https://github.com/innerhat-dev/OpenCE/commit/129d3483dcf0602eb46b033738dd92cae960500c). `player_control_port_menu_has_controller` suppresses gameplay input for the player whose controller owns a menu. A network match itself continues running; other players are not paused. Retained without replacing upstream's fix. |
| Custom Edition support and cross-play | Partial: the current protocol-28 integration includes upstream community-map discovery/transfer and download admission. It does not provide an iOS standalone Custom Edition import/switcher, and no claim is made that arbitrary Xbox and CE content can share a match. Retail ISO import remains the startup path; full CE content import and end-to-end CE-map interoperability remain follow-up work. |
| Move/remap/add/remove touch controls, reset, named layouts; physical remapping | A full touch-layout editor and named controller-layout manager are not implemented. These are feature requests, not closed by the routing fix. Track separately rather than claim the graphics settings or default profile bindings satisfy them. |

## Hosting and CI

Source: [cybersecurity's hosting/testing concern](https://github.com/OpenCommunityEdition/OpenCE/pull/64#issuecomment-6075561927).

The contribution moved to the Apple-maintained innerhat fork, whose base already
contains macOS workflows. It asks for no workflow or runner changes in the old
OpenCommunityEdition repository. This does not eliminate Apple runner costs or
transfer physical-device testing responsibility to the original maintainer.
The controller regression checks extend the existing Apple job; they add no
new runner job. Personal bundle identifiers and artwork remain downstream on
`apple/ios-internal`, outside this PR.

## Validation and limits

`tools/test_ios_controller_routing.py` compiles the production routing functions
with deterministic discovery/input and ASan/UBSan. It checks default sharing,
separate-player isolation, controller disconnect/reconnect, bounded enumeration,
modal input suppression, and the different iOS/desktop single-controller rules.
These checks establish routing behavior, not a complete multiplayer match.
The device build validates the Objective-C settings/controls and iOS guest code.
No physical iPhone/iPad installation or play session was performed for this review.

## LiveContainer startup follow-up

[UEMxMDE's follow-up](https://github.com/innerhat-dev/OpenCE/pull/1#issuecomment-6139443664)
reports successful import followed by `KERN_INVALID_ADDRESS` reserving the
fixed guest arena on iPhone 17 Pro Max / iOS 26.0. The logs do not distinguish
missing host-process Extended Virtual Addressing from other container VM
restrictions. LiveContainer documents that guest entitlements do not apply to
its host; its file-picker workaround does not resolve this requirement.

The startup memory check now runs before import, logs the requested base/size
and kernel code, and directs users to standalone signing without deleting data.
The fatal SDL message box is replaced by a dedicated scene-backed, scrollable
UIKit screen. Its Copy details and Close buttons remain outside the scrolling
text. A forced-error XCTest on an iPhone simulator exercised both buttons on
three launches with orientation changes. An unsigned device build also passed.
This is failure-path validation, not a LiveContainer compatibility result.
