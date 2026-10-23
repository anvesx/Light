"""A read-only view of company memory limited to the areas one run may see."""
from .area_denied import AreaDenied


class ScopedMemory:
    def __init__(self, store, area_ids):
        self._store = store
        self.area_ids = frozenset(area_ids)

    def _check(self, area_id):
        if area_id not in self.area_ids:
            raise AreaDenied(f"area {area_id!r} is not allowed here")

    def items(self, area_id=None, kinds=None, status=None, topic=None, before=None):
        """Items of one allowed area, or of all allowed areas when area_id is None."""
        if area_id is None:
            areas = sorted(self.area_ids)
        else:
            self._check(area_id)
            areas = [area_id]
        return self._store.items(areas, kinds=kinds, status=status, topic=topic, before=before)

    def get_item(self, item_id):
        item = self._store.get_item(item_id)
        if item is not None:
            self._check(item["area_id"])
        return item

    def links_of(self, item_id):
        """Links of an allowed item. Links to items in other areas are left out."""
        self.get_item(item_id)
        out = []
        for link in self._store.links_of(item_id):
            other = link["to_id"] if link["from_id"] == item_id else link["from_id"]
            other_item = self._store.get_item(other)
            if other_item is None or other_item["area_id"] in self.area_ids:
                out.append(link)
        return out
