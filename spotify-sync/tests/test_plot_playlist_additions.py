import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from plot_playlist_additions import (
    Addition,
    contributor_summary,
    read_additions,
)


class PlotPlaylistAdditionsTests(unittest.TestCase):
    def test_summary_finds_busiest_week_and_longest_gap(self):
        start = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)
        additions = [
            Addition("One", "Artist", start, "user"),
            Addition("Two", "Artist", start + timedelta(days=1), "user"),
            Addition("Three", "Artist", start + timedelta(days=30), "user"),
        ]
        summary = contributor_summary("user", additions)
        self.assertEqual(summary.busiest_week_count, 2)
        self.assertEqual(summary.busiest_week.date(), start.date())
        self.assertEqual(summary.longest_gap, timedelta(days=29))

    def test_summary_ranks_top_five_weeks_and_gaps(self):
        start = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)
        additions = []
        for week, count in enumerate((1, 6, 3, 5, 2, 4)):
            additions.extend(
                Addition(
                    f"Song {week}-{item}",
                    "Artist",
                    start + timedelta(weeks=week, minutes=item),
                    "user",
                )
                for item in range(count)
            )
        summary = contributor_summary("user", additions)
        self.assertEqual([peak.count for peak in summary.peak_weeks], [6, 5, 4, 3, 2])
        self.assertEqual(len(summary.longest_gaps), 5)
        self.assertEqual(
            list(summary.longest_gaps),
            sorted(
                summary.longest_gaps,
                key=lambda gap: (-gap.duration.total_seconds(), gap.start),
            ),
        )

    def test_csv_requires_expected_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "playlist.csv"
            path.write_text("song,artist\nOne,Artist\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing columns"):
                read_additions(path)


if __name__ == "__main__":
    unittest.main()
