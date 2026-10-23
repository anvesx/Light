# Extractor agent (`brain_extractor`)

**Role in the harness:** Second internal brain agent. It turns clean lines into items with source spans.

- Code (`control_plane/company_brain/extract_rules.py`) finds candidate lines from topic cues and kind cues.
- The model returns items. The fake brain uses the same rules.
- Check step: lines exist, the text is a quote of the clean lines, topic is in the lexicon, kind is allowed, no opinion about a person's work, no item from an injected line.
- Confidence 0.6 or more is stored `active`. Lower, or from an untranslated line, is stored `unconfirmed`. Nothing waits.
- Instructions inside a source are data. The read tool logs a warning step and the run makes no other call.
- Exam: `replay_exam.py` (recall and precision at 0.9 each, evidence on every item, injection ignored).
