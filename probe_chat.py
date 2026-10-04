"""M0 侦察第四步：完整走 搜索->部门->定位店长->打开会话（不发送任何消息）。"""
import ctypes
import sys
import time
from pathlib import Path

import win32clipboard
import win32gui
import uiautomation as auto
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wecom  # noqa: E402

SHOT = wecom.ROOT / "shots" / "search"
user32 = ctypes.windll.user32
engine = RapidOCR()


def set_clipboard(text):
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()


def snap(hwnd, name):
    p = wecom.capture_window(hwnd, SHOT / name)
    print("shot:", p.name, flush=True)
    return p


def ocr(path, region):
    img = Image.open(path).crop(region)
    res, _ = engine(img)
    out = []
    if res:
        for b, text, score in res:
            xs = [p[0] for p in b]
            ys = [p[1] for p in b]
            out.append({
                "text": text,
                "x": int(min(xs)) + region[0],
                "y": int(min(ys)) + region[1],
                "w": int(max(xs) - min(xs)),
                "h": int(max(ys) - min(ys)),
                "score": score,
            })
    return out


def main():
    store = sys.argv[1] if len(sys.argv) > 1 else "示例门店"
    manager = sys.argv[2] if len(sys.argv) > 2 else "示例店长"
    prev_fg = user32.GetForegroundWindow()
    hwnd = wecom.enum_wework_windows()[0][0]
    ok = wecom.bring_to_front(hwnd)
    print("foreground:", ok, flush=True)
    if not ok:
        return 1
    time.sleep(0.6)
    left, top = win32gui.GetWindowRect(hwnd)[:2]

    auto.Click(left + 60, top + 443)
    time.sleep(0.7)
    auto.Click(left + 330, top + 38)
    time.sleep(0.4)
    auto.SendKeys("{Ctrl}a", waitTime=0.1)
    set_clipboard(store)
    auto.SendKeys("{Ctrl}v", waitTime=0.1)
    time.sleep(1.5)

    p0 = snap(hwnd, "c00_results.png")
    box_lines = ocr(p0, (200, 15, 640, 60))
    box_text = " ".join(l["text"] for l in box_lines)
    print("search box text:", box_text, flush=True)
    if box_text.count(store) != 1:
        print("WARN: search box text unexpected", flush=True)
    dept_lines = ocr(p0, (150, 55, 600, 150))
    print("dept region lines:", [(l["text"], l["x"], l["y"]) for l in dept_lines], flush=True)
    hit = next((l for l in dept_lines if store in l["text"]), None)
    if not hit:
        print("ABORT: department result not found", flush=True)
        return 2
    auto.Click(left + hit["x"] + 30, top + hit["y"] + 10)
    time.sleep(1.2)

    p1 = snap(hwnd, "c01_members.png")
    lines = ocr(p1, (150, 80, 640, 540))
    print("member lines:", [(l["text"], l["x"], l["y"]) for l in lines], flush=True)
    name_hits = [l for l in lines if l["text"].strip() == manager]
    if not name_hits:
        print("ABORT: manager name not found in member list", flush=True)
        return 3
    target = None
    for nm in name_hits:
        below = [l for l in lines if l["y"] > nm["y"] and l["y"] < nm["y"] + 40]
        title = min(below, key=lambda l: l["y"]) if below else None
        if title and "店长" in title["text"]:
            target = (nm, title)
            break
    if not target:
        nm = name_hits[0]
        target = (nm, None)
    nm, title = target
    print(f"clicking member: {nm['text']} ({nm['x']},{nm['y']}) title={title['text'] if title else None}", flush=True)
    auto.Click(left + nm["x"] + 15, top + nm["y"] + 10)
    time.sleep(1.3)

    p2 = snap(hwnd, "c02_profile.png")
    card = ocr(p2, (1180, 90, 1950, 520))
    print("profile lines:", [(l["text"], l["x"], l["y"]) for l in card], flush=True)
    prof_name = [l for l in card if manager in l["text"]]
    prof_dept = [l for l in card if store in l["text"]]
    print("verify name:", bool(prof_name), "verify dept:", bool(prof_dept), flush=True)
    send_btn = next((l for l in card if "发消息" in l["text"]), None)
    if not send_btn:
        print("ABORT: 发消息 button not found", flush=True)
        return 4
    auto.Click(left + send_btn["x"] + send_btn["w"] // 2, top + send_btn["y"] + send_btn["h"] // 2)
    time.sleep(1.8)
    snap(hwnd, "c03_chat_open.png")

    auto.SetCursorPos(left + 1500, top + 300)
    time.sleep(0.3)
    snap(hwnd, "c04_chat_clean.png")

    if prev_fg:
        try:
            user32.SetForegroundWindow(prev_fg)
        except Exception:
            pass
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
