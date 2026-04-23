import httpx
import json
from urllib.parse import quote
from aic import kairos

def search(query: str, api_key: str, max_results: int = 5) -> list[dict]:
    """Brave Search API client. Returns {title, url, snippet}"""
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
    }

    # Cap max_results at 10
    limit = min(max_results, 10)
    url = f"https://api.search.brave.com/res/v1/web/search?q={quote(query)}&count={limit}"

    try:
        resp = httpx.get(url, headers=headers, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for result in data.get("web", {}).get("results", []):
            results.append({
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "snippet": result.get("description", "")
            })

        return results[:limit]

    except Exception as e:
        kairos.log_event("search_error", "system", {"provider": "brave", "error": str(e)})
        return []
