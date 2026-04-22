import httpx
import json
from aic import kairos

def search(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo HTML scrape or API fallback. Returns {title, url, snippet}"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1"

    try:
        resp = httpx.get(url, headers=headers, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()

        results = []
        if data.get("AbstractText") and data.get("AbstractURL"):
             results.append({
                 "title": data.get("Heading", "Abstract"),
                 "url": data.get("AbstractURL"),
                 "snippet": data.get("AbstractText")
             })

        for result in data.get("RelatedTopics", []):
            if "Text" in result and "FirstURL" in result:
                results.append({
                    "title": result.get("Text", "").split(" - ")[0] if " - " in result.get("Text", "") else "Result",
                    "url": result.get("FirstURL"),
                    "snippet": result.get("Text")
                })

        return results[:max_results]

    except Exception as e:
        # Fallback of fallback: return empty list silently
        kairos.log_event("search_error", "system", {"provider": "ddg", "error": str(e)})
        return []
