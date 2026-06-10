"""A tiny vulnerable Flask app used by the demo evaluation.

Planted vulnerabilities (the demo expects the pipeline to surface these):
  * SQL injection — ``search_users``
  * OS command injection — ``ping_host``
  * Insecure deserialization — ``load_session``
  * Code injection (eval) — ``run_calc``
"""
import os
import pickle
import sqlite3
import subprocess


DB_PATH = "/tmp/myapp.db"


def search_users(query: str):
    """SQL injection: query is concatenated directly into SQL."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM users WHERE name = '" + query + "'")
    return cur.fetchall()


def ping_host(host: str):
    """OS command injection: host flows into a shell command."""
    return subprocess.check_output("ping -c1 " + host, shell=True)


def load_session(blob: bytes):
    """Insecure deserialization: pickle.loads on attacker-controlled bytes."""
    return pickle.loads(blob)


def run_calc(expr: str):
    """Code injection: eval over untrusted input."""
    return eval(expr)


def healthcheck():
    """Benign function used to verify false-positive rejection."""
    return {"status": "ok", "pid": os.getpid()}
