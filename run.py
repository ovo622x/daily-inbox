#!/usr/bin/env python3
"""通知漏斗 · 一键入口。

  python run.py            抓取微信/钉钉窗口并生成页面
  python run.py --build    跳过抓取，只用现有数据重新生成
  python run.py --open     生成后用默认浏览器打开
  python run.py --app wechat  只抓某一个来源（可重复）
"""

import argparse
import os
import sys
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)


def main():
    ap = argparse.ArgumentParser(description="把微信和钉钉的通知收敛成每日待办页面")
    ap.add_argument("--build", action="store_true", help="跳过抓取，只用 data/state.json 重新生成")
    ap.add_argument("--open", action="store_true", help="生成后用浏览器打开")
    ap.add_argument("--app", choices=["wechat", "dingtalk"], action="append",
                    help="只抓指定来源，可重复使用")
    args = ap.parse_args()

    if not args.build:
        import collect
        collect.main(args.app or None)

    import build
    build.build()

    out = os.path.join(ROOT, "site", "index.html")
    if args.open and os.path.exists(out):
        webbrowser.open("file:///" + out.replace("\\", "/"))


if __name__ == "__main__":
    main()
