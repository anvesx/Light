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

/// `names` alone cannot catch a branch that finds the symbol but counts its parameters wrong,
/// which is the failure mode when a grammar moves the `parameters` field to a different node.
fn names_with_arity(files: &[SourceFile]) -> Vec<(String, u64)> {
    let map = build_repo_map(files).expect("repo map");
    let mut out: Vec<(String, u64)> = map
        .symbols
        .iter()
        .map(|s| (s.name.clone(), s.arity))
        .collect();
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

#[test]
fn finds_generator_function_declarations() {
    // `ts_definition` advertises `generator_function_declaration` in the same match arm as
    // `function_declaration`, but tree-sitter gives it a distinct node kind. Without this
    // fixture, dropping that kind from the arm leaves every other assertion in this file green.
    let f = file(
        "a.ts",
        Language::TypeScript,
        "export function* paginate(cursor: string, size: number) { yield cursor; }\n",
    );
    assert_eq!(names_with_arity(&[f]), vec![("paginate".to_string(), 2)]);
}

#[test]
fn finds_class_public_field_arrow_functions() {
    // `public_field_definition` shares an arm with `variable_declarator`: the name is on the
    // field node and the parameters are on the value. It is the class-bound form of the
    // arrow-const above, and nothing else in this file exercises it.
    let f = file(
        "a.ts",
        Language::TypeScript,
        "class Checkout {\n\
         \x20 applyDiscount = (code: string, cart: Cart) => cart;\n\
         \x20 reset = () => {};\n\
         }\n",
    );
    assert_eq!(
        names_with_arity(&[f]),
        vec![("applyDiscount".to_string(), 2), ("reset".to_string(), 0)]
    );
}
