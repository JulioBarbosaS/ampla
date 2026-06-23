"""Scheduling algebra (Epic 08 · 8.1): next_run is pure + deterministic, so the
tests pin exact instants — no wall clock involved."""

from datetime import UTC, datetime

import pytest

from app.services.scheduler import next_run, validate_spec


def at(y=2026, mo=6, d=23, h=12, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


class TestInterval:
    def test_adds_seconds(self):
        assert next_run("interval", "300", at(h=12, mi=0)) == at(h=12, mi=5)

    def test_rejects_non_positive(self):
        with pytest.raises(ValueError):
            validate_spec("interval", "0")
        with pytest.raises(ValueError):
            validate_spec("interval", "abc")


class TestOnce:
    def test_future_instant_fires_once(self):
        assert next_run("once", "2026-06-23T18:00:00+00:00", at(h=12)) == at(h=18)

    def test_past_instant_never_fires(self):
        assert next_run("once", "2026-06-23T06:00:00+00:00", at(h=12)) is None

    def test_naive_instant_is_utc(self):
        assert next_run("once", "2026-06-23T18:00:00", at(h=12)) == at(h=18)


class TestCron:
    def test_every_minute(self):
        assert next_run("cron", "* * * * *", at(h=12, mi=0)) == at(h=12, mi=1)

    def test_daily_at_fixed_time(self):
        # 09:30 every day; from 12:00 → tomorrow 09:30
        assert next_run("cron", "30 9 * * *", at(d=23, h=12)) == at(d=24, h=9, mi=30)

    def test_step_minutes(self):
        # */15 → next quarter hour
        assert next_run("cron", "*/15 * * * *", at(h=12, mi=7)) == at(h=12, mi=15)

    def test_range_and_list(self):
        # minute 0 of hours 9 or 17 → next is 17:00 same day from 12:00
        assert next_run("cron", "0 9,17 * * *", at(d=23, h=12)) == at(d=23, h=17, mi=0)

    def test_day_of_week(self):
        # 2026-06-23 is a Tuesday; "0 0 * * 1" (Monday) → next Monday 2026-06-29
        assert next_run("cron", "0 0 * * 1", at(d=23, h=12)) == at(d=29, h=0, mi=0)

    def test_dom_or_dow_when_both_restricted(self):
        # cron OR-semantics: day 1 OR Sunday. From mid-June 2026, the 1st of July
        # comes before the next listed weekday only if sooner — assert it matches
        # the 1st (a Wednesday) rather than waiting for a weekday-only rule.
        assert next_run("cron", "0 0 1 * 0", at(y=2026, mo=6, d=23, h=12)) == at(
            y=2026, mo=6, d=28, h=0, mi=0
        )  # 2026-06-28 is the first Sunday reached before July 1

    def test_invalid_specs_rejected(self):
        for bad in ("* * * *", "60 * * * *", "* 24 * * *", "*/0 * * * *", "5-2 * * * *"):
            with pytest.raises(ValueError):
                validate_spec("cron", bad)


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        next_run("weekly", "x", at())
    with pytest.raises(ValueError):
        validate_spec("weekly", "x")
