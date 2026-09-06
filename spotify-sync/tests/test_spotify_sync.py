import json
import plistlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from spotify_sync import (
    FavoriteAlbum,
    FavoriteTrack,
    canonical_album,
    canonical_artist,
    canonical_title,
    load_history,
    load_itunes_library,
    location_path,
    playlist_id,
    spotify_track,
    write_report,
)


class SpotifySyncTests(unittest.TestCase):
    def test_title_normalization_ignores_mastering_suffixes(self):
        self.assertEqual(canonical_title("Once in a Lifetime (Remastered 2005)"), "once in a lifetime")
        self.assertEqual(canonical_title("Everywhere - 2017 Remaster"), "everywhere")
        self.assertEqual(canonical_title("Song (feat. Guest)"), "song")
        self.assertEqual(canonical_title("Gumboots (with Boyoyo Boys)"), "gumboots")
        self.assertEqual(canonical_title("Once in a Lifetime"), "once in a lifetime")

    def test_artist_and_album_editions_are_normalized(self):
        self.assertEqual(canonical_artist("The Police"), "police")
        self.assertEqual(
            canonical_album("Graceland (25th Anniversary Deluxe Edition)"),
            "graceland",
        )

    def test_non_track_playlist_items_are_ignored(self):
        self.assertIsNone(spotify_track(True))

    def test_playlist_id_accepts_urls_and_ids(self):
        self.assertEqual(
            playlist_id("https://open.spotify.com/playlist/3xrpLGhAyZp4i5WnKfaFYG?si=test"),
            "3xrpLGhAyZp4i5WnKfaFYG",
        )
        self.assertEqual(playlist_id("3xrpLGhAyZp4i5WnKfaFYG"), "3xrpLGhAyZp4i5WnKfaFYG")

    def test_itunes_location_is_converted_to_windows_path(self):
        self.assertEqual(
            location_path("file://localhost/C:/Music/Paul%20Simon/Graceland.m4a"),
            Path(r"C:\Music\Paul Simon\Graceland.m4a"),
        )

    def test_extended_and_legacy_history_are_aggregated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Streaming_History_Audio_0.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "ts": "2025-01-01T12:00:00Z",
                            "ms_played": 120000,
                            "master_metadata_track_name": "Track",
                            "master_metadata_album_artist_name": "Artist",
                            "master_metadata_album_album_name": "Album",
                        },
                        {
                            "endTime": "2025-01-02 12:00",
                            "msPlayed": 60000,
                            "trackName": "Track",
                            "artistName": "Artist",
                            "albumName": "Album",
                        },
                        {
                            "ts": "2025-01-03T12:00:00Z",
                            "ms_played": 5000,
                            "master_metadata_track_name": "Skipped",
                            "master_metadata_album_artist_name": "Artist",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            tracks = load_history([Path(directory)], datetime(2024, 1, 1, tzinfo=timezone.utc))

        self.assertEqual(len(tracks), 1)
        track = next(iter(tracks.values()))
        self.assertEqual(track.play_count, 2)
        self.assertEqual(track.milliseconds, 180000)

    def test_itunes_file_tracks_are_matched(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "iTunes Library.xml"
            with path.open("wb") as stream:
                plistlib.dump(
                    {
                        "Tracks": {
                            "1": {
                                "Name": "Song (Remastered)",
                                "Artist": "The Artist feat. Guest",
                                "Album": "The Album",
                                "Track Type": "File",
                                "Location": "file://localhost/C:/Music/song.m4a",
                            },
                            "2": {
                                "Name": "Cloud only",
                                "Artist": "Artist",
                                "Album": "Album",
                                "Track Type": "Remote",
                            },
                        }
                    },
                    stream,
                )
            library = load_itunes_library(Path(directory))

        self.assertEqual(library.track_count, 1)
        self.assertTrue(library.owns_track(FavoriteTrack("Song", "The Artist", "The Album")))
        self.assertTrue(library.owns_album(FavoriteAlbum("The Album", "The Artist")))

    def test_report_marks_missing_recommendations(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.md"
            library = type(
                "Library",
                (),
                {
                    "track_count": 0,
                    "source": Path("library.xml"),
                    "owns_track": lambda self, track: False,
                    "owns_album": lambda self, album: False,
                },
            )()
            track = FavoriteTrack("Missing Song", "Artist", "Missing Album", play_count=4)
            track.sources.add("streaming history")
            second_track = FavoriteTrack("Another Song", "Artist", "Missing Album", play_count=2)
            second_track.sources.add("streaming history")
            write_report(output, [track, second_track], library, 3, 100, 50)
            report = output.read_text(encoding="utf-8")

        self.assertIn("## Recommended songs to buy", report)
        self.assertIn("Missing Song", report)
        self.assertIn("Missing Album", report)

    def test_single_track_album_is_not_recommended(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.md"
            library = type(
                "Library",
                (),
                {
                    "track_count": 0,
                    "source": Path("library.xml"),
                    "owns_track": lambda self, track: False,
                    "owns_album": lambda self, album: False,
                },
            )()
            write_report(
                output,
                [FavoriteTrack("Only Favorite", "Artist", "Album")],
                library,
                3,
                100,
                50,
            )
            report = output.read_text(encoding="utf-8")

        album_section = report.split("## Recommended albums to buy", 1)[1]
        self.assertIn("No missing favorite albums were found.", album_section)


if __name__ == "__main__":
    unittest.main()
