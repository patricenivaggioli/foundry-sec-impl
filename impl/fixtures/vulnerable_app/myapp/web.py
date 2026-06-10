"""Web routes that wire the vulnerable functions to HTTP."""
from flask import Flask, request

from myapp import load_session, ping_host, run_calc, search_users

app = Flask(__name__)


@app.route("/search")
def search():
    return {"results": search_users(request.args.get("q", ""))}


@app.route("/ping")
def ping():
    return {"output": ping_host(request.args.get("host", "127.0.0.1")).decode(errors="ignore")}


@app.route("/session", methods=["POST"])
def session_load():
    return {"data": str(load_session(request.data))}


@app.route("/calc")
def calc():
    return {"value": run_calc(request.args.get("expr", "1+1"))}
