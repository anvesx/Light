"""Dispatch: hands each task to a starter. The runtime behind the starter runs the way-in check."""


def dispatch(tasks, starter):
    """Call starter(task) for each task, in order. Returns the results in the same order."""
    return [starter(task) for task in tasks]
