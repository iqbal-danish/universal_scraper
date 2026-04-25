import requests

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
           res = requests.get(config["base_url"], 
                headers=headers)

        res.raise_for_status()
        return res.json()


    def fetch_detail(self, url):
        res = requests.get(url, headers={
        "User-Agent": "Mozilla/5.0"
         })
        res.raise_for_status()
        return res.json()
