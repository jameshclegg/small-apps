import tempfile
import unittest
from pathlib import Path

from itunes_purchase_report import StoreMatch, choose_match, resolve_library_location
from spotify_sync import FavoriteTrack


class ITunesPurchaseReportTests(unittest.TestCase):
    def test_prefers_matching_album_and_purchasable_track(self):
        track = FavoriteTrack("Late in the Evening", "Paul Simon", "One-Trick Pony")
        results = [
            {
                "trackName": "Late in the Evening",
                "artistName": "Paul Simon",
                "collectionName": "Greatest Hits",
                "trackPrice": 0.79,
                "currency": "GBP",
                "trackViewUrl": "https://example.test/hits",
            },
            {
                "trackName": "Late in the Evening",
                "artistName": "Paul Simon",
                "collectionName": "One-Trick Pony",
                "trackPrice": 0.99,
                "currency": "GBP",
                "trackViewUrl": "https://example.test/album",
            },
        ]
        match = choose_match(track, results)
        self.assertEqual(match.status, "Matched")
        self.assertEqual(match.album, "One-Trick Pony")

    def test_rejects_different_track(self):
        track = FavoriteTrack("Original", "Artist", "Album")
        match = choose_match(
            track,
            [{"trackName": "Live Version", "artistName": "Artist", "trackPrice": 0.99}],
        )
        self.assertEqual(match, StoreMatch("No confident match"))

    def test_remaps_stale_itunes_media_location(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "iTunes"
            source = root / "Previous iTunes Libraries" / "Library.xml"
            moved = root / "iTunes Media" / "Music" / "Artist" / "Song.m4a"
            moved.parent.mkdir(parents=True)
            moved.touch()
            resolved = resolve_library_location(
                Path("C:/Users/name/Music/iTunes/iTunes Media/Music/Artist/Song.m4a"),
                source,
            )
        self.assertEqual(resolved, moved)


if __name__ == "__main__":
    unittest.main()
