import requests
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

class Fetcher:

    def fetch(self, config, offset=0):
        method = config.get("method", "GET")
        headers = {
           "User-Agent": "Mozilla/5.0",
           **config.get("headers", {})
        }

        if method == "POST":
            body = config.get("body", {}).copy()

            # 🔥 Inject offset for pagination
            if config.get("pagination", {}).get("type") == "offset":
                body["offset"] = offset

            res = requests.post(
                config["base_url"],
                json=body,
                headers=headers
          )
        else:
           res = requests.get(self.build_url(config, offset),
                headers=headers)

        res.raise_for_status()
        return res.json()

    def build_url(self, config, offset=0):
        url = config["base_url"]
        params = config.get("params", {}).copy()
        pagination = config.get("pagination", {})

        if pagination.get("type") == "offset":
            params[pagination.get("offset_param", "offset")] = offset
            if pagination.get("limit_param") and pagination.get("step"):
                params[pagination["limit_param"]] = pagination["step"]

        if not params:
            return url

        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        for key, value in params.items():
            query[key] = [value]

        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

    def fetch_detail(self, url):
        res = requests.get(url, headers={
        "User-Agent": "Mozilla/5.0"
         })
        res.raise_for_status()
        return res.json()

    def fetch_text(self, url):
        res = requests.get(url, headers={
        "User-Agent": "Mozilla/5.0"
         })
        res.raise_for_status()
        return res.text
