import hashlib
import json
import sqlite3
from uuid import uuid4

import pytest

from app.market_data.candles import Candle
from app.research.experiment_ledger import ExperimentLedger, fingerprint_candles


def make_candles(count=4):
    rows = []
    for index in range(count):
        price = 100.0 + index
        opened = index * 900_000
        rows.append(Candle(
            symbol="BTCUSDT", interval="15m", open_time=opened,
            open=price, high=price + 1, low=price - 1, close=price + 0.5,
            volume=10.0, close_time=opened + 899_999,
            quote_volume=1000.0, trade_count=10,
            taker_buy_base=5.0, taker_buy_quote=500.0,
        ))
    return rows


def start(ledger, run_id=None):
    rows = make_candles()
    run_id = run_id or str(uuid4())
    ledger.start_run(
        run_id=run_id, core_version="0.1.0", symbol="BTCUSDT",
        interval="15m", query_start_time=900_000,
        query_end_time=2 * 900_000 + 899_999, mode="free",
        parameters={"top_k": 5, "fee_bps_per_side": 5.0},
        input_fingerprint=fingerprint_candles(rows),
        input_candle_count=len(rows),
    )
    return run_id


def sample_result(run_id):
    return {
        "run_id": run_id, "core_version": "0.1.0",
        "research_status": "REQUIRES_WALK_FORWARD_VALIDATION",
        "decision": {"abstain": True, "trading_signal": None},
        "modules": {"pattern_intelligence": {"analogs_returned": 5}},
    }


def test_ledger_persists_completed_run_and_verifiable_result(tmp_path):
    ledger = ExperimentLedger(tmp_path / "analytics.db")
    run_id = start(ledger)
    result = sample_result(run_id)
    completed = ledger.complete_run(run_id, result)

    assert completed["status"] == "completed"
    assert completed["result_sha256"] == hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()
    record = ledger.get_run(run_id)
    assert record["run"]["parameters"] == {
        "fee_bps_per_side": 5.0, "top_k": 5
    }
    assert record["result"] == result
    assert [event["event_type"] for event in record["events"]] == [
        "started", "completed"
    ]
    assert record["events"][1]["previous_hash"] == record["events"][0]["event_hash"]
    assert ledger.verify_integrity()["ok"] is True


def test_ledger_rejects_update_and_delete_mutations(tmp_path):
    path = tmp_path / "analytics.db"
    ledger = ExperimentLedger(path)
    run_id = start(ledger)
    ledger.complete_run(run_id, sample_result(run_id))
    connection = sqlite3.connect(path)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "UPDATE experiment_runs SET mode='five_stage' WHERE run_id=?",
            (run_id,),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "DELETE FROM experiment_events WHERE run_id=?", (run_id,)
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "UPDATE experiment_results SET result_json='{}' WHERE run_id=?",
            (run_id,),
        )
    connection.close()


def test_ledger_failed_run_is_recorded_without_leaking_exception_message(tmp_path):
    ledger = ExperimentLedger(tmp_path / "analytics.db")
    run_id = start(ledger)
    ledger.fail_run(run_id, "ValueError: private/path/should/not/be/stored")
    record = ledger.get_run(run_id)
    assert record["result"] is None
    assert record["events"][-1]["event_type"] == "failed"
    assert record["events"][-1]["payload"] == {"error_type": "ValueErrorprivateshouldnotbestored"}
    assert ledger.verify_integrity()["ok"] is True


def test_ledger_rejects_terminal_transition_twice_and_duplicate_run(tmp_path):
    ledger = ExperimentLedger(tmp_path / "analytics.db")
    run_id = start(ledger)
    ledger.fail_run(run_id, "RuntimeError")
    with pytest.raises(ValueError, match="terminal event"):
        ledger.fail_run(run_id, "RuntimeError")
    with pytest.raises(sqlite3.IntegrityError):
        start(ledger, run_id=run_id)


def test_ledger_lists_runs_with_filters_and_validates_pagination(tmp_path):
    ledger = ExperimentLedger(tmp_path / "analytics.db")
    first = start(ledger)
    second = start(ledger)
    ledger.complete_run(first, sample_result(first))
    ledger.fail_run(second, "ValueError")
    rows = ledger.list_runs(limit=10, symbol="BTCUSDT", interval="15m")
    assert {row["run_id"] for row in rows} == {first, second}
    assert {row["status"] for row in rows} == {"completed", "failed"}
    assert ledger.list_runs(limit=1)[0]["run_id"] == second
    with pytest.raises(ValueError, match="limit"):
        ledger.list_runs(limit=0)


def test_candle_fingerprint_is_stable_and_sensitive_to_data():
    original = make_candles()
    assert fingerprint_candles(original) == fingerprint_candles(list(original))
    changed = list(original)
    item = changed[-1]
    changed[-1] = Candle(
        symbol=item.symbol, interval=item.interval, open_time=item.open_time,
        open=item.open, high=item.high, low=item.low, close=item.close + 0.01,
        volume=item.volume, close_time=item.close_time,
        quote_volume=item.quote_volume, trade_count=item.trade_count,
        taker_buy_base=item.taker_buy_base, taker_buy_quote=item.taker_buy_quote,
    )
    assert fingerprint_candles(changed) != fingerprint_candles(original)


def test_ledger_detects_tampered_event_hash(tmp_path):
    path = tmp_path / "analytics.db"
    ledger = ExperimentLedger(path)
    run_id = start(ledger)
    ledger.complete_run(run_id, sample_result(run_id))
    connection = sqlite3.connect(path)
    connection.execute(
        "DROP TRIGGER experiment_events_no_update"
    )
    connection.execute(
        "UPDATE experiment_events SET payload_json='{}' WHERE run_id=? AND sequence=1",
        (run_id,),
    )
    connection.commit()
    connection.close()
    audit = ledger.verify_integrity()
    assert audit["ok"] is False
    assert any("event hash mismatch" in issue for issue in audit["issues"])


def test_ledger_rejects_invalid_fingerprint_and_non_uuid(tmp_path):
    ledger = ExperimentLedger(tmp_path / "analytics.db")
    rows = make_candles()
    with pytest.raises(ValueError, match="UUID"):
        ledger.start_run(
            run_id="not-a-uuid", core_version="0.1.0", symbol="BTCUSDT",
            interval="15m", query_start_time=0, query_end_time=1,
            mode="free", parameters={}, input_fingerprint="x" * 64,
            input_candle_count=len(rows),
        )
    with pytest.raises(ValueError, match="fingerprint"):
        ledger.start_run(
            run_id=str(uuid4()), core_version="0.1.0", symbol="BTCUSDT",
            interval="15m", query_start_time=0, query_end_time=1,
            mode="free", parameters={}, input_fingerprint="INVALID",
            input_candle_count=len(rows),
        )
