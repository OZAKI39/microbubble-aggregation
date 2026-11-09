"""
Start here: explicit inputs -> pretraining-tier trajectory -> stored run.
Commands: check (imports and inputs), run (a PRETRAIN config).
"""

from pathlib import Path
import argparse
import json

ROOT = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(
        description="Independent microbubble simulation (exploratory, uncalibrated)"
    )
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Verify imports and inputs")
    r = sub.add_parser("run", help="Run a configured PRETRAIN trajectory")
    r.add_argument("--config", required=True)
    r.add_argument("--out", required=True)
    args = p.parse_args()
    from microbubble.io import clean

    if args.command == "check":
        # 导入一遍各个物理模块，看有没有坏的
        from workflows.validation import check

        result = check(ROOT)
    else:
        # 整条调用链（准备阶段 → 时间循环 → 写结果）
        from workflows.f10ag import run

        result = run(ROOT, args.config, args.out)

    # 把结果打印到屏幕
    print(json.dumps(clean(result), indent=2, ensure_ascii=False))
    
    # 设定退出码：运行失败（status 是 FAIL）时，让程序以 1 退出
    if isinstance(result, dict) and (result.get("status") == "FAIL" or result.get("PASS") is False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
