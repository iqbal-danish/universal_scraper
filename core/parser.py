from bs4 import BeautifulSoup
from urllib.parse import urljoin
from core.location_utils import normalize_location
from datetime import datetime, timedelta
import json
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
    # ICIMS PUBLIC PORTAL
    # =========================
    def parse_icims_links(self, html, base_url):
        soup = BeautifulSoup(html, "html.parser")
        links = []
        seen = set()

        for link in soup.find_all("a", href=True):
            href = urljoin(base_url, link["href"])
            if not re.search(r"/jobs/\d+/.+/job", href):
                continue

            if "in_iframe=1" not in href:
                separator = "&" if "?" in href else "?"
                href = f"{href}{separator}in_iframe=1"

            clean_key = re.sub(r"[?&]in_iframe=1", "", href)
            if clean_key in seen:
                continue

            seen.add(clean_key)
            links.append(href)

        return links


    def parse_icims_detail(self, html, job_url, config):
        soup = BeautifulSoup(html, "html.parser")
        job = self.extract_jobposting_json_ld(soup) or {}

        title = job.get("title") or self.first_text(soup, [
            "h1",
            ".iCIMS_Header .iCIMS_Header_JobTitle",
            ".iCIMS_JobHeader .iCIMS_JobHeader_JobTitle"
        ])
        req_id = self.icims_identifier(job) or self.icims_id_from_url(job_url)
        loc_str = self.icims_location(job) or self.first_text(soup, [
            ".iCIMS_JobHeader .iCIMS_JobHeader_JobLocation",
            ".iCIMS_InfoMsg_JobLocation",
            "[class*=JobLocation]"
        ])
        loc = normalize_location(loc_str)

        company = (
            self.icims_hiring_org(job)
            or config.get("company")
            or config.get("portal_host", "").split(".")[0].replace("-", " ").title()
        )

        description = (
            job.get("description")
            or self.first_html(soup, [
                ".iCIMS_JobContent",
                ".iCIMS_JobDescription",
                "[class*=JobDescription]"
            ])
        )

        return {
            "id": req_id,
            "req_id": req_id,
            "title": self.clean_text(title),
            "company": company,
            **loc,
            "raw_location": loc_str,
            "posted_date": job.get("datePosted"),
            "employment_type": self.icims_employment_type(job.get("employmentType")),
            "description": self.clean_html_light(description),
            "job_url": re.sub(r"[?&]in_iframe=1", "", job_url),
            "json_url": job_url,
            "source": "icims"
        }

    # =========================
    # DAYFORCE PUBLIC PORTAL
    # =========================
    def parse_dayforce_links(self, html, base_url):
        soup = BeautifulSoup(html, "html.parser")
        links = []
        seen = set()

        for link in soup.find_all("a", href=True):
            href = urljoin(base_url, link["href"])
            if not self.is_dayforce_job_url(href):
                continue

            clean_key = href.split("?")[0].rstrip("/")
            if clean_key in seen:
                continue

            seen.add(clean_key)
            links.append(href)

        return links


    def parse_dayforce_detail(self, html, job_url, config):
        soup = BeautifulSoup(html, "html.parser")
        job = self.extract_jobposting_json_ld(soup) or {}

        page_text = soup.get_text("\n", strip=True)
        title = job.get("title") or self.first_text(soup, ["h1"])
        req_id = self.icims_identifier(job) or self.dayforce_req_id(page_text) or self.dayforce_id_from_url(job_url)
        loc_str = self.icims_location(job) or self.dayforce_location(page_text, req_id)
        loc = normalize_location(loc_str)

        return {
            "id": req_id,
            "req_id": req_id,
            "title": self.clean_text(title),
            "company": config.get("company") or config.get("client_name", "").replace("-", " ").title(),
            **loc,
            "raw_location": loc_str,
            "posted_date": job.get("datePosted") or self.dayforce_posted_date(page_text),
            "employment_type": self.icims_employment_type(job.get("employmentType")),
            "description": self.clean_html_light(job.get("description") or self.dayforce_description_html(soup)),
            "job_url": job_url,
            "json_url": job_url,
            "source": "dayforce"
        }


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
        if ats == "lever":
            return self.parse_lever_api(data, config)
        if ats == "smartrecruiters":
            return self.parse_smartrecruiters_api(data, config)
        if ats == "ashby":
            return self.parse_ashby_api(data, config)

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
    # ASHBY JOB POSTINGS API
    # =========================
    def parse_ashby_api(self, data, config):
        jobs = []

        for job in data.get("jobs", []) or []:
            if job.get("isListed") is False:
                continue

            location_name = job.get("location") or self.ashby_location_from_address(job.get("postalAddress"))
            loc = normalize_location(location_name)
            req_id = job.get("id") or job.get("jobId") or job.get("jobPostingId") or job.get("jobUrl")

            jobs.append({
                "id": req_id,
                "req_id": req_id,
                "title": self.clean_text(job.get("title")),
                "company": config.get("company") or config.get("board_name", "").replace("-", " ").title(),
                **loc,
                "raw_location": location_name,
                "posted_date": job.get("publishedAt") or job.get("createdAt"),
                "employment_type": job.get("employmentType"),
                "description": self.clean_html_light(job.get("descriptionHtml") or job.get("description")),
                "job_url": job.get("jobUrl") or job.get("applyUrl"),
                "json_url": None,
                "source": "ashby"
            })

        return jobs

    # =========================
    # LEVER POSTINGS API
    # =========================
    def parse_lever_api(self, data, config):
        jobs = []
        items = data if isinstance(data, list) else data.get("postings", [])

        for job in items or []:
            categories = job.get("categories") or {}
            location_name = categories.get("location")
            loc = normalize_location(location_name)
            req_id = job.get("id")

            jobs.append({
                "id": req_id,
                "req_id": req_id,
                "title": self.clean_text(job.get("text")),
                "company": config.get("company") or config.get("site", "").replace("-", " ").title(),
                **loc,
                "raw_location": location_name,
                "posted_date": job.get("createdAt"),
                "employment_type": categories.get("commitment"),
                "description": self.clean_html_light(
                    job.get("description")
                    or job.get("descriptionPlain")
                    or self.lever_lists_to_html(job.get("lists"))
                ),
                "job_url": job.get("hostedUrl") or job.get("applyUrl"),
                "json_url": None,
                "source": "lever"
            })

        return jobs

    # =========================
    # SMARTRECRUITERS POSTING API
    # =========================
    def parse_smartrecruiters_api(self, data, config):
        jobs = []

        for job in data.get("content", []) or []:
            location = job.get("location") or {}
            loc_str = self.smartrecruiters_location(location, job)
            loc = normalize_location(loc_str)
            req_id = job.get("uuid") or job.get("id")

            jobs.append({
                "id": req_id,
                "req_id": job.get("refNumber") or req_id,
                "title": self.clean_text(job.get("name")),
                "company": self.smartrecruiters_company(job, config),
                **loc,
                "raw_location": loc_str,
                "posted_date": job.get("releasedDate"),
                "employment_type": self.label_value(job.get("typeOfEmployment")),
                "job_url": self.smartrecruiters_job_url(job, config),
                "json_url": job.get("ref") or self.smartrecruiters_detail_url(job, config),
                "source": "smartrecruiters"
            })

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
                **loc,
                "raw_location": location_name,
                "description": self.clean_html_light(job.get("content")),
                "job_url": job.get("absolute_url"),
                "json_url": None,
                "source": "greenhouse"
            })

        return jobs


                    # =========================
                    # WORKDAY DETAIL API
                    # =========================
    def parse_detail(self, data, job_meta=None, config=None):
        ats = (config or {}).get("ats", "workday")

        if ats in ["greenhouse", "lever"]:
            return {}
        if ats == "smartrecruiters":
            return self.parse_smartrecruiters_detail(data)

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


    def parse_smartrecruiters_detail(self, data):
        location = data.get("location") or {}
        loc_str = self.smartrecruiters_location(location, data)
        loc = normalize_location(loc_str)

        return {
            "description": self.clean_html_light(self.smartrecruiters_description(data)),
            "employment_type": self.label_value(data.get("typeOfEmployment")),
            "posted_date": data.get("releasedDate"),
            **loc,
            "raw_location": loc_str,
        }


    def lever_lists_to_html(self, lists):
        if not lists:
            return None

        sections = []
        for item in lists:
            heading = item.get("text")
            content = item.get("content")

            if heading and content:
                sections.append(f"<h3>{heading}</h3>{content}")
            elif content:
                sections.append(content)

        return "".join(sections) or None


    def smartrecruiters_description(self, job):
        job_ad = job.get("jobAd") or {}
        sections = job_ad.get("sections") or {}

        if isinstance(sections, dict):
            parts = []
            for section in sections.values():
                if isinstance(section, dict):
                    text = section.get("text") or section.get("html")
                    if text:
                        parts.append(text)
                elif isinstance(section, str):
                    parts.append(section)
            if parts:
                return "".join(parts)

        return job.get("description") or job.get("jobDescription")


    def smartrecruiters_location(self, location, job=None):
        if not location and job:
            location = job.get("location") or {}

        city = location.get("city")
        region = location.get("region")
        country = location.get("country")

        parts = [part for part in [city, region, country] if part]
        if parts:
            return ", ".join(parts)

        if location.get("remote") or (job or {}).get("remote"):
            return "Remote"

        return None


    def smartrecruiters_company(self, job, config):
        company = job.get("company") or {}
        return (
            company.get("name")
            or config.get("company")
            or config.get("company_identifier", "").replace("-", " ").title()
        )


    def smartrecruiters_job_url(self, job, config):
        if job.get("applyUrl"):
            return job.get("applyUrl")

        company_identifier = config.get("company_identifier")
        job_id = job.get("id") or job.get("uuid")

        if company_identifier and job_id:
            return f"https://jobs.smartrecruiters.com/{company_identifier}/{job_id}"

        return None


    def smartrecruiters_detail_url(self, job, config):
        company_identifier = config.get("company_identifier")
        job_id = job.get("id") or job.get("uuid")

        if company_identifier and job_id:
            return f"https://api.smartrecruiters.com/v1/companies/{company_identifier}/postings/{job_id}"

        return None


    def label_value(self, value):
        if isinstance(value, dict):
            return value.get("label") or value.get("name") or value.get("id")

        return value


    def ashby_location_from_address(self, address):
        if not isinstance(address, dict):
            return None

        parts = [
            address.get("addressLocality"),
            address.get("addressRegion"),
            address.get("addressCountry")
        ]

        parts = [part for part in parts if part]
        return ", ".join(parts) if parts else None


    def is_dayforce_job_url(self, url):
        return bool(
            re.search(r"/jobs/\d+/?(?:$|\?)", url)
            or re.search(r"/Posting/View/\d+/?(?:$|\?)", url, re.IGNORECASE)
        )


    def dayforce_id_from_url(self, url):
        match = re.search(r"/(?:jobs|Posting/View)/(\d+)", url, re.IGNORECASE)
        return match.group(1) if match else None


    def dayforce_req_id(self, text):
        match = re.search(r"Req\s*#\s*([A-Za-z0-9_-]+)", text)
        return match.group(1) if match else None


    def dayforce_location(self, text, req_id=None):
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        for index, line in enumerate(lines):
            if req_id and f"Req #{req_id}" in line and index + 1 < len(lines):
                next_line = lines[index + 1]
                if next_line.lower() not in ["job description", "job details"]:
                    return next_line

        for index, line in enumerate(lines):
            if line.lower() == "job description" and index > 0:
                candidate = lines[index - 1]
                if not candidate.lower().startswith("req #"):
                    return candidate

        return None


    def dayforce_posted_date(self, text):
        match = re.search(r"Posted\s+(.+?)(?:\n|$)", text)
        return match.group(1).strip() if match else None


    def dayforce_description_html(self, soup):
        heading = None
        for node in soup.find_all(["h2", "h3"]):
            if node.get_text(" ", strip=True).lower() == "job description":
                heading = node
                break

        if not heading:
            return self.first_html(soup, ["main", "[role=main]", "body"])

        parts = []
        for sibling in heading.find_next_siblings():
            if sibling.name in ["h2", "h3"] and "job details" in sibling.get_text(" ", strip=True).lower():
                break
            parts.append(str(sibling))

        return "".join(parts) if parts else None


    def extract_jobposting_json_ld(self, soup):
        for script in soup.find_all("script", type="application/ld+json"):
            if not script.string:
                continue

            try:
                data = json.loads(script.string.strip())
            except json.JSONDecodeError:
                continue

            job = self.find_jobposting_node(data)
            if job:
                return job

        return None


    def find_jobposting_node(self, data):
        if isinstance(data, list):
            for item in data:
                found = self.find_jobposting_node(item)
                if found:
                    return found

        if isinstance(data, dict):
            item_type = data.get("@type")
            if item_type == "JobPosting" or (isinstance(item_type, list) and "JobPosting" in item_type):
                return data

            graph = data.get("@graph")
            if graph:
                return self.find_jobposting_node(graph)

        return None


    def icims_identifier(self, job):
        identifier = job.get("identifier")

        if isinstance(identifier, dict):
            return str(identifier.get("value") or identifier.get("name") or "").strip() or None

        if identifier:
            return str(identifier)

        return None


    def icims_id_from_url(self, url):
        match = re.search(r"/jobs/(\d+)/", url)
        return match.group(1) if match else None


    def icims_hiring_org(self, job):
        org = job.get("hiringOrganization")

        if isinstance(org, dict):
            return org.get("name")

        return org


    def icims_employment_type(self, value):
        if isinstance(value, list):
            return ", ".join([str(item) for item in value if item])

        return value


    def icims_location(self, job):
        locations = job.get("jobLocation")
        if isinstance(locations, dict):
            locations = [locations]

        if not isinstance(locations, list):
            return None

        for location in locations:
            address = location.get("address") if isinstance(location, dict) else None
            if not isinstance(address, dict):
                continue

            parts = [
                address.get("addressLocality"),
                address.get("addressRegion"),
                address.get("addressCountry")
            ]
            parts = [part for part in parts if part]
            if parts:
                return ", ".join(parts)

        return None


    def first_text(self, soup, selectors):
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                text = node.get_text(" ", strip=True)
                if text:
                    return text

        return None


    def first_html(self, soup, selectors):
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                return str(node)

        return None


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
