"""抓取微信 / 钉钉窗口快照，供后续识别待办。只读截图，不修改应用数据。"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import winctl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = os.path.join(ROOT, "data", "snapshots")
STATUS = os.path.join(ROOT, "data", "status.json")
KEEP_PNGS = 80


def main(apps=None, screens=12):
    apps = apps or ["wechat", "dingtalk"]
    os.makedirs(SHOT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    report = {"time": datetime.now().isoformat(timespec="seconds"), "shots": []}
    status = {"checkedAt": report["time"], "apps": {}}

    for app in apps:
        state, detail = winctl.app_state(app)
        entry = {"state": state, "detail": detail, "captured": False, "screens": 0}
        win = winctl.find_main_window(app) if state == "online" else None
        if not win:
            report["shots"].append({"app": app, "ok": False, "reason": detail})
            status["apps"][app] = entry
            print(f"[{app}] {state} - {detail}")
            continue

        def path_for(i, _app=app):
            return os.path.join(SHOT_DIR, f"{_app}_{stamp}_p{i:02d}.png")

        try:
            shots = winctl.scroll_capture(win["hwnd"], app, path_for,
                                          max_screens=screens, step=700, settle=0.5)
            entry["screens"] = len(shots)
            entry["captured"] = bool(shots) and shots[0]["filled"] > 0.05
            if not entry["captured"]:
                entry["state"] = "blank"
                entry["detail"] = "画面为空，窗口可能被遮挡"
            elif len(shots) == 1:
                entry["detail"] = "只采到 1 屏，列表可能已到底或滚动未生效"
            report["shots"].append({"app": app, "ok": entry["captured"],
                                    "screens": entry["screens"],
                                    "files": [s["path"] for s in shots]})
            print(f"[{app}] {entry['screens']} 屏, filled={shots[0]['filled'] if shots else 0}")
        except Exception as exc:
            entry["state"] = "error"
            entry["detail"] = str(exc)
            report["shots"].append({"app": app, "ok": False, "reason": str(exc)})
            print(f"[{app}] 失败: {exc}")
        status["apps"][app] = entry

    with open(os.path.join(SHOT_DIR, "last_run.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    with open(STATUS, "w", encoding="utf-8") as fh:
        json.dump(status, fh, ensure_ascii=False, indent=2)

    files = sorted(f for f in os.listdir(SHOT_DIR) if f.lower().endswith(".png"))
    for old in files[:-KEEP_PNGS]:
        try:
            os.remove(os.path.join(SHOT_DIR, old))
        except OSError:
            pass
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="采集微信/钉钉窗口画面")
    ap.add_argument("--app", choices=["wechat", "dingtalk"], action="append")
    ap.add_argument("--screens", type=int, default=12, help="每个来源最多抓几屏")
    args = ap.parse_args()
    res = main(args.app or None, args.screens)
    ok = sum(1 for s in res["shots"] if s.get("ok"))
    total = sum(s.get("screens", 0) for s in res["shots"])
    print(f"完成：{ok}/{len(res['shots'])} 个来源可用，共 {total} 屏")
