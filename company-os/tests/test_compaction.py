"""Tests for core.compaction: threshold, prefix, tool pairs, idempotence, kept facts."""
import unittest

from core.compaction import SUMMARY_OPEN, compact_if_needed, estimate_tokens


def fake_summary(messages):
    return "## Goal\n- finish the brief\n## Decisions\n- (see kept list)"


def build(n_pairs=10):
    msgs = [{"role": "user", "content": "Prepare the PR05 brief."}]
    for i in range(n_pairs):
        msgs.append({"role": "assistant", "content": f"step {i} " + "x" * 200,
                     "tool_calls": [{"id": f"c{i}", "name": "read", "args": {}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "name": "read", "content": "y" * 200})
    msgs[3]["content"] = "We decided to ship on 2026-11-05 for INR 4,50,000. Quote I77 backs it."
    return msgs


class CompactionTest(unittest.TestCase):
    def test_below_threshold_unchanged(self):
        msgs = build(2)
        out, note = compact_if_needed(msgs, window_tokens=100_000, model_call=fake_summary)
        self.assertIs(out, msgs)
        self.assertIsNone(note)

    def test_above_threshold_folds_middle_and_keeps_ends(self):
        msgs = build()
        out, note = compact_if_needed(msgs, window_tokens=estimate_tokens(msgs), model_call=fake_summary)
        self.assertEqual(out[0], msgs[0])
        self.assertIn(SUMMARY_OPEN, out[1]["content"])
        self.assertEqual(out[-6:], msgs[-6:])
        self.assertGreater(note.folded_messages, 0)
        self.assertLess(note.after_tokens, note.before_tokens)
        self.assertEqual(len(out), 2 + note.kept_recent)

    def test_tool_pairs_never_split(self):
        msgs = build()
        for keep in range(1, 10):
            out, _ = compact_if_needed(msgs, window_tokens=100, model_call=fake_summary, keep_recent=keep)
            calls = {c["id"] for m in out for c in m.get("tool_calls", [])}
            for m in out:
                if m["role"] == "tool":
                    self.assertIn(m["tool_call_id"], calls)

    def test_idempotent_on_second_call(self):
        msgs = build()
        window = estimate_tokens(msgs)
        once, _ = compact_if_needed(msgs, window_tokens=window, model_call=fake_summary)
        twice, note = compact_if_needed(once, window_tokens=window, model_call=fake_summary)
        self.assertEqual(once, twice)
        self.assertIsNone(note)

    def test_summary_keeps_planted_decision_and_number(self):
        msgs = build()
        out, _ = compact_if_needed(msgs, window_tokens=estimate_tokens(msgs), model_call=fake_summary)
        summary = out[1]["content"]
        self.assertIn("We decided to ship on 2026-11-05", summary)
        self.assertIn("4,50,000", summary)
        self.assertIn("I77", summary)

    def test_deterministic(self):
        msgs = build()
        a = compact_if_needed(msgs, window_tokens=1000, model_call=fake_summary)
        b = compact_if_needed(msgs, window_tokens=1000, model_call=fake_summary)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
