"""本机实时服务。

手机和电脑连同一个 Wi-Fi 时，用 http://<电脑内网IP>:8765/ 打开页面，
页面右上角的刷新会真的触发一次「抓取 → 识别 → 重建」，不是重新拉旧页面。

  python scripts/server.py           默认 8765 端口
  PORT=9000 python scripts/server.py 换端口

公网链接那份仍然是静态快照，刷新只是重新加载。
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
EXTRACT = os.path.join(ROOT, "scripts", "extract.py")
PY = sys.executable
PORT = int(os.environ.get("PORT", "8765"))

STATE = {"running": False, "ok": None, "step": "", "startedAt": 0,
         "finishedAt": 0, "log": ""}
LOCK = threading.Lock()


def _run(script, timeout):
    return subprocess.run([PY, script], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=timeout)


def pipeline():
    with LOCK:
        if STATE["running"]:
            return
        STATE.update(running=True, ok=None, step="抓取窗口画面", startedAt=time.time(), log="")
    logs = []
    ok = False
    try:
        r = _run(os.path.join(ROOT, "scripts", "collect.py"), 300)
        logs.append(r.stdout)
        if r.returncode == 0:
            with LOCK:
                STATE["step"] = "读图识别"
            r2 = _run(os.path.join(ROOT, "scripts", "extract_api.py"), 600)
            logs.append(r2.stdout + r2.stderr)
            with LOCK:
                STATE["step"] = "生成页面"
            r3 = _run(os.path.join(ROOT, "scripts", "build.py"), 120)
            logs.append(r3.stdout)
            ok = r3.returncode == 0
            with LOCK:
                STATE["step"] = "已更新" if r2.returncode == 0 else "已抓取，识别失败"
        else:
            with LOCK:
                STATE["step"] = "抓取失败"
    except Exception as exc:
        logs.append(f"{type(exc).__name__}: {exc}")
        with LOCK:
            STATE["step"] = "出错"
    finally:
        with LOCK:
            STATE["running"] = False
            STATE["ok"] = ok
            STATE["finishedAt"] = time.time()
            STATE["log"] = "".join(logs)[-2000:]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SITE, **kwargs)

    def log_message(self, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/status":
            with LOCK:
                return self._json(dict(STATE))
        if path == "/api/settings":
            import config
            return self._json(config.masked())
        if path == "/api/refresh":
            if STATE["running"]:
                return self._json({"started": False, "reason": "已经在跑了"})
            threading.Thread(target=pipeline, daemon=True).start()
            return self._json({"started": True})
        if path in ("/", ""):
            self.path = "/index.html"
        self.send_response(200)
        try:
            return super().do_GET()
        except BrokenPipeError:
            pass

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._json({"ok": False, "error": "请求体不是 JSON"}, 400)

        import config

        if path == "/api/settings":
            if not body.get("apiKey") or "…" in str(body.get("apiKey", "")):
                body.pop("apiKey", None)
            merged = config.save(body)
            return self._json({"ok": True, "settings": config.masked(merged)})

        if path == "/api/settings/test":
            cfg = config.load()
            if body.get("apiBase"):
                cfg["apiBase"] = body["apiBase"]
            if body.get("apiModel"):
                cfg["apiModel"] = body["apiModel"]
            if body.get("apiKey") and "…" not in body["apiKey"]:
                cfg["apiKey"] = body["apiKey"]
            missing = [k for k in ("apiBase", "apiModel", "apiKey") if not cfg.get(k)]
            if missing:
                return self._json({"ok": False, "error": "还缺 " + "、".join(missing)})
            return self._json(test_api(cfg))

        self._json({"ok": False, "error": "未知接口"}, 404)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()


def test_api(cfg):
    """用填好的配置发一次最小请求，确认接口和密钥能用。"""
    import urllib.error
    import urllib.request as ur

    body = {"model": cfg["apiModel"],
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 4}
    req = ur.Request(cfg["apiBase"].rstrip("/") + "/chat/completions",
                     data=json.dumps(body).encode(), method="POST")
    req.add_header("Authorization", "Bearer " + cfg["apiKey"])
    req.add_header("Content-Type", "application/json")
    opener = ur.build_opener(ur.ProxyHandler({}))
    try:
        with opener.open(req, timeout=40) as resp:
            data = json.load(resp)
        msg = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"ok": True, "message": (msg or "连通").strip()[:60]}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"{e.code} {e.read()[:280].decode('utf-8', 'replace')}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    ip = local_ip()
    print(f"通知漏斗 · 本机服务")
    print(f"  电脑打开:  http://127.0.0.1:{PORT}/")
    print(f"  手机打开:  http://{ip}:{PORT}/   （需同一个 Wi-Fi）")
    print(f"  按 Ctrl+C 停止\n")
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
