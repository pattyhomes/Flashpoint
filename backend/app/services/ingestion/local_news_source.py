import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib import robotparser
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.services.geocoding import LocalGeocoder
from app.services.ingestion import rss_registry
from app.services.ingestion.base import ObservationCandidate
from app.services.ingestion.classifier import classify


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).replace(tzinfo=None)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None


def _strip_html(value: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()


def _domain(url: str | None) -> str:
    return urlparse(url or "").netloc.lower()


def _child_text(node: ET.Element, names: tuple[str, ...]) -> str | None:
    for name in names:
        child = node.find(name)
        if child is not None and child.text:
            return child.text.strip()
    for child in node:
        local = child.tag.rsplit("}", 1)[-1]
        if local in names and child.text:
            return child.text.strip()
    return None


class LocalNewsSource:
    source_name = "local_news"

    def __init__(self):
        self.stats = {"fetched": 0, "rejected": 0, "reject_counts": {}}
        self.geocoder = LocalGeocoder()
        self._robots_cache: dict[str, robotparser.RobotFileParser] = {}

    def fetch(self) -> list[ObservationCandidate]:
        if not settings.local_news_enabled:
            return []
        feed_configs = self._feed_configs()
        feed_urls = [feed_url for feed_url, _, _ in feed_configs]
        allowed_domains = {domain for _, domains, _ in feed_configs for domain in domains}
        if not allowed_domains:
            self._reject("allowlist_required")
            return []
        candidates: list[ObservationCandidate] = []
        feed_names = {feed_url: name for feed_url, _, name in feed_configs}
        for feed_url in feed_urls:
            domains = next(domains for url, domains, _ in feed_configs if url == feed_url)
            if _domain(feed_url) not in domains:
                self._reject("domain_not_allowed")
                continue
            try:
                response = httpx.get(feed_url, headers={"User-Agent": settings.local_news_user_agent}, timeout=30)
                response.raise_for_status()
                candidates.extend(self._parse_feed(response.text, feed_url, domains, feed_names[feed_url]))
            except Exception as exc:
                print(f"[local_news] Fetch error for {feed_url}: {exc}")
                self._reject("fetch_error")
        return candidates[: settings.local_news_max_records]

    def _feed_configs(self) -> list[tuple[str, set[str], str]]:
        configured_urls = _split_csv(settings.local_news_feed_urls)
        configured_domains = set(_split_csv(settings.local_news_allowed_domains))
        if configured_urls:
            return [(feed_url, configured_domains, _domain(feed_url) or "Local News") for feed_url in configured_urls]
        return [
            (feed.feed_url, set(feed.allowed_domains), feed.name)
            for feed in rss_registry.load_enabled_local_news_feeds()
        ]

    def _parse_feed(self, text: str, feed_url: str, allowed_domains: set[str], feed_name: str) -> list[ObservationCandidate]:
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            self._reject("parse_error")
            return []
        items = root.findall(".//item") or [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "entry"]
        candidates = []
        for item in items:
            self.stats["fetched"] += 1
            candidate = self._candidate_from_item(item, feed_url, allowed_domains, feed_name)
            if candidate:
                candidates.append(candidate)
        return candidates

    def _candidate_from_item(self, item: ET.Element, feed_url: str, allowed_domains: set[str], feed_name: str) -> ObservationCandidate | None:
        title = _child_text(item, ("title",)) or "Local news item"
        link = _child_text(item, ("link",))
        if link is None:
            link_node = item.find("{http://www.w3.org/2005/Atom}link")
            link = link_node.attrib.get("href") if link_node is not None else None
        description = _strip_html(_child_text(item, ("description", "summary", "content")))
        article_text = self._fetch_article(link, allowed_domains) if settings.local_news_fetch_articles else ""
        body = " ".join(part for part in [description, article_text] if part)
        result = classify(title=title, body=body, categories=[], concepts=[], min_score=0.55)
        if result is None:
            self._reject("classified_out")
            return None
        geocode = self.geocoder.resolve(text=f"{title} {body}")
        if geocode is None:
            self._reject("bad_location")
        published_at = _parse_dt(_child_text(item, ("pubDate", "published", "updated")))
        return ObservationCandidate(
            source_type="local_news",
            source_record_id=_child_text(item, ("guid", "id")) or link,
            source_url=link,
            source_name=feed_name or _domain(feed_url) or "Local News",
            source_title=title[:160],
            excerpt=body[:2000] or description,
            published_at=published_at,
            trust_tier="news",
            raw_payload={"feed_url": feed_url, "link": link, "title": title},
            status="lead",
            title=title[:160],
            summary=body[:500] or None,
            candidate_event_type=result.event_type,
            latitude=geocode.latitude if geocode else None,
            longitude=geocode.longitude if geocode else None,
            city=geocode.city if geocode else None,
            state=geocode.state if geocode else None,
            observed_at=published_at,
            confidence_score=min(0.68, 0.35 + result.score * 0.35),
            severity_score=0.35,
            location_precision=geocode.precision if geocode else None,
            location_confidence=geocode.confidence if geocode else 0.0,
            location_reason=geocode.reason if geocode else None,
            exception_category=None if geocode else "bad_location",
            exception_detail=None if geocode else "Local geocoder could not resolve a city/state.",
        )

    def _fetch_article(self, url: str | None, allowed_domains: set[str]) -> str:
        if not url or _domain(url) not in allowed_domains:
            return ""
        if not self._robots_allows(url):
            self._reject("robots_disallowed")
            return ""
        try:
            time.sleep(0.05)
            response = httpx.get(url, headers={"User-Agent": settings.local_news_user_agent}, timeout=30)
            response.raise_for_status()
        except Exception:
            self._reject("article_fetch_error")
            return ""
        text = _strip_html(response.text)
        return text[:4000]

    def _robots_allows(self, url: str) -> bool:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        if robots_url in self._robots_cache:
            parser = self._robots_cache[robots_url]
            return parser.can_fetch(settings.local_news_user_agent, url)
        parser = robotparser.RobotFileParser()
        parser.set_url(robots_url)
        try:
            response = httpx.get(robots_url, headers={"User-Agent": settings.local_news_user_agent}, timeout=10)
            if getattr(response, "status_code", 200) >= 400:
                parser.parse(["User-agent: *", "Allow: /"])
            else:
                parser.parse(response.text.splitlines())
        except Exception:
            parser.parse(["User-agent: *", "Allow: /"])
        self._robots_cache[robots_url] = parser
        return parser.can_fetch(settings.local_news_user_agent, url)

    def _reject(self, category: str):
        self.stats["rejected"] += 1
        counts = self.stats["reject_counts"]
        counts[category] = counts.get(category, 0) + 1
