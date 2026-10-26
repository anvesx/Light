# Guardrails

What this agent must never do. The code guards still enforce the rules. This file tells the model.

- Never link an item outside this source's client area.
- Never add a link that was not planned, unless the pair is unsure and you are sure of the relation.
- Never use a link type outside supersedes, refines, same_as and the other allowed types.
- Never set the scope of an item outside this area.
