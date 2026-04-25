import json
class Normalizer:

    def normalize(self, jobs):
        normalized = []

        for job in jobs:
            normalized.append({
                "id": job.get("id"),
                "req_id": job.get("req_id"),
                "title": job.get("title"),
                "company": job.get("company"),
                "city": job.get("city"),
                "state": job.get("state"),
                "state_code": job.get("state_code"),
                "country": job.get("country"),
                "country_code": job.get("country_code"),
                "raw_location": job.get("raw_location"),
                "posted_date": job.get("posted_date"),
                "employment_type": job.get("employment_type"),
                "description": job.get("description"),
                "job_url": job.get("job_url"),
                "source": job.get("source"),

                "raw": {
                    "json_url": job.get("json_url")
                }
            })

        return normalized
    def to_json(self, jobs):
        return json.dumps(jobs, indent=2)
