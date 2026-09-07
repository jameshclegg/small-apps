import unittest
from datetime import datetime, timezone
from pathlib import Path

from spotify_dashboard import discovery_series, sessions_for


def event(timestamp, title="Song", album="Album", **overrides):
    value = {
        "dt": datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc),
        "title": title,
        "artist": "Artist",
        "album": album,
        "uri": "",
        "ms": 180000,
        "skipped": False,
        "shuffle": False,
        "offline": False,
        "incognito": False,
        "platform": "test",
        "reason_start": "clickrow",
        "reason_end": "trackdone",
    }
    value.update(overrides)
    return value


class SpotifyDashboardTests(unittest.TestCase):
    def test_dynamic_svg_elements_are_explicitly_closed(self):
        template = Path(__file__).parents[1] / "spotify_dashboard_template.html"
        content = template.read_text(encoding="utf-8")
        self.assertNotIn("<line class=axis", content)
        self.assertNotIn('stroke-width=3/>', content)
        self.assertNotIn('stroke-width=4/>', content)

    def test_discovery_series_separates_first_and_return_plays(self):
        rows = discovery_series(
            [
                event("2025-01-01T12:00:00"),
                event("2025-01-02T12:00:00"),
                event("2025-02-01T12:00:00", title="New"),
            ]
        )
        self.assertEqual(rows[0]["discoveries"], 1)
        self.assertEqual(rows[0]["returns"], 1)
        self.assertEqual(rows[1]["discoveries"], 1)

    def test_sessions_split_after_thirty_minutes(self):
        rows = sessions_for(
            [
                event("2025-01-01T12:00:00"),
                event("2025-01-01T12:10:00", title="Two"),
                event("2025-01-01T13:00:00", title="Three"),
            ]
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["tracks"], 2)


if __name__ == "__main__":
    unittest.main()
