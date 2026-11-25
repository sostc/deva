"""
P3 其余来源验收：RSS（BIS / 媒体）、GPU 定价页

全部离线样例；每个来源各自测「解析 → 入库 → 去重」。
"""

import pytest

from deva.naja.geo_risk.collectors import parse_feed
from deva.naja.geo_risk.collectors import bis, media, gpu_pricing
from deva.naja.geo_risk.collectors.ingest import persist_items
from deva.naja.geo_risk.entities import EntityIndex
from deva.naja.geo_risk.seeds import load_seed
from deva.naja.geo_risk.store import GeoRiskDB

RSS_SAMPLE = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>BIS Adds Entities to the Entity List</title>
    <link>https://www.bis.gov/press/2026-1118</link>
    <guid>bis-2026-1118</guid>
    <pubDate>Tue, 18 Nov 2026 09:00:00 GMT</pubDate>
    <description>&lt;p&gt;Bureau of Industry and Security updates the Entity List.&lt;/p&gt;</description>
  </item>
  <item>
    <title>Commerce Announces Semiconductor Export Review</title>
    <link>https://www.bis.gov/press/2026-1115</link>
    <guid>bis-2026-1115</guid>
    <pubDate>Sun, 15 Nov 2026 14:30:00 GMT</pubDate>
    <description>Semiconductor export review announced.</description>
  </item>
</channel></rss>"""

ATOM_SAMPLE = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Data centre financing slows in Southeast Asia</title>
    <link href="https://example.com/news/2026/11/dc-financing" />
    <id>tag:example.com,2026:dc-financing</id>
    <updated>2026-11-17T08:00:00Z</updated>
    <summary>Financing conditions tighten for regional data centres.</summary>
  </entry>
</feed>"""

GPU_HTML = """<html><body>
<p>CoreWeave: NVIDIA H100 $2.49/hr</p>
<p>CoreWeave: NVIDIA H200 $3.99/hr</p>
<p>Lambda: NVIDIA A100 $1.29/hr</p>
</body></html>"""


@pytest.fixture
def db(tmp_path):
    d = GeoRiskDB(tmp_path / "geo_risk.db")
    load_seed(d)
    yield d
    d.close()


def test_rss_and_atom_parsing():
    rss = parse_feed(RSS_SAMPLE, "bis")
    assert len(rss) == 2
    assert rss[0].external_id == "bis-2026-1118"
    assert rss[0].published_at.startswith("2026-11-18")
    assert "<" not in rss[0].body, "应剥掉 HTML 标签"

    atom = parse_feed(ATOM_SAMPLE, "media")
    assert len(atom) == 1
    assert atom[0].url.endswith("/dc-financing")
    assert atom[0].published_at.startswith("2026-11-17")


BIS_HTML = """<!DOCTYPE html><html><head></head><body>
<script id="__NEXT_DATA__" type="application/json">{
  "props": {
    "pageProps": {
      "pressReleaseTeasers": [
        {
          "title": "BIS Issues Rule Addressing Remote Access to American Super Intelligence Technology",
          "path": "/press-release/bis-issues-rule-addressing-remote-access",
          "publishedOn": {"time": "2026-11-16T05:00:00+00:00"},
          "body": {"processed": "<p>WASHINGTON, D.C. &mdash; Today, BIS released an interim final rule.</p>"},
          "uuid": "f65a3e69-ddad-4fa2-99ed-6cddbbc8c92b",
          "id": "30873",
          "newsUpdatesTopic": [{"name": "Regulations"}]
        },
        {
          "title": "BIS Reaches Administrative Enforcement Settlement with Lambda",
          "path": "/press-release/bis-settlement-lambda",
          "publishedOn": {"time": "2026-10-02T16:00:00+00:00"},
          "body": {"processed": "<p>Settlement announced.</p>"},
          "uuid": "4f24caa8-0000-0000-0000-000000000000",
          "id": "30870",
          "newsUpdatesTopic": [{"name": "Enforcement"}]
        }
      ]
    }
  }
}</script></body></html>"""


def test_bis_parses_next_data_json():
    items = bis.parse(BIS_HTML)
    assert {it.source for it in items} == {"bis"}
    assert len(items) == 2
    assert items[0].title.startswith("BIS Issues Rule")
    assert items[0].url == "https://www.bis.gov/press-release/bis-issues-rule-addressing-remote-access"
    assert items[0].published_at == "2026-11-16T05:00:00+00:00"
    assert items[0].external_id == "f65a3e69-ddad-4fa2-99ed-6cddbbc8c92b"
    assert items[0].event_hint == "bis_regulations"
    assert "<" not in items[0].body, "应剥掉 HTML 标签"
    assert items[1].event_hint == "bis_enforcement"


def test_bis_missing_next_data_raises():
    with pytest.raises(ValueError, match="__NEXT_DATA__"):
        bis.parse("<html><body>no data</body></html>")


def test_media_source_tag():
    items = media.parse(RSS_SAMPLE, "the_edge")
    assert {it.source for it in items} == {"the_edge"}


def test_gpu_prices_parse_and_persist(db):
    idx = EntityIndex.from_db(db)
    items = gpu_pricing.parse_prices(GPU_HTML, url="fixture://gpu/pricing")
    assert len(items) == 3
    assert items[0].event_hint == "gpu_rental_price"

    stats = persist_items(db, items, idx)
    # 三条价格上下文里都出现了 NVIDIA / CoreWeave，按最长命中词选主体
    assert stats == {"fetched": 3, "stored": 3, "duplicates": 0, "unresolved": 0}
    rows = db.query("SELECT subject_id FROM evidence WHERE source = 'gpu_pricing'")
    assert "ent_coreweave" in {r["subject_id"] for r in rows}


def test_gpu_prices_dedupe(db):
    idx = EntityIndex.from_db(db)
    items = gpu_pricing.parse_prices(GPU_HTML, url="fixture://gpu/pricing")
    persist_items(db, items, idx)
    again = persist_items(db, items, idx)
    assert again["stored"] == 0 and again["duplicates"] == 3
