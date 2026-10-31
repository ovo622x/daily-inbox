"""读写本机的模型配置。密钥只落在 data/settings.json，不进版本库。"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS = os.path.join(ROOT, "data", "settings.json")

DEFAULTS = {"apiBase": "", "apiModel": "", "apiKey": ""}


def _from_env():
    path = os.path.join(ROOT, ".env")
    env = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def load():
    cfg = dict(DEFAULTS)
    if os.path.exists(SETTINGS):
        try:
            with open(SETTINGS, encoding="utf-8") as fh:
                cfg.update(json.load(fh))
        except Exception:
            pass

    env = _from_env()
    for key, name in (("apiBase", "API_BASE"), ("apiModel", "API_MODEL"), ("apiKey", "API_KEY")):
        if not cfg.get(key) and env.get(name):
            cfg[key] = env[name]
    return cfg


def save(cfg):
    current = load()
    for key in DEFAULTS:
        if key in cfg and cfg[key] is not None:
            current[key] = str(cfg[key]).strip()
    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    with open(SETTINGS, "w", encoding="utf-8") as fh:
        json.dump(current, fh, ensure_ascii=False, indent=2)
    return current


def masked(cfg=None):
    cfg = cfg or load()
    key = cfg.get("apiKey") or ""
    shown = (key[:5] + "…" + key[-4:]) if len(key) > 12 else ("已填写" if key else "")
    return {
        "apiBase": cfg.get("apiBase", ""),
        "apiModel": cfg.get("apiModel", ""),
        "apiKey": shown,
        "hasKey": bool(key),
        "ready": bool(cfg.get("apiBase") and cfg.get("apiModel") and key),
    }
