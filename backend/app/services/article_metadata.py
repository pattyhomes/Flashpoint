import html
import ipaddress
import re
import socket
import time
from dataclasses import dataclass
from urllib import robotparser
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.services.event_display import is_generic_title
from app.services.ingestion.classifier import classify

MAX_ARTICLE_BYTES = 800_000
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_OG_TITLE_RE = re.compile(
    r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)[\"'][^>]*>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SITE_SUFFIX_RE = re.compile(r"\s+[-|]\s+[^-|]{2,80}$")
_robots_cache: dict[str, robotparser.RobotFileParser] = {}


@dataclass(frozen=True)
class ArticleMetadata:
    title: str | None
    excerpt: str | None
    final_url: str | None
    reason: str | None = None

    @property
    def usable(self) -> bool:
        return bool(self.title and not is_generic_title(self.title))


def is_specific_unrest_metadata(metadata: ArticleMetadata, *, min_score: float = 0.55) -> bool:
    if not metadata.usable or not metadata.title:
        return False
    return classify(
        title=metadata.title,
        body=metadata.excerpt,
        categories=[],
        concepts=[],
        min_score=min_score,
    ) is not None


def _clean_text(value: str | None, *, limit: int | None = None) -> str | None:
    if not value:
        return None
    cleaned = html.unescape(value)
    cleaned = _HTML_TAG_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return None
    if limit is not None:
        return cleaned[:limit].strip()
    return cleaned


def normalize_article_title(value: str | None) -> str | None:
    cleaned = _clean_text(value, limit=240)
    if not cleaned:
        return None
    stripped = _SITE_SUFFIX_RE.sub("", cleaned).strip()
    if stripped and len(stripped) >= 8:
        cleaned = stripped
    if is_generic_title(cleaned):
        return None
    return cleaned


def _host_is_public(hostname: str | None) -> bool:
    if not hostname:
        return False
    host = hostname.strip().lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(host)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return True
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def _safe_url(url: str | None) -> tuple[bool, str | None]:
    parsed = urlparse(url or "")
    if parsed.scheme not in {"http", "https"}:
        return False, "URL must be HTTP(S)."
    if not _host_is_public(parsed.hostname):
        return False, "URL host is not public."
    return True, None


def _robots_allows(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    if robots_url in _robots_cache:
        parser = _robots_cache[robots_url]
        return parser.can_fetch(settings.local_news_user_agent, url)
    parser = robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        response = httpx.get(robots_url, headers={"User-Agent": settings.local_news_user_agent}, timeout=8)
        if getattr(response, "status_code", 200) >= 400:
            parser.parse(["User-agent: *", "Allow: /"])
        else:
            parser.parse(response.text.splitlines())
    except Exception:
        parser.parse(["User-agent: *", "Allow: /"])
    _robots_cache[robots_url] = parser
    return parser.can_fetch(settings.local_news_user_agent, url)


def fetch_article_metadata(url: str | None, *, rate_limit_seconds: float = 0.05) -> ArticleMetadata:
    safe, reason = _safe_url(url)
    if not safe:
        return ArticleMetadata(title=None, excerpt=None, final_url=url, reason=reason)
    assert url is not None
    if not _robots_allows(url):
        return ArticleMetadata(title=None, excerpt=None, final_url=url, reason="robots.txt disallowed article fetch.")
    try:
        if rate_limit_seconds > 0:
            time.sleep(rate_limit_seconds)
        response = httpx.get(
            url,
            headers={"User-Agent": settings.local_news_user_agent},
            timeout=20,
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception as exc:
        return ArticleMetadata(title=None, excerpt=None, final_url=url, reason=str(exc)[:220])

    final_url = str(getattr(response, "url", url))
    safe, reason = _safe_url(final_url)
    if not safe:
        return ArticleMetadata(title=None, excerpt=None, final_url=final_url, reason=reason)
    content_type = response.headers.get("content-type", "").lower()
    if content_type and "html" not in content_type and "text" not in content_type:
        return ArticleMetadata(title=None, excerpt=None, final_url=final_url, reason="Response was not HTML/text.")
    content = response.content[:MAX_ARTICLE_BYTES]
    text = content.decode(response.encoding or "utf-8", errors="replace")
    og_match = _OG_TITLE_RE.search(text)
    title_match = _TITLE_RE.search(text)
    title = normalize_article_title(og_match.group(1) if og_match else (title_match.group(1) if title_match else None))
    excerpt = _clean_text(text, limit=1000)
    if not title:
        return ArticleMetadata(title=None, excerpt=excerpt, final_url=final_url, reason="No specific article title found.")
    return ArticleMetadata(title=title, excerpt=excerpt, final_url=final_url)
