"""用多模态 API 读截图，生成 state.json。

配置写在项目根目录的 .env（不进版本库）：
  API_BASE=https://xxx/v1
  API_KEY=sk-...
  API_MODEL=模型名

跑法：
  python scripts/extract_api.py            读 data/snapshots 下全部截图
  python scripts/extract_api.py --dry      只统计要发多少张，不调用
"""

import base64
import json
import os
import re
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = os.path.join(ROOT, "data", "snapshots")
STATE = os.path.join(ROOT, "data", "state.json")
BATCH = 3

PROMPT = """你在看桌面端聊天软件的窗口截图。每张图左侧三分之一是会话列表，每一行是「头像 + 会话名 + 最后一条消息 + 时间」；右侧是当前打开的那个会话的聊天内容。

请把左侧会话列表里**今天往前 7 天内**的会话逐条读出来，判断哪些需要我动手。

只输出 JSON，不要解释，格式：
{
  "items": [
    {"from":"会话名","text":"最后一条消息原文","time":"14:50","kind":"deadline","action":"下一步具体做什么","deadline":"11月14日 15:00"}
  ],
  "noise": [
    {"from":"会话名","text":"消息","time":"15:20"}
  ]
}

规则：
- kind 取值：overdue（有截止且已过）、deadline（有截止未到）、reply（等我回话）、todo（要做没截止）、info（知道就行）
- 表情、闲聊、「ok」「收到」「牛逼」、加群/扫码/邀请、公众号推送、系统通知、打卡、通话记录 → 全部放 noise
- action 写成人话，告诉下一步做什么，不要复述原文
- 没有截止时间时 deadline 写 null
- 同一会话在多张图里重复出现（滚动重叠）只保留一条
- 时间照截图原样写：今天只写「14:50」，以前的写「10-27」

多张图是同一个账号连续滚动截的，注意去重。"""


def load_env():
    """配置优先从 data/settings.json 读，其次 .env，最后环境变量。"""
    import config
    cfg = config.load()
    return {
        "API_BASE": cfg.get("apiBase") or os.environ.get("API_BASE", ""),
        "API_KEY": cfg.get("apiKey") or os.environ.get("API_KEY", ""),
        "API_MODEL": cfg.get("apiModel") or os.environ.get("API_MODEL", ""),
    }


def images():
    out = []
    for root, _, files in os.walk(SHOT_DIR):
        for f in sorted(files):
            if f.lower().endswith(".png"):
                out.append(os.path.join(root, f))
    return sorted(out)


def b64(path):
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode()


def call(env, batch):
    content = [{"type": "text", "text": PROMPT}]
    for p in batch:
        content.append({"type": "image_url",
                        "image_url": {"url": "data:image/png;base64," + b64(p)}})
    body = {
        "model": env["API_MODEL"],
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.1,
    }
    req = install_req(env)
    import urllib.request
    req.data = json.dumps(body).encode("utf-8")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=240) as resp:
        payload = json.load(resp)
    text = payload["choices"][0]["message"]["content"]
    return text


def install_req(env):
    import urllib.request
    url = env["API_BASE"].rstrip("/") + "/chat/completions"
    req = urllib.request.Request(url, method="POST")
    req.add_header("Authorization", "Bearer " + env["API_KEY"])
    req.add_header("Content-Type", "application/json")
    return req


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def merge(parts):
    items, noise, seen = [], [], set()
    for part in parts:
        for key, bucket in (("items", items), ("noise", noise)):
            for row in part.get(key, []) or []:
                sig = (str(row.get("from", ""))[:20], str(row.get("text", ""))[:24])
                if sig in seen:
                    continue
                seen.add(sig)
                bucket.append(row)
    return items, noise


def build_state(items, noise):
    now = datetime.now()
    week = "周一二三四五六日"[now.weekday()]
    out_items = []
    for i, row in enumerate(items, 1):
        src = "dingtalk" if "钉" in str(row.get("source", "")) else "wechat"
        out_items.append({
            "id": f"i{i}",
            "source": row.get("source") if row.get("source") in ("wechat", "dingtalk") else src,
            "from": row.get("from", ""),
            "text": row.get("text", ""),
            "action": row.get("action", ""),
            "kind": row.get("kind", "info"),
            "time": row.get("time", ""),
            "deadline": row.get("deadline"),
        })
    out_noise = []
    for i, row in enumerate(noise, 1):
        out_noise.append({
            "id": f"n{i}",
            "source": row.get("source") if row.get("source") in ("wechat", "dingtalk") else "wechat",
            "from": row.get("from", ""),
            "text": row.get("text", ""),
            "time": row.get("time", ""),
        })
    return {
        "day": f"{now.month}月{now.day}日 {week}",
        "updated": now.isoformat(timespec="seconds"),
        "sources": {
            "wechat": {"label": "微信", "color": "#07C160"},
            "dingtalk": {"label": "钉钉", "color": "#3296FA"},
        },
        "items": out_items,
        "noise": out_noise,
        "extractedBy": "api",
    }


def main():
    paths = images()
    if not paths:
        print("没有截图")
        return 1
    if "--dry" in sys.argv:
        print(f"待发送 {len(paths)} 张，分 {(len(paths) + BATCH - 1) // BATCH} 批")
        return 0

    env = load_env()
    missing = [k for k in ("API_BASE", "API_KEY", "API_MODEL") if not env.get(k)]
    if missing:
        print("缺少配置：" + "、".join(missing) + "（写在 .env 里）")
        return 1

    parts = []
    for i in range(0, len(paths), BATCH):
        chunk = paths[i:i + BATCH]
        print(f"第 {i // BATCH + 1} 批，{len(chunk)} 张")
        try:
            text = call(env, chunk)
        except Exception as exc:
            print(f"  调用失败：{type(exc).__name__} {exc}")
            continue
        parsed = parse_json(text)
        if parsed:
            parts.append(parsed)
        else:
            print("  返回的不是 JSON，跳过")

    if not parts:
        print("全部失败，保留原数据")
        return 1

    items, noise = merge(parts)
    state = build_state(items, noise)
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
    print(f"完成：{len(state['items'])} 条待办，{len(state['noise'])} 条噪音")
    return 0


if __name__ == "__main__":
    sys.exit(main())
