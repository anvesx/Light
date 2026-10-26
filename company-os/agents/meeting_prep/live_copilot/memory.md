# Memory map

Which store areas this agent reads and writes, and why. Role scopes decide which areas a run may read.

## Reads

- The call lines and script (`live_call_script`).
- The brain view for the call's area: history, open items, decisions and the kickoff checklist (`live_call_brain`). This agent sets `reads_library`.

## Writes

- Nothing from the pack. The live session stores the finished call as a `live_call` source in the brain.

## Why

- Suggestions need the history of the same client and the checklist of past lessons.
- Code finds the gaps and contradictions. The model only writes the end summary.
