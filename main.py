"""Start here: explicit inputs -> physical workflow -> stored evidence -> analysis."""

from pathlib import Path
import argparse
import json

ROOT = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(
        description="Independent microbubble simulation (exploratory, uncalibrated)"
    )
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Verify inputs, environment, states and discrete frequencies")
    sub.add_parser("history", help="Read frozen scientific admission, without rerunning it")
    r = sub.add_parser("single", help="Separate F1-only RK45 diagnostic, not a full-physics cloud")
    r.add_argument("--out", required=True)
    r = sub.add_parser("run", help="Run a configured HF or guarded LF trajectory")
    r.add_argument("--config", default=str(ROOT / "configs/minimal_hf.json"))
    r.add_argument("--out", required=True)
    r = sub.add_parser("analyze", help="Analyze actual stored fixed-ID positions")
    r.add_argument("trajectory")
    r.add_argument("--out", required=True)
    r.add_argument("--frequency", type=int, default=2500000)
    r.add_argument("--phase-deg", type=int, default=0)
    r = sub.add_parser("plot", help="PNG/PDF from an analysis directory")
    r.add_argument("directory")
    r = sub.add_parser("compare", help="Compare exact shared HF/LF times")
    r.add_argument("hf")
    r.add_argument("lf")
    r = sub.add_parser("validate", help="Run frozen-old/new numerical regression")
    r.add_argument("--out", required=True)
    args = p.parse_args()
    from microbubble.io import read, clean

    if args.command == "check":
        from workflows.validation import check

        result = check(ROOT)
    elif args.command == "single":
        from workflows.f10ag import context
        from workflows.diagnostics import single_bubble
        from microbubble.io import identity
        from microbubble.initial_conditions import load_state

        c = context(ROOT)
        x, _ = load_state(ROOT / "inputs/initial_states.h5", "AG32_random_0")
        row = next(
            r
            for r in read(ROOT / "evidence/f10ag/STATIC_RESULTS.json")["rows"]
            if r["frequency_Hz"] == 2500000 and r["phase_deg"] == 0
        )
        result = single_bubble(
            c, x, [r["position_m"][0] for r in row["roots"]], args.out, identity(ROOT)
        )
    elif args.command == "run":
        from workflows.f10ag import run

        result = run(ROOT, args.config, args.out)
    elif args.command == "history":
        from workflows.analysis import historical

        result = historical(ROOT)
    elif args.command == "analyze":
        from workflows.analysis import analyze

        rows = read(ROOT / "evidence/f10ag/STATIC_RESULTS.json")["rows"]
        row = next(
            r
            for r in rows
            if r["frequency_Hz"] == args.frequency and r["phase_deg"] == args.phase_deg
        )
        result = analyze(
            args.trajectory,
            args.out,
            [r["position_m"][0] for r in row["roots"]],
            read(ROOT / "configs/frozen/f10ag_protocol.json"),
        )
    elif args.command == "plot":
        from workflows.visualization import plot

        result = plot(args.directory)
    elif args.command == "compare":
        from workflows.analysis import compare

        result = compare(args.hf, args.lf)
    else:
        from workflows.validation import regression

        result = regression(ROOT, args.out)
    print(json.dumps(clean(result), indent=2, ensure_ascii=False))
    if isinstance(result, dict) and (result.get("status") == "FAIL" or result.get("PASS") is False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
