# Central KB connectivity — `retail-os-central-kb` → `knowledge` → `context`

Date: 2026-09-22 · Author: Rachit Shah · Status: proposal, nothing built

**The question this answers:** we have a curated estate knowledge base and a harness that never
reads it. How do they connect, concretely, without violating the LLD's authority rules?

Related node blueprints: [`knowledge`](../knowledge/BLUEPRINT.md), [`context`](../context/BLUEPRINT.md),
[`probe_learn`](../probe_learn/BLUEPRINT.md). This document is the *integration* plan across them;
it does not restate their contracts.

---

## 1. What exists on each side, measured

### The KB — `devx-commerce/retail-os-central-kb`, 129 files (2026-09-22)

| Path | Files | Read as |
|---|---|---|
| `corpus/features` | 31 | context |
| `corpus/domain` | 17 | context |
| `corpus/integrations/{shopify,unicommerce,storepro,payments}` | 23 | context |
| `corpus/defects` | 13 | context |
| `corpus/architecture` | 12 | context |
| `playbooks/` | 7 | context |
| `standards/` | **1** (`_PROMOTION.md` only) | **authority** |

The corpus/standards split is deliberate and already matches LLD §11's *"imported memory remains
data and cannot increase capability grants"*. `corpus/` is bulk-loadable and ungated. `standards/`
is near-empty **by design** — it grows from real runs, never from a bulk import. Nothing in this
plan changes that.

### The harness

- `scan` is a stub. Its own runtime label: `merges zero questions, no ambiguity agents run`.
- `plan` is a stub: `fixed draft, not per-task`.
- `knowledge` build status is `partial` — `fleet-memory` retrieval and `fleet-context` seams exist;
  there is no `KnowledgeStore` implementation that reads an external repo.
- A lane today receives **only the task string**. Observed directly: a builder lane on a real POSX
  task replied *"you haven't provided the current contents, I'll assume a basic structure"* and
  invented a file.

**So the gap is not retrieval quality. It is that 96 curated files are sitting unread while lanes
start from zero.**

---

## 2. The connection, edge by edge

```
retail-os-central-kb (git)
        │  ① sync
        ▼
  local snapshot + index
        │  ② KnowledgeStore impl
        ▼
     knowledge  ──③ SourceManifest──▶  context  ──▶  builder lane
        ▲
        └──④ offline -> knowledge (promotion; see learning-promotion-loop.md)
```

### ① Sync — how the KB gets to the machine

**Proposal: shallow git clone into `$FLEET_STATE/kb/<remote-digest>/`, refreshed on demand.**

Rejected alternatives, with reasons:

| Option | Why not |
|---|---|
| GitHub API per query | Network on the hot path; a lane would fail on a rate limit or an offline laptop. Fleet is explicitly local-first. |
| Vendor the KB into the fleet repo | Couples release cadence of two repos; the KB changes far more often. |

(MCP is deliberately *not* in this table — it is a **serving** mechanism, not a **fetching** one.
See §2.5.)


A git clone gives the **revision** and **digest** that `KnowledgeItem` already requires for free:
commit SHA is the revision, blob SHA is the per-item `source_digest`. No new provenance
machinery.

**Open decision:** refresh policy. `--kb-refresh` explicit, TTL, or per-run. Default should be
*explicit*, so a run is reproducible against a pinned commit — the ledger records which.

### ② `KnowledgeStore` over markdown

`knowledge`'s public contract already exists:

```rust
pub trait KnowledgeStore {
    fn list(&self, query: &str, scope: &Scope, limit: u32) -> Result<Vec<KnowledgeItem>, KnowledgeError>;
    fn put_candidate(&self, item: KnowledgeItem) -> Result<(), KnowledgeError>;
}
```

A `CentralKbStore` implements it over the cloned tree. Per file:

| `KnowledgeItem` field | Source |
|---|---|
| `id` | path-derived, e.g. `DEF-0001` |
| `kind` | `corpus/**` → `Lesson`; `standards/**` → `Standard` |
| `text_ref` | repo-relative path |
| `source_digest` | git blob SHA |
| `revision` | commit SHA of the snapshot |
| `scope` | front-matter (see the open question below) |
| `evidence_count` | corpus: 0. **Standards must carry a real count** — that is the promotion gate's job, not this reader's. |
| `expires_at` | front-matter, optional |

**`kind` is decided by path, not by content.** A file cannot promote itself into authority by
declaring `kind: standard` in its own front matter. Path is the boundary; promotion moves files.

**Open question — scope.** `Scope` needs to answer *"does DOM-0001 apply to this repo?"*. The KB is
estate-wide but several entries are client-specific (`DOM-0004` is Unicommerce facility routing;
Mokobara and EUME differ). Front-matter `repos: [...]` / `clients: [...]` with empty meaning
*applies everywhere* is the obvious shape and matches what `posx-kb` already does. **Needs a KB-side
schema change**, so it is a coordination item, not a fleet-only one.

### ③ `knowledge -> context` — retrieval, and the denominator

`sources()` returns a `SourceManifest` that already must publish `checked,total`, freshness and
omitted refs. That is the rule this integration must not weaken:

> **A retrieval that examined zero sources is a failure, not an empty context.**

If the KB snapshot is missing, stale beyond policy, or the scope filter matches nothing, the
manifest reports `checked == 0` and the run refuses. It does **not** silently proceed with an
uninformed lane — which is exactly today's behaviour and exactly what makes today's lanes invent
files.

Retrieval itself should start **lexical, not semantic**. `tantivy` is already a dependency of
`crates/context`. BM25 over 96 documents will not be the weak link, and it has no model, no
embedding store, and no drift. Add vectors only when a measured recall failure justifies it.

### ②·5 In-process and MCP are not alternatives

**This is a sequencing question, not an architecture one, and both should exist.**

`KnowledgeStore` is the seam:

```rust
pub trait KnowledgeStore {
    fn list(&self, query: &str, scope: &Scope, limit: u32) -> Result<Vec<KnowledgeItem>, KnowledgeError>;
    fn put_candidate(&self, item: KnowledgeItem) -> Result<(), KnowledgeError>;
}
```

An MCP server over the KB is a **thin wrapper around the same `CentralKbStore`**. Building
in-process first throws nothing away; it just means retrieval is proven before a protocol is
added on top of it.

**The argument for MCP is stronger than a fleet-only view suggests**, and it is the estate's
existing design: the Sept 2026 plan says the KB and the analyser are *"both exposed to Fleet via
MCP"*. An MCP server is readable by **Claude Code, kiro, Cursor and Codex as well as fleet** — so
the same governed corpus reaches every agent on every developer's machine, not just lanes. Given
that POSX work happens across several agents today, that reach is most of the value.

**Correcting an objection that does not hold:** MCP does not breach `TARGET.md`'s
*"fleet is a LOCAL CLI… It is NOT a server"* rule. An MCP server mounted over **stdio is a
subprocess, not a daemon** — the same shape Claude Code already uses for `context7`. The
no-server-shaped-machinery constraint is about horizontal scaling, HA and uptime SLOs, none of
which a stdio MCP server implies.

So the only real claim here is ordering: **in-process first, so that a wrong retrieval design is
one function to debug rather than a server, a protocol, a client and a function.** Fleet's own
`fleet mcp` subcommand is a stub today (`fleet-worker`'s sandbox manifest fn is not public), so
the MCP path is not a smaller step in any case.

### ④ Promotion

Out of scope here — see [`learning-promotion-loop.md`](./learning-promotion-loop.md).

---

## 3. What this unlocks, grounded in POSX

The estate's measured problems that a context-aware lane addresses directly:

- **`DOM-0002` — POS never sells a SET as a product.** A lane touching cart or order code without
  this writes a correct-looking bug. The rule exists in the KB today and no lane can see it.
- **`DOM-0001` — targets compare against net ex-GST.** Same shape.
- **`DEF-0001` — no `compensate` on money steps.** 81% of POSX workflow steps lack compensation. A
  lane adding a money step should be told before it writes, not after review.
- **`ARC-0003` — thin routes, workflows, steps.** The Medusa idiom a generic model will not guess.

This is the item that is genuinely **not** substitutable by Claude Code, Cursor or Codex: they can
read a `CLAUDE.md` in one repo, but none of them carries a governed, versioned, estate-wide corpus
with per-item provenance and a retrieval denominator.

---

## 4. Sequencing, and the dependency that is easy to miss

**This plan is second, not first.**

`FD-8` (gate result parsers are libtest-shaped) blocks it. Today a POSX repo runs
`npm run test:unit`, passes 671 tests, and fleet reports `Unparseable`. Until a Node repo can pass
a gate, a perfectly-contextualised lane still ends in refusal — so the value of this work is not
observable.

Order: **FD-8 → this → promotion loop.**

## 5. Verification

Nothing here is built. When it is, these are the claims that need real output:

1. A lane on a Mokobara cart task receives `DOM-0002` in its context, shown in the ledger's
   source manifest with a real `checked/total`.
2. Deleting the KB snapshot makes the run **refuse**, not proceed with an empty context.
3. A `standards/` entry with no evidence count is **rejected at read time**, not silently loaded
   as authority.
4. Two runs against the same pinned KB commit produce identical source manifests.
5. Scope filtering: a Mokobara-scoped entry does not reach an EUME lane.

## 6. Open decisions for the lead

1. KB refresh policy — explicit, TTL, or per-run. Recommendation: explicit and pinned.
2. Front-matter scope schema. **Needs a KB-side change**; blocks ②.
3. **Ordering** of in-process vs MCP — see §2.5. The recommendation is sequencing only; both ship.
4. Whether `playbooks/` is `corpus` (context) or a third kind. It reads like procedure, not fact.
