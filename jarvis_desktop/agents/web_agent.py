"""
Web Agent — Headless browser automation (no visible window)
"""

import time
import requests
from urllib.parse import quote_plus
from utils.logger import JarvisLogger
from utils.config import Config


class WebAgent:
    def __init__(self, config: Config):
        self.config = config
        self.logger = JarvisLogger("WebAgent")
        self.driver = None

    def _init_driver(self) -> bool:
        # Legacy stub: Selenium is deprecated in favor of BS4 for speed.
        return True

    def search(self, query: str) -> str:
        """Ultra-Fast modern search using direct text-summary integration"""
        try:
            self.logger.info(f"Searching web for: {query}")
            from duckduckgo_search import DDGS
            
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=3))
                
            if not results:
                return f"I searched, but couldn't find active info for '{query}'."
                
            # Collate the best text bits instantly
            summary = " | ".join([r.get("body", "") for r in results])
            # Just in case, return a healthy chunk
            return summary[:600]
            
        except Exception as e:
            self.logger.error(f"Modern search failed: {e}")
            # Safe Fallback to original BS4 text extractor on Google if DDGS crashes
            return self.get_page_text(f"https://www.google.com/search?q={quote_plus(query)}")

    def get_page_text(self, url: str) -> str:
        """Lightweight and fast HTML requests with BeautifulSoup extraction"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code != 200:
                return f"HTTP Error {r.status_code}"
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")
            
            # Rip away scripts/styles
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()
                
            text = soup.get_text(separator=" ")
            # Simple cleanup whitespace
            cleaned = " ".join(text.split())
            return cleaned[:800]
        except Exception as e:
            self.logger.warning(f"Lightweight scrape failed: {e}")
            return "Could not read page."

    def open_url_visible(self, url: str) -> str:
        """Open in default browser (visible to user)"""
        import webbrowser
        webbrowser.open(url)
        return f"Opened {url} in your browser."

    def send_email_draft(self, content: str) -> str:
        url = f"https://mail.google.com/mail/?view=cm&fs=1&body={quote_plus(content)}"
        return self.open_url_visible(url)

    def handle_command(self, cmd: str) -> str:
        c = cmd.lower()

        if "youtube" in c:
            q = c.replace("youtube", "").replace("search", "").replace("on", "").strip()
            url = f"https://youtube.com/results?search_query={quote_plus(q)}" if q else "https://youtube.com"
            return self.open_url_visible(url)

        elif "search" in c or "google" in c or "find" in c:
            q = (c.replace("search", "").replace("google", "").replace("find", "")
                  .replace("online", "").replace("on the web", "").strip())
            result = self.search(q)
            return result or f"No results found for '{q}'."

        elif "email" in c:
            return self.send_email_draft(cmd)

        else:
            q = c.strip()
            return self.search(q)

    def close(self):
        pass
