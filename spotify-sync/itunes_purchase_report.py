#!/usr/bin/env python3
"""Create UK iTunes purchase links and an owned-files playlist."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

import keyring
import spotipy
from spotipy.oauth2 import SpotifyOAuth

from spotify_sync import (
    KEYRING_SERVICE,
    FavoriteTrack,
    artist_names,
    canonical_album,
    canonical_text,
    canonical_title,
    load_itunes_library,
    paged_items,
    playlist_id,
    spotify_track,
)


SEARCH_URL = "https://itunes.apple.com/search"


@dataclass
class StoreMatch:
    status: str
    title: str = ""
    artist: str = ""
    album: str = ""
    price: float | None = None
    currency: str = ""
    url: str = ""


def spotify_client() -> spotipy.Spotify:
    client_id = keyring.get_password(KEYRING_SERVICE, "client-id")
    client_secret = keyring.get_password(KEYRING_SERVICE, "client-secret")
    if not client_id or not client_secret:
        raise RuntimeError("Run `py spotify_sync.py --configure` first")
    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri="http://127.0.0.1:8888/callback",
            scope="playlist-read-private playlist-read-collaborative",
            open_browser=True,
        )
    )


def playlist_tracks(spotify: spotipy.Spotify, value: str) -> tuple[str, list[FavoriteTrack]]:
    identifier = playlist_id(value)
    playlist = spotify.playlist(identifier, fields="name")
    tracks: list[FavoriteTrack] = []
    seen: set[tuple[str, str]] = set()
    first_page = spotify.playlist_items(identifier, limit=50)
    for entry in paged_items(spotify, first_page):
        track = spotify_track(entry.get("item") or entry.get("track") or {})
        if track and track.key not in seen:
            seen.add(track.key)
            tracks.append(track)
    return playlist["name"], tracks


def load_cache(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read search cache {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Invalid search cache: {path}")
    return value


def save_cache(path: Path, cache: dict[str, list[dict[str, Any]]]) -> None:
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def search_store(track: FavoriteTrack) -> list[dict[str, Any]]:
    params = urlencode(
        {
            "term": f"{track.title} {track.artist}",
            "country": "GB",
            "media": "music",
            "entity": "song",
            "limit": 10,
            "explicit": "Yes",
        }
    )
    request = Request(f"{SEARCH_URL}?{params}", headers={"User-Agent": "spotify-sync/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"iTunes search failed for {track.title} — {track.artist}: {exc}") from exc
    return payload.get("results", [])


def score_result(track: FavoriteTrack, result: dict[str, Any]) -> int:
    wanted_title = canonical_title(track.title)
    result_title = canonical_title(result.get("trackName"))
    wanted_artists = artist_names(track.artist)
    result_artists = artist_names(result.get("artistName"))
    if not wanted_title or wanted_title != result_title or not wanted_artists & result_artists:
        return -1
    score = 100
    if canonical_album(track.album) == canonical_album(result.get("collectionName")):
        score += 30
    if canonical_text(track.artist) == canonical_text(result.get("artistName")):
        score += 10
    if result.get("trackPrice", -1) >= 0:
        score += 5
    return score


def choose_match(track: FavoriteTrack, results: list[dict[str, Any]]) -> StoreMatch:
    ranked = sorted(
        ((score_result(track, result), result) for result in results),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not ranked or ranked[0][0] < 100:
        return StoreMatch("No confident match")
    score, result = ranked[0]
    price = result.get("trackPrice")
    purchasable = isinstance(price, (int, float)) and price >= 0
    status = "Matched" if score >= 130 else "Check edition"
    if not purchasable:
        status = "Album only / unavailable"
        price = None
    return StoreMatch(
        status=status,
        title=result.get("trackName", ""),
        artist=result.get("artistName", ""),
        album=result.get("collectionName", ""),
        price=price,
        currency=result.get("currency", ""),
        url=result.get("trackViewUrl", ""),
    )


def search_link(track: FavoriteTrack) -> str:
    query = quote_plus(f"{track.title} {track.artist}")
    return f"https://music.apple.com/gb/search?term={query}"


def escape(value: str) -> str:
    return value.replace("|", r"\|").replace("\n", " ")


def write_m3u(path: Path, tracks: list[FavoriteTrack], library: Any) -> int:
    locations: list[Path] = []
    seen: set[str] = set()
    for track in tracks:
        for location in sorted(library.locations_for(track)):
            location = resolve_library_location(location, library.source)
            if location is None:
                continue
            normalized = str(location).casefold()
            if normalized not in seen:
                seen.add(normalized)
                locations.append(location)
                break
    lines = ["#EXTM3U", *(str(location) for location in locations)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return len(locations)


def resolve_library_location(location: Path, library_source: Path) -> Path | None:
    if location.exists():
        return location
    parts = list(location.parts)
    media_index = next(
        (index for index, part in enumerate(parts) if part.casefold() == "itunes media"),
        None,
    )
    itunes_root = next(
        (
            parent
            for parent in (library_source.parent, *library_source.parents)
            if parent.name.casefold() == "itunes"
        ),
        None,
    )
    if media_index is None or itunes_root is None:
        return None
    candidate = itunes_root.joinpath(*parts[media_index:])
    return candidate if candidate.exists() else None


def write_report(
    path: Path,
    playlist_name: str,
    tracks: list[FavoriteTrack],
    library: Any,
    matches: dict[tuple[str, str], StoreMatch],
    owned_playlist: Path,
    owned_count: int,
) -> None:
    missing = [track for track in tracks if not library.owns_track(track)]
    total = sum(
        match.price or 0
        for match in matches.values()
        if match.status in {"Matched", "Check edition"}
    )
    priced = sum(match.price is not None for match in matches.values())
    lines = [
        f"# {playlist_name}: iTunes purchase guide",
        "",
        f"- Spotify tracks: **{len(tracks)}**",
        f"- Already owned in iTunes: **{len(tracks) - len(missing)}**",
        f"- Missing from iTunes: **{len(missing)}**",
        f"- UK Store matches with individual prices: **{priced}**",
        f"- Estimated individual-track total: **£{total:.2f}**",
        f"- Owned-files playlist: `{owned_playlist}` ({owned_count} tracks)",
        "",
        "> Check every edition before purchasing. This report never buys anything.",
        "",
        "| # | Spotify track | Artist | Album | Match | Price | UK iTunes Store |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, track in enumerate(missing, 1):
        match = matches.get(track.key, StoreMatch("Not searched"))
        price = f"£{match.price:.2f}" if match.price is not None else "-"
        link = f"[Open match]({match.url})" if match.url else f"[Search]({search_link(track)})"
        matched_description = match.status
        if match.title:
            matched_description += f": {match.title} — {match.artist} ({match.album})"
        lines.append(
            "| "
            + " | ".join(
                escape(value)
                for value in (
                    str(index),
                    track.title,
                    track.artist,
                    track.album or "-",
                    matched_description,
                    price,
                    link,
                )
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--playlist", required=True, help="Spotify playlist ID or URL.")
    result.add_argument(
        "--itunes",
        type=Path,
        default=Path.home() / "OneDrive" / "Music" / "iTunes",
    )
    result.add_argument("--output", type=Path, default=Path("itunes-purchase-guide.md"))
    result.add_argument("--m3u", type=Path, default=Path("JC-Erykah-owned.m3u8"))
    result.add_argument("--cache", type=Path, default=Path(".itunes-search-cache.json"))
    result.add_argument("--delay", type=float, default=3.1)
    result.add_argument("--limit", type=int, help="Search only the first N missing tracks.")
    return result


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = parser().parse_args()
    try:
        spotify = spotify_client()
        name, tracks = playlist_tracks(spotify, args.playlist)
        library = load_itunes_library(args.itunes)
        missing = [track for track in tracks if not library.owns_track(track)]
        if args.limit is not None:
            missing = missing[: args.limit]
        cache = load_cache(args.cache)
        matches: dict[tuple[str, str], StoreMatch] = {}
        for index, track in enumerate(missing, 1):
            key = f"{canonical_title(track.title)}|{canonical_text(track.artist)}"
            if key not in cache:
                print(f"[{index}/{len(missing)}] Searching: {track.title} — {track.artist}", flush=True)
                cache[key] = search_store(track)
                save_cache(args.cache, cache)
                if index < len(missing):
                    time.sleep(max(args.delay, 0))
            matches[track.key] = choose_match(track, cache[key])
        owned_count = write_m3u(args.m3u, tracks, library)
        write_report(args.output, name, tracks, library, matches, args.m3u, owned_count)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}")
        return 1
    print(f"Wrote {args.output} and {args.m3u}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
