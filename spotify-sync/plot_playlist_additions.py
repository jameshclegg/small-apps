#!/usr/bin/env python3
"""Plot collaborative Spotify playlist additions and gaps from a CSV export."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np


COLORS = ("#1DB954", "#A970FF", "#F59B23", "#E255A1", "#4C9AFF")


@dataclass(frozen=True)
class Addition:
    song: str
    artist: str
    added_at: datetime
    added_by: str


@dataclass(frozen=True)
class PeakWeek:
    week: datetime
    count: int


@dataclass(frozen=True)
class AdditionGap:
    duration: timedelta
    start: datetime
    end: datetime


@dataclass(frozen=True)
class ContributorSummary:
    name: str
    total: int
    peak_weeks: tuple[PeakWeek, ...]
    longest_gaps: tuple[AdditionGap, ...]

    @property
    def busiest_week(self) -> datetime:
        return self.peak_weeks[0].week

    @property
    def busiest_week_count(self) -> int:
        return self.peak_weeks[0].count

    @property
    def longest_gap(self) -> timedelta:
        return self.longest_gaps[0].duration

    @property
    def gap_start(self) -> datetime:
        return self.longest_gaps[0].start

    @property
    def gap_end(self) -> datetime:
        return self.longest_gaps[0].end


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_additions(path: Path) -> list[Addition]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            expected = {"song", "artist", "date_added", "added_by"}
            missing = expected - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"CSV is missing columns: {', '.join(sorted(missing))}")
            additions = [
                Addition(
                    song=row["song"].strip(),
                    artist=row["artist"].strip(),
                    added_at=parse_timestamp(row["date_added"]),
                    added_by=row["added_by"].strip() or "Unknown",
                )
                for row in reader
                if row["date_added"].strip()
            ]
    except OSError as exc:
        raise ValueError(f"Could not read {path}: {exc}") from exc
    if not additions:
        raise ValueError("CSV contains no dated playlist additions")
    return sorted(additions, key=lambda item: item.added_at)


def week_start(value: datetime) -> datetime:
    midnight = value.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=value.weekday())


def contributor_summary(name: str, additions: Iterable[Addition]) -> ContributorSummary:
    rows = sorted(
        (addition for addition in additions if addition.added_by == name),
        key=lambda item: item.added_at,
    )
    if not rows:
        raise ValueError(f"No additions found for contributor {name}")
    weekly = Counter(week_start(row.added_at) for row in rows)
    peak_weeks = tuple(
        PeakWeek(week, count)
        for week, count in sorted(
            weekly.items(), key=lambda item: (-item[1], item[0])
        )[:5]
    )
    if len(rows) == 1:
        longest_gaps = (
            AdditionGap(timedelta(0), rows[0].added_at, rows[0].added_at),
        )
    else:
        longest_gaps = tuple(
            sorted(
                (
                    AdditionGap(
                        later.added_at - earlier.added_at,
                        earlier.added_at,
                        later.added_at,
                    )
                    for earlier, later in zip(rows, rows[1:])
                ),
                key=lambda gap: (-gap.duration.total_seconds(), gap.start),
            )[:5]
        )
    return ContributorSummary(
        name=name,
        total=len(rows),
        peak_weeks=peak_weeks,
        longest_gaps=longest_gaps,
    )


def format_gap(value: timedelta) -> str:
    seconds = value.total_seconds()
    if seconds >= 86_400:
        return f"{seconds / 86_400:.1f} days"
    if seconds >= 3_600:
        return f"{seconds / 3_600:.1f} hours"
    return f"{seconds / 60:.1f} minutes"


def plot_additions(additions: list[Addition], output: Path, title: str) -> None:
    contributors = sorted({addition.added_by for addition in additions})
    summaries = {
        name: contributor_summary(name, additions) for name in contributors
    }
    colors = {name: COLORS[index % len(COLORS)] for index, name in enumerate(contributors)}

    figure = plt.figure(figsize=(18, 16), facecolor="#08110d", constrained_layout=True)
    grid = figure.add_gridspec(3, 2, height_ratios=(1.15, 1, 1.05))
    cumulative_axis = figure.add_subplot(grid[0, :])
    gaps_axis = figure.add_subplot(grid[1, 0])
    weekly_axis = figure.add_subplot(grid[1, 1])
    summary_axis = figure.add_subplot(grid[2, :])
    axes = (cumulative_axis, gaps_axis, weekly_axis, summary_axis)
    for axis in axes:
        axis.set_facecolor("#102019")
        axis.tick_params(colors="#c8ddd1")
        for spine in axis.spines.values():
            spine.set_color("#355345")

    for name in contributors:
        rows = [row for row in additions if row.added_by == name]
        dates = [row.added_at for row in rows]
        counts = np.arange(1, len(rows) + 1)
        cumulative_axis.step(
            dates,
            counts,
            where="post",
            color=colors[name],
            linewidth=2.3,
            label=f"{name} ({len(rows)})",
        )
        cumulative_axis.plot(
            dates,
            counts,
            linestyle="none",
            marker="|",
            markersize=7,
            markeredgewidth=1.1,
            color=colors[name],
            alpha=0.7,
        )
        summary = summaries[name]
        cumulative_axis.axvspan(
            summary.gap_start,
            summary.gap_end,
            color=colors[name],
            alpha=0.09,
        )
    cumulative_axis.set_title(
        f"{title}: cumulative song additions",
        color="white",
        fontsize=20,
        fontweight="bold",
        loc="left",
    )
    cumulative_axis.set_xlabel("Calendar date", color="#c8ddd1")
    cumulative_axis.set_ylabel("Cumulative songs added", color="#c8ddd1")
    cumulative_axis.grid(axis="both", color="#284238", alpha=0.55)
    cumulative_axis.legend(facecolor="#102019", edgecolor="#355345", labelcolor="white")
    cumulative_axis.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    cumulative_axis.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))

    positive_gap_days: dict[str, list[float]] = {}
    for name in contributors:
        dates = [
            row.added_at for row in additions if row.added_by == name
        ]
        positive_gap_days[name] = [
            (later - earlier).total_seconds() / 86_400
            for earlier, later in zip(dates, dates[1:])
            if later > earlier
        ]
    all_gaps = [gap for gaps in positive_gap_days.values() for gap in gaps]
    minimum = max(min(all_gaps, default=1 / 1_440), 1 / 1_440)
    maximum = max(all_gaps, default=1)
    bins = np.geomspace(minimum, maximum * 1.001, 28)
    for name in contributors:
        gaps_axis.hist(
            positive_gap_days[name],
            bins=bins,
            histtype="step",
            linewidth=2.2,
            color=colors[name],
            label=name,
        )
    gaps_axis.set_xscale("log")
    gaps_axis.set_title(
        "Time between additions", color="white", fontsize=17, fontweight="bold", loc="left"
    )
    gaps_axis.set_xlabel("Gap in days (logarithmic scale)", color="#c8ddd1")
    gaps_axis.set_ylabel("Number of gaps", color="#c8ddd1")
    gaps_axis.grid(color="#284238", alpha=0.5)
    gaps_axis.legend(facecolor="#102019", edgecolor="#355345", labelcolor="white")

    first_week = min(week_start(row.added_at) for row in additions)
    last_week = max(week_start(row.added_at) for row in additions)
    week_count = ((last_week - first_week).days // 7) + 1
    weeks = [first_week + timedelta(weeks=index) for index in range(week_count)]
    moving_window = min(4, len(weeks))
    for name in contributors:
        counts = Counter(
            week_start(row.added_at)
            for row in additions
            if row.added_by == name
        )
        values = [counts[week] for week in weeks]
        moving_values = np.convolve(
            values, np.ones(moving_window) / moving_window, mode="valid"
        )
        moving_weeks = weeks[moving_window - 1 :]
        weekly_axis.plot(
            moving_weeks,
            moving_values,
            color=colors[name],
            linewidth=1.8,
            marker="o",
            markersize=3,
            label=name,
        )
        peak_index = int(np.argmax(moving_values))
        weekly_axis.annotate(
            f"{name}: {moving_values[peak_index]:.1f}",
            (moving_weeks[peak_index], moving_values[peak_index]),
            xytext=(8, 8),
            textcoords="offset points",
            color=colors[name],
            fontsize=9,
            fontweight="bold",
        )
    weekly_axis.set_title(
        f"Songs added per week — {moving_window}-week moving average",
        color="white",
        fontsize=17,
        fontweight="bold",
        loc="left",
    )
    weekly_axis.set_xlabel("Week beginning", color="#c8ddd1")
    weekly_axis.set_ylabel("Average songs added", color="#c8ddd1")
    weekly_axis.grid(color="#284238", alpha=0.5)
    weekly_axis.legend(facecolor="#102019", edgecolor="#355345", labelcolor="white")
    weekly_axis.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    weekly_axis.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))

    summary_axis.axis("off")
    summary_axis.set_title(
        "Peak weeks and longest pauses",
        color="white",
        fontsize=17,
        fontweight="bold",
        loc="left",
    )
    columns = max(len(contributors), 1)
    for index, name in enumerate(contributors):
        summary = summaries[name]
        x = (index + 0.04) / columns
        peak_lines = "\n".join(
            f"{rank}. {peak.week:%d %b %Y} — {peak.count} songs"
            for rank, peak in enumerate(summary.peak_weeks, start=1)
        )
        gap_lines = "\n".join(
            f"{rank}. {format_gap(gap.duration)} — "
            f"{gap.start:%d %b %Y} → {gap.end:%d %b %Y}"
            for rank, gap in enumerate(summary.longest_gaps, start=1)
        )
        summary_axis.text(
            x,
            0.91,
            name,
            color=colors[name],
            fontsize=17,
            fontweight="bold",
            transform=summary_axis.transAxes,
        )
        summary_axis.text(
            x,
            0.80,
            (
                f"{summary.total} total additions\n"
                f"\nTop 5 peak weeks\n{peak_lines}"
                f"\n\nTop 5 longest gaps\n{gap_lines}"
            ),
            color="#dcebe3",
            fontsize=10.5,
            linespacing=1.45,
            transform=summary_axis.transAxes,
            va="top",
        )
    figure.suptitle(
        "How the playlist grew",
        color="white",
        fontsize=28,
        fontweight="bold",
        x=0.02,
        ha="left",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180, facecolor=figure.get_facecolor())
    plt.close(figure)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("csv", type=Path, help="Playlist CSV with Spotify addition metadata.")
    result.add_argument(
        "--output",
        type=Path,
        help="PNG output path (default: <CSV name>-analysis.png beside the CSV).",
    )
    result.add_argument("--title", default="JC/Erykah")
    return result


def main() -> int:
    args = parser().parse_args()
    output = args.output or args.csv.with_name(f"{args.csv.stem}-analysis.png")
    try:
        additions = read_additions(args.csv)
        plot_additions(additions, output, args.title)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    print(f"Wrote {output.resolve()} from {len(additions)} additions.")
    for name in sorted({addition.added_by for addition in additions}):
        summary = contributor_summary(name, additions)
        print(f"{name}:")
        for rank, peak in enumerate(summary.peak_weeks, start=1):
            print(f"  peak {rank}: {peak.week:%Y-%m-%d} ({peak.count})")
        for rank, gap in enumerate(summary.longest_gaps, start=1):
            print(
                f"  gap {rank}: {format_gap(gap.duration)} "
                f"({gap.start:%Y-%m-%d} to {gap.end:%Y-%m-%d})"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
