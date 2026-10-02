# Halo fork: contributor and agent rules

## Project direction

This is `pfista/halo-ce-universal`, the Xbox-derived Apple port. Preserve original
Xbox Halo: Combat Evolved NTSC gameplay and presentation while improving native
performance, portability and online play. Community maps are separate content
imports; they do not authorize adopting another engine's competitive rules.

## Reviewing cybersecurity upstream

Stay current with useful core improvements from `cybersecurity/halo-ce-universal`
through selective integration. During upstream update work, fetch and review all
new commits since the last recorded review; inspect the actual diff and its
dependencies, not just the commit title. Do not merge upstream wholesale.

- Prioritize verified decompilation/matching accuracy, correctness, stability,
  performance, renderer correctness and platform compatibility fixes that
  preserve the original game's behavior and appearance.
- Consider netcode and matchmaking improvements case by case. Review their
  effects on simulation timing, input, fairness, session compatibility and
  service dependencies before adoption. Their category alone is not approval.
- Exclude renaming/rebranding (including OpenCE), replacement fonts or artwork,
  new overhead player labels, and changes to sounds, weapons, balance or game
  rules from the original-game baseline. Timers and other competitive
  modifications require separate explicit user direction.
- Split mixed commits or port the relevant fix when possible. Do not take an
  unwanted modification merely to obtain a performance or matching improvement;
  defer the change with a reason if it cannot be separated safely.
- Record each reviewed commit's hash, purpose, decision (adopt, partially adopt,
  exclude or defer), behavioral effect and relevant validation in
  [the fidelity policy](docs/xbox-fidelity.md) or a linked review record. Track
  the last reviewed revision separately from the last integrated baseline so
  excluded commits are not accidentally reintroduced during later updates.
- Run checks appropriate to the selected change. Assess performance with
  comparable settings and workloads; verify gameplay-sensitive changes against
  the chosen Xbox reference and record any remaining uncertainty.

## Fidelity and performance are separate checks

Preserve the original 30 Hz simulation. High-refresh rendering (for example
120 FPS) can be appropriate without changing the game rules; review interpolation
and camera/input latency separately. A 30 FPS reference preset is a comparison
tool, not a requirement for normal play or a reason to reject performance work.
Do not silently impose a rendering cap as part of a gameplay-fidelity change.

Matching decompilation progress refers to the original executable target and
build configuration. Do not describe a native ARM Mac executable as byte-identical
to an Xbox executable, or a successful smoke test as proof of full retail parity.

Read [docs/xbox-fidelity.md](docs/xbox-fidelity.md) for the recorded baseline,
excluded upstream changes, current settings and validation limits, and
[docs/apple-build.md](docs/apple-build.md) for build and contribution workflow.
