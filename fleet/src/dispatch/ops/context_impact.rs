//! `fleet impact`'s caller resolution, split out of `context_cmd.rs` to keep both files under
//! the 80-line gate (same reason `repomap_parse.rs` was split out of `repomap.rs`).
//!
//! `build_repo_map` already returns `edges: Vec<(SymbolId, SymbolId)>` -- caller, callee. Before
//! this module the command loaded those edges and never read them: it counted symbols whose name
//! matched and reported that. So `impact --symbol build` answered "5", meaning five functions are
//! *named* `build`, while the repo holds 26 places that *call* one. The count was a fact about
//! the name, not about the blast radius.
//!
//! **What an edge does and does not carry.** It is a pair of ids -- caller, callee -- and nothing
//! else. There is no call location in it, so this reports the functions that call the target and
//! where each of *those* is defined. It deliberately does not say "line 7 and line 8 of
//! `caller_two`": the graph does not know that, and naming the field `call_sites` would have
//! implied it did. One calling function is one row however many times it calls.

use context::{RepoMap, SymbolId, SymbolRef};
use std::collections::{HashMap, HashSet};

/// A function that calls the searched-for symbol. `path`/`line` locate the *caller's own
/// definition*, not the call -- see the module note.
#[derive(serde::Serialize)]
pub struct Caller {
    pub name: String,
    pub path: String,
    pub line: u64,
}

/// Every function that calls any symbol named `symbol`, sorted by `(path, line, name)` so two
/// runs of the same repo produce byte-identical output.
pub fn callers(map: &RepoMap, symbol: &str) -> Vec<Caller> {
    let targets: HashSet<&SymbolId> = map
        .symbols
        .iter()
        .filter(|s| s.name == symbol)
        .map(|s| &s.id)
        .collect();
    if targets.is_empty() {
        return Vec::new();
    }
    // An edge is two opaque ids; this index turns a caller id back into its name, file and line.
    let by_id: HashMap<&SymbolId, &SymbolRef> = map.symbols.iter().map(|s| (&s.id, s)).collect();

    let mut found: Vec<Caller> = map
        .edges
        .iter()
        .filter(|(_, callee)| targets.contains(callee))
        // A caller with no entry in `by_id` is a call from outside the parsed set (a dependency,
        // a macro body). Dropping it is correct: we cannot name a file or line for it, and
        // emitting a placeholder would be inventing evidence.
        .filter_map(|(caller, _)| by_id.get(caller))
        .map(|s| Caller {
            name: s.name.clone(),
            path: s.path.clone(),
            line: s.line,
        })
        .collect();

    found.sort_by(|a, b| (&a.path, a.line, &a.name).cmp(&(&b.path, b.line, &b.name)));
    // A function that calls the target three times is still one function to review. The key must
    // carry `line`: a function's identity here is (file, line), not (file, name). Two different
    // functions can share a name in one file -- a TypeScript overload pair, a Python redefinition --
    // and keying on name alone silently drops one of them from the report. `SymbolId` does not help,
    // because it is derived from (path, name, arity) and carries no line either.
    found.dedup_by(|a, b| a.path == b.path && a.line == b.line && a.name == b.name);
    found
}
