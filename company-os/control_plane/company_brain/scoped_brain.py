"""A read-only view of the brain limited to the areas one run may see. The library needs the `playbooks` area."""
from control_plane.company_memory import AreaDenied

from .brain_store import LIBRARY


class ScopedBrain:
    def __init__(self, store, area_ids, *, hide_deal_stage=False):
        self._store = store
        self.area_ids = frozenset(area_ids)
        self._hide = hide_deal_stage  # CSM rule (PLAN 5): no deal discussions, so deal-stage sources and their evidence go

    def _shown(self, source):
        return source is not None and not (self._hide and self._store.is_deal_stage(source))

    def _filtered(self, item):
        """The item with deal-stage evidence removed, or None when nothing else backs it."""
        if not self._hide or item is None or not item["evidence"]:
            return item
        keep = [e for e in item["evidence"] if self._shown(self._store.get_source(e["source_id"]))]
        return {**item, "evidence": keep} if keep else None

    def _check(self, area_id):
        if area_id not in self.area_ids:
            raise AreaDenied(f"area {area_id!r} is not allowed here")

    def _areas(self, area_ids):
        if area_ids is None:
            return sorted(self.area_ids)
        areas = [area_ids] if isinstance(area_ids, str) else list(area_ids)
        for area in areas:
            self._check(area)
        return areas

    def get_source(self, source_id):
        source = self._store.get_source(source_id)
        if source is not None:
            self._check(source["area_id"])
        return source if self._shown(source) else None

    def source_lines(self, source_id):
        if self.get_source(source_id) is None:
            return []
        return self._store.source_lines(source_id)

    def sources(self, area_ids=None, *, status=None, kind=None):
        return [s for s in self._store.sources(self._areas(area_ids), status=status, kind=kind) if self._shown(s)]

    def get_brain_item(self, item_id):
        item = self._store.get_brain_item(item_id)
        if item is not None:
            self._check(item["area_id"])
        return self._filtered(item)

    def brain_items(self, area_ids=None, **filters):
        items = self._store.brain_items(self._areas(area_ids), **filters)
        return [i for i in map(self._filtered, items) if i is not None]

    def projects(self, area_ids=None):
        return self._store.projects(self._areas(area_ids))

    def deals(self, area_ids=None, **filters):
        return self._store.deals(self._areas(area_ids), **filters)

    def revenue(self, area_ids=None):
        return self._store.revenue(self._areas(area_ids))

    def reviews(self, area_ids=None, **filters):
        return self._store.reviews(self._areas(area_ids), **filters)

    def unconfirmed_count(self, area_id, project_id=None, deal_id=None):
        self._check(area_id)
        if self._hide:
            return len(self.brain_items(area_id, state="unconfirmed", project_id=project_id, deal_id=deal_id))
        return self._store.unconfirmed_count(area_id, project_id=project_id, deal_id=deal_id)

    def playbooks(self, **filters):
        self._check(LIBRARY)
        return self._store.playbooks(**filters)

    def checklist(self, **filters):
        self._check(LIBRARY)
        return self._store.checklist(**filters)
