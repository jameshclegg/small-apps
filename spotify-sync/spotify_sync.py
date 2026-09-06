#!/usr/bin/env python3
"""Compare Spotify favorites with an owned iTunes library."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import plistlib
import re
import sys
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import unquote, urlparse


AUDIO_HISTORY_PATTERNS = (
    re.compile(r"Streaming_History_Audio_.*\.json$", re.IGNORECASE),
    re.compile(r"StreamingHistory.*\.json$", re.IGNORECASE),
)
ANNUAL_PLAYLIST_PATTERN = re.compile(r"(?:your\s+)?top\s+songs\s+(\d{4})", re.IGNORECASE)
PLAYLIST_ID_PATTERN = re.compile(r"(?:playlist[/:])([A-Za-z0-9]+)")
QUALIFIER_PATTERN = re.compile(
    r"\s*[\[(](?:\d{4}\s+)?(?:re-?master(?:ed)?|mono|stereo|explicit)(?:[^)\]]*)[\])]\s*",
    re.IGNORECASE,
)
FEATURE_PATTERN = re.compile(
    r"\s*[\[(](?:feat\.?|featuring|with)\s+[^)\]]+[\])]\s*",
    re.IGNORECASE,
)
TRAILING_VERSION_PATTERN = re.compile(
    r"\s+-\s+(?:(?:\d{4}\s+)?re-?master(?:ed)?(?:\s+\d{4})?|"
    r"\d{4}\s+mix|single version|album version|radio edit|mono|stereo)\s*$",
    re.IGNORECASE,
)
ALBUM_EDITION_PATTERN = re.compile(
    r"\s*[\[(][^)\]]*(?:re-?master(?:ed)?|deluxe|legacy|anniversary|expanded|"
    r"special edition|mono|stereo)[^)\]]*[\])]\s*",
    re.IGNORECASE,
)
KEYRING_SERVICE = "spotify-sync"


def canonical_text(value: str | None) -> str:
    text = (value or "").casefold().replace("&", " and ")
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def canonical_title(value: str | None) -> str:
    text = FEATURE_PATTERN.sub(" ", value or "")
    text = QUALIFIER_PATTERN.sub(" ", text)
    text = TRAILING_VERSION_PATTERN.sub(" ", text)
    return canonical_text(text)


def canonical_artist(value: str | None) -> str:
    text = canonical_text(value)
    return text[4:] if text.startswith("the ") else text


def canonical_album(value: str | None) -> str:
    return canonical_text(ALBUM_EDITION_PATTERN.sub(" ", value or ""))


def artist_names(value: str | None) -> set[str]:
    if not value:
        return set()
    names = re.split(r"\s+(?:feat\.?|featuring|with)\s+|[,;/]|\s+&\s+", value, flags=re.I)
    result = {canonical_artist(name) for name in names if canonical_artist(name)}
    result.add(canonical_artist(value))
    return result


def subtract_years(value: datetime, years: int) -> datetime:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def parse_timestamp(value: str) -> datetime:
    value = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class FavoriteTrack:
    title: str
    artist: str
    album: str
    spotify_uri: str = ""
    play_count: int = 0
    milliseconds: int = 0
    spotify_score: int = 0
    sources: set[str] | None = None

    def __post_init__(self) -> None:
        if self.sources is None:
            self.sources = set()

    @property
    def key(self) -> tuple[str, str]:
        return canonical_title(self.title), canonical_artist(self.artist)


@dataclass
class FavoriteAlbum:
    title: str
    artist: str
    play_count: int = 0
    milliseconds: int = 0
    spotify_score: int = 0
    favorite_tracks: int = 0

    @property
    def key(self) -> tuple[str, str]:
        return canonical_album(self.title), canonical_artist(self.artist)


@dataclass
class LibraryIndex:
    tracks: set[tuple[str, str]]
    albums: set[tuple[str, str]]
    track_locations: dict[tuple[str, str], set[Path]]
    track_count: int
    source: Path

    def owns_track(self, favorite: FavoriteTrack) -> bool:
        title = canonical_title(favorite.title)
        return any((title, artist) in self.tracks for artist in artist_names(favorite.artist))

    def owns_album(self, favorite: FavoriteAlbum) -> bool:
        album = canonical_album(favorite.title)
        return any((album, artist) in self.albums for artist in artist_names(favorite.artist))

    def locations_for(self, favorite: FavoriteTrack) -> set[Path]:
        title = canonical_title(favorite.title)
        locations: set[Path] = set()
        for artist in artist_names(favorite.artist):
            locations.update(self.track_locations.get((title, artist), set()))
        return locations


def location_path(value: str | None) -> Path | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme != "file":
        return None
    path = unquote(parsed.path)
    if re.match(r"^/[A-Za-z]:/", path):
        path = path[1:]
    return Path(path.replace("/", os.sep))


def history_json_sources(path: Path) -> Iterator[tuple[str, bytes]]:
    if path.is_dir():
        for candidate in sorted(path.rglob("*.json")):
            if any(pattern.search(candidate.name) for pattern in AUDIO_HISTORY_PATTERNS):
                yield str(candidate), candidate.read_bytes()
        return

    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if any(pattern.search(Path(name).name) for pattern in AUDIO_HISTORY_PATTERNS):
                    yield f"{path}!{name}", archive.read(name)
        return

    yield str(path), path.read_bytes()


def load_history(paths: Iterable[Path], cutoff: datetime) -> dict[tuple[str, str], FavoriteTrack]:
    tracks: dict[tuple[str, str], FavoriteTrack] = {}
    found_files = 0
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Spotify history path does not exist: {path}")
        for source, content in history_json_sources(path):
            found_files += 1
            try:
                events = json.loads(content)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {source}: {exc}") from exc
            if not isinstance(events, list):
                raise ValueError(f"Expected a JSON array in {source}")
            for event in events:
                timestamp = event.get("ts") or event.get("endTime")
                title = event.get("master_metadata_track_name") or event.get("trackName")
                artist = event.get("master_metadata_album_artist_name") or event.get("artistName")
                if not timestamp or not title or not artist:
                    continue
                if parse_timestamp(timestamp) < cutoff:
                    continue
                milliseconds = int(event.get("ms_played", event.get("msPlayed", 0)) or 0)
                if milliseconds < 30_000:
                    continue
                album = event.get("master_metadata_album_album_name") or event.get("albumName") or ""
                uri = event.get("spotify_track_uri") or ""
                favorite = FavoriteTrack(title, artist, album, uri)
                existing = tracks.get(favorite.key)
                if existing is None:
                    existing = favorite
                    tracks[favorite.key] = existing
                existing.play_count += 1
                existing.milliseconds += milliseconds
                existing.sources.add("streaming history")
                if not existing.album and album:
                    existing.album = album
                if not existing.spotify_uri and uri:
                    existing.spotify_uri = uri
    if paths and found_files == 0:
        raise ValueError("No Spotify audio history JSON files were found")
    return tracks


def spotify_track(item: dict[str, Any]) -> FavoriteTrack | None:
    if not isinstance(item, dict) or not item.get("name") or not item.get("artists"):
        return None
    artists = ", ".join(artist["name"] for artist in item["artists"])
    album = (item.get("album") or {}).get("name", "")
    return FavoriteTrack(item["name"], artists, album, item.get("uri", ""))


def merge_spotify_signal(
    tracks: dict[tuple[str, str], FavoriteTrack],
    item: dict[str, Any],
    source: str,
    score: int,
) -> None:
    favorite = spotify_track(item)
    if favorite is None:
        return
    existing = tracks.get(favorite.key)
    if existing is None:
        existing = favorite
        tracks[favorite.key] = existing
    existing.spotify_score += max(score, 1)
    existing.sources.add(source)
    if not existing.album:
        existing.album = favorite.album
    if not existing.spotify_uri:
        existing.spotify_uri = favorite.spotify_uri


def playlist_id(value: str) -> str:
    match = PLAYLIST_ID_PATTERN.search(value)
    return match.group(1) if match else value.strip()


def credential_store() -> Any | None:
    try:
        import keyring
    except ImportError:
        return None
    return keyring


def configure_credentials() -> None:
    keyring = credential_store()
    if keyring is None:
        raise RuntimeError(
            "Secure credential storage requires keyring. "
            "Run: py -m pip install -r requirements.txt"
        )
    client_id = input("Spotify Client ID: ").strip()
    client_secret = getpass.getpass("Spotify Client Secret (hidden): ").strip()
    if not client_id or not client_secret:
        raise RuntimeError("Spotify Client ID and Client Secret are required")
    keyring.set_password(KEYRING_SERVICE, "client-id", client_id)
    keyring.set_password(KEYRING_SERVICE, "client-secret", client_secret)


def paged_items(spotify: Any, first_page: dict[str, Any]) -> Iterator[dict[str, Any]]:
    page = first_page
    while page:
        yield from page.get("items", [])
        page = spotify.next(page) if page.get("next") else None


def add_spotify_api_favorites(
    tracks: dict[tuple[str, str], FavoriteTrack],
    cutoff_year: int,
    current_year: int,
    client_id: str | None = None,
    requested_playlists: Iterable[str] = (),
) -> None:
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
    except ImportError as exc:
        raise RuntimeError(
            "Spotify API support requires Spotipy. Run: py -m pip install -r requirements.txt"
        ) from exc

    keyring = credential_store()
    stored_client_id = keyring.get_password(KEYRING_SERVICE, "client-id") if keyring else None
    stored_client_secret = (
        keyring.get_password(KEYRING_SERVICE, "client-secret") if keyring else None
    )
    client_id = client_id or os.environ.get("SPOTIPY_CLIENT_ID") or stored_client_id
    if not client_id:
        client_id = input("Spotify Client ID: ").strip()
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET") or stored_client_secret
    if not client_secret:
        client_secret = getpass.getpass("Spotify Client Secret (hidden): ").strip()
    redirect_uri = os.environ.get(
        "SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback"
    )
    if not client_id or not client_secret:
        raise RuntimeError("Spotify Client ID and Client Secret are required")

    spotify = spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="user-top-read playlist-read-private playlist-read-collaborative",
            open_browser=True,
        )
    )
    current_user_id = spotify.current_user()["id"]
    weights = {"short_term": 1, "medium_term": 2, "long_term": 3}
    for time_range, weight in weights.items():
        items = spotify.current_user_top_tracks(limit=50, time_range=time_range)["items"]
        for rank, item in enumerate(items, 1):
            merge_spotify_signal(
                tracks, item, f"Spotify {time_range.replace('_', ' ')} top tracks", weight * (51 - rank)
            )

    playlists = paged_items(spotify, spotify.current_user_playlists(limit=50))
    for playlist in playlists:
        match = ANNUAL_PLAYLIST_PATTERN.search(playlist.get("name", ""))
        if not match:
            continue
        year = int(match.group(1))
        if not cutoff_year <= year <= current_year:
            continue
        owner_id = (playlist.get("owner") or {}).get("id")
        if owner_id != current_user_id and not playlist.get("collaborative"):
            print(
                f"warning: cannot read '{playlist['name']}' under Spotify's 2026 API rules; "
                "copy its tracks into a playlist you own to include it",
                file=sys.stderr,
            )
            continue
        entries = paged_items(spotify, spotify.playlist_items(playlist["id"], limit=50))
        for rank, entry in enumerate(entries, 1):
            merge_spotify_signal(
                tracks,
                entry.get("item") or entry.get("track") or {},
                f"Your Top Songs {year}",
                max(101 - rank, 1) * 2,
            )

    for requested in requested_playlists:
        requested_id = playlist_id(requested)
        playlist = spotify.playlist(requested_id, fields="id,name")
        entries = paged_items(spotify, spotify.playlist_items(requested_id, limit=50))
        for entry in entries:
            merge_spotify_signal(
                tracks,
                entry.get("item") or entry.get("track") or {},
                f"playlist {playlist['name']}",
                1,
            )


def newest_itunes_xml(root: Path) -> Path:
    if root.is_file():
        return root
    if not root.exists():
        raise FileNotFoundError(f"iTunes path does not exist: {root}")
    candidates = list(root.rglob("*.xml"))
    if not candidates:
        raise FileNotFoundError(f"No iTunes XML library found below: {root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def load_itunes_library(root: Path) -> LibraryIndex:
    source = newest_itunes_xml(root)
    try:
        with source.open("rb") as stream:
            library = plistlib.load(stream)
    except (OSError, plistlib.InvalidFileException) as exc:
        raise ValueError(f"Could not read iTunes library {source}: {exc}") from exc

    tracks: set[tuple[str, str]] = set()
    albums: set[tuple[str, str]] = set()
    track_locations: defaultdict[tuple[str, str], set[Path]] = defaultdict(set)
    owned_count = 0
    for item in library.get("Tracks", {}).values():
        title = item.get("Name")
        location = item.get("Location")
        track_type = item.get("Track Type")
        if not title or not (location or track_type == "File"):
            continue
        artists = artist_names(item.get("Artist")) | artist_names(item.get("Album Artist"))
        if not artists:
            continue
        owned_count += 1
        normalized_title = canonical_title(title)
        tracks.update((normalized_title, artist) for artist in artists)
        path = location_path(location)
        if path:
            for artist in artists:
                track_locations[(normalized_title, artist)].add(path)
        if item.get("Album"):
            normalized_album = canonical_album(item["Album"])
            albums.update((normalized_album, artist) for artist in artists)
    return LibraryIndex(tracks, albums, dict(track_locations), owned_count, source)


def album_favorites(tracks: Iterable[FavoriteTrack]) -> list[FavoriteAlbum]:
    albums: dict[tuple[str, str], FavoriteAlbum] = {}
    album_track_keys: defaultdict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for track in tracks:
        if not track.album:
            continue
        favorite = FavoriteAlbum(track.album, track.artist)
        existing = albums.get(favorite.key)
        if existing is None:
            existing = favorite
            albums[favorite.key] = existing
        existing.play_count += track.play_count
        existing.milliseconds += track.milliseconds
        existing.spotify_score += track.spotify_score
        album_track_keys[favorite.key].add(track.key)
    for key, album in albums.items():
        album.favorite_tracks = len(album_track_keys[key])
    return sorted(
        albums.values(),
        key=lambda album: (album.milliseconds, album.spotify_score, album.play_count),
        reverse=True,
    )


def format_duration(milliseconds: int) -> str:
    minutes = round(milliseconds / 60_000)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def markdown_table(headers: list[str], rows: Iterable[list[str]]) -> list[str]:
    escaped_rows = [[str(value).replace("|", r"\|").replace("\n", " ") for value in row] for row in rows]
    return [
        f"| {' | '.join(headers)} |",
        f"| {' | '.join('---' for _ in headers)} |",
        *(f"| {' | '.join(row)} |" for row in escaped_rows),
    ]


def write_report(
    output: Path,
    tracks: list[FavoriteTrack],
    library: LibraryIndex,
    years: int,
    track_limit: int,
    album_limit: int,
) -> None:
    albums = album_favorites(tracks)
    missing_tracks = [track for track in tracks if not library.owns_track(track)]
    missing_albums = [
        album for album in albums if album.favorite_tracks >= 2 and not library.owns_album(album)
    ]
    generated = datetime.now().astimezone()

    lines = [
        "# Spotify favorites and iTunes ownership",
        "",
        f"Generated {generated:%Y-%m-%d %H:%M %Z}. Rankings cover the last {years} years where "
        "streaming history is available and are supplemented by Spotify top-track signals.",
        "",
        "## Summary",
        "",
        f"- Favorite tracks considered: **{len(tracks)}**",
        f"- Favorite albums considered: **{len(albums)}**",
        f"- Tracks missing from iTunes: **{len(missing_tracks)}**",
        f"- Favorite albums missing from iTunes: **{len(missing_albums)}**",
        f"- Owned iTunes tracks indexed: **{library.track_count}**",
        f"- iTunes catalog: `{library.source}`",
        "",
        "## Top listened tracks",
        "",
    ]
    lines.extend(
        markdown_table(
            ["#", "Track", "Artist", "Album", "Plays", "Listening time", "Owned"],
            (
                [
                    str(rank),
                    track.title,
                    track.artist,
                    track.album or "-",
                    str(track.play_count) if track.play_count else "-",
                    format_duration(track.milliseconds) if track.milliseconds else "-",
                    "Yes" if library.owns_track(track) else "**No**",
                ]
                for rank, track in enumerate(tracks[:track_limit], 1)
            ),
        )
    )
    lines.extend(["", "## Recommended songs to buy", ""])
    if missing_tracks:
        lines.extend(
            markdown_table(
                ["#", "Track", "Artist", "Album", "Plays", "Listening time", "Why it ranks"],
                (
                    [
                        str(rank),
                        track.title,
                        track.artist,
                        track.album or "-",
                        str(track.play_count) if track.play_count else "-",
                        format_duration(track.milliseconds) if track.milliseconds else "-",
                        ", ".join(sorted(track.sources or [])),
                    ]
                    for rank, track in enumerate(missing_tracks[:track_limit], 1)
                ),
            )
        )
    else:
        lines.append("No missing favorite songs were found.")

    lines.extend(["", "## Recommended albums to buy", ""])
    if missing_albums:
        lines.extend(
            markdown_table(
                ["#", "Album", "Artist", "Favorite tracks", "Plays", "Listening time"],
                (
                    [
                        str(rank),
                        album.title,
                        album.artist,
                        str(album.favorite_tracks),
                        str(album.play_count) if album.play_count else "-",
                        format_duration(album.milliseconds) if album.milliseconds else "-",
                    ]
                    for rank, album in enumerate(missing_albums[:album_limit], 1)
                ),
            )
        )
    else:
        lines.append("No missing favorite albums were found.")

    lines.extend(
        [
            "",
            "## Matching notes",
            "",
            "Ownership is based on normalized track/album titles and artists in the iTunes XML. "
            "Remaster, mono, stereo, deluxe, legacy, and anniversary labels are ignored. Album "
            "recommendations require at least two favorite tracks. Review compilations and changed "
            "artist credits before purchasing.",
            "",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    default_itunes = Path.home() / "OneDrive" / "Music" / "iTunes"
    result = argparse.ArgumentParser(
        description="Rank Spotify favorites and identify songs/albums missing from iTunes."
    )
    result.add_argument(
        "--history",
        action="append",
        type=Path,
        default=[],
        help="Spotify export directory, ZIP, or history JSON (repeatable).",
    )
    result.add_argument("--no-api", action="store_true", help="Do not query the Spotify API.")
    result.add_argument(
        "--client-id",
        help="Spotify Client ID. If omitted, use SPOTIPY_CLIENT_ID or prompt securely.",
    )
    result.add_argument(
        "--configure",
        action="store_true",
        help="Store Spotify credentials securely in Windows Credential Manager, then exit.",
    )
    result.add_argument(
        "--playlist",
        action="append",
        default=[],
        help="Include every track from this Spotify playlist ID or URL (repeatable).",
    )
    result.add_argument("--itunes", type=Path, default=default_itunes, help="iTunes folder or XML file.")
    result.add_argument("--output", type=Path, default=Path("spotify-favorites.md"))
    result.add_argument("--years", type=int, default=3)
    result.add_argument("--top-tracks", type=int, default=100)
    result.add_argument("--top-albums", type=int, default=50)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.configure:
        try:
            configure_credentials()
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print("Stored Spotify credentials securely in Windows Credential Manager.")
        return 0
    if args.years < 1 or args.top_tracks < 1 or args.top_albums < 1:
        print("years and result limits must be positive integers", file=sys.stderr)
        return 2
    if not args.history and args.no_api:
        print("Provide --history or enable Spotify API access", file=sys.stderr)
        return 2

    try:
        now = datetime.now(timezone.utc)
        cutoff = subtract_years(now, args.years)
        tracks = load_history(args.history, cutoff)
        if not args.no_api:
            add_spotify_api_favorites(
                tracks,
                cutoff.year,
                now.year,
                args.client_id,
                args.playlist,
            )
        if not tracks:
            raise ValueError("No Spotify tracks were found for the selected period")
        ranked_tracks = sorted(
            tracks.values(),
            key=lambda track: (track.milliseconds, track.spotify_score, track.play_count),
            reverse=True,
        )
        library = load_itunes_library(args.itunes.expanduser())
        write_report(
            args.output,
            ranked_tracks,
            library,
            args.years,
            args.top_tracks,
            args.top_albums,
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {args.output.resolve()}")
    print(f"Compared {len(ranked_tracks)} Spotify favorites with {library.track_count} iTunes tracks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
