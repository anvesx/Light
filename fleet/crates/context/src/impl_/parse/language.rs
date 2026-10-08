//! `language_for` (graph.rs:767-774, retyped to this crate's `Language` enum).

use super::super::types::Language;
use std::path::Path;

pub fn language_for(path: &Path) -> Option<Language> {
    match path.extension().and_then(|extension| extension.to_str()) {
        Some("rs") => Some(Language::Rust),
        Some("sh") | Some("bash") => Some(Language::Bash),
        Some("py") => Some(Language::Python),
        // `.js`/`.mjs`/`.cjs` parse cleanly under the TypeScript grammar, which is a superset.
        Some("ts") | Some("mts") | Some("cts") | Some("js") | Some("mjs") | Some("cjs") => {
            Some(Language::TypeScript)
        }
        Some("tsx") | Some("jsx") => Some(Language::Tsx),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn maps_known_extensions() {
        assert_eq!(language_for(Path::new("a.rs")), Some(Language::Rust));
        assert_eq!(language_for(Path::new("a.py")), Some(Language::Python));
        assert_eq!(language_for(Path::new("a.sh")), Some(Language::Bash));
        assert_eq!(language_for(Path::new("a.txt")), None);
    }

    #[test]
    fn maps_typescript_and_tsx() {
        for ext in ["ts", "mts", "cts", "js", "mjs", "cjs"] {
            let path = format!("a.{ext}");
            assert_eq!(language_for(Path::new(&path)), Some(Language::TypeScript));
        }
        for ext in ["tsx", "jsx"] {
            let path = format!("a.{ext}");
            assert_eq!(language_for(Path::new(&path)), Some(Language::Tsx));
        }
    }
}
