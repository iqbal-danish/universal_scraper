import aiohttp
import asyncio

class AsyncFetcher:

  async def fetch_detail(self, session, url):
    try:
        async with session.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json"
            }
        ) as res:

            text = await res.text()

            # 🔥 Skip empty responses
            if not text.strip():
                return None

            try:
                return await res.json()
            except:
                import json
                return json.loads(text)

    except Exception as e:
        print("DETAIL ERROR:", url, e)
        return None

  async def fetch_text(self, session, url):
    try:
        async with session.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/html,application/xhtml+xml"
            }
        ) as res:
            return await res.text()

    except Exception as e:
        print("DETAIL ERROR:", url, e)
        return None
