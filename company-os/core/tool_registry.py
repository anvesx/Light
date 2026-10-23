"""Holds the tool specs. The list sent to the model is sorted by name so the cached prefix stays stable."""


class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def add(self, spec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str):
        return self._tools.get(name)

    def sorted_specs(self) -> list:
        return [self._tools[n] for n in sorted(self._tools)]
