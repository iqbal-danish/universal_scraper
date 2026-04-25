import asyncio
import aiohttp

from core.fetcher import Fetcher
from core.parser import Parser
from core.normalizer import Normalizer
from core.async_fetcher import AsyncFetcher


class UniversalScraper:

    def __init__(self, config):
        self.config = config
        self.fetcher = Fetcher()
        self.parser = Parser()
        self.normalizer = Normalizer()

    def run(self):
        jobs = []

        # =========================
        # ICIMS PUBLIC PORTAL SCRAPING
        # =========================
        if self.config["type"] == "icims":
            job_urls = self.discover_icims_jobs()
            detailed_jobs = asyncio.run(
                self.fetch_icims_details(job_urls)
            )

            return self.normalizer.normalize(detailed_jobs)

        # =========================
        # API SCRAPING (Workday etc.)
        # =========================
        if self.config["type"] == "api":

            pagination = self.config.get("pagination", {})
            step = pagination.get("step", 20)
            max_pages = pagination.get("max_pages", 50)

            for page in range(max_pages):
                offset = page * step

                data = self.fetcher.fetch(self.config, offset)
                extracted = self.parser.parse_api(data, self.config)

                if not extracted:
                    break

                jobs.extend(extracted)

                if pagination.get("type") != "offset" or len(extracted) < step:
                    break

            # 🔥 DEDUPLICATION (fix mismatch issue)
            unique = {}
            for job in jobs:
                key = job.get("id") or job.get("json_url")
                if key:
                    unique[key] = job

            jobs = list(unique.values())

            # 🔥 ASYNC DETAIL SCRAPING
            detailed_jobs = asyncio.run(
                self.fetch_all_details(jobs)
            )

            return self.normalizer.normalize(detailed_jobs)

        # =========================
        # HTML SCRAPING
        # =========================
        else:
            data = self.fetcher.fetch(self.config)
            jobs = self.parser.parse_html(data, self.config["base_url"])

            return self.normalizer.normalize(jobs)

    # =========================
    # ASYNC DETAIL FETCH
    # =========================
    async def fetch_all_details(self, jobs):
        fetcher = AsyncFetcher()
        sem = asyncio.Semaphore(10)  # control concurrency

        async with aiohttp.ClientSession() as session:

            async def safe_fetch(job):
                try:
                    # 🔥 Use json_url instead of apply_url
                    url = job.get("json_url")

                    if not url:
                        return job

                    async with sem:
                        data = await fetcher.fetch_detail(session, url)

                    if data:
                        details = self.parser.parse_detail(data, job, self.config) or {}
                        job.update(details)
                    else:
                        job["description"] = None

                except Exception as e:
                  print("❌ JOB FAILED:", job.get("json_url"), e)
                  job["description"] = "Failed"

                return job

            tasks = [safe_fetch(job) for job in jobs]
            results = await asyncio.gather(*tasks)

            return results

    # =========================
    # ICIMS LINK DISCOVERY
    # =========================
    def discover_icims_jobs(self):
        base_url = self.config["base_url"]
        max_pages = self.config.get("pagination", {}).get("max_pages", 25)
        jobs = []
        seen = set()

        for page in range(max_pages):
            url = self.config.get("search_url_template", "{host}/jobs/search?pr={page}&in_iframe=1").format(
                host=self.config["host"],
                page=page
            )

            try:
                html = self.fetcher.fetch_text(url)
            except Exception:
                if page != 0:
                    break
                try:
                    html = self.fetcher.fetch_text(f"{self.config['host']}/jobs?in_iframe=1")
                except Exception:
                    break

            links = self.parser.parse_icims_links(html, base_url)
            new_links = [link for link in links if link not in seen]

            if not new_links:
                break

            for link in new_links:
                seen.add(link)
                jobs.append(link)

        return jobs

    # =========================
    # ICIMS DETAIL FETCH
    # =========================
    async def fetch_icims_details(self, job_urls):
        fetcher = AsyncFetcher()
        sem = asyncio.Semaphore(10)

        async with aiohttp.ClientSession() as session:

            async def safe_fetch(url):
                try:
                    async with sem:
                        html = await fetcher.fetch_text(session, url)

                    if not html:
                        return None

                    return self.parser.parse_icims_detail(html, url, self.config)

                except Exception as e:
                    print("❌ ICIMS JOB FAILED:", url, e)
                    return None

            tasks = [safe_fetch(url) for url in job_urls]
            results = await asyncio.gather(*tasks)

            return [job for job in results if job]
