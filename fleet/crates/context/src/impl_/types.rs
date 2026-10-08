//! Shared data types: already-read source, symbols, repo map, scored/placed chunks.

use std::collections::BTreeMap;

/// One already-read source file. The caller resolves the path and reads the bytes.
pub struct SourceFile {
    /// Repo-relative, forward-slash-normalized path.
    pub path: String,
    pub language: Language,
    pub source: String,
}

/// The languages this crate's tree-sitter grammars cover today. `TypeScript` and `Tsx` are
/// separate because tree-sitter ships two grammars: `.tsx` cannot be parsed by the plain
/// TypeScript grammar (JSX conflicts with type assertions), and 248 of the POSX storefront's
/// 458 source files are `.tsx`.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub enum Language {
    Rust,
    Python,
    Bash,
    TypeScript,
    Tsx,
}

/// A stable identifier for one symbol, derived deterministically from `(path, name, arity)`.
#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd, Hash)]
pub struct SymbolId(pub(crate) String);

/// One extracted symbol and the fact PageRank attaches to it.
#[derive(Clone, Debug)]
pub struct SymbolRef {
    pub id: SymbolId,
    pub path: String,
    pub name: String,
    pub arity: u64,
    pub line: u64,
}

/// The full parsed-and-scored repo map.
#[derive(Clone, Debug)]
pub struct RepoMap {
    pub symbols: Vec<SymbolRef>,
    pub edges: Vec<(SymbolId, SymbolId)>,
    pub importance: BTreeMap<SymbolId, f64>,
}

/// One candidate chunk of code text, already scored and ready to place into the budget.
pub struct ScoredChunk {
    pub id: SymbolId,
    pub path: String,
    pub text: String,
    pub score: f64,
}

/// A chunk actually placed into the returned context, and whether it was summarized to fit.
pub struct PlacedChunk {
    pub id: SymbolId,
    pub path: String,
    pub text: String,
    pub compacted: bool,
}

pub struct ContextSlice {
    pub chunks: Vec<PlacedChunk>,
    pub tokens_used: types::Tokens,
    pub tokens_budget: types::Tokens,
    pub dropped: Vec<SymbolId>,
}
