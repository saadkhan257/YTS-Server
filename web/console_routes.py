import os
import json
import queue
import threading
from flask import Blueprint, render_template, request, session, redirect, url_for
from flask_sock import Sock
from web.log_streamer import log_generator

# 🔐 Hardcoded login (can be moved to env/config)
USERNAME = "admin"
PASSWORD = "yt12345"

console_bp = Blueprint("console", __name__, template_folder="templates", static_folder="static")
sock = Sock()

# ✅ Simple login page
@console_bp.route("/console/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == USERNAME and password == PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("console.dashboard"))
        return render_template("console.html", error="Invalid credentials")
    return render_template("console.html")

# ✅ Console dashboard
@console_bp.route("/console")
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("console.login"))
    return render_template("console.html")

# ✅ Logout
@console_bp.route("/console/logout")
def logout():
    session.clear()
    return redirect(url_for("console.login"))

# ✅ WebSocket for live logs
log_queue = queue.Queue()

@sock.route("/ws/logs")
def logs_socket(ws):
    def stream_logs():
        for line in log_generator(log_queue):
            try:
                ws.send(line)
            except Exception:
                break

    t = threading.Thread(target=stream_logs)
    t.daemon = True
    t.start()

    while True:
        try:
            msg = ws.receive()
            if msg == "ping":
                ws.send("pong")
        except Exception:
            break
