# Changelog

Release convention: every push to `main` requires a matching versioned note under
`docs/releases/` and an entry in this file. See [CONTRIBUTING.md](CONTRIBUTING.md).

## [0.2.2] - 2026-09-22

Docs only. Independent of 0.2.0 (`feat/typescript-symbol-graph`) and 0.2.1
(`feat/impact-call-sites`), both of which are open PRs off `main`. Renumber if they land in a
different order.

### Added

- `docs/blueprints-next/_research/central-kb-connectivity.md` — how `retail-os-central-kb`
  (129 files, 96 of them corpus) reaches a builder lane through the existing `knowledge -> context`
  edge. Records the measured gap: `scan` and `plan` are stubs, `knowledge` is `partial`, and a lane
  receives only the task string.
- `docs/blueprints-next/_research/learning-promotion-loop.md` — how a verified failure becomes a
  rule that blocks, through `verify -> candidate -> offline -> knowledge -> standards`. Records
  that `offline`, the node preventing one failure from becoming a rule, is greenfield.

### Notes

- Both are proposals naming their own open decisions, not settled designs.
- `FD-8` blocks the KB plan: until a Node repo can pass a gate, a contextualised lane still
  refuses. Order is FD-8 → KB connectivity → promotion loop.

## [0.1.1] - 2026-09-15

### Added

- Human-readable LLD execution tracing for `fleet run`.
- Numbered LLD path logs for every stage and node, including crash-resumed stages.
- Interactive-answer tracing that identifies the direct adapter path and states when the full
  pipeline is not traversed.
- Native Apple Silicon development artifacts under `target/aarch64-apple-darwin`.

### Fixed

- `cargo-watch` now invokes `scripts/fleet-build.sh` through shell mode instead of incorrectly
  dispatching `cargo bash`.
- Adopted legacy watchers now use their existing `.dev-watch/watch.log` for diagnostics.
- `./dev.sh watch` stays in watcher mode instead of forwarding `watch` to Fleet.
- ARM64 development no longer selects the x86_64 Rust toolchain when the native toolchain is
  installed.
- The optional `sccache` wrapper is opt-in via `FLEET_USE_SCCACHE=1`; the default avoids a
  stalled ARM64 Cargo/x86_64 toolchain combination.

### Verification

- Native binary confirmed as `Mach-O 64-bit executable arm64`.
- `cargo test -p print`: 19 passed.
- Repeat native build: 0.436 seconds after the initial 63-second build.
- Real `fleet run` printed the LLD path trace through Verify.

### Known limitation

- The real pipeline run reached Verify but the repository secret scanner timed out, so that run
  is not recorded as a full pipeline pass.
