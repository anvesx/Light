"""The role matrix: which console role sees which pages, data and memory areas (PLAN_v2 section 5)."""
from control_plane.connectors.people_directory import HOLD_AREA, INTERNAL_AREA

CONSOLE_ROLES = ("admin", "csm", "growth")
DB_ROLE_TO_CONSOLE = {"ceo": "admin", "rnd_lead": "admin", "finance_lead": "admin", "csm": "csm", "growth": "growth"}
ADMIN_DB_ROLES = frozenset({"ceo", "rnd_lead", "finance_lead"})
DEMO_PEOPLE = (("P01", "admin"), ("P05", "csm"), ("P03", "growth"))
LIBRARY_AREA = "playbooks"
PAGES = {"admin": ("home", "brain", "review", "meeting_prep", "deals", "live", "finance", "travel", "approvals", "runs"),
         "csm": ("home", "brain", "review", "meeting_prep", "live", "travel", "approvals"),
         "growth": ("home", "brain", "review", "deals", "live", "travel")}
DATA = {"project_items": {"admin", "csm"}, "deal_items": {"admin", "growth"}, "library": {"admin", "growth"},
        "revenue": {"admin"}, "deal_value": {"admin", "growth"}, "finance": {"admin"}, "travel_all": {"admin"},
        "travel_own": {"admin", "csm", "growth"}, "runs_all": {"admin"}, "hold_area": {"admin"}}


def console_role(directory, person_id):
    """The console role for a person, or None (system, clients and other jobs have no console)."""
    return DB_ROLE_TO_CONSOLE.get(directory.role(person_id))


def may_open_page(role, page_id) -> bool:
    return page_id in PAGES.get(role, ())


def may_see(role, data_kind) -> bool:
    return role in DATA.get(data_kind, ())


def readable_areas(directory, person_id) -> set:
    """Memory areas the person may read. Other jobs: use directory.client_access()."""
    role = console_role(directory, person_id)
    if role is None:
        return directory.client_access(person_id)
    areas = set(directory.client_access(person_id))
    if role == "admin":
        areas = areas | getattr(directory, "all_client_areas", set)() | {INTERNAL_AREA}
    if may_see(role, "hold_area"):
        areas.add(HOLD_AREA)
    if may_see(role, "library"):
        areas.add(LIBRARY_AREA)
    return areas
