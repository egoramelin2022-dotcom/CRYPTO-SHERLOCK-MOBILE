from pathlib import Path

from app.research import archive_jobs, jobs


def test_archive_job_writes_only_to_separate_staging_database(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    analytics = tmp_path / "analytics.db"
    staging = tmp_path / "staging.db"
    raw = tmp_path / "raw"
    source.touch()
    monkeypatch.setattr(jobs, "_configured_paths", lambda: (source, analytics))
    monkeypatch.setenv("SHERLOCK_ARCHIVE_STAGING_DB", str(staging))
    monkeypatch.setenv("SHERLOCK_ARCHIVE_RAW_DIR", str(raw))

    def fake_download(start, end, raw_dir, db_path, progress_callback=None):
        assert start == "2017-08"
        assert end == "2017-09"
        assert raw_dir == raw
        assert db_path == staging
        assert progress_callback is not None
        progress_callback("15m 2017-08: ok; inserted=12")
        return 12

    monkeypatch.setattr(archive_jobs, "download_archives", fake_download)
    job = jobs._new_job("binance_archive_download")
    archive_jobs.run_archive_download(job.job_id, "2017-08", "2017-09")
    result = jobs.get_job(job.job_id)
    assert result["status"] == "completed"
    assert result["result"]["inserted_this_run"] == 12
    assert "staging" in result["result"]["staging_database"]
    assert "Source market database was not modified" in result["result"]["note"]


def test_archive_job_rejects_source_database_as_staging(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    source.touch()
    analytics = tmp_path / "analytics.db"
    monkeypatch.setattr(jobs, "_configured_paths", lambda: (source, analytics))
    monkeypatch.setenv("SHERLOCK_ARCHIVE_STAGING_DB", str(source))
    job = jobs._new_job("binance_archive_download")
    archive_jobs.run_archive_download(job.job_id, "2017-08", "2017-09")
    result = jobs.get_job(job.job_id)
    assert result["status"] == "failed"
    assert "separate" in result["error"]



def test_recent_sync_job_targets_only_current_month_closed_candles(
    tmp_path, monkeypatch
):
    from datetime import datetime, timezone
    from app.market_data.sync import SyncResult

    source = tmp_path / "source.db"
    analytics = tmp_path / "analytics.db"
    staging = tmp_path / "staging.db"
    source.touch()
    monkeypatch.setattr(jobs, "_configured_paths", lambda: (source, analytics))
    monkeypatch.setenv("SHERLOCK_ARCHIVE_STAGING_DB", str(staging))
    calls = []

    class FakeEngine:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def sync(self, **kwargs):
            calls.append(kwargs)
            return SyncResult("COMPLETE", 10, 10, kwargs["end_ms"] + 1, 1)

    monkeypatch.setattr(archive_jobs, "HistoricalSyncEngine", FakeEngine)
    job = jobs._new_job("binance_recent_sync")
    reference = datetime(2026, 11, 13, 10, 40, tzinfo=timezone.utc)
    archive_jobs.run_recent_sync_job(job.job_id, now=reference)

    result = jobs.get_job(job.job_id)
    assert result["status"] == "completed"
    assert [call["interval"] for call in calls] == ["15m", "4h", "1d"]
    assert all(call["symbol"] == "BTCUSDT" for call in calls)
    assert all(call["resume"] is True for call in calls)
    assert calls[0]["start_ms"] == int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp() * 1000)
    assert calls[0]["end_ms"] == int(datetime(2026, 11, 13, 10, 15, tzinfo=timezone.utc).timestamp() * 1000)
    assert calls[1]["end_ms"] == int(datetime(2026, 11, 13, 4, 0, tzinfo=timezone.utc).timestamp() * 1000)
    assert calls[2]["end_ms"] == int(datetime(2026, 11, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    assert result["result"]["intervals"]["15m"]["status"] == "COMPLETE"
    assert source.stat().st_size == 0
    assert analytics.exists() is False


def test_recent_sync_job_skips_intervals_without_a_closed_current_month_candle(
    tmp_path, monkeypatch
):
    from datetime import datetime, timezone

    source = tmp_path / "source.db"
    analytics = tmp_path / "analytics.db"
    staging = tmp_path / "staging.db"
    source.touch()
    monkeypatch.setattr(jobs, "_configured_paths", lambda: (source, analytics))
    monkeypatch.setenv("SHERLOCK_ARCHIVE_STAGING_DB", str(staging))

    class NoCallEngine:
        def __init__(self, connection):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def sync(self, **kwargs):
            raise AssertionError("there should be no closed current-month candle yet")

    monkeypatch.setattr(archive_jobs, "HistoricalSyncEngine", NoCallEngine)
    job = jobs._new_job("binance_recent_sync")
    archive_jobs.run_recent_sync_job(
        job.job_id,
        now=datetime(2026, 12, 1, 0, 5, tzinfo=timezone.utc),
    )
    result = jobs.get_job(job.job_id)
    assert result["status"] == "completed"
    assert all(
        item["status"] == "NO_CLOSED_CANDLES"
        for item in result["result"]["intervals"].values()
    )
