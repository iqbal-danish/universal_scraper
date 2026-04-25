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
