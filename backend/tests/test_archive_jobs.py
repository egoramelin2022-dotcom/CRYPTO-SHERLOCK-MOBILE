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
        if progress_callback:
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
