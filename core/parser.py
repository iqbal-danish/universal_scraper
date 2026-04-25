from bs4 import BeautifulSoup
from urllib.parse import urljoin
from core.location_utils import normalize_location
from datetime import datetime, timedelta
import re


class Parser:

    # =========================
    # HTML PARSER
    # =========================
    def parse_html(self, html, base):
        soup = BeautifulSoup(html, "html.parser")
        jobs = []

        for item in soup.select("article.product_pod"):
            title = item.select_one("h3 a")["title"]
            link = item.select_one("h3 a")["href"]

            jobs.append({
                "title": title,
                "apply_url": urljoin(base, link)
            })

        return jobs


        # =========================
        # JSON PARSER
        # =========================
    def parse_json(self, data):
        return data if isinstance(data, list) else []


    # =========================
    # WORKDAY LIST API
    # =========================
    def parse_api(self, data, config):
        ats = config.get("ats", "workday")

        if ats == "greenhouse":
            return self.parse_greenhouse_api(data, config)

        return self.parse_workday_api(data, config)

    def parse_workday_api(self, data, config):
        jobs = []

        items = data.get(config.get("data_path", "jobPostings")) or []

        for job in items:
            parsed = {}

            parsed["title"] = self.clean_text(job.get("title"))
            parsed["posted_date"] = normalize_posted_date(job.get("postedOn"))
            parsed["employment_type"] = job.get("timeType")
            parsed["source"] = "workday"
            parsed["company"] = config.get("tenant").replace("-", " ").title()

            # 🔹 REQ ID
            bullet_fields = job.get("bulletFields") or []
            req_id = None

            for field in bullet_fields:
                if field and "req" in field.lower():
                    req_id = field
                    break

            external_path = job.get("externalPath")

            if not req_id and external_path and "_" in external_path:
                req_id = external_path.split("_")[-1]

            parsed["req_id"] = req_id
            parsed["id"] = req_id

                    # 🔹 URLs
            if external_path:
                parsed["job_url"] = config.get("host") + external_path

                parsed["json_url"] = (
                    config.get("host")
                    + "/wday/cxs/"
                    + config.get("tenant")
                    + "/"
                    + config.get("site")
                    + external_path
                )

                jobs.append(parsed)

        return jobs

    # =========================
    # GREENHOUSE JOB BOARD API
    # =========================
    def parse_greenhouse_api(self, data, config):
        jobs = []

        for job in data.get("jobs", []) or []:
            offices = job.get("offices") or []
            location_name = None

            if offices:
                location_name = offices[0].get("name")
            elif job.get("location"):
                location_name = job.get("location", {}).get("name")

            loc = normalize_location(location_name)
            req_id = str(job.get("id")) if job.get("id") is not None else None

            jobs.append({
                "id": req_id,
                "req_id": req_id,
                "title": self.clean_text(job.get("title")),
                "company": config.get("company") or config.get("board_token", "").replace("-", " ").title(),
                "raw_location": location_name,
                "description": self.clean_html_light(job.get("content")),
                "job_url": job.get("absolute_url"),
                "json_url": None,
                "source": "greenhouse",
                **loc
            })

        return jobs


                    # =========================
                    # WORKDAY DETAIL API
                    # =========================
    def parse_detail(self, data, job_meta=None, config=None):
        ats = (config or {}).get("ats", "workday")

        if ats == "greenhouse":
            return {}

        return self.parse_workday_detail(data, job_meta)

    def parse_workday_detail(self, data, job_meta=None):
        job = data.get("jobPostingInfo", {})

    # 🔹 PRIMARY
        loc_str = job.get("location")

    # 🔹 FALLBACK 1
        if not loc_str:
            locations = job.get("additionalLocations") or []
            if locations:
                loc_str = locations[0]

            # 🔹 FALLBACK 2 (URL)
        if not loc_str and job_meta:
            json_url = job_meta.get("json_url")
            if json_url:
                parts = json_url.split("/")
                if len(parts) > 2:
                    loc_str = parts[2].replace("---", " - ")

                        # 🔹 NORMALIZE
        loc = normalize_location(loc_str)

                        # 🔹 CITY FROM TITLE
        title = job.get("title") or ""
        match = re.search(r"-\s*([^,]+),\s*([A-Z]{2})$", title)

        if match:
            loc["city"] = match.group(1).strip()

        return {
             "description": job.get("jobDescription"),
             "employment_type": job.get("timeType"),
             "posted_date": job.get("postedOn"),
             "raw_location": loc_str,
             **loc
        }


                        # =========================
                        # CLEAN TEXT
                        # =========================
    def clean_text(self, text):
        if not text:
            return text

        return (
        text.replace("\u2013", "-")
        .replace("\u2019", "'")
        .strip()
    )


    def clean_html_light(self, html):
        if not html:
            return html

        return (
        html.replace('\n', '')
        .replace('style="text-align:inherit"', '')
        .strip()
    )


    # =========================
    # DATE NORMALIZER
    # =========================
def normalize_posted_date(text):
    if not text:
        return text

    text = text.lower()

    if "today" in text:
        return datetime.today().strftime("%Y-%m-%d")

    if "yesterday" in text:
        return (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    return text
