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


def test_parse_detail_original_and_repack_size():
    html = '''<html><body>
    <h1 class="entry-title">Game</h1>
    <div class="entry-content">
        <p>Original Size: 50.2 GB</p>
        <p>Repack Size: 12.4 GB</p>
    </div>
    </body></html>'''
    scraper = FitGirlScraper()
    detail = scraper.parse_detail(html, "https://example.com/game/")
    assert detail.original_size == "50.2 GB"
    assert detail.repack_size == "12.4 GB"
    assert detail.size_info == "12.4 GB"


def test_parse_detail_full_description():
    html = '''<html><body>
    <h1 class="entry-title">Game</h1>
    <div class="entry-content">
        <p>An epic open-world adventure game set in a fantasy realm.</p>
        <p>Explore vast landscapes and battle fearsome enemies.</p>
        <ul><li>Feature one</li><li>Feature two</li></ul>
        <p>System Requirements</p>
        <p>Minimum: OS: Windows 10</p>
    </div>
    </body></html>'''
    scraper = FitGirlScraper()
    detail = scraper.parse_detail(html, "https://example.com/game/")
    assert "epic open-world" in detail.description
    assert "Explore vast" in detail.description
    assert "System Requirements" not in detail.description


def test_parse_detail_genres():
    html = '''<html><body>
    <h1 class="entry-title">Game</h1>
    <div class="entry-content">
        <p>Genres/Tags: Action, RPG, Open World, Adventure</p>
    </div>
    </body></html>'''
    scraper = FitGirlScraper()
    detail = scraper.parse_detail(html, "https://example.com/game/")
    assert "Action" in detail.genres
    assert "RPG" in detail.genres
    assert "Open World" in detail.genres


def test_parse_detail_system_requirements():
    html = '''<html><body>
    <h1 class="entry-title">Game</h1>
    <div class="entry-content">
        <p>Great game description.</p>
        <p>Minimum Requirements: OS: Windows 10, CPU: i5, RAM: 8GB
Recommended: OS: Windows 11, CPU: i7, RAM: 16GB</p>
        <p>Screenshots</p>
    </div>
    </body></html>'''
    scraper = FitGirlScraper()
    detail = scraper.parse_detail(html, "https://example.com/game/")
    assert detail.system_requirements is not None
    assert "Minimum" in detail.system_requirements


def test_parse_detail_screenshots_filtering():
    html = '''<html><body>
    <h1 class="entry-title">Game</h1>
    <div class="entry-content">
        <img class="alignleft" src="https://example.com/cover.jpg" />
        <a href="https://example.com/screen1.jpg"><img src="https://example.com/screen1_thumb.jpg" /></a>
        <a href="https://example.com/screen2.png"><img src="https://example.com/screen2_thumb.png" /></a>
        <img src="https://example.com/donate-button.png" />
    </div>
    </body></html>'''
    scraper = FitGirlScraper()
    detail = scraper.parse_detail(html, "https://example.com/game/")
    assert "https://example.com/screen1.jpg" in detail.screenshots
    assert "https://example.com/screen2.png" in detail.screenshots
    assert "https://example.com/cover.jpg" not in detail.screenshots
    assert "https://example.com/donate-button.png" not in detail.screenshots


def test_parse_popular_deduplicates_by_url():
    """Multiple Jetpack widgets with overlapping items should not produce duplicates."""
    widget = '''<div class="widget-grid-view-image">
        <a href="https://fitgirl-repacks.site/game-a/" title="Game A">
            <img src="https://example.com/a.jpg" />
        </a>
    </div>
    <div class="widget-grid-view-image">
        <a href="https://fitgirl-repacks.site/game-b/" title="Game B">
            <img src="https://example.com/b.jpg" />
        </a>
    </div>'''
    # Simulate 3 widgets with the same entries (like the yearly page)
    html = f"<html><body>{widget}{widget}{widget}</body></html>"
    scraper = FitGirlScraper()
    results = scraper.parse_popular(html)
    assert len(results) == 2
    assert results[0].title == "Game A"
    assert results[1].title == "Game B"
