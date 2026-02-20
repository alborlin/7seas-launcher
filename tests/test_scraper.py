"""Tests for FitGirl scraper — uses saved HTML fixtures and synthetic HTML."""

import os
import pytest

from sevenseas.core.scraper import FitGirlScraper, GameResult, GameDetail


@pytest.fixture
def scraper():
    return FitGirlScraper()


def test_extract_magnet_from_detail():
    """Should extract magnet link from detail page HTML."""
    html = '''<html><body>
    <h1 class="entry-title">Test Game</h1>
    <div class="entry-content">
        <p>Repack Size: 5.2 GB</p>
        <a href="magnet:?xt=urn:btih:abc123&dn=Test+Game">Magnet</a>
    </div>
    </body></html>'''
    scraper = FitGirlScraper()
    detail = scraper.parse_detail(html, "https://fitgirl-repacks.site/test-game/")
    assert detail.magnet_uri is not None
    assert detail.magnet_uri.startswith("magnet:")
    assert "abc123" in detail.magnet_uri


def test_extract_magnet_returns_none_when_absent():
    html = '<html><body><h1 class="entry-title">No Magnet</h1><div class="entry-content"><p>No magnet here</p></div></body></html>'
    scraper = FitGirlScraper()
    detail = scraper.parse_detail(html, "https://fitgirl-repacks.site/test/")
    assert detail.magnet_uri is None


def test_parse_listing_from_synthetic_html():
    """Should parse articles from listing HTML."""
    html = '''<html><body>
    <article>
        <h2 class="entry-title"><a href="https://fitgirl-repacks.site/elden-ring/">Elden Ring</a></h2>
        <p>Repack Size: 35.2 GB</p>
    </article>
    <article>
        <h2 class="entry-title"><a href="https://fitgirl-repacks.site/cyberpunk-2077/">Cyberpunk 2077</a></h2>
        <p>Repack Size: 42.1 GB</p>
    </article>
    </body></html>'''
    scraper = FitGirlScraper()
    results = scraper.parse_listing(html)
    assert len(results) == 2
    assert results[0].title == "Elden Ring"
    assert results[0].url == "https://fitgirl-repacks.site/elden-ring/"
    assert results[1].title == "Cyberpunk 2077"


def test_game_result_dataclass():
    r = GameResult(title="Test", url="https://example.com", thumbnail=None, size_info="5 GB")
    assert r.title == "Test"
    assert r.size_info == "5 GB"


def test_slug_from_url():
    scraper = FitGirlScraper()
    assert scraper.slug_from_url("https://fitgirl-repacks.site/elden-ring/") == "elden-ring"
    assert scraper.slug_from_url("https://fitgirl-repacks.site/some-game/") == "some-game"


def test_parse_detail_extracts_title():
    html = '''<html><body>
    <h1 class="entry-title">Cool Game (v1.2 + DLCs)</h1>
    <div class="entry-content"><p>Some content</p></div>
    </body></html>'''
    scraper = FitGirlScraper()
    detail = scraper.parse_detail(html, "https://fitgirl-repacks.site/cool-game/")
    assert detail.title == "Cool Game (v1.2 + DLCs)"


def test_parse_detail_extracts_size():
    html = '''<html><body>
    <h1 class="entry-title">Game</h1>
    <div class="entry-content"><p>Repack Size: 12.4 GB</p></div>
    </body></html>'''
    scraper = FitGirlScraper()
    detail = scraper.parse_detail(html, "https://example.com/game/")
    assert detail.size_info == "12.4 GB"
