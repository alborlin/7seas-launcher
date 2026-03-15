"""Discover view — Epic Games Store-style home page with hero carousel and trending sidebar."""

import re
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango

from sevenseas.ui.widgets.game_card import (
    GameCard, _CACHE_DIR, cache_path_for_url, atomic_write_cache,
)
from sevenseas.ui.widgets.trending_row import TrendingRow

HERO_COUNT = 5
DISCOVER_COUNT = 15


class DiscoverView(Gtk.ScrolledWindow):
    """Home page with hero carousel, trending sidebar, and horizontal discovery row."""

    def __init__(self, scraper, on_card_click=None, sgdb_api_key: str | None = None) -> None:
        super().__init__()
        self.set_vexpand(True)
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scraper = scraper
        self._on_card_click = on_card_click
        self._sgdb_api_key = sgdb_api_key
        self._loaded = False

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        root.set_margin_top(16)
        root.set_margin_bottom(16)
        root.set_margin_start(16)
        root.set_margin_end(16)
        self.set_child(root)

        # --- Hero section: carousel + trending sidebar ---
        hero_section = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        root.append(hero_section)

        # Hero carousel (left, expands)
        hero_main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        hero_main.set_hexpand(True)
        hero_section.append(hero_main)

        carousel_wrap = Gtk.Overlay()
        carousel_wrap.set_overflow(Gtk.Overflow.HIDDEN)
        carousel_wrap.add_css_class("hero-carousel")
        hero_main.append(carousel_wrap)

        self._carousel = Adw.Carousel()
        self._carousel.set_allow_long_swipes(True)
        carousel_wrap.set_child(self._carousel)

        # Carousel arrows
        left_btn = Gtk.Button(icon_name="go-previous-symbolic")
        left_btn.add_css_class("discover-scroll-arrow")
        left_btn.set_valign(Gtk.Align.CENTER)
        left_btn.set_halign(Gtk.Align.START)
        left_btn.set_margin_start(12)
        left_btn.connect("clicked", self._on_carousel_prev)
        carousel_wrap.add_overlay(left_btn)

        right_btn = Gtk.Button(icon_name="go-next-symbolic")
        right_btn.add_css_class("discover-scroll-arrow")
        right_btn.set_valign(Gtk.Align.CENTER)
        right_btn.set_halign(Gtk.Align.END)
        right_btn.set_margin_end(12)
        right_btn.connect("clicked", self._on_carousel_next)
        carousel_wrap.add_overlay(right_btn)

        self._indicator = Adw.CarouselIndicatorDots(carousel=self._carousel)
        self._indicator.set_halign(Gtk.Align.CENTER)
        hero_main.append(self._indicator)

        # Trending sidebar (right, fixed width)
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        sidebar.set_size_request(350, -1)
        sidebar.add_css_class("trending-sidebar")
        hero_section.append(sidebar)

        trending_label = Gtk.Label(label="Trending")
        trending_label.set_halign(Gtk.Align.START)
        trending_label.add_css_class("section-title")
        sidebar.append(trending_label)

        self._trending_list = Gtk.ListBox()
        self._trending_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._trending_list.add_css_class("boxed-list")
        sidebar.append(self._trending_list)

        # --- Discover Something New section ---
        discover_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        root.append(discover_header)

        discover_label = Gtk.Label(label="Discover Something New")
        discover_label.set_halign(Gtk.Align.START)
        discover_label.set_hexpand(True)
        discover_label.add_css_class("section-title")
        discover_header.append(discover_label)

        arrow_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        discover_header.append(arrow_box)

        self._disc_left = Gtk.Button(icon_name="go-previous-symbolic")
        self._disc_left.add_css_class("discover-scroll-arrow")
        self._disc_left.connect("clicked", self._on_discover_scroll_left)
        arrow_box.append(self._disc_left)

        self._disc_right = Gtk.Button(icon_name="go-next-symbolic")
        self._disc_right.add_css_class("discover-scroll-arrow")
        self._disc_right.connect("clicked", self._on_discover_scroll_right)
        arrow_box.append(self._disc_right)

        # Horizontal scrolling row of game cards
        self._discover_scroll = Gtk.ScrolledWindow()
        self._discover_scroll.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)
        self._discover_scroll.set_min_content_height(340)
        root.append(self._discover_scroll)

        self._discover_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._discover_scroll.set_child(self._discover_row)

        # --- Upcoming Repacks section (below discover) ---
        self._upcoming_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._upcoming_section.set_visible(False)
        root.append(self._upcoming_section)

        upcoming_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._upcoming_section.append(upcoming_header)

        upcoming_label = Gtk.Label(label="Upcoming Repacks")
        upcoming_label.set_halign(Gtk.Align.START)
        upcoming_label.set_hexpand(True)
        upcoming_label.add_css_class("section-title")
        upcoming_header.append(upcoming_label)

        up_arrow_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        upcoming_header.append(up_arrow_box)

        up_left = Gtk.Button(icon_name="go-previous-symbolic")
        up_left.add_css_class("discover-scroll-arrow")
        up_left.connect("clicked", self._on_upcoming_scroll_left)
        up_arrow_box.append(up_left)

        up_right = Gtk.Button(icon_name="go-next-symbolic")
        up_right.add_css_class("discover-scroll-arrow")
        up_right.connect("clicked", self._on_upcoming_scroll_right)
        up_arrow_box.append(up_right)

        self._upcoming_scroll = Gtk.ScrolledWindow()
        self._upcoming_scroll.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)
        self._upcoming_scroll.set_min_content_height(340)
        self._upcoming_section.append(self._upcoming_scroll)

        self._upcoming_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._upcoming_scroll.set_child(self._upcoming_row)

        # Loading spinner (centered)
        self._spinner = Gtk.Spinner()
        self._spinner.set_halign(Gtk.Align.CENTER)
        self._spinner.set_valign(Gtk.Align.CENTER)
        root.append(self._spinner)

    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self._spinner.start()
        # Launch all fetches concurrently
        threading.Thread(target=self._fetch_latest, daemon=True).start()
        threading.Thread(target=self._fetch_trending, daemon=True).start()
        threading.Thread(target=self._fetch_upcoming, daemon=True).start()

    def _fetch_latest(self) -> None:
        try:
            needed = HERO_COUNT + DISCOVER_COUNT
            all_results = []
            page = 1
            while len(all_results) < needed:
                page_results = self._scraper.get_latest(page=page)
                if not page_results:
                    break
                all_results.extend(page_results)
                page += 1
            GLib.idle_add(self._populate_hero_and_discover, all_results[:needed])
        except Exception:
            GLib.idle_add(self._spinner.stop)

    def _fetch_trending(self) -> None:
        try:
            results = self._scraper.get_top_monthly()
            GLib.idle_add(self._populate_trending, results[:6] if results else [])
        except Exception:
            pass

    def _fetch_upcoming(self) -> None:
        try:
            names = self._scraper.get_upcoming()
            if not names:
                return
            items = []  # list of (name, cover_url | None)
            if self._sgdb_api_key:
                import httpx as _httpx
                from sevenseas.core.steamgriddb import SteamGridDBClient
                sgdb = SteamGridDBClient(api_key=self._sgdb_api_key)
                for name in names:
                    cover_url = self._resolve_grid_art(name, sgdb, _httpx)
                    items.append((name, cover_url))
            else:
                items = [(n, None) for n in names]
            GLib.idle_add(self._populate_upcoming, items)
        except Exception:
            pass

    def _resolve_grid_art(self, name, sgdb, _httpx):
        """Resolve a Steam grid cover URL for a game name."""
        try:
            clean = self._clean_title(name)
            # Try Steam CDN grid first
            appid = sgdb.get_steam_appid(clean)
            if appid:
                cdn_url = f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_600x900_2x.jpg"
                try:
                    resp = _httpx.head(cdn_url, follow_redirects=True, timeout=10.0)
                    if resp.status_code == 200:
                        return cdn_url
                except Exception:
                    pass
            # Fall back to SteamGridDB community grids
            search_terms = self._search_variations(clean)
            game_id = None
            for term in search_terms:
                results = sgdb.search_game(term)
                if results:
                    game_id = results[0]["id"]
                    break
            if game_id is None:
                return None
            resp = sgdb._http.get(
                f"/grids/game/{game_id}",
                params={"dimensions": "600x900", "types": "static"},
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if data:
                best = max(data, key=lambda x: x.get("score", 0))
                return best["url"]
        except Exception:
            pass
        return None

    def _populate_hero_and_discover(self, results) -> None:
        self._spinner.stop()
        hero_results = results[:HERO_COUNT]
        discover_results = results[HERO_COUNT:HERO_COUNT + DISCOVER_COUNT]

        for r in hero_results:
            slide = self._make_hero_slide(r)
            self._carousel.append(slide)

        for r in discover_results:
            card = GameCard(
                title=r.title,
                size_info=r.size_info,
                thumbnail_url=r.thumbnail,
                on_action=lambda _title, card=None, r=r: self._on_game_clicked(r, card),
            )
            self._discover_row.append(card)

    def _populate_trending(self, results) -> None:
        for r in results:
            row = TrendingRow(
                title=r.title,
                size_info=r.size_info,
                thumbnail_url=r.thumbnail,
                on_click=lambda r=r: self._on_game_clicked(r),
            )
            self._trending_list.append(row)

    def _populate_upcoming(self, items) -> None:
        if not items:
            return
        self._upcoming_section.set_visible(True)
        for name, cover_url in items:
            card = GameCard(
                title=name,
                thumbnail_url=cover_url,
            )
            self._upcoming_row.append(card)

    def _make_hero_slide(self, game_result):
        """Create a hero carousel slide with image overlay."""
        overlay = Gtk.Overlay()
        overlay.set_size_request(-1, 380)
        overlay.set_overflow(Gtk.Overflow.HIDDEN)
        overlay.add_css_class("hero-slide")

        picture = Gtk.Picture()
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.set_hexpand(True)
        picture.set_vexpand(True)
        overlay.set_child(picture)

        # Load thumbnail immediately, then try to replace with a proper hero image
        if game_result.thumbnail:
            self._load_image_async(game_result.thumbnail, picture)
        threading.Thread(
            target=self._fetch_hero_image,
            args=(game_result.title, picture),
            daemon=True,
        ).start()

        # Title overlay at bottom
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title_box.set_valign(Gtk.Align.END)
        title_box.set_halign(Gtk.Align.FILL)
        title_box.add_css_class("hero-slide-overlay")
        overlay.add_overlay(title_box)

        title_label = Gtk.Label(label=game_result.title)
        title_label.set_halign(Gtk.Align.START)
        title_label.set_ellipsize(Pango.EllipsizeMode.END)
        title_label.add_css_class("title-1")
        title_box.append(title_label)

        if game_result.size_info:
            sub = Gtk.Label(label=game_result.size_info)
            sub.set_halign(Gtk.Align.START)
            sub.add_css_class("dim-label")
            title_box.append(sub)

        view_btn = Gtk.Button(label="View Game")
        view_btn.add_css_class("hero-action-btn")
        view_btn.set_halign(Gtk.Align.START)
        view_btn.connect("clicked", lambda _b, r=game_result: self._on_game_clicked(r))
        title_box.append(view_btn)

        # Make the whole slide clickable
        click = Gtk.GestureClick()
        click.connect("released", lambda _g, _n, _x, _y, r=game_result: self._on_game_clicked(r))
        overlay.add_controller(click)
        overlay.set_cursor_from_name("pointer")

        return overlay

    @staticmethod
    def _clean_title(title: str) -> str:
        """Strip FitGirl version/build/DLC suffixes for cleaner searches."""
        clean = re.sub(r"\s*[,–—-]\s*(?:v[\d.].*|Build\s.*)$", "", title).strip()
        clean = re.sub(r"\s*\(.*?v[\d.].*?\)\s*$", "", clean).strip()
        clean = re.sub(r"\s*[–—-]\s*(?:Deluxe|Ultimate|Gold|GOTY|Complete).*$", "", clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r"\s*\+\s*(?:\d+\s+)?DLCs?\b.*$", "", clean, flags=re.IGNORECASE).strip()
        return clean or title

    @staticmethod
    def _search_variations(title: str) -> list[str]:
        """Generate progressively simpler search terms from a title."""
        variations = [title]
        # Strip subtitle after colon or dash
        base = re.split(r"\s*[:\u2013\u2014-]\s+", title, maxsplit=1)[0].strip()
        if base and base != title:
            variations.append(base)
        # Strip trailing roman numerals or numbers
        shorter = re.sub(r"\s+(?:[IVXLC]+|\d+)\s*$", "", base).strip()
        if shorter and shorter not in variations:
            variations.append(shorter)
        return variations

    def _fetch_hero_image(self, title, picture):
        """Fetch a hero image for the carousel slide.

        Priority: Steam CDN hero (no API key needed) → SGDB community hero → give up.
        """
        try:
            from sevenseas.core.steamgriddb import SteamGridDBClient
            import httpx as _httpx

            clean = self._clean_title(title)
            image_url = None

            # 1. Try official Steam CDN hero (uses Steam Store search, no API key needed)
            steam_appid = SteamGridDBClient.get_steam_appid(clean)
            if steam_appid:
                cdn_url = f"https://cdn.akamai.steamstatic.com/steam/apps/{steam_appid}/library_hero.jpg"
                try:
                    resp = _httpx.head(cdn_url, follow_redirects=True, timeout=10.0)
                    if resp.status_code == 200:
                        image_url = cdn_url
                except Exception:
                    pass

            # 2. Fall back to SteamGridDB community heroes (requires API key)
            if not image_url and self._sgdb_api_key:
                sgdb = SteamGridDBClient(api_key=self._sgdb_api_key)
                search_terms = self._search_variations(clean)
                game_id = None
                for term in search_terms:
                    results = sgdb.search_game(term)
                    if results:
                        game_id = results[0]["id"]
                        break
                if game_id is not None:
                    try:
                        resp = sgdb._http.get(
                            f"/heroes/game/{game_id}",
                            params={"types": "static", "dimensions": "1920x620,3840x1240"},
                        )
                        resp.raise_for_status()
                        data = resp.json().get("data", [])
                        if not data:
                            resp = sgdb._http.get(
                                f"/heroes/game/{game_id}",
                                params={"types": "static"},
                            )
                            resp.raise_for_status()
                            data = resp.json().get("data", [])
                        if data:
                            best = max(data, key=lambda x: x.get("score", 0))
                            image_url = best["url"]
                    except Exception:
                        pass

            if not image_url:
                return

            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path = cache_path_for_url(image_url, prefix="hero_")
            if not cache_path.exists():
                resp = _httpx.get(image_url, follow_redirects=True, timeout=30.0)
                resp.raise_for_status()
                atomic_write_cache(cache_path, resp.content)
            GLib.idle_add(picture.set_filename, str(cache_path))
        except Exception:
            pass

    @staticmethod
    def _load_image_async(url, picture):
        """Download image in background and set on Gtk.Picture."""
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = cache_path_for_url(url)

        if cache_path.exists():
            picture.set_filename(str(cache_path))
            return

        def download():
            try:
                import httpx
                resp = httpx.get(url, follow_redirects=True, timeout=15.0)
                resp.raise_for_status()
                atomic_write_cache(cache_path, resp.content)
                GLib.idle_add(picture.set_filename, str(cache_path))
            except Exception:
                pass

        threading.Thread(target=download, daemon=True).start()

    def _on_game_clicked(self, game_result, source_card=None) -> None:
        if self._on_card_click:
            self._on_card_click(game_result, source_card)

    # --- Carousel navigation ---

    def _on_carousel_prev(self, button) -> None:
        pos = self._carousel.get_position()
        if pos > 0:
            page = self._carousel.get_nth_page(int(pos - 1))
            self._carousel.scroll_to(page, True)

    def _on_carousel_next(self, button) -> None:
        pos = self._carousel.get_position()
        n = self._carousel.get_n_pages()
        if pos < n - 1:
            page = self._carousel.get_nth_page(int(pos + 1))
            self._carousel.scroll_to(page, True)

    # --- Discover row scrolling ---

    def _on_discover_scroll_left(self, button) -> None:
        adj = self._discover_scroll.get_hadjustment()
        adj.set_value(max(adj.get_value() - 400, adj.get_lower()))

    def _on_discover_scroll_right(self, button) -> None:
        adj = self._discover_scroll.get_hadjustment()
        adj.set_value(min(adj.get_value() + 400, adj.get_upper() - adj.get_page_size()))

    # --- Upcoming row scrolling ---

    def _on_upcoming_scroll_left(self, button) -> None:
        adj = self._upcoming_scroll.get_hadjustment()
        adj.set_value(max(adj.get_value() - 400, adj.get_lower()))

    def _on_upcoming_scroll_right(self, button) -> None:
        adj = self._upcoming_scroll.get_hadjustment()
        adj.set_value(min(adj.get_value() + 400, adj.get_upper() - adj.get_page_size()))
