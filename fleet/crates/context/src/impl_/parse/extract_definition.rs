//! `definition` -- per-language "is this node a function definition" + arity.
//! Ported verbatim from `graph.rs:863-890`.

use super::super::error::ContextError;
use super::super::parse::extract::node_text;
use super::super::types::Language;
use super::extract_definition_ts::ts_definition;
use tree_sitter::Node;

pub fn definition(
    node: Node<'_>,
    source: &str,
    language: Language,
) -> Result<Option<(String, u64)>, ContextError> {
    let kind = node.kind();
    // TypeScript has several definition shapes and its dominant one carries no `name` field,
    // so it cannot share the generic name/arity read below. See `extract_definition_ts`.
    if matches!(language, Language::TypeScript | Language::Tsx) {
        return ts_definition(node, source);
    }
    let is_definition = match language {
        Language::Rust => kind == "function_item",
        Language::Python => kind == "function_definition",
        Language::Bash => kind == "function_definition",
        Language::TypeScript | Language::Tsx => unreachable!("handled above"),
    };
    if !is_definition {
        return Ok(None);
    }
    let Some(name_node) = node.child_by_field_name("name") else {
        return Ok(None);
    };
    let name = node_text(name_node, source)?.trim().to_string();
    if name.is_empty() {
        return Ok(None);
    }
    let arity = match node.child_by_field_name("parameters") {
        Some(parameters) => parameters.named_child_count() as u64,
        None => 0,
    };
    Ok(Some((name, arity)))
}
