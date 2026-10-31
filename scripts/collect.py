"""抓取微信 / 钉钉窗口快照，供后续识别待办。只读，不修改应用数据。"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import winctl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = os.path.join(ROOT, "data", "snapshots")
STATUS = os.path.join(ROOT, "data", "status.json")


def main(apps=None):
    apps = apps or ["wechat", "dingtalk"]
    os.makedirs(SHOT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    report = {"time": datetime.now().isoformat(timespec="seconds"), "shots": []}
    status = {"checkedAt": report["time"], "apps": {}}

    for app in apps:
        state, detail = winctl.app_state(app)
        entry = {"state": state, "detail": detail, "captured": False}
        win = winctl.find_main_window(app) if state == "online" else None
        if not win:
            report["shots"].append({"app": app, "ok": False, "reason": detail})
            status["apps"][app] = entry
            print(f"[{app}] {state} - {detail}")
            continue
        out = os.path.join(SHOT_DIR, f"{app}_{stamp}.png")
        try:
            meta = winctl.capture(win["hwnd"], out)
            entry["captured"] = meta["filled"] > 0.05
            if not entry["captured"]:
                entry["state"] = "blank"
                entry["detail"] = "画面为空，窗口可能被遮挡"
            meta.update({"app": app, "ok": entry["captured"]})
            if not meta["ok"]:
                meta["reason"] = entry["detail"]
            report["shots"].append(meta)
            print(f"[{app}] {meta['size']} filled={meta['filled']} -> {out}")
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

    keep = 40
    files = sorted(f for f in os.listdir(SHOT_DIR) if f.lower().endswith(".png"))
    for old in files[:-keep]:
        try:
            os.remove(os.path.join(SHOT_DIR, old))
        except OSError:
            pass
    return report


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a in ("wechat", "dingtalk")]
    res = main(args or None)
    ok = sum(1 for s in res["shots"] if s.get("ok"))
    print(f"完成：{ok}/{len(res['shots'])} 张可用")
