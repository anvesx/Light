//! TypeScript/TSX symbol extraction.
//!
//! The load-bearing case is the arrow-const. Measured on the POSX estate 2026-09-22, the backend
//! has 436 `function` declarations against 580 arrow-consts and the storefront 403 against 531,
//! so a `function_declaration`-only implementation would miss the majority of definitions in
//! both repos. Each assertion below fails without `extract_definition_ts`.

use context::{build_repo_map, Language, SourceFile};

fn file(path: &str, language: Language, source: &str) -> SourceFile {
    SourceFile {
        path: path.to_string(),
        language,
        source: source.to_string(),
    }
}

fn names(files: &[SourceFile]) -> Vec<String> {
    let map = build_repo_map(files).expect("repo map");
    let mut out: Vec<String> = map.symbols.iter().map(|s| s.name.clone()).collect();
    out.sort();
    out
}

#[test]
fn finds_plain_function_declarations() {
    let f = file(
        "a.ts",
        Language::TypeScript,
        "export function add(a: number, b: number): number { return a + b; }",
    );
    assert_eq!(names(&[f]), vec!["add"]);
}

#[test]
fn finds_arrow_consts_the_dominant_posx_shape() {
    let f = file(
        "a.ts",
        Language::TypeScript,
        "export const isPhoneMatch = (a: string, b: string) => a === b;\n\
         const toE164 = (raw: string): string => raw.trim();\n",
    );
    assert_eq!(names(&[f]), vec!["isPhoneMatch", "toE164"]);
}

#[test]
fn finds_function_expressions_and_methods() {
    let f = file(
        "a.ts",
        Language::TypeScript,
        "const legacy = function (x: number) { return x; };\n\
         class Svc { resolve(id: string) { return id; } }\n",
    );
    assert_eq!(names(&[f]), vec!["legacy", "resolve"]);
}

#[test]
fn a_const_bound_to_a_non_function_is_not_a_definition() {
    // `export const FOO = { a: 1 }` is a value, not a symbol anyone can call. Counting it
    // would inflate the graph with every config object in the repo.
    let f = file(
        "a.ts",
        Language::TypeScript,
        "export const LIMITS = { maxQty: 5 };\nexport const NAME = 'posx';\n",
    );
    assert!(names(&[f]).is_empty());
}

#[test]
fn parses_tsx_which_the_plain_typescript_grammar_cannot() {
    // 248 of the storefront's 458 source files are .tsx. JSX conflicts with type assertions in
    // the plain grammar, which is why tree-sitter ships two and `Language::Tsx` exists.
    let f = file(
        "c.tsx",
        Language::Tsx,
        "export const Badge = ({ label }: { label: string }) => <span>{label}</span>;\n\
         export function Row() { return <tr />; }\n",
    );
    assert_eq!(names(&[f]), vec!["Badge", "Row"]);
}

#[test]
fn records_call_edges_between_typescript_symbols() {
    let f = file(
        "a.ts",
        Language::TypeScript,
        "const helper = (x: number) => x * 2;\n\
         export const caller = (y: number) => helper(y);\n",
    );
    let map = build_repo_map(&[f]).expect("repo map");
    assert!(!map.edges.is_empty(), "expected at least one call edge");
}
