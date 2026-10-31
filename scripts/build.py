"""把 data/state.json 渲染成 site/index.html。"""

import html
import json
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "data", "state.json")
STATUS_FILE = os.path.join(ROOT, "data", "status.json")
TEMPLATE = os.path.join(ROOT, "site", "template.html")
OUT = os.path.join(ROOT, "site", "index.html")

STATE_LABELS = {
    "online": ("on", "在线"),
    "no-window": ("warn", "无窗口"),
    "blank": ("warn", "画面为空"),
    "error": ("warn", "采集出错"),
    "offline": ("off", "未打开"),
    "unknown": ("off", "未检测"),
}

SECTIONS = [
    ("催着的", ("overdue", "deadline"), "先在下面这几条里挑一条动手"),
    ("等你回复", ("reply",), "别人在等你一句话"),
    ("有空再做", ("todo", "info"), "不着急，但别忘"),
]

CHECK_SVG = '<svg viewBox="0 0 16 16" fill="none"><path d="M3.5 8.5L6.5 11.5L12.5 4.5" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'


def esc(s):
    return html.escape(str(s or ""))


def card(it, colors):
    c = colors.get(it["source"], "#9C9C95")
    kind = it.get("kind")
    hot = kind == "overdue"
    dl = ""
    if it.get("deadline"):
        cls = "dl hot" if hot else "dl"
        dl = f'<span class="{cls}">{esc(it["deadline"])}</span>'
    act = f'<div class="act">{esc(it["action"])}</div>' if it.get("action") else ""
    label = colors.get(it["source"] + "_label", it["source"])
    return f'''<article class="card" data-id="{esc(it["id"])}" style="--c:{c}">
  <div class="body">
    <div class="meta"><span class="src">{esc(it["from"])}</span><span class="t">{esc(it["time"])}</span></div>
    <div class="text">{esc(it["text"])}</div>
    {act}
    {dl}
  </div>
  <button class="btn" aria-label="标记完成">{CHECK_SVG}</button>
</article>'''


def render_status(data, override=None):
    if override is not None:
        chips = []
        for key, meta in data.get("sources", {}).items():
            state = override.get(key, {}).get("state", "online")
            cls, word = STATE_LABELS.get(state, ("off", "未检测"))
            chips.append(f'<span class="chip {cls}"><i></i>{meta["label"]} · {word}</span>')
        return "".join(chips)

    apps = {}
    checked = ""
    try:
        with open(STATUS_FILE, encoding="utf-8") as fh:
            payload = json.load(fh)
        apps = payload.get("apps", {})
        checked = payload.get("checkedAt", "")
    except Exception:
        pass
    chips = []
    for key, meta in data.get("sources", {}).items():
        info = apps.get(key, {})
        state = info.get("state", "unknown")
        cls, word = STATE_LABELS.get(state, ("off", "未检测"))
        title = info.get("detail", "")
        tips = f' title="{esc(title)}"' if title else ""
        chips.append(f'<span class="chip {cls}"{tips}><i></i>{meta["label"]} · {word}</span>')
    return "".join(chips)


def build(force_example=False, out_path=None):
    if force_example:
        src = os.path.join(ROOT, "data", "state.example.json")
    else:
        src = STATE if os.path.exists(STATE) else os.path.join(ROOT, "data", "state.example.json")
        if not os.path.exists(STATE):
            print("未找到 data/state.json，改用 data/state.example.json 生成示例页")
    out = out_path or OUT
    with open(src, encoding="utf-8") as fh:
        data = json.load(fh)
    with open(TEMPLATE, encoding="utf-8") as fh:
        tpl = fh.read()

    colors = {}
    for k, v in data.get("sources", {}).items():
        colors[k] = v["color"]
        colors[k + "_label"] = v["label"]

    items = data.get("items", [])
    noise = data.get("noise", [])

    blocks = []
    for title, kinds, hint in SECTIONS:
        group = [i for i in items if i.get("kind") in kinds]
        if not group:
            continue
        if title == "催着的":
            group.sort(key=lambda i: 0 if i.get("kind") == "overdue" else 1)
        blocks.append(
            f'<h2>{title} <em>{len(group)}</em></h2>\n'
            + "\n".join(card(i, colors) for i in group)
        )

    noise_rows = "\n".join(
        f'<div class="nrow"><b>{esc(n["from"])}</b><i>{esc(n["text"])}</i><s>{esc(n["time"])}</s></div>'
        for n in noise
    )

    by_src = {}
    for i in items:
        by_src[i["source"]] = by_src.get(i["source"], 0) + 1

    parts = []
    for k, v in data.get("sources", {}).items():
        if by_src.get(k):
            parts.append(f"{v['label']} {by_src[k]} 条")
    lede = "今天有 <strong>%d 件事</strong>要动。%s；另外 %d 条已经当噪音滤掉了。" % (
        len(items), "、".join(parts) or "没有新消息", len(noise))

    demo_status = None
    if force_example:
        demo_status = {k: {"state": "online"} for k in data.get("sources", {})}

    out_html = (tpl
                .replace("__DAY__", esc(data.get("day", "")))
                .replace("__SUBTITLE__", esc(datetime.now().strftime("更新于 %H:%M")))
                .replace("__LEFT__", str(len(items)))
                .replace("__STATUS__", render_status(data, demo_status))
                .replace("__LEDE__", lede)
                .replace("__SECTIONS__", "\n".join(blocks))
                .replace("__NOISE_COUNT__", str(len(noise)))
                .replace("__NOISE_ROWS__", noise_rows)
                .replace("__UPDATED__", esc(data.get("updated", "").replace("T", " ")[5:16]))
                .replace("__TOTAL__", str(len(items))))

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(out_html)
    print(f"已生成 {out}（{len(items)} 条待办，{len(noise)} 条噪音）")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="把 state.json 渲染成页面")
    ap.add_argument("--example", action="store_true", help="强制用示例数据")
    ap.add_argument("--out", help="输出文件路径，默认 site/index.html")
    args = ap.parse_args()
    build(force_example=args.example, out_path=args.out)
