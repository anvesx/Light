# Cleaner agent (`brain_cleaner`)

**Role in the harness:** First internal brain agent. It makes clean English lines for one stored source.

- Code removes filler and fixes speaker names from the participants.
- The model translates non-English lines. The fake brain looks them up in `translations.json`.
- A line it cannot translate keeps its raw text, gets a `translation` row on the check list and still goes to the Extractor. Nothing waits for a person.
- Raw text never changes (the store refuses it). No line is dropped.
- Tools: `brain_read_source`, `brain_save_clean_lines`, `brain_queue_review` (`control_plane/company_brain/write_tools.py`). Each refuses a source outside the run's area.
- Exam: `replay_exam.py` (every non-English line has clean text or a review entry, 0 dropped, raw unchanged).
