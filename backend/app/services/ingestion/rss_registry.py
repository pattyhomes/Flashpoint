import csv
from dataclasses import dataclass
from pathlib import Path


REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "rss_feed_registry.csv"


@dataclass(frozen=True)
class RssFeed:
    name: str
    feed_url: str
    allowed_domains: tuple[str, ...]
    region: str
    source_family: str
    enabled: bool
    priority: int = 5
    expected_region: str = ""
    specificity_goal: str = ""
    notes: str = ""


def load_feed_registry(path: Path | None = None, *, enabled_only: bool = False) -> list[RssFeed]:
    registry_path = path or REGISTRY_PATH
    feeds: list[RssFeed] = []
    with registry_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            feed = RssFeed(
                name=(row.get("name") or "").strip(),
                feed_url=(row.get("feed_url") or "").strip(),
                allowed_domains=tuple(
                    part.strip().lower()
                    for part in (row.get("allowed_domains") or "").split(";")
                    if part.strip()
                ),
                region=(row.get("region") or "").strip(),
                source_family=(row.get("source_family") or "news").strip(),
                enabled=(row.get("enabled") or "").strip().lower() in {"1", "true", "yes", "on"},
                priority=int((row.get("priority") or "5").strip() or "5"),
                expected_region=(row.get("expected_region") or row.get("region") or "").strip(),
                specificity_goal=(row.get("specificity_goal") or "").strip(),
                notes=(row.get("notes") or "").strip(),
            )
            if enabled_only and not feed.enabled:
                continue
            _validate_feed(feed)
            feeds.append(feed)
    return feeds


def load_enabled_local_news_feeds(path: Path | None = None) -> list[RssFeed]:
    return load_feed_registry(path, enabled_only=True)


def _validate_feed(feed: RssFeed):
    if not feed.name:
        raise ValueError("RSS registry row is missing name")
    if feed.enabled and not feed.feed_url:
        raise ValueError(f"Enabled RSS feed {feed.name!r} is missing feed_url")
    if feed.enabled and not feed.allowed_domains:
        raise ValueError(f"Enabled RSS feed {feed.name!r} is missing allowlist domains")
