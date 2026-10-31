"""Windows 窗口发现与截图工具（只读，不修改任何应用数据）。"""

import ctypes
import ctypes.wintypes as w
import time

from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

SW_RESTORE = 9
SW_MINIMIZE = 6
SW_SHOW = 5
SW_HIDE = 0
PW_RENDERFULLCONTENT = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

user32.GetWindowDC.restype = w.HDC
user32.GetWindowDC.argtypes = [w.HWND]
user32.ReleaseDC.argtypes = [w.HWND, w.HDC]
user32.PrintWindow.argtypes = [w.HWND, w.HDC, w.UINT]
user32.GetWindowTextW.argtypes = [w.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetClassNameW.argtypes = [w.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
user32.IsWindowVisible.argtypes = [w.HWND]
user32.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
user32.IsIconic.argtypes = [w.HWND]
kernel32 = ctypes.windll.kernel32
kernel32.OpenProcess.restype = w.HANDLE

gdi32.CreateCompatibleDC.restype = w.HDC
gdi32.CreateCompatibleDC.argtypes = [w.HDC]
gdi32.CreateCompatibleBitmap.restype = w.HBITMAP
gdi32.CreateCompatibleBitmap.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = w.HGDIOBJ
gdi32.SelectObject.argtypes = [w.HDC, w.HGDIOBJ]
gdi32.DeleteObject.argtypes = [w.HGDIOBJ]
gdi32.DeleteDC.argtypes = [w.HDC]
gdi32.GetDIBits.argtypes = [w.HDC, w.HBITMAP, w.UINT, w.UINT, ctypes.c_void_p,
                            ctypes.c_void_p, w.UINT]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG),
        ("biPlanes", w.WORD), ("biBitCount", w.WORD), ("biCompression", w.DWORD),
        ("biSizeImage", w.DWORD), ("biXPelsPerMeter", w.LONG),
        ("biYPelsPerMeter", w.LONG), ("biClrUsed", w.DWORD), ("biClrImportant", w.DWORD),
    ]


def _proc_name(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        size = w.DWORD(512)
        ok = kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        return buf.value.rsplit("\\", 1)[-1] if ok else ""
    finally:
        kernel32.CloseHandle(h)


def list_windows():
    rows = []
    CALLBACK = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)

    def cb(hwnd, _):
        pid = w.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        name = _proc_name(pid.value)
        if name not in ("Weixin.exe", "WeChat.exe", "DingTalk.exe"):
            return True
        t = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, t, 512)
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, c, 256)
        r = w.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        rows.append({
            "hwnd": hwnd, "proc": name, "title": t.value, "cls": c.value,
            "visible": bool(user32.IsWindowVisible(hwnd)),
            "iconic": bool(user32.IsIconic(hwnd)),
            "w": r.right - r.left, "h": r.bottom - r.top,
        })
        return True

    user32.EnumWindows(CALLBACK(cb), 0)
    return rows


TARGETS = {
    "wechat": {"proc": "Weixin.exe", "title": "微信"},
    "dingtalk": {"proc": "DingTalk.exe", "title": "钉钉"},
}

TH32CS_SNAPPROCESS = 0x00000002


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ProcessID", w.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", w.DWORD),
        ("cntThreads", w.DWORD), ("th32ParentProcessID", w.DWORD),
        ("pcPriClassBase", ctypes.c_long), ("dwFlags", w.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


kernel32.CreateToolhelp32Snapshot.restype = w.HANDLE
kernel32.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
kernel32.Process32FirstW.argtypes = [w.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.argtypes = [w.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]


def running_procs():
    names = set()
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap in (-1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
        return names
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            names.add(entry.szExeFile)
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return names


def app_state(app):
    """返回 (state, detail)：online / no-window / offline。"""
    spec = TARGETS[app]
    if spec["proc"] not in running_procs():
        return "offline", "进程未运行"
    if not find_main_window(app):
        return "no-window", "进程在，但没有可截取的窗口"
    return "online", "进程与窗口均正常"


def find_main_window(app):
    spec = TARGETS[app]
    wins = [r for r in list_windows() if r["proc"] == spec["proc"]]
    exact = [r for r in wins if r["title"] == spec["title"]]
    if exact:
        return exact[0]
    cands = [r for r in wins if r["w"] > 300 and r["h"] > 300]
    if not cands:
        return None
    return max(cands, key=lambda r: r["w"] * r["h"])


def capture(hwnd, out_path, quiet=True):
    was_iconic = bool(user32.IsIconic(hwnd))
    was_visible = bool(user32.IsWindowVisible(hwnd))
    try:
        if not was_visible:
            user32.ShowWindow(hwnd, SW_SHOW)
            time.sleep(1.8)
        if was_iconic:
            user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(1.6)
        rect = w.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width <= 0 or height <= 0:
            raise RuntimeError(f"invalid window rect {width}x{height}")

        hdc = user32.GetWindowDC(hwnd)
        mem = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, width, height)
        gdi32.SelectObject(mem, bmp)
        user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)

        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth = width
        bi.biHeight = -height
        bi.biPlanes = 1
        bi.biBitCount = 32
        buf = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits(mem, bmp, 0, height, buf, ctypes.byref(bi), 0)
        img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1).convert("RGB")
        img.save(out_path)

        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(hwnd, hdc)

        gray = img.convert("L").histogram()
        filled = sum(gray[20:]) / (width * height)
        return {"path": str(out_path), "size": f"{width}x{height}", "filled": round(filled, 3)}
    finally:
        if quiet:
            if was_iconic:
                user32.ShowWindow(hwnd, SW_MINIMIZE)
            elif not was_visible:
                user32.ShowWindow(hwnd, SW_HIDE)
