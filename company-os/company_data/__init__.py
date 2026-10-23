"""Dummy company systems in one SQLite file. DB_PATH is the built file; connect() opens it."""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "company_data.db")


def connect(path=None):
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
