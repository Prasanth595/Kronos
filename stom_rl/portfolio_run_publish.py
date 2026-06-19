"""Publish a consolidated portfolio run into ``webui/rl_runs``.

Pages 10/11/12 emit portfolio artifacts (train smoke, expanding-window walk
forward, read-only paper replay) under ``.omx/artifacts``.  The v2 dashboard
serves runs strictly from ``webui/rl_runs`` through the existing ``/api/rl/*``
routes, so this module copies the *already produced* portfolio artifacts into a
single run directory that the read-only dashboard recognises.

It does not run any model, broker, or order code.  It only reads existing CSV /
JSON artifacts and re-emits them under the run-directory layout the dashboard
understands, plus a ``portfolio_paper_summary.json`` signature file that marks
the directory as a portfolio run.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_NAME = "stom_1s_2025_portfolio_paper"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "webui" / "rl_runs" / DEFAULT_RUN_NAME

DEFAULT_PAPER_DIR = REPO_ROOT / ".omx" / "artifacts" / "page12_paper"
DEFAULT_WALK_FORWARD_DIR = REPO_ROOT / ".omx" / "artifacts" / "page11_walk_forward"
DEFAULT_TRAIN_DIR = REPO_ROOT / ".omx" / "artifacts" / "page10_train"

# Signature file the dashboard uses to detect a portfolio paper run.
SIGNATURE_FILE = "portfolio_paper_summary.json"


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def _copy_if_exists(src: Path, dst: Path) -> bool:
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        return True
    return False


def publish_portfolio_run(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    paper_dir: Path = DEFAULT_PAPER_DIR,
    walk_forward_dir: Path = DEFAULT_WALK_FORWARD_DIR,
    train_dir: Path = DEFAULT_TRAIN_DIR,
) -> Dict[str, Any]:
    """Consolidate portfolio artifacts into ``output_dir`` for the dashboard.

    Returns the signature payload that was written.  Raises ``FileNotFoundError``
    if the required paper-replay summary is missing.
    """

    output_dir = Path(output_dir)
    paper_summary_path = Path(paper_dir) / "paper_replay_summary.json"
    if not paper_summary_path.is_file():
        raise FileNotFoundError(
            f"paper_replay_summary.json not found at {paper_summary_path}. "
            "Run the Page 12 paper replay first."
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    paper_summary = _read_json(paper_summary_path)
    copied: Dict[str, bool] = {}

    # Paper replay artifacts (NAV curve, decisions/positions, risk + blocked logs).
    copied["nav_csv"] = _copy_if_exists(Path(paper_dir) / "nav.csv", output_dir / "nav.csv")
    copied["decisions_csv"] = _copy_if_exists(
        Path(paper_dir) / "decisions.csv", output_dir / "decisions.csv"
    )
    copied["candidates_csv"] = _copy_if_exists(
        Path(paper_dir) / "candidates.csv", output_dir / "candidates.csv"
    )
    copied["risk_triggers_json"] = _copy_if_exists(
        Path(paper_dir) / "risk_triggers.json", output_dir / "risk_triggers.json"
    )
    copied["blocked_actions_json"] = _copy_if_exists(
        Path(paper_dir) / "blocked_actions.json", output_dir / "blocked_actions.json"
    )

    # Walk-forward fold summary (Page 11).
    wf_report_path = Path(walk_forward_dir) / "portfolio_walk_forward_report.json"
    copied["walk_forward_folds_csv"] = _copy_if_exists(
        Path(walk_forward_dir) / "portfolio_walk_forward_folds.csv",
        output_dir / "portfolio_walk_forward_folds.csv",
    )
    copied["walk_forward_report_json"] = _copy_if_exists(
        wf_report_path, output_dir / "portfolio_walk_forward_report.json"
    )

    # Train smoke trades (Page 10) — gives the trades table a real source.
    copied["trades_csv"] = _copy_if_exists(Path(train_dir) / "trades.csv", output_dir / "trades.csv")

    # Live step events (Page 14) — the train smoke now emits per-step
    # ``rl_live_events.jsonl`` (NAV mapped to equity) so the dashboard's
    # realtime follow/replay view streams the portfolio run like a live
    # training session.  The existing ``/table/events`` route serves whichever
    # of these files is present, so copying them is all the wiring needed.
    copied["live_events_jsonl"] = _copy_if_exists(
        Path(train_dir) / "rl_live_events.jsonl", output_dir / "rl_live_events.jsonl"
    )
    copied["live_summary_json"] = _copy_if_exists(
        Path(train_dir) / "rl_live_summary.json", output_dir / "rl_live_summary.json"
    )

    walk_forward_summary: Dict[str, Any] = {}
    if wf_report_path.is_file():
        try:
            walk_forward_summary = dict(_read_json(wf_report_path).get("summary", {}))
        except (ValueError, OSError):
            walk_forward_summary = {}

    summary = dict(paper_summary.get("summary", {}))
    summary.setdefault("read_only", True)
    summary["walk_forward_n_folds"] = walk_forward_summary.get("n_folds")
    summary["walk_forward_best_policy"] = walk_forward_summary.get("best_policy_by_return")
    summary["walk_forward_holdout"] = walk_forward_summary.get("holdout")

    signature: Dict[str, Any] = {
        "mode": "stom_rl_portfolio_paper_run",
        "run_name": output_dir.name,
        "config": paper_summary.get("config", {}),
        "summary": summary,
        "walk_forward_summary": walk_forward_summary,
        "sources": {
            "paper_dir": str(Path(paper_dir)),
            "walk_forward_dir": str(Path(walk_forward_dir)),
            "train_dir": str(Path(train_dir)),
        },
        "copied_artifacts": copied,
    }
    _write_json(output_dir / SIGNATURE_FILE, signature)
    return signature


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--paper-dir", default=str(DEFAULT_PAPER_DIR))
    parser.add_argument("--walk-forward-dir", default=str(DEFAULT_WALK_FORWARD_DIR))
    parser.add_argument("--train-dir", default=str(DEFAULT_TRAIN_DIR))
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    signature = publish_portfolio_run(
        output_dir=Path(args.output_dir),
        paper_dir=Path(args.paper_dir),
        walk_forward_dir=Path(args.walk_forward_dir),
        train_dir=Path(args.train_dir),
    )
    print(json.dumps(signature, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
