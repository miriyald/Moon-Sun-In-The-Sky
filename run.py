"""
Sun/Moon times CSV generator for a given location and year.

Produces daily sun rise/set, moon rise/set, overlap (both visible),
and no-sun-no-moon periods in local time (00:00–23:59), with yearly totals.
"""

import csv
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.moon import moonrise, moonset
from astral.sun import sun


def _day_bounds(date: datetime.date, tz: datetime.tzinfo):
    """Return (day_start, day_end) for the given date. Day is [00:00:00, next 00:00:00) so the last minute counts fully."""
    day_start = datetime.datetime(date.year,
                                  date.month,
                                  date.day,
                                  0, 0, 0,
                                  tzinfo=tz)
    day_end = day_start + datetime.timedelta(days=1)  # midnight next day
    return day_start, day_end


def _clip_interval(start: datetime.datetime,
                   end: datetime.datetime,
                   day_start: datetime.datetime,
                   day_end: datetime.datetime):
    """Clip (start, end) to [day_start, day_end]. Returns None if no overlap."""
    if start is None or end is None:
        return None
    s = max(start, day_start)
    e = min(end, day_end)
    if s < e:
        return (s, e)
    return None


def _clip_intervals_to_day(intervals: list[tuple[datetime.datetime, datetime.datetime]],
                           day_start: datetime.datetime,
                           day_end: datetime.datetime) -> list[tuple[datetime.datetime, datetime.datetime]]:
    """Clip each interval to the day window; return list of non-empty clipped intervals."""
    out = []
    for start, end in intervals:
        clipped = _clip_interval(start, end, day_start, day_end)
        if clipped:
            out.append(clipped)
    return out


def _intersect_intervals(intervals_a: list[tuple[datetime.datetime, datetime.datetime]],
                         intervals_b: list[tuple[datetime.datetime, datetime.datetime]]) -> list[tuple[datetime.datetime, datetime.datetime]]:
    """Return intersection of two interval lists (within the same day)."""
    out = []
    for (a0, a1) in intervals_a:
        for (b0, b1) in intervals_b:
            s = max(a0, b0)
            e = min(a1, b1)
            if s < e:
                out.append((s, e))
    return sorted(out, key=lambda x: x[0])


def _complement_intervals(intervals: list[tuple[datetime.datetime, datetime.datetime]],
                          day_start: datetime.datetime,
                          day_end: datetime.datetime) -> list[tuple[datetime.datetime, datetime.datetime]]:
    """Return intervals not covered by the given intervals, within [day_start, day_end]."""
    if not intervals:
        return [(day_start, day_end)]
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    out = []
    cur = day_start
    for start, end in sorted_intervals:
        if start > cur:
            out.append((cur, min(start, day_end)))
        cur = max(cur, end)
        if cur >= day_end:
            break
    if cur < day_end:
        out.append((cur, day_end))
    return [p for p in out if p[0] < p[1]]


def _total_seconds(intervals: list[tuple[datetime.datetime,
                                         datetime.datetime]]) -> float:
    """Total length of all intervals in seconds."""
    return sum((e - s).total_seconds() for s, e in intervals)


def _first_start_last_end(intervals: list[tuple[datetime.datetime, datetime.datetime]]) -> tuple[datetime.datetime | None, datetime.datetime | None]:
    """Return (first start time, last end time) or (None, None) if empty."""
    if not intervals:
        return None, None
    return intervals[0][0], intervals[-1][1]


def _time_str(dt: datetime.datetime | None) -> str:
    """Format datetime as HH:MM:SS; return empty string if None."""
    if dt is None:
        return ""
    return dt.strftime("%H:%M:%S")


def _duration_str(seconds: float) -> str:
    """Format duration in seconds as H:MM:SS."""
    if seconds <= 0:
        return "0:00:00"
    total = int(round(seconds))
    h, r = divmod(total, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}"


def _seconds_to_days(seconds: float) -> int:
    """Convert seconds to whole number of days (rounded)."""
    return round(seconds / (24 * 3600))


def _get_sun_up_intervals(observer,
                          date: datetime.date,
                          tz: datetime.tzinfo,
                          day_start: datetime.datetime,
                          day_end: datetime.datetime) -> list[tuple[datetime.datetime, datetime.datetime]]:
    """Get sun-up intervals for the day (clipped to day). Handle polar (no rise/set)."""
    try:
        s = sun(observer, date=date, tzinfo=tz)
    except Exception:
        return []
    sunrise_dt = s.get("sunrise")
    sunset_dt = s.get("sunset")
    if sunrise_dt is None or sunset_dt is None:
        return []
    interval = _clip_interval(sunrise_dt, sunset_dt, day_start, day_end)
    if interval:
        return [interval]
    return []


def _get_moon_up_intervals(observer,
                           date: datetime.date,
                           tz: datetime.tzinfo,
                           day_start: datetime.datetime,
                           day_end: datetime.datetime) -> tuple[list[tuple[datetime.datetime, datetime.datetime]], datetime.datetime | None, datetime.datetime | None]:
    """
    Get moon-up intervals for the day (clipped to day).
    If moon doesn't rise (moonset only): moon up from 00:00 to moonset.
    If moon doesn't set (moonrise only): moon up from moonrise to 23:59.
    If both None: moon down all day.
    Astral raises ValueError when moon never rises/sets; we treat as None.
    """
    try:
        mr = moonrise(observer, date, tz)
    except ValueError:
        mr = None
    try:
        ms = moonset(observer, date, tz)
    except ValueError:
        ms = None
    intervals = []
    if mr is not None and ms is not None:
        if mr < ms:
            intervals.append((mr, ms))
        else:
            # Set in morning, rise in evening
            intervals.append((day_start, ms))
            intervals.append((mr, day_end))
    elif mr is not None:
        intervals.append((mr, day_end))
    elif ms is not None:
        intervals.append((day_start, ms))
    # else: no rise and no set -> moon down all day
    clipped = _clip_intervals_to_day(intervals, day_start, day_end)
    return clipped, mr, ms


def _compute_day_row(date: datetime.date,
                     observer,
                     tz: datetime.tzinfo) -> dict:
    """Compute one row of data for the given date."""
    day_start, day_end = _day_bounds(date, tz)
    sun_up = _get_sun_up_intervals(observer, date, tz, day_start, day_end)
    moon_up, moon_rise_actual, moon_set_actual = _get_moon_up_intervals(
        observer, date, tz, day_start, day_end)

    # Sun times (first segment only for rise/set)
    sun_rise_dt, sun_set_dt = None, None
    if sun_up:
        sun_rise_dt, sun_set_dt = sun_up[0][0], sun_up[-1][1]
    total_sun_seconds = _total_seconds(sun_up)

    # Moon times: two segments per day when moon is up twice (e.g. already up at midnight, sets 7AM; rises 8PM).
    # Segment 1: Rise-1 = start of first interval (blank if 00:00 = already up); Set-1 = end (blank if runs to midnight).
    # Segment 2: Rise-2, Set-2 same idea. Civil end of day = 23:59:59 for "did it set today?" display.
    civil_end = day_end - datetime.timedelta(seconds=1)  # 23:59:59
    moon_rise_1 = moon_up[0][0] if moon_up and moon_up[0][0] > day_start else None
    moon_set_1 = moon_up[0][1] if moon_up and moon_up[0][1] <= civil_end else None
    moon_rise_2 = moon_up[1][0] if len(moon_up) > 1 else None
    moon_set_2 = moon_up[1][1] if len(
        moon_up) > 1 and moon_up[1][1] <= civil_end else None
    total_moon_seconds = _total_seconds(moon_up)

    # Overlap (sun and moon both up)
    overlap = _intersect_intervals(sun_up, moon_up)
    overlap_start, overlap_end = _first_start_last_end(overlap)
    total_overlap_seconds = _total_seconds(overlap)

    # No sun, no moon: complement of (sun_up ∪ moon_up)
    union = sorted(sun_up + moon_up, key=lambda x: x[0])
    merged = []
    for start, end in union:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    no_sun_no_moon = _complement_intervals(merged, day_start, day_end)
    no_sun_no_moon_start, no_sun_no_moon_end = _first_start_last_end(
        no_sun_no_moon)
    total_no_sun_no_moon_seconds = _total_seconds(no_sun_no_moon)

    return {"date": date.isoformat(),
            "sun_rise_time": _time_str(sun_rise_dt),
            "sun_set_time": _time_str(sun_set_dt),
            "total_sun_seconds": total_sun_seconds,
            "moon_rise_1_time": _time_str(moon_rise_1),
            "moon_set_1_time": _time_str(moon_set_1),
            "moon_rise_2_time": _time_str(moon_rise_2),
            "moon_set_2_time": _time_str(moon_set_2),
            "total_moon_seconds": total_moon_seconds,
            "overlap_start_time": _time_str(overlap_start),
            "overlap_end_time": _time_str(overlap_end),
            "total_overlap_seconds": total_overlap_seconds,
            "no_sun_no_moon_start_time": _time_str(no_sun_no_moon_start),
            "no_sun_no_moon_end_time": _time_str(no_sun_no_moon_end),
            "total_no_sun_no_moon_seconds": total_no_sun_no_moon_seconds}


CSV_HEADER = ["Date",
              "Sun-Rise-Time",
              "Sun-Set-Time",
              "Total-Sun-Time",
              "Moon-Rise-1-Time",
              "Moon-Set-1-Time",
              "Moon-Rise-2-Time",
              "Moon-Set-2-Time",
              "Total-Moon-Time",
              "Overlap-Sun-Moon-Start-Time",
              "Overlap-Sun-Moon-End-Time",
              "Total-Overlap-Time",
              "No-Moon-No-Sun-Start-Time",
              "No-Moon-No-Sun-End-Time",
              "Total-No-Moon-No-Sun-Time",
              "Total-Sun-Days",
              "Total-Moon-Days",
              "Total-Overlap-Days",
              "Total-No-Sun-No-Moon-Days"]


def generate_csv(latitude: float,
                 longitude: float,
                 timezone_name: str,
                 year: int,
                 output_path: str | None = None) -> str:
    """
    Generate a CSV with daily sun/moon times and overlap totals for the given
    location and year. Returns the path of the written file.

    Location: latitude, longitude, and IANA timezone (e.g. "America/New_York").
    Day window: 00:00:00 to 23:59:00 local time.
    """
    tz = ZoneInfo(timezone_name)
    location = LocationInfo(name="Location",
                            region="",
                            timezone=timezone_name,
                            latitude=latitude,
                            longitude=longitude)
    observer = location.observer

    if output_path is None:
        output_path = f"sun_moon_{latitude}_{longitude}_{year}.csv"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    total_sun = 0.0
    total_moon = 0.0
    total_overlap = 0.0
    total_no_sun_no_moon = 0.0

    start_date = datetime.date(year, 1, 1)
    end_date = datetime.date(year, 12, 31)
    d = start_date
    while d <= end_date:
        row = _compute_day_row(d, observer, tz)
        rows.append(row)
        total_sun += row["total_sun_seconds"]
        total_moon += row["total_moon_seconds"]
        total_overlap += row["total_overlap_seconds"]
        total_no_sun_no_moon += row["total_no_sun_no_moon_seconds"]
        d += datetime.timedelta(days=1)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        for row in rows:
            writer.writerow([row["date"],
                             row["sun_rise_time"],
                             row["sun_set_time"],
                             _duration_str(row["total_sun_seconds"]),
                             row["moon_rise_1_time"],
                             row["moon_set_1_time"],
                             row["moon_rise_2_time"],
                             row["moon_set_2_time"],
                             _duration_str(row["total_moon_seconds"]),
                             row["overlap_start_time"],
                             row["overlap_end_time"],
                             _duration_str(row["total_overlap_seconds"]),
                             row["no_sun_no_moon_start_time"],
                             row["no_sun_no_moon_end_time"],
                             _duration_str(
                                 row["total_no_sun_no_moon_seconds"]),
                             "",  # Total-Sun-Days (daily row: blank)
                             "",  # Total-Moon-Days
                             "",  # Total-Overlap-Days
                             ""])  # Total-No-Sun-No-Moon-Days

        # Year total row (durations + whole-number days)
        writer.writerow(["Year Total",
                         "",
                         "",
                         _duration_str(total_sun),
                         "",
                         "",
                         "",
                         "",
                         _duration_str(total_moon),
                         "",
                         "",
                         _duration_str(total_overlap),
                         "",
                         "",
                         _duration_str(total_no_sun_no_moon),
                         _seconds_to_days(total_sun),
                         _seconds_to_days(total_moon),
                         _seconds_to_days(total_overlap),
                         _seconds_to_days(total_no_sun_no_moon)])

    totals = {"total_sun_seconds": total_sun,
              "total_moon_seconds": total_moon,
              "total_overlap_seconds": total_overlap,
              "total_no_sun_no_moon_seconds": total_no_sun_no_moon}
    return str(output_path), totals


def print_summary(totals: dict, location_name: str, year: int) -> None:
    """Print readable year totals to the console (whole-number days)."""
    sun_d = _seconds_to_days(totals["total_sun_seconds"])
    moon_d = _seconds_to_days(totals["total_moon_seconds"])
    overlap_d = _seconds_to_days(totals["total_overlap_seconds"])
    no_sun_no_moon_d = _seconds_to_days(totals["total_no_sun_no_moon_seconds"])
    print("")
    print(f"{location_name}-{year}")
    print(f"  Sun:                    {sun_d} days")
    print(f"  Moon:                   {moon_d} days")
    print(f"  Sun-Moon Overlap:       {overlap_d} days")
    print(f"  No Sun No Moon:         {no_sun_no_moon_d} days")
    print("")


def generate_summary_csv(summary_data: list[dict],
                         output_path: str | None = None) -> str:
    """
    Generate a summary CSV with yearly totals for all locations.
    """
    if output_path is None:
        output_path = "summary.csv"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Location",
                         "Year",
                         "Sun-Days",
                         "Moon-Days",
                         "Overlap-Days",
                         "No-Sun-No-Moon-Days"])
        for row in summary_data:
            writer.writerow([row["location"],
                             row["year"],
                             row["sun_days"],
                             row["moon_days"],
                             row["overlap_days"],
                             row["no_sun_no_moon_days"]])

    return str(output_path)


def main():
    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    locations = {
        # North America
        "NewYork": (40.7128, -74.0060, "America/New_York"),
        # South America
        "SaoPaulo": (-23.5505, -46.6333, "America/Sao_Paulo"),
        # Europe
        "London": (51.5072, -0.1276, "Europe/London"),
        # Africa
        "Cairo": (30.0444, 31.2357, "Africa/Cairo"),
        # Asia
        "Tokyo": (35.6895, 139.6917, "Asia/Tokyo"),
        # Oceania
        "Sydney": (-33.8688, 151.2093, "Australia/Sydney"),
        # Antarctica
        "McMurdo": (-77.8460, 166.6760, "Antarctica/McMurdo"),
        # India
        "Varanasi": (25.3176, 83.0062, "Asia/Kolkata"),
    }

    start_year = 2000
    end_year = datetime.datetime.now().year
    summary_data = []

    for location_name, (latitude, longitude, timezone_name) in locations.items():
        for year in range(start_year, end_year):
            output_path = results_dir / location_name / \
                f"{location_name}-{year}.csv"
            path, totals = generate_csv(latitude=latitude,
                                        longitude=longitude,
                                        timezone_name=timezone_name,
                                        year=year,
                                        output_path=output_path)
            print_summary(totals, location_name, year)

            # Collect summary data
            sun_d = _seconds_to_days(totals["total_sun_seconds"])
            moon_d = _seconds_to_days(totals["total_moon_seconds"])
            overlap_d = _seconds_to_days(totals["total_overlap_seconds"])
            no_sun_no_moon_d = _seconds_to_days(totals["total_no_sun_no_moon_seconds"])

            summary_data.append({"location": location_name,
                                 "year": year,
                                 "sun_days": sun_d,
                                 "moon_days": moon_d,
                                 "overlap_days": overlap_d,
                                 "no_sun_no_moon_days": no_sun_no_moon_d})

    # Generate summary CSV
    summary_csv_path = results_dir / "summary.csv"
    generate_summary_csv(summary_data, output_path=str(summary_csv_path))
    print(f"\nSummary CSV generated: {summary_csv_path}")


if __name__ == "__main__":
    main()
