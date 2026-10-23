"""Shared helpers for the S1 brain tests: a small Company OS with the two agents, and the manifest sources."""
import json

from control_plane.company_brain import inbox
from control_plane.company_brain.pipeline import read_manifest_file
from control_plane.triggers.inbox_trigger import MANIFEST_PATH
from wiring.build_company_os import build_company_os

AGENTS = ("brain_cleaner", "brain_extractor")


def make_cos():
    return build_company_os(agents=AGENTS)


def manifest_row(ref):
    return next(r for r in json.loads(MANIFEST_PATH.read_text())["sources"] if r["origin_ref"] == ref)


def receive_ref(cos, ref):
    row = manifest_row(ref)
    return inbox.receive(cos.brain, cos.data_conn, kind=row["kind"], content=read_manifest_file(row), origin_ref=ref,
                         hint_area=row["hint_area"], received_at=row["arrives_at"], force=True)
