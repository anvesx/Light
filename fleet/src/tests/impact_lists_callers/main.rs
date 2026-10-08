//! Drives the real compiled `fleet` binary (BLUEPRINT §9).
//!
//! `impact` already loaded `RepoMap::edges` and never read them, so it answered "how many symbols
//! carry this name" while presenting itself as an impact command. These tests pin the difference.
//!
//! They also pin the honest limit. An edge is `(SymbolId, SymbolId)` and carries no call
//! location, so `caller_two` below -- which calls the target twice, on two different lines --
//! is ONE row, reported at the line where `caller_two` itself is defined. The first draft of
//! this test asserted three rows and failed, which is how the field came to be named `callers`
//! rather than `call_sites`.

#[path = "../support/mod.rs"]
mod support;
use support::cmd;

/// Two callers of `target`, one of them calling it twice on separate lines, plus a function that
/// does not call it at all -- so counting symbols, or counting every function, gives a different
/// number than the correct one. The double call also pins the dedup: two calls, one caller.
const FIXTURE: &str = r#"
fn target(x: u64) -> u64 { x + 1 }

fn caller_one() -> u64 { target(1) }

fn caller_two() -> u64 {
    let a = target(2);
    let b = target(3);
    a + b
}

fn unrelated() -> u64 { 7 }
"#;

fn impact_json(dir: &std::path::Path, symbol: &str) -> serde_json::Value {
    let out = cmd()
        .args([
            "impact",
            "--repo",
            dir.to_str().unwrap(),
            "--symbol",
            symbol,
            "--json",
        ])
        .output()
        .expect("run impact");
    assert!(
        out.status.success(),
        "impact failed: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    serde_json::from_slice(&out.stdout).expect("impact emits json")
}

fn fixture_dir() -> tempfile::TempDir {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("lib.rs"), FIXTURE).unwrap();
    dir
}

#[test]
fn reports_every_call_site_not_just_the_definition_count() {
    let dir = fixture_dir();
    let report = impact_json(dir.path(), "target");
    assert_eq!(report["matching_symbols"], 1, "one definition of `target`");
    let found = report["callers"].as_array().expect("callers array");
    assert_eq!(
        found.len(),
        2,
        "two calling functions; caller_two's two calls collapse to one row"
    );
}

#[test]
fn a_caller_names_its_file_line_and_function() {
    let dir = fixture_dir();
    let report = impact_json(dir.path(), "target");
    let found = report["callers"].as_array().unwrap();
    let names: Vec<&str> = found.iter().map(|c| c["name"].as_str().unwrap()).collect();
    assert!(names.contains(&"caller_one"), "got {names:?}");
    assert!(names.contains(&"caller_two"), "got {names:?}");
    assert!(!names.contains(&"unrelated"), "got {names:?}");
    for caller in found {
        assert!(caller["path"].as_str().unwrap().ends_with("lib.rs"));
        assert!(caller["line"].as_u64().unwrap() > 0, "a real line number");
    }
}

#[test]
fn the_reported_line_is_the_callers_own_definition_not_the_call() {
    // Pins the limit deliberately: `caller_two` is defined on line 6 and calls `target` on 7
    // and 8. If the graph ever carries call locations this test should be the one that fails.
    let dir = fixture_dir();
    let report = impact_json(dir.path(), "target");
    let two = report["callers"]
        .as_array()
        .unwrap()
        .iter()
        .find(|c| c["name"] == "caller_two")
        .expect("caller_two present");
    assert_eq!(two["line"], 6, "the line where caller_two is defined");
}

#[test]
fn an_uncalled_symbol_reports_a_definition_and_no_callers() {
    let dir = fixture_dir();
    let report = impact_json(dir.path(), "unrelated");
    assert_eq!(report["matching_symbols"], 1);
    assert_eq!(report["callers"].as_array().unwrap().len(), 0);
}

#[test]
fn an_unknown_symbol_reports_nothing_rather_than_failing() {
    let dir = fixture_dir();
    let report = impact_json(dir.path(), "no_such_symbol");
    assert_eq!(report["matching_symbols"], 0);
    assert_eq!(report["callers"].as_array().unwrap().len(), 0);
}

/// Two *different* functions that share a name in one file, both calling the target. Python
/// allows the redefinition outright; a TypeScript overload pair has the same shape. They differ
/// in arity, which is what gives them distinct `SymbolId`s -- `SymbolId` is derived from
/// `(path, name, arity)` and carries no line, so a same-arity pair would already be one symbol
/// before `callers` ever runs. This is the narrowest fixture that reaches the dedup.
const SAME_NAME_FIXTURE: &str = r#"
def helper(x):
    return x

def process(a):
    return helper(a)

def process(a, b):
    return helper(a) + helper(b)
"#;

fn same_name_dir() -> tempfile::TempDir {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("mod.py"), SAME_NAME_FIXTURE).unwrap();
    dir
}

#[test]
fn two_same_named_callers_in_one_file_are_both_reported() {
    // Deduping on `(path, name)` alone silently drops one of these: they agree on file and name
    // and differ only in the line that the sort above already orders on.
    let dir = same_name_dir();
    let report = impact_json(dir.path(), "helper");
    let found = report["callers"].as_array().expect("callers array");
    let lines: Vec<u64> = found.iter().map(|c| c["line"].as_u64().unwrap()).collect();
    assert_eq!(
        found.len(),
        2,
        "both `process` definitions call `helper`; got lines {lines:?}"
    );
    assert_eq!(
        lines.len(),
        lines.iter().collect::<std::collections::HashSet<_>>().len(),
        "the two rows must be distinct definitions, not one row twice"
    );
}
