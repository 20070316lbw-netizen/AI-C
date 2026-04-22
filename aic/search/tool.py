from typing import List, Dict
from aic.search import brave, ddg
from aic.config import get_config

class WebSearchTool:
    def __init__(self, config: dict = None):
        self.config = config or get_config()
        self.search_config = self.config.get("search", {})

    def search(self, query: str, max_results: int = None) -> List[Dict[str, str]]:
        if max_results is None:
            max_results = self.search_config.get("max_results", 5)

        brave_api_key = self.search_config.get("brave_api_key", "")

        if brave_api_key:
            results = brave.search(query, brave_api_key, max_results)
            if results:
                return results

        # DuckDuckGo fallback
        return ddg.search(query, max_results)

    def format_for_context(self, results: List[Dict[str, str]]) -> str:
        if not results:
            return "No results found."

        formatted = "### Web Search Results\n\n"
        for i, res in enumerate(results):
            title = res.get("title", "No Title")
            url = res.get("url", "#")
            snippet = res.get("snippet", "No snippet available.")
            formatted += f"**{i+1}. {title}**\n"
            formatted += f"URL: {url}\n"
            formatted += f"{snippet}\n\n"

        return formatted.strip()

SEARCH_TOOL_SCHEMA = {
    "name": "web_search",
    "description": "Search the web for current information. Use ONLY when the query requires up-to-date facts not available in context. Do not use for general knowledge, code help, or reasoning tasks.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"}
        },
        "required": ["query"]
    }
}
