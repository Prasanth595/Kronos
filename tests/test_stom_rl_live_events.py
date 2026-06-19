import json
from pathlib import Path

from stom_rl.rl_events import RlLiveEvent, RlLiveEventWriter, read_live_events, summarize_live_event_file


def test_live_event_writer_roundtrips_jsonl_tail(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    writer = RlLiveEventWriter(path, run_id="run-a")
    writer.reset()
    writer.write_step(
        algorithm="dqn",
        phase="train",
        global_step=1,
        action=1,
        reward=0.25,
        episode_id="ep-1",
        timestamp="2025-01-03T09:00:01",
        price=101.0,
        position=1,
        equity=None,
        info={"invalid_action": False},
    )
    writer.write(
        RlLiveEvent(
            run_id="run-a",
            algorithm="dqn",
            phase="eval",
            global_step=2,
            action=2,
            reward=float("nan"),
            equity=1.01,
        )
    )
    path.write_text(path.read_text(encoding="utf-8") + "not-json\\n", encoding="utf-8")
    rows, truncated = read_live_events(path, limit=1)
    assert truncated is True
    assert rows[0]["phase"] == "eval"
    assert rows[0]["reward"] is None
    assert rows[0]["action_name"] == "sell"

    summary = summarize_live_event_file(path)
    assert summary["event_count"] == 2
    assert summary["phases"] == {"eval": 1, "train": 1}
    assert summary["latest_equity"] == 1.01


def test_live_event_payload_is_json_serializable():
    payload = RlLiveEvent(
        run_id="run-b",
        algorithm="ppo",
        phase="train",
        global_step=3,
        action=0,
        reward=0.0,
    ).to_dict()
    assert payload["schema_version"] == "stom_rl_live_event.v1"
    assert payload["action_name"] == "hold"
    json.dumps(payload)
