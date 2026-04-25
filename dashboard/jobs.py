import sqlite3, json
from core.scraper import UniversalScraper
from datetime import datetime
from urllib.parse import parse_qs, urlparse

DB = "dashboard/db.sqlite"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY,
        config TEXT,
        status TEXT,
        processed INTEGER DEFAULT 0,
        total INTEGER DEFAULT 0
    )
    """)

    # 🔥 Add column safely
    try:
        c.execute("ALTER TABLE runs ADD COLUMN file_path TEXT")
    except:
        pass  # column already exists

    conn.commit()
    conn.close()

def enqueue_job(job_data):
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # 🔥 store only config string in DB
    c.execute(
        "INSERT INTO runs (config, status) VALUES (?, ?)",
        (job_data["config"], "QUEUED")
    )

    run_id = c.lastrowid

    conn.commit()
    conn.close()

    return {
        "run_id": run_id,
        "config": job_data["config"],
        "url": job_data["url"]   # runtime only (NOT stored in DB)
    }

def update_progress(run_id, processed=None, total=None):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if total is not None:
        c.execute("UPDATE runs SET total=? WHERE id=?", (total, run_id))
    if processed is not None:
        c.execute("UPDATE runs SET processed=? WHERE id=?", (processed, run_id))
    conn.commit()
    conn.close()

def build_workday_config(config, url):
    from urllib.parse import urlparse

    parsed = urlparse(url)

    host = parsed.netloc                  # example: company.wd5.myworkdayjobs.com
    site = parsed.path.strip("/")         # example: External
    tenant = host.split(".")[0]           # example: company

    # 🔥 Build API endpoint dynamically
    config["base_url"] = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"

    # 🔥 Used later for detail API
    config["host"] = f"https://{host}"
    config["tenant"] = tenant
    config["site"] = site

    return config

def build_greenhouse_config(config, url):
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)

    board_token = config.get("board_token")

    if "boards.greenhouse.io" in parsed.netloc:
        board_token = query.get("for", [None])[0] or (path_parts[0] if path_parts else board_token)
    elif "job-boards.greenhouse.io" in parsed.netloc:
        board_token = path_parts[0] if path_parts else board_token
    elif "boards-api.greenhouse.io" in parsed.netloc and len(path_parts) >= 3:
        board_token = path_parts[2]

    if not board_token:
        raise ValueError("Could not detect Greenhouse board token from URL")

    config["board_token"] = board_token
    config["company"] = board_token.replace("-", " ").title()
    config["base_url"] = (
        f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    )

    return config

def build_lever_config(config, url):
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]

    site = config.get("site")

    if "jobs.lever.co" in parsed.netloc:
        site = path_parts[0] if path_parts else site
    elif "api.lever.co" in parsed.netloc and len(path_parts) >= 3:
        site = path_parts[2]

    if not site:
        raise ValueError("Could not detect Lever site from URL")

    config["site"] = site
    config["company"] = site.replace("-", " ").title()
    config["base_url"] = f"https://api.lever.co/v0/postings/{site}"
    config["params"] = {
        "mode": "json"
    }

    return config

def build_smartrecruiters_config(config, url):
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]

    company_identifier = config.get("company_identifier")

    if "careers.smartrecruiters.com" in parsed.netloc:
        company_identifier = path_parts[0] if path_parts else company_identifier
    elif "jobs.smartrecruiters.com" in parsed.netloc:
        company_identifier = path_parts[0] if path_parts else company_identifier
    elif "api.smartrecruiters.com" in parsed.netloc:
        try:
            companies_index = path_parts.index("companies")
            company_identifier = path_parts[companies_index + 1]
        except (ValueError, IndexError):
            pass

    if not company_identifier:
        raise ValueError("Could not detect SmartRecruiters company identifier from URL")

    config["company_identifier"] = company_identifier
    config["company"] = company_identifier.replace("-", " ").title()
    config["base_url"] = f"https://api.smartrecruiters.com/v1/companies/{company_identifier}/postings"

    return config

def build_icims_config(config, url):
    parsed = urlparse(url)
    host = f"https://{parsed.netloc}"
    portal_host = parsed.netloc

    config["base_url"] = f"{host}/jobs"
    config["host"] = host
    config["portal_host"] = portal_host
    config["company"] = portal_host.split(".")[0].replace("-", " ").title()
    config["search_url_template"] = f"{host}/jobs/search?pr={{page}}&in_iframe=1"

    return config

def build_ashby_config(config, url):
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]

    board_name = config.get("board_name")

    if "jobs.ashbyhq.com" in parsed.netloc:
        board_name = path_parts[0] if path_parts else board_name
    elif "api.ashbyhq.com" in parsed.netloc and len(path_parts) >= 3:
        board_name = path_parts[2]

    if not board_name:
        raise ValueError("Could not detect Ashby job board name from URL")

    config["board_name"] = board_name
    config["company"] = board_name.replace("-", " ").title()
    config["base_url"] = f"https://api.ashbyhq.com/posting-api/job-board/{board_name}"
    config["params"] = {
        "includeCompensation": "true"
    }

    return config

def build_dayforce_config(config, url):
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    host = f"https://{parsed.netloc}"

    client_name = config.get("client_name")
    locale = config.get("locale", "en-US")
    portal = config.get("portal", "CANDIDATEPORTAL")

    if "dayforcehcm.com" in parsed.netloc:
        if path_parts and path_parts[0].lower() == "candidateportal" and len(path_parts) >= 3:
            locale = path_parts[1]
            client_name = path_parts[2]
            if len(path_parts) >= 5 and path_parts[3].lower() == "site":
                portal = path_parts[4]
        elif len(path_parts) >= 2:
            locale = path_parts[0]
            client_name = path_parts[1]
        if path_parts and path_parts[0].lower() != "candidateportal" and len(path_parts) >= 3:
            portal = path_parts[2]

    if not client_name:
        raise ValueError("Could not detect Dayforce client name from URL")

    config["client_name"] = client_name
    config["locale"] = locale
    config["portal"] = portal
    config["company"] = client_name.replace("-", " ").title()
    config["host"] = host
    if path_parts and path_parts[0].lower() == "candidateportal":
        config["base_url"] = f"{host}/CandidatePortal/{locale}/{client_name}/Site/{portal}"
    else:
        config["base_url"] = f"{host}/{locale}/{client_name}/{portal}"
    config["search_url"] = config["base_url"]

    return config

def build_ats_config(config_file, config, url):
    if config_file == "workday.json":
        return build_workday_config(config, url)

    if config_file == "greenhouse.json":
        return build_greenhouse_config(config, url)

    if config_file == "lever.json":
        return build_lever_config(config, url)

    if config_file == "smartrecruiters.json":
        return build_smartrecruiters_config(config, url)

    if config_file == "icims.json":
        return build_icims_config(config, url)

    if config_file == "ashby.json":
        return build_ashby_config(config, url)

    if config_file == "dayforce.json":
        return build_dayforce_config(config, url)

    config["base_url"] = url
    return config

def execute_job(job):
    run_id = job["run_id"]
    config_file = job["config"]
    url = job["url"]

    filepath = None   # 🔥 always initialize
    status = "FAILED"  # default

    # 🔹 Set status RUNNING
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE runs SET status=? WHERE id=?", ("RUNNING", run_id))
    conn.commit()
    conn.close()

    try:
        # 🔹 Load config
        with open(f"config/{config_file}") as f:
            config = json.load(f)

        config = build_ats_config(config_file, config, url)

        # 🔹 Run scraper
        scraper = UniversalScraper(config)
        jobs = scraper.run()

        total = len(jobs)
        update_progress(run_id, total=total)

        for i, _ in enumerate(jobs, start=1):
            update_progress(run_id, processed=i)

        # 🔹 File naming
        ats_name = config_file.replace(".json", "").capitalize()
        parsed = urlparse(url)
        org_name = config.get("company") or parsed.netloc.split(".")[0].replace("-", " ").title()
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        filename = f"{ats_name} - {org_name} - {timestamp}.json"
        filepath = f"output/{filename}"

        # 🔹 Save output
        with open(filepath, "w") as f:
            json.dump(jobs, f, indent=2)

        status = "SUCCESS"   # ✅ only if everything works

    except Exception as e:
        print("❌ JOB ERROR:", e)

    finally:
        # 🔹 Always update DB (no crash here)
        conn = sqlite3.connect(DB)
        c = conn.cursor()

        c.execute(
            "UPDATE runs SET status=?, file_path=? WHERE id=?",
            (status, filepath, run_id)
        )

        conn.commit()
        conn.close()
