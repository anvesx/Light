"""Open a SQLite file for the people surface, making its folder if needed."""
import sqlite3
from pathlib import Path


def open_db(path):
    path = str(path)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn
