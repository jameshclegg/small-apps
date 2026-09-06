#!/usr/bin/env python3
"""Generate a self-contained interactive dashboard from Spotify history."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from spotify_sync import (
    KEYRING_SERVICE,
    FavoriteAlbum,
    FavoriteTrack,
    artist_names,
    canonical_album,
    canonical_text,
    canonical_title,
    history_json_sources,
    load_itunes_library,
    paged_items,
    parse_timestamp,
    playlist_id,
)


def load_events(paths: Iterable[Path]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Spotify history path does not exist: {path}")
        for source, content in history_json_sources(path):
            try:
                rows = json.loads(content)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {source}: {exc}") from exc
            for row in rows:
                title = row.get("master_metadata_track_name") or row.get("trackName")
                artist = row.get("master_metadata_album_artist_name") or row.get("artistName")
                timestamp = row.get("ts") or row.get("endTime")
                if not title or not artist or not timestamp:
                    continue
                events.append(
                    {
                        "dt": parse_timestamp(timestamp),
                        "title": title,
                        "artist": artist,
                        "album": row.get("master_metadata_album_album_name")
                        or row.get("albumName")
                        or "",
                        "uri": row.get("spotify_track_uri") or "",
                        "ms": int(row.get("ms_played", row.get("msPlayed", 0)) or 0),
                        "skipped": bool(row.get("skipped")),
                        "shuffle": bool(row.get("shuffle")),
                        "offline": bool(row.get("offline")),
                        "incognito": bool(row.get("incognito_mode")),
                        "platform": row.get("platform") or "Unknown",
                        "reason_start": row.get("reason_start") or "Unknown",
                        "reason_end": row.get("reason_end") or "Unknown",
                    }
                )
    events.sort(key=lambda event: event["dt"])
    return events


def track_key(event: dict[str, Any]) -> tuple[str, str]:
    return canonical_title(event["title"]), canonical_text(event["artist"])


def album_key(event: dict[str, Any]) -> tuple[str, str]:
    return canonical_album(event["album"]), canonical_text(event["artist"])


def top_rows(
    events: list[dict[str, Any]],
    key_function: Any,
    limit: int,
    library: Any,
    kind: str,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    tracks_by_album: defaultdict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for event in events:
        if event["ms"] < 30_000:
            continue
        key = key_function(event)
        if not key[0]:
            continue
        item = grouped.setdefault(
            key,
            {
                "title": (
                    event["title"]
                    if kind == "track"
                    else event["album"] if kind == "album" else event["artist"]
                ),
                "artist": event["artist"],
                "album": event["album"],
                "plays": 0,
                "ms": 0,
                "skips": 0,
            },
        )
        item["plays"] += 1
        item["ms"] += event["ms"]
        item["skips"] += int(event["skipped"] or event["ms"] < 30_000)
        if kind == "album":
            tracks_by_album[key].add(track_key(event))
    rows = sorted(grouped.values(), key=lambda item: (item["ms"], item["plays"]), reverse=True)
    for row in rows:
        row["hours"] = round(row.pop("ms") / 3_600_000, 2)
        if kind == "track":
            row["owned"] = library.owns_track(
                FavoriteTrack(row["title"], row["artist"], row["album"])
            )
        elif kind == "album":
            key = canonical_album(row["title"]), canonical_text(row["artist"])
            row["distinct_tracks"] = len(tracks_by_album[key])
            row["owned"] = library.owns_album(FavoriteAlbum(row["title"], row["artist"]))
    return rows[:limit]


def sessions_for(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sessions: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for event in events:
        if event["ms"] < 30_000:
            continue
        if current and event["dt"] - current[-1]["dt"] > timedelta(minutes=30):
            sessions.append(current)
            current = []
        current.append(event)
    if current:
        sessions.append(current)

    result = []
    for session in sessions:
        album_counts = Counter(album_key(event) for event in session)
        top_album_share = album_counts.most_common(1)[0][1] / len(session)
        shuffle_share = sum(event["shuffle"] for event in session) / len(session)
        start = session[0]["dt"]
        if top_album_share >= 0.7 and len(session) >= 4:
            category = "Focused album"
        elif shuffle_share >= 0.7 and len(session) >= 8:
            category = "Shuffle session"
        elif start.hour >= 23 or start.hour < 5:
            category = "Late night"
        elif start.weekday() < 5 and (7 <= start.hour < 10 or 16 <= start.hour < 19):
            category = "Commute hours"
        else:
            category = "General"
        result.append(
            {
                "year": start.year,
                "category": category,
                "tracks": len(session),
                "minutes": round(sum(event["ms"] for event in session) / 60_000, 1),
            }
        )
    return result


def aggregate_view(
    events: list[dict[str, Any]], library: Any, session_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    qualifying = [event for event in events if event["ms"] >= 30_000]
    day_ms: Counter[str] = Counter()
    clock_ms: Counter[tuple[int, int]] = Counter()
    month_ms: Counter[str] = Counter()
    month_plays: Counter[str] = Counter()
    month_skips: Counter[str] = Counter()
    platforms: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for event in events:
        month = event["dt"].strftime("%Y-%m")
        if event["ms"] >= 30_000:
            day_ms[event["dt"].date().isoformat()] += event["ms"]
            clock_ms[(event["dt"].weekday(), event["dt"].hour)] += event["ms"]
            month_ms[month] += event["ms"]
            month_plays[month] += 1
            platforms[event["platform"]] += event["ms"]
        if event["skipped"] or event["ms"] < 30_000:
            month_skips[month] += 1
            reasons[event["reason_end"]] += 1

    tracks = top_rows(events, track_key, 30, library, "track")
    artists = top_rows(
        events,
        lambda event: (canonical_text(event["artist"]), ""),
        25,
        library,
        "artist",
    )
    albums = top_rows(events, album_key, 30, library, "album")
    purchases = [
        row for row in top_rows(events, album_key, 200, library, "album")
        if not row["owned"] and row["distinct_tracks"] >= 2
    ][:30]
    session_counts: Counter[str] = Counter(row["category"] for row in session_rows)
    return {
        "stats": {
            "hours": round(sum(event["ms"] for event in qualifying) / 3_600_000, 1),
            "plays": len(qualifying),
            "unique_tracks": len({track_key(event) for event in qualifying}),
            "unique_artists": len({canonical_text(event["artist"]) for event in qualifying}),
            "skip_rate": round(
                100
                * sum(event["skipped"] or event["ms"] < 30_000 for event in events)
                / max(len(events), 1),
                1,
            ),
            "shuffle_rate": round(
                100 * sum(event["shuffle"] for event in events) / max(len(events), 1), 1
            ),
            "offline_rate": round(
                100 * sum(event["offline"] for event in events) / max(len(events), 1), 1
            ),
        },
        "days": [{"date": day, "hours": round(ms / 3_600_000, 2)} for day, ms in sorted(day_ms.items())],
        "clock": [
            round(clock_ms[(weekday, hour)] / 3_600_000, 2)
            for weekday in range(7)
            for hour in range(24)
        ],
        "months": [
            {
                "month": month,
                "hours": round(month_ms[month] / 3_600_000, 2),
                "plays": month_plays[month],
                "skips": month_skips[month],
            }
            for month in sorted(set(month_ms) | set(month_skips))
        ],
        "tracks": tracks,
        "artists": artists,
        "albums": albums,
        "purchases": purchases,
        "platforms": [
            {"name": name, "hours": round(ms / 3_600_000, 1)}
            for name, ms in platforms.most_common(10)
        ],
        "sessions": [{"name": name, "count": count} for name, count in session_counts.most_common()],
        "reasons": [{"name": name, "count": count} for name, count in reasons.most_common(10)],
    }


def discovery_series(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    first_seen: dict[tuple[str, str], datetime] = {}
    monthly: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for event in events:
        if event["ms"] < 30_000:
            continue
        key = track_key(event)
        month = event["dt"].strftime("%Y-%m")
        if key not in first_seen:
            first_seen[key] = event["dt"]
            monthly[month]["discoveries"] += 1
        else:
            monthly[month]["returns"] += 1
    return [{"month": month, **monthly[month]} for month in sorted(monthly)]


def long_term_insights(events: list[dict[str, Any]]) -> dict[str, Any]:
    qualifying = [event for event in events if event["ms"] >= 30_000]
    track_dates: defaultdict[tuple[str, str], list[datetime]] = defaultdict(list)
    track_labels: dict[tuple[str, str], tuple[str, str]] = {}
    artist_years: defaultdict[str, set[int]] = defaultdict(set)
    artist_ms: Counter[str] = Counter()
    artist_label: dict[str, str] = {}
    track_months: defaultdict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for event in qualifying:
        key = track_key(event)
        track_dates[key].append(event["dt"])
        track_labels[key] = event["title"], event["artist"]
        artist = canonical_text(event["artist"])
        artist_years[artist].add(event["dt"].year)
        artist_ms[artist] += event["ms"]
        artist_label[artist] = event["artist"]
        track_months[key][event["dt"].strftime("%Y-%m")] += 1

    rediscoveries = []
    for key, dates in track_dates.items():
        gaps = [(later - earlier).days for earlier, later in zip(dates, dates[1:])]
        if gaps and max(gaps) >= 180:
            title, artist = track_labels[key]
            rediscoveries.append({"title": title, "artist": artist, "gap_days": max(gaps)})
    rediscoveries.sort(key=lambda item: item["gap_days"], reverse=True)

    obsessions = []
    for key, months in track_months.items():
        peak_month, peak_plays = months.most_common(1)[0]
        total = sum(months.values())
        if peak_plays >= 5:
            title, artist = track_labels[key]
            obsessions.append(
                {
                    "title": title,
                    "artist": artist,
                    "month": peak_month,
                    "peak_plays": peak_plays,
                    "share": round(100 * peak_plays / total),
                }
            )
    obsessions.sort(key=lambda item: (item["peak_plays"], item["share"]), reverse=True)

    loyalty = [
        {
            "artist": artist_label[key],
            "years": len(years),
            "hours": round(artist_ms[key] / 3_600_000, 1),
        }
        for key, years in artist_years.items()
    ]
    loyalty.sort(key=lambda item: (item["years"], item["hours"]), reverse=True)
    return {
        "discoveries": discovery_series(events),
        "rediscoveries": rediscoveries[:30],
        "obsessions": obsessions[:30],
        "loyalty": loyalty[:30],
    }


def race_data(events: list[dict[str, Any]]) -> dict[str, Any]:
    qualifying = [event for event in events if event["ms"] >= 30_000]
    overall: Counter[tuple[str, str]] = Counter(track_key(event) for event in qualifying)
    keys = [key for key, _ in overall.most_common(12)]
    labels: dict[tuple[str, str], str] = {}
    monthly: defaultdict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    for event in qualifying:
        key = track_key(event)
        if key in keys:
            labels[key] = f"{event['title']} — {event['artist']}"
            monthly[event["dt"].strftime("%Y-%m")][key] += 1
    months = sorted(monthly)
    cumulative: Counter[tuple[str, str]] = Counter()
    frames = []
    for month in months:
        cumulative.update(monthly[month])
        frames.append(
            {
                "month": month,
                "values": [
                    {"name": labels[key], "plays": cumulative[key]} for key in keys
                ],
            }
        )
    return {"frames": frames}


def playlist_evolution(value: str | None, events: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        import keyring
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
    except ImportError:
        return {"error": "Install requirements to load playlist evolution."}
    client_id = keyring.get_password(KEYRING_SERVICE, "client-id")
    client_secret = keyring.get_password(KEYRING_SERVICE, "client-secret")
    if not client_id or not client_secret:
        return {"error": "Run spotify_sync.py --configure to load playlist evolution."}
    spotify = spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri="http://127.0.0.1:8888/callback",
            scope="playlist-read-private playlist-read-collaborative",
        )
    )
    identifier = playlist_id(value)
    playlist = spotify.playlist(identifier, fields="name,owner,collaborative")
    rows = list(paged_items(spotify, spotify.playlist_items(identifier, limit=50)))
    contributors: Counter[str] = Counter()
    monthly_adds: defaultdict[str, Counter[str]] = defaultdict(Counter)
    artist_counts: Counter[str] = Counter()
    items = []
    history_first: dict[str, datetime] = {}
    for event in events:
        if event["uri"] and event["uri"] not in history_first:
            history_first[event["uri"]] = event["dt"]
    for row in rows:
        item = row.get("item") or row.get("track") or {}
        if not isinstance(item, dict) or not item.get("name"):
            continue
        added_at = parse_timestamp(row["added_at"]) if row.get("added_at") else None
        contributor = (row.get("added_by") or {}).get("id") or "Unknown"
        contributors[contributor] += 1
        if added_at:
            monthly_adds[added_at.strftime("%Y-%m")][contributor] += 1
        artists = ", ".join(artist["name"] for artist in item.get("artists", []))
        if item.get("artists"):
            artist_counts[item["artists"][0]["name"]] += 1
        uri = item.get("uri", "")
        first_listen = history_first.get(uri)
        lag = (first_listen - added_at).days if first_listen and added_at else None
        items.append(
            {
                "title": item["name"],
                "artist": artists,
                "added_at": added_at.date().isoformat() if added_at else "",
                "added_by": contributor,
                "first_listen_lag": lag,
            }
        )
    contributor_names = sorted(contributors)
    running = Counter()
    cumulative = []
    for month in sorted(monthly_adds):
        running.update(monthly_adds[month])
        cumulative.append(
            {
                "month": month,
                "values": {name: running[name] for name in contributor_names},
                "adds": dict(monthly_adds[month]),
            }
        )
    return {
        "name": playlist["name"],
        "owner": playlist["owner"]["id"],
        "contributors": [
            {"name": name, "count": contributors[name]} for name in contributor_names
        ],
        "cumulative": cumulative,
        "top_artists": [
            {"name": name, "count": count} for name, count in artist_counts.most_common(20)
        ],
        "items": items,
    }


def build_data(events: list[dict[str, Any]], library: Any, playlist: str | None) -> dict[str, Any]:
    years = sorted({event["dt"].year for event in events})
    sessions = sessions_for(events)
    views = {"all": aggregate_view(events, library, sessions)}
    for year in years:
        year_events = [event for event in events if event["dt"].year == year]
        year_sessions = [session for session in sessions if session["year"] == year]
        views[str(year)] = aggregate_view(year_events, library, year_sessions)
    wrapped = {}
    for year in years:
        view = views[str(year)]
        wrapped[str(year)] = {
            "stats": view["stats"],
            "track": view["tracks"][0] if view["tracks"] else None,
            "artist": view["artists"][0] if view["artists"] else None,
            "album": view["albums"][0] if view["albums"] else None,
        }
    return {
        "generated": datetime.now().astimezone().isoformat(),
        "range": [events[0]["dt"].date().isoformat(), events[-1]["dt"].date().isoformat()],
        "years": years,
        "views": views,
        "long_term": long_term_insights(events),
        "race": race_data(events),
        "wrapped": wrapped,
        "playlist": playlist_evolution(playlist, events),
        "library_tracks": library.track_count,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--history", action="append", type=Path, required=True)
    result.add_argument(
        "--itunes", type=Path, default=Path.home() / "OneDrive" / "Music" / "iTunes"
    )
    result.add_argument("--playlist", help="Spotify playlist ID or URL for evolution analysis.")
    result.add_argument("--output", type=Path, default=Path("spotify-dashboard.html"))
    result.add_argument(
        "--template",
        type=Path,
        default=Path(__file__).with_name("spotify_dashboard_template.html"),
    )
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        events = load_events(args.history)
        if not events:
            raise ValueError("No Spotify track history was found")
        library = load_itunes_library(args.itunes)
        data = build_data(events, library, args.playlist)
        template = args.template.read_text(encoding="utf-8")
        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        args.output.write_text(template.replace("__SPOTIFY_DATA__", encoded), encoding="utf-8")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}")
        return 1
    print(f"Wrote {args.output.resolve()}")
    print(f"Analyzed {len(events):,} track events from {data['range'][0]} to {data['range'][1]}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
