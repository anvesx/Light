# Changelog

Release convention: every push to `main` requires a matching versioned note under
`docs/releases/` and an entry in this file. See [CONTRIBUTING.md](CONTRIBUTING.md).

## [0.2.1] - 2026-09-22

Independent of 0.2.0 — cut from `main`, no shared files. 0.2.0 landed first, so this keeps 0.2.1.

### Added

- `fleet impact --symbol <name>` now reports the functions that call the symbol, under a new
  `callers` field. `build_repo_map` already returned `edges: Vec<(SymbolId, SymbolId)>`; the
  command loaded them on every run and never read them, so `impact --symbol build` answered `5`
  (five functions *named* `build`) while the repo held 26 places calling one.
- `src/tests/impact_lists_callers` — 6 tests against the real binary.

### Changed

- `ImpactReport` gains `callers`. `matching_symbols` is unchanged, so existing JSON consumers keep
  working.

### Notes

- The field is `callers`, not `call_sites`, because an edge carries no call location: a reported
  line is where the *caller* is defined. A function calling the target three times is one row.
  `the_reported_line_is_the_callers_own_definition_not_the_call` pins that limit on purpose.
- Verified on `posx-mokobara-backend` against grep: `customerIdentityPhone` → 5 call locations
  inside **3** handler functions, reported as 3 callers; `performShopifyReturnWithRefund` → the
  2 subscribers that call it.
- `fleet graph` is untouched and still prints only three counts.

## [0.2.0] - 2026-09-22

### Added

- TypeScript and TSX symbol extraction in `crates/context`, so `fleet graph` and `fleet impact`
  cover `.ts`, `.tsx`, `.js`, `.jsx`, `.mts`, `.cts`, `.mjs` and `.cjs`. Measured on the POSX
  estate: the backend goes from 2 files / 60 symbols / 65 edges to 1,304 / 1,486 / 1,642, and the
  storefront from 0 / 0 / 0 to 458 / 1,216 / 1,327.
- `extract_definition_ts` handles the definition shapes TypeScript actually uses —
  `function_declaration`, `generator_function_declaration`, `method_definition`, and the binding
  forms `variable_declarator` / `public_field_definition` whose value is an `arrow_function` or
  `function_expression`. Arrow-consts outnumber `function` declarations in both POSX repos
  (580 vs 436, and 531 vs 403), so handling only the latter would miss the majority.
- `Language::Tsx` as a separate variant: tree-sitter ships two grammars because JSX conflicts
  with type assertions, and 248 of the storefront's 458 source files are `.tsx`.
- `crates/context/tests/typescript_symbols` — 6 tests. Disabling only the arrow-const path fails
  4 of them; restoring it returns 6/6.

### Changed

- `Language` gains two variants. This breaks an exhaustive match downstream, which is why this is
  a minor and not a patch release.

### Known limitations

- `impact` still counts definitions, not call sites (`build` → 5 definitions, 26 real call sites).
  This release makes that count correct on TypeScript; it does not change what is counted.
- `graph` computes 1,642 edges on the POSX backend and exposes none of them.
- Nothing here is wired into dispatch; a build lane still receives no assembled context.
- `clippy -D warnings` and 16 workspace test targets fail identically on `origin/main`, verified
  on a pristine worktree. See `docs/releases/v0.2.0.md`.

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
