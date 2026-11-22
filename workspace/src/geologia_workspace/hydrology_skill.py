"""Lightweight descriptive skill for groundwater level CSV time series.

This local tool performs quality checks and descriptive statistics only. It
does not calibrate a groundwater model, estimate yield, or forecast levels.
"""
from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import math
from pathlib import Path
import statistics
from typing import Any

MAX_ANALYSIS_BYTES = 20 * 1024 * 1024
MAX_ANALYSIS_ROWS = 250_000
ALLOWED_REFERENCES = {"elevation", "depth_to_water"}


def analyze_water_level_timeseries(
    path: str | Path,
    *,
    vertical_datum: str | None = None,
    measurement_reference: str | None = None,
) -> dict[str, Any]:
    """Validate and summarize a CSV with timestamp/date and water_level_m columns."""
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("input must be a regular, non-symlink CSV file")
    if source.stat().st_size > MAX_ANALYSIS_BYTES:
        raise ValueError("time-series file exceeds the local analysis size limit")

    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    timestamps: list[datetime] = []
    measurements: list[float] = []
    timestamp_header: str | None = None

    try:
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            headers = next(reader, None)
            if not headers:
                raise ValueError("CSV header is missing")
            normalized = [name.strip().casefold() for name in headers]
            if any(not name for name in normalized):
                raise ValueError("CSV contains an empty column name")
            if len(set(normalized)) != len(normalized):
                raise ValueError("CSV column names must be unique after normalization")
            timestamp_header = next(
                (name for name in ("timestamp", "datetime", "date") if name in normalized),
                None,
            )
            if timestamp_header is None:
                raise ValueError("expected timestamp, datetime, or date column")
            if "water_level_m" not in normalized:
                raise ValueError("expected water_level_m column with explicit metre units")
            time_index = normalized.index(timestamp_header)
            value_index = normalized.index("water_level_m")
            timezone_flags: set[bool] = set()
            for row_number, row in enumerate(reader, start=2):
                if not row or all(not cell.strip() for cell in row):
                    continue
                if row_number > MAX_ANALYSIS_ROWS + 1:
                    raise ValueError("time-series row count exceeds local analysis limit")
                if len(row) != len(headers):
                    errors.append({"code": "row_width", "row": row_number})
                    continue
                try:
                    raw_time = row[time_index].strip()
                    parsed = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                    timezone_flags.add(parsed.utcoffset() is not None)
                    raw_value = row[value_index].strip()
                    value = float(raw_value)
                    if not math.isfinite(value):
                        raise ValueError("water_level_m must be finite")
                except (ValueError, OverflowError):
                    errors.append({"code": "invalid_timestamp_or_measurement", "row": row_number})
                    continue
                timestamps.append(parsed)
                measurements.append(value)
    except (UnicodeDecodeError, csv.Error, OSError) as exc:
        raise ValueError(f"could not parse time-series CSV: {exc}") from exc

    if not timestamps:
        errors.append({"code": "no_valid_measurements"})
    if len(timezone_flags) > 1:
        errors.append({"code": "mixed_timezone_awareness"})
    if errors:
        return {
            "skill_id": "hydrology.water_level_descriptive",
            "skill_version": "1.0.0",
            "status": "invalid_input",
            "error_count": len(errors),
            "errors": errors[:50],
            "input_sha256": digest.hexdigest(),
            "analysis_level": "descriptive_only",
            "scientific_interpretation": False,
            "model_executed": False,
        }

    original_order = list(timestamps)
    if original_order != sorted(original_order):
        warnings.append({
            "code": "timestamps_not_monotonic",
            "message": "Rows are not chronological.",
        })
    unique_times = sorted(set(timestamps))
    duplicate_count = len(timestamps) - len(unique_times)
    if duplicate_count:
        warnings.append({
            "code": "duplicate_timestamps",
            "count": duplicate_count,
            "message": "Duplicate timestamps are retained in summary statistics.",
        })
    if timezone_flags == {False}:
        warnings.append({
            "code": "timezone_not_declared",
            "message": "Timezone missing; intervals use naive local clock time.",
        })

    intervals = [
        (later - earlier).total_seconds()
        for earlier, later in zip(unique_times, unique_times[1:])
    ]
    positive_intervals = [seconds for seconds in intervals if seconds > 0]
    # Lower median prevents one long outage from inflating the gap baseline.
    median_interval = (
        statistics.median_low(positive_intervals) if positive_intervals else None
    )
    gap_threshold = median_interval * 3 if median_interval is not None else None
    gaps = [
        seconds for seconds in positive_intervals
        if gap_threshold is not None and seconds > gap_threshold
    ]
    max_gap = max(positive_intervals, default=None)

    mean_value = statistics.fmean(measurements)
    median_value = statistics.median(measurements)
    std_value = statistics.pstdev(measurements) if len(measurements) > 1 else 0.0
    slope = None
    if len(unique_times) >= 2:
        origin = unique_times[0]
        x_values = [(item - origin).total_seconds() / 86400 for item in timestamps]
        x_mean = statistics.fmean(x_values)
        y_mean = mean_value
        denominator = sum((x - x_mean) ** 2 for x in x_values)
        if denominator:
            slope = sum(
                (x - x_mean) * (y - y_mean)
                for x, y in zip(x_values, measurements)
            ) / denominator

    reference_valid = measurement_reference in ALLOWED_REFERENCES
    metadata_complete = bool(vertical_datum and vertical_datum.strip()) and reference_valid
    if not vertical_datum or not vertical_datum.strip():
        warnings.append({
            "code": "vertical_datum_missing",
            "message": "Declare the vertical datum before interpreting water-level elevations.",
        })
    if not reference_valid:
        warnings.append({
            "code": "measurement_reference_missing",
            "message": "Specify whether values are elevation or depth_to_water.",
        })

    return {
        "skill_id": "hydrology.water_level_descriptive",
        "skill_version": "1.0.0",
        "status": "completed_with_warnings" if warnings else "completed",
        "analysis_level": "descriptive_only",
        "metadata_status": "declared" if metadata_complete else "incomplete",
        "vertical_datum_declared": vertical_datum.strip() if vertical_datum else None,
        "measurement_reference": measurement_reference if reference_valid else None,
        "input_sha256": digest.hexdigest(),
        "row_count": len(measurements),
        "unique_timestamp_count": len(unique_times),
        "duplicate_timestamp_count": duplicate_count,
        "timestamp_header": timestamp_header,
        "timezone_aware": timezone_flags == {True},
        "start_time": min(timestamps).isoformat(),
        "end_time": max(timestamps).isoformat(),
        "statistics": {
            "minimum_m": min(measurements),
            "maximum_m": max(measurements),
            "mean_m": mean_value,
            "median_m": median_value,
            "population_standard_deviation_m": std_value,
            "descriptive_linear_slope_m_per_day": slope,
        },
        "sampling": {
            "median_interval_seconds": median_interval,
            "gap_threshold_seconds": gap_threshold,
            "gap_count": len(gaps),
            "maximum_interval_seconds": max_gap,
        },
        "warnings": warnings,
        "scientific_interpretation": False,
        "groundwater_model_executed": False,
        "forecast_generated": False,
        "drilling_or_yield_recommendation": False,
    }
