"""用 CDP 精确控制视口，把页面截成手机尺寸的整页图。

  python scripts/shot.py demo/index.html docs/screenshot.png [宽度]

只用于生成文档配图，不参与抓取和构建流程。
依赖：websocket-client（见 requirements-dev.txt）
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

import websocket

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
PORT = 9333


def find_chrome():
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit("没找到 Chrome 或 Edge")


def main():
    if len(sys.argv) < 3:
        raise SystemExit("用法: python scripts/shot.py <html> <out.png> [宽度]")
    src = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2])
    width = int(sys.argv[3]) if len(sys.argv) > 3 else 390
    url = "file:///" + src.replace("\\", "/")

    profile = tempfile.mkdtemp(prefix="shot-")
    proc = subprocess.Popen(
        [find_chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--disable-extensions",
         f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
         "--no-first-run", "--no-default-browser-check", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise SystemExit("Chrome 调试端口没起来")

        tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list"))
        page = next(t for t in tabs if t.get("type") == "page")
        ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=60)

        counter = [0]

        def call(method, params=None):
            counter[0] += 1
            ws.send(json.dumps({"id": counter[0], "method": method, "params": params or {}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == counter[0]:
                    return msg

        call("Page.enable")
        call("Emulation.setDeviceMetricsOverride",
             {"width": width, "height": 900, "deviceScaleFactor": 2, "mobile": False})
        call("Page.navigate", {"url": url})
        time.sleep(1.8)

        res = call("Runtime.evaluate",
                   {"expression": "document.documentElement.scrollHeight", "returnByValue": True})
        height = int(res["result"]["result"]["value"]) + 8

        call("Emulation.setDeviceMetricsOverride",
             {"width": width, "height": height, "deviceScaleFactor": 2, "mobile": False})
        time.sleep(0.6)

        shot = call("Page.captureScreenshot", {"format": "png"})
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as fh:
            fh.write(base64.b64decode(shot["result"]["data"]))
        print(f"已截图 {out}（{width}x{height} css, 2x）")
        ws.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
