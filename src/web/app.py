# file path: /src/web/app.py
import os, json
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, render_template, request
from src.core.collect import collect_all
from src.core.diagnostics import list_errors  # <-- make sure this import exists near the top
import pathlib, sys
project_root = pathlib.Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


app = Flask(__name__, template_folder="templates", static_folder="static")

SEVEN_DAYS = 7 * 24 * 3600

def _fresh_rows():
    # Pull on-demand each page load (simple for now)
    return collect_all()

def _slice(rows, mode: str):
    out = []
    now = datetime.now(timezone.utc).timestamp()
    for r in rows:
        secs = r.get("secs")
        # treat None as not schedulable; UI won’t show those unless requested
        if not isinstance(secs, int):
            continue
        if mode == "upcoming":
            if 0 < secs <= SEVEN_DAYS:
                out.append(r)
        elif mode == "closed":
            # recent closings within the last 7 days (secs <= 0 and >= -7d)
            if -SEVEN_DAYS <= secs <= 0:
                out.append(r)
    # sort
    if mode == "upcoming":
        out.sort(key=lambda x: x.get("secs", 99999999))
    else:
        out.sort(key=lambda x: x.get("secs", 0), reverse=True)  # least negative first
    return out

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/listings")
def api_listings():
    mode = request.args.get("mode", "upcoming")
    rows = _fresh_rows()
    data = _slice(rows, "upcoming" if mode == "upcoming" else "closed")
    return jsonify({"count": len(data), "rows": data})

@app.route("/api/errors")
def api_errors():
    """Return any scraper errors captured during collect_all()."""
    return jsonify({"errors": list_errors()})

@app.route("/ui/govdeals")
def ui_govdeals():
    # Simple server-rendered shell; frontend JS will fetch /api/listings?mode=upcoming
    return render_template("govdeals.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
