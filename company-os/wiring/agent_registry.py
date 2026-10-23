"""Names every agent and its package, so the builder, the exams and the console all find agents the same way."""
import importlib

AGENTS = {  # agent name -> package with pack.py (make_pack), fake_brain.py (brain), optional replay_exam.py
    "meeting_prep":    "agents.meeting_prep.project_brief",
    "deal_brief":      "agents.meeting_prep.deal_brief",
    "live_copilot":    "agents.meeting_prep.live_copilot",
    "finance_watch":   "agents.finance.watch",
    "spend_advisor":   "agents.finance.spend_advice",
    "travel_booking":  "agents.finance.travel_booking",
    "brain_cleaner":   "control_plane.company_brain.agents.cleaner",
    "brain_extractor": "control_plane.company_brain.agents.extractor",
    "brain_linker":    "control_plane.company_brain.agents.linker",
    "brain_playbook":  "control_plane.company_brain.agents.playbook",
}
FAMILIES = {"meeting_prep": ("meeting_prep", "deal_brief", "live_copilot"),
            "finance": ("finance_watch", "spend_advisor", "travel_booking"),
            "company_brain": ("brain_cleaner", "brain_extractor", "brain_linker", "brain_playbook")}
FAMILY_TITLES = {"meeting_prep": "Meeting prep agent", "finance": "Finance agent", "company_brain": "Company brain"}


def available_agents() -> tuple[tuple[str, ...], dict[str, str]]:
    """Return (names whose pack and fake brain import, {name: reason} for each one that does not)."""
    ok, missing = [], {}
    for name, package in AGENTS.items():
        try:
            importlib.import_module(f"{package}.pack")
            importlib.import_module(f"{package}.fake_brain")
            ok.append(name)
        except ImportError as e:
            missing[name] = str(e)
    return tuple(ok), missing
