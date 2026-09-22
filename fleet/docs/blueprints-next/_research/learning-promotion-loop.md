# Learning promotion loop — a failure becomes an enforced rule

Date: 2026-09-22 · Author: Rachit Shah · Status: proposal, nothing built

**The question this answers:** fleet already writes lessons. How does a lesson stop being prose
someone might read and become a check that blocks a merge — without one model completion being
enough to create a rule?

Related node blueprints: [`candidate`](../candidate/BLUEPRINT.md), [`offline`](../offline/BLUEPRINT.md),
[`knowledge`](../knowledge/BLUEPRINT.md), [`verify`](../verify/BLUEPRINT.md).
Depends on [`central-kb-connectivity.md`](./central-kb-connectivity.md) — a lesson needs somewhere
governed to live.

---

## 1. Why this is the item that matters

Everything else fleet does, another tool can approximately do. This one nothing else does.

`CLAUDE.md` is prose a model may or may not honour, and the estate has already measured what that
is worth: the same duplicate-order bug was root-caused **three separate times over two months**,
~30 hours, because the lesson from the first was written down and not enforced. A rule that blocks
a merge cannot be skipped by a model having a bad day.

The measurable claim is **repeat-mistake rate** — findings matching a rule already recorded. It is
the one KPI in the SOW that no bought tool can produce, and it is how we would know this loop
works rather than merely exists.

---

## 2. The chain, which is already designed

The edges exist in `EDGE-TYPES.md`; the nodes exist as blueprints. Neither is built.

```
verify ──GateEvidence──▶ candidate ──CandidateLesson + fixture──▶ offline
                                                                     │
                                                          OfflineScore (promote/retain/reject)
                                                                     ▼
                                                                 knowledge
                                                                     │
                                                       standards/ (human grant)
                                                                     ▼
                                                             a gate that blocks
```

| Node | Owns | Build status today |
|---|---|---|
| `candidate` | canonical failure signature, scope predicate, regression-fixture reference | `partial` — `fleet-memory/src/promote.rs`, `gate_check.rs`, `fleet-plan/src/teach.rs` are seams |
| `offline` | paired baseline-vs-variant trial before promotion | **`greenfield`** — nothing exists |
| `knowledge` | activation, revision pinning, expiry | `partial` |

**`offline` is the gap.** It is the node that stops a single failure becoming a rule, and it is the
one with no code at all.

---

## 3. The four gates a lesson must pass

Taken from the node blueprints, stated as one sequence so the whole path is visible:

**Gate 1 — the failure is real.** `verify` produced `GateEvidence` with a real `{checked,total}`.
A refusal from a stub gate, an environment fault, or a zero denominator produces no candidate. The
`checked==0 is a failure` rule does double duty here: it also stops noise entering the loop.

**Gate 2 — the failure has a signature.** `candidate` derives a canonical failure signature plus a
scope predicate and **a regression fixture**. No fixture, no candidate. This is the step that turns
"this went wrong once" into "here is an input that reproduces it".

**Gate 3 — the lesson helps.** `offline` runs the candidate against baseline and held-out tasks and
emits `OfflineScore` — promote, retain, or reject. This is what prevents a lesson that fixes one
case and breaks four others. *This is the greenfield node.*

**Gate 4 — a human grants authority.** `standards/_PROMOTION.md` already defines the
`StandardMaintainerGrant`. Promotion into `standards/` is a reviewed PR against the KB repo, not an
automated write. Per LLD §11, imported memory never increases capability grants on its own.

Only after all four does an entry sit in `standards/` with a pinned revision and become something
`verify` can enforce.

---

## 4. What the KB side already provides

`retail-os-central-kb` is not a blank target:

- `standards/_PROMOTION.md` — the grant definition exists
- `standards/` holds nothing else, which is **correct**. A bulk import into `standards/` would
  contradict the LLD; a bulk import into `corpus/` is exactly what LLD §11 contemplates.
- `corpus/defects/` has 13 real entries (`DEF-0001` no-compensate on money steps, `DEF-0010`
  cash-and-carry duplicate sale order, …). These are **candidates written by hand** — the same
  shape the loop should produce mechanically.

So the loop is not being invented from nothing. It is being automated where humans currently do it
by hand, and the hand-written entries are the fixture set to test it against.

---

## 5. The honest shape of the first increment

Do not build all four gates. Build the narrowest slice that produces a real promotion:

1. **`candidate` from a real gate failure.** `verify` already emits evidence with `{checked,total}`.
   Derive a signature and write a candidate to `corpus/` as a PR. No activation, no authority.
2. **Human review is gate 3 initially.** `offline` is greenfield; a paired evaluator is a large
   piece of work. Until it exists, a person plays that role — which is honest, and matches how the
   13 existing `DEF-*` entries came to be.
3. **One rule promoted to `standards/` end to end**, with the grant, and a `verify` gate that
   actually blocks on it.

One rule that genuinely blocks a merge is worth more than a pipeline that produces candidates
nobody activates. `DEF-0001` (money steps without `compensate`) is the obvious first: it is
mechanically detectable, it recurs, and 81% of POSX workflow steps currently violate it.

**Warn-only first.** A new rule that blocks on day one, before its false-positive rate is known, is
how gates get switched off. Two weeks warn-only, then block — the SOW says the same, for the same
reason.

---

## 6. What this does not do

- **It does not make a lesson travel to five repos automatically.** Cross-repo propagation is a
  separate capability (`--repo a b c`).
- **It does not replace review.** A promoted standard blocks a known failure shape; it says nothing
  about whether a change is a good idea.
- **It cannot promote from a single completion.** By design. Gate 3 exists precisely to stop that,
  and until `offline` is built a human occupies that slot rather than the slot being skipped.
- **It does not lower the bar for `standards/`.** If the loop cannot produce an entry that passes
  gates 1–4, the correct outcome is no entry.

---

## 7. Verification

When built, these are the claims needing real output:

1. A real gate failure produces a candidate with a signature and a regression fixture that
   reproduces it.
2. A candidate with **no** fixture is rejected, not stored.
3. A promoted standard makes `verify` fail a change that reintroduces the original failure — and
   the fixture proves it, by failing before the fix and passing after.
4. Promotion without a `StandardMaintainerGrant` is refused.
5. Repeat-mistake rate is computable: a finding matching an existing `rule_id` is counted as a
   repeat.

Claim 3 is the whole thing. If it cannot be demonstrated once, end to end, the loop is decoration.

---

## 8. Open decisions for the lead

1. **Who writes the candidate PR** — fleet with a bot token, or fleet emits a file and a human
   opens it. Recommendation: emit a file first. A bot with write access to the KB is a permission
   grant that should be deliberate.
2. **`offline` scope.** A real paired evaluator is large. Is a human in that slot acceptable for
   the first promotion, explicitly recorded as such?
3. **Where the enforcement lives** — a fleet gate, a semgrep rule generated from the standard, or
   both. `corpus` entries already carry a `detector` field concept in the KB design.
4. **Rule expiry.** `KnowledgeItem` has `expires_at`. A standard nobody has hit in a year is either
   load-bearing or dead, and we will not know which without a usage count.
