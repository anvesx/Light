//! TypeScript/TSX definition shapes. Rust has exactly one (`function_item` with a `name` field),
//! which is why `definition` could read name and arity generically. TypeScript has several, and
//! the most common one in real code carries no `name` field at all: an arrow function's name
//! lives on the parent `variable_declarator`.
//!
//! Measured on the POSX estate (2026-09-22): the backend has 436 `function` declarations against
//! 580 arrow-consts, the storefront 403 against 531. Handling only `function_declaration` would
//! miss the majority of definitions in both repos -- worse than not parsing at all, because the
//! output would look plausible.

use super::super::error::ContextError;
use super::super::parse::extract::node_text;
use tree_sitter::Node;

/// `(name, arity)` for a TypeScript definition node, or `None` if this node is not one.
pub fn ts_definition(node: Node<'_>, source: &str) -> Result<Option<(String, u64)>, ContextError> {
    match node.kind() {
        // `function foo(a, b) {}`, `function* gen() {}`, and class/object methods.
        "function_declaration" | "generator_function_declaration" | "method_definition" => {
            named_with_params(node, source)
        }
        // `const foo = (a, b) => {}` / `= function (a) {}`, and the class-property form
        // `foo = (a) => {}`. The name is here; the parameters are on the value.
        "variable_declarator" | "public_field_definition" => bound_function(node, source),
        _ => Ok(None),
    }
}

/// A node that carries both its own `name` and its own `parameters`.
fn named_with_params(node: Node<'_>, source: &str) -> Result<Option<(String, u64)>, ContextError> {
    let Some(name_node) = node.child_by_field_name("name") else {
        return Ok(None);
    };
    let name = node_text(name_node, source)?.trim().to_string();
    if name.is_empty() {
        return Ok(None);
    }
    Ok(Some((name, arity_of(node))))
}

/// A binding whose value is a function: the name is on the binding, the parameters on the value.
/// Anything else bound to a `const` (an object, a string, a call result) is not a definition.
fn bound_function(node: Node<'_>, source: &str) -> Result<Option<(String, u64)>, ContextError> {
    let Some(value) = node.child_by_field_name("value") else {
        return Ok(None);
    };
    if !matches!(value.kind(), "arrow_function" | "function_expression") {
        return Ok(None);
    }
    let Some(name_node) = node.child_by_field_name("name") else {
        return Ok(None);
    };
    let name = node_text(name_node, source)?.trim().to_string();
    if name.is_empty() {
        return Ok(None);
    }
    Ok(Some((name, arity_of(value))))
}

/// `formal_parameters` gives a count directly. A single-parameter arrow written without
/// parentheses (`x => x + 1`) has a `parameter` field instead, which is exactly one.
fn arity_of(node: Node<'_>) -> u64 {
    if let Some(parameters) = node.child_by_field_name("parameters") {
        return parameters.named_child_count() as u64;
    }
    u64::from(node.child_by_field_name("parameter").is_some())
}
