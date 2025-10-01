# /app.py
from flask import Flask, render_template
from src.sites.govdeals import fetch_listings

app = Flask(__name__)

@app.route("/")
def index():
    raw = fetch_listings(pages=2, page_delay=5.0)

    trucks = []
    for it in raw:
        price_str = "N/A" if it.get("bid_cents") is None else f"{it['bid_cents']/100:,.2f}"
        specialty = ", ".join(it.get("tags", [])) or "—"
        trucks.append({
            "title": it.get("title") or "Untitled",
            "price": price_str,          # ${{ truck.price }} in template
            "engine_match": "—",         # not tracked yet
            "specialty_match": specialty,
            "link": it.get("url"),

        })

    return render_template("index.html", trucks=trucks)

if __name__ == "__main__":
    app.run(debug=True)
