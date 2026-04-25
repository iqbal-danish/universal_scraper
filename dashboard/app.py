from flask import Flask, render_template, request, redirect, send_file, jsonify
import sqlite3, json, os
from .jobs import init_db, enqueue_job
from .queue_worker import job_queue

app = Flask(__name__)
init_db()

PREVIEW_FIELDS = [
    "id",
    "req_id",
    "title",
    "company",
    "city",
    "state",
    "country",
    "raw_location",
    "posted_date",
    "employment_type",
    "job_url",
    "source"
]

def compact_preview_jobs(jobs, limit=3):
    preview = []

    for job in jobs[:limit]:
        preview.append({
            field: job.get(field)
            for field in PREVIEW_FIELDS
            if job.get(field) is not None
        })

    return preview

@app.route("/")
def home():
    conn = sqlite3.connect("dashboard/db.sqlite")
    c = conn.cursor()

    rows = c.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
    conn.close()

    runs = []
    for r in rows:
        runs.append({
            "id": r[0],
            "config": r[1],
            "status": r[2],
            "processed": r[3],
            "total": r[4],
            "file_path": r[5] if len(r) > 5 else None
        })

    configs = os.listdir("config")

    return render_template("dashboard.html", configs=configs, runs=runs)

@app.route("/run", methods=["POST"])
def run():
    config_file = request.form["config"]
    url = request.form["url"]

    # 🔥 auto detect ATS
    detected = detect_ats(url)

    if detected:
        config_file = detected

    job = enqueue_job({
        "config": config_file,
        "url": url
    })

    job_queue.put(job)
    return redirect("/")
@app.route("/api/test", methods=["POST"])
def test_url():
    import requests

    data = request.get_json()
    url = data.get("url")

    if not url:
        return {"status": "error", "message": "No URL provided"}

    try:
        res = requests.get(url, timeout=5)

        if res.status_code == 200:
            return {
                "status": "success",
                "message": f"✅ URL reachable (Status {res.status_code})"
            }
        else:
            return {
                "status": "warning",
                "message": f"⚠️ URL responded with status {res.status_code}"
            }

    except Exception as e:
        return {
            "status": "error",
            "message": f"❌ Failed to reach URL"
        }
@app.route("/api/preview", methods=["POST"])
def preview_jobs():
    import json

    data = request.get_json()
    url = data.get("url")
    config_file = data.get("config")

    if not url or not config_file:
        return {"status": "error", "message": "Missing URL or config"}

    try:
        # 🔹 load config
        with open(f"config/{config_file}") as f:
            config = json.load(f)

        from dashboard.jobs import build_ats_config
        config = build_ats_config(config_file, config, url)

        from core.fetcher import Fetcher
        from core.parser import Parser

        if config.get("type") == "icims":
            from core.scraper import UniversalScraper
            config["pagination"]["max_pages"] = 1
            jobs = UniversalScraper(config).run()

            return {
                "status": "success",
                "jobs": compact_preview_jobs(jobs)
            }

        fetcher = Fetcher()
        parser = Parser()

        # 🔥 ONLY FIRST API CALL (NO PAGINATION)
        data = fetcher.fetch(config, offset=0)

        jobs = parser.parse_api(data, config)

        # 🔥 ONLY 3 JOBS
        preview = compact_preview_jobs(jobs)

        return {
            "status": "success",
            "jobs": preview
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

@app.route("/api/runs")
def api_runs():
    conn = sqlite3.connect("dashboard/db.sqlite")
    c = conn.cursor()

    rows = c.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
    conn.close()

    runs = []
    for r in rows:
        runs.append({
            "id": r[0],
            "config": r[1],
            "status": r[2],
            "processed": r[3],
            "total": r[4],
            "file_path": r[5] if len(r) > 5 else None
        })

    return jsonify(runs)

@app.route("/preview/<int:run_id>")
def preview(run_id):
    conn = sqlite3.connect("dashboard/db.sqlite")
    c = conn.cursor()

    c.execute("SELECT file_path FROM runs WHERE id=?", (run_id,))
    row = c.fetchone()
    conn.close()

    if not row or not row[0]:
        return "❌ No output file found"

    filepath = row[0]

    if not os.path.exists(filepath):
        return "❌ File missing"

    with open(filepath) as f:
        data = json.load(f)

    return render_template("json_viewer.html", data=data[:50])

@app.route("/download/<int:run_id>")
def download(run_id):
    conn = sqlite3.connect("dashboard/db.sqlite")
    c = conn.cursor()

    c.execute("SELECT file_path FROM runs WHERE id=?", (run_id,))
    row = c.fetchone()
    conn.close()

    if not row or not row[0]:
        return "❌ No file found"

    filepath = row[0]

    if not os.path.exists(filepath):
        return "❌ File missing"

    return send_file(filepath, as_attachment=True)

@app.route("/config/<filename>", methods=["GET", "POST"])
def edit_config(filename):
    path = os.path.join("config", filename)

    if request.method == "POST":
        content = request.form["content"]
        with open(path, "w") as f:
            f.write(content)
        return redirect("/")

    with open(path) as f:
        content = f.read()

    return render_template("config_editor.html",
                           filename=filename,
                           content=content)
    
@app.route("/delete/<int:run_id>", methods=["POST"])
def delete_run(run_id):
    conn = None
    try:
        conn = sqlite3.connect("dashboard/db.sqlite")
        c = conn.cursor()

        # 🔹 get run
        c.execute("SELECT status, file_path FROM runs WHERE id=?", (run_id,))
        row = c.fetchone()

        if not row:
            return redirect("/")   # ✅ always return

        status, filepath = row

        # 🔥 block running jobs
        if status == "RUNNING":
            return redirect("/")   # ✅ return

        # 🔥 delete file if exists (optional)
        if filepath and os.path.exists(filepath):
            os.remove(filepath)

        # 🔥 ALWAYS delete DB row (IMPORTANT)
        c.execute("DELETE FROM runs WHERE id=?", (run_id,))
        conn.commit()

        return redirect("/")   # ✅ return

    except Exception as e:
        print("DELETE ERROR:", e)
        return redirect("/")   # ✅ return

    finally:
        if conn:
            conn.close()
def detect_ats(url):
    url = url.lower()

    if "myworkdayjobs" in url:
        return "workday.json"
    elif "greenhouse" in url:
        return "greenhouse.json"
    elif "lever.co" in url:
        return "lever.json"
    elif "smartrecruiters" in url:
        return "smartrecruiters.json"
    elif "icims" in url:
        return "icims.json"
    elif "taleo" in url or "oraclecloud" in url:
        return "taleo.json"

    return None

if __name__ == "__main__":
    app.run(debug=True)
