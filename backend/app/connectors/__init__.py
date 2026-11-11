"""Connector registry: `sources.connector` -> implementation.

To support a new kind of source (sitemap, a partner webhook, YouTube Data
API...), add a class implementing connectors.base.Connector and register it
here; the job pipeline doesn't change.
"""

from app.connectors.base import Connector
from app.connectors.rss import RssConnector
from app.connectors.vietnamnet import VietnamnetJsonLdConnector
from app.connectors.youtube import YouTubeApiConnector

CONNECTORS: dict[str, Connector] = {
    "rss": RssConnector(),
    "vietnamnet_jsonld": VietnamnetJsonLdConnector(),
    "youtube_api": YouTubeApiConnector(),
}


def get_connector(name: str) -> Connector:
    try:
        return CONNECTORS[name]
    except KeyError:
        raise ValueError(f"unknown connector {name!r}; known: {sorted(CONNECTORS)}") from None
