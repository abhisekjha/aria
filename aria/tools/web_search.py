import httpx
from typing import List
from urllib.parse import quote_plus
from aria.utils.logger import get_logger
from aria.utils.rate_limiter import web_search_limiter

logger = get_logger(__name__)

try:
    import trafilatura
    _HAS_TRAFILATURA = True
except ImportError:
    _HAS_TRAFILATURA = False


def web_search(query: str, max_results: int = 5) -> List[dict]:
    """
    Search DuckDuckGo (free, no API key).
    Returns list of {title, url, snippet}.
    Never raises.
    """
    web_search_limiter.wait()

    try:
        encoded = quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AriaBot/1.0)"}

        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        resp.raise_for_status()

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")

        results = []
        for result in soup.select(".result")[:max_results]:
            title_el = result.select_one(".result__title")
            url_el = result.select_one(".result__url")
            snippet_el = result.select_one(".result__snippet")

            title = title_el.get_text(strip=True) if title_el else ""
            href = url_el.get_text(strip=True) if url_el else ""
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""

            if title:
                results.append({"title": title, "url": href, "snippet": snippet})

        logger.info(f"[WEB_SEARCH] '{query[:50]}' → {len(results)} results")
        return results

    except Exception as e:
        logger.error(f"[WEB_SEARCH] failed for '{query[:50]}': {e}")
        return []


def web_fetch(url: str, max_chars: int = 3000) -> str:
    """
    Fetch and extract main text content from a URL.
    Returns clean text, truncated to max_chars.
    Never raises.
    """
    web_search_limiter.wait()

    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AriaBot/1.0)"}
        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        resp.raise_for_status()

        if _HAS_TRAFILATURA:
            text = trafilatura.extract(resp.text) or ""
        else:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)

        text = " ".join(text.split())  # Normalize whitespace
        truncated = text[:max_chars]

        logger.info(f"[WEB_FETCH] {url[:60]} → {len(truncated)} chars")
        return truncated

    except Exception as e:
        logger.error(f"[WEB_FETCH] failed for {url[:60]}: {e}")
        return ""
