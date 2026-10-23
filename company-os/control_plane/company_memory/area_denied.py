"""The error raised when memory is read outside the areas a run may see."""


class AreaDenied(PermissionError):
    """A read asked for an area that is not in the allowed set."""
