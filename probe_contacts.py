"""M0 侦察：在企业微信通讯录搜索门店名，截图记录每一步的界面（只搜索不发送）。"""
import ctypes
import sys
import time
from pathlib import Path

import win32clipboard
import win32gui
import uiautomation as auto

user32 = ctypes.windll.user32

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wecom  # noqa: E402

SHOT = wecom.ROOT / "shots" / "search"


def set_clipboard(text):
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()


def snap(hwnd, name):
    p = wecom.capture_window(hwnd, SHOT / name)
    print("shot:", p.name, flush=True)
    return p


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "示例门店"
    prev_fg = user32.GetForegroundWindow()
    hwnd = wecom.enum_wework_windows()[0][0]
    ok = wecom.bring_to_front(hwnd)
    print("foreground switched:", ok, flush=True)
    if not ok:
        print("ABORT: could not bring WeCom to front", flush=True)
        return 1
    time.sleep(0.6)

    left, top = win32gui.GetWindowRect(hwnd)[:2]
    snap(hwnd, "p01_front.png")

    auto.Click(left + 60, top + 443)
    time.sleep(0.8)
    snap(hwnd, "p02_contacts.png")

    auto.Click(left + 330, top + 38)
    time.sleep(0.5)
    snap(hwnd, "p03_searchbox.png")

    set_clipboard(query)
    auto.SendKeys("{Ctrl}v", waitTime=0.1)
    time.sleep(1.5)
    snap(hwnd, "p04_results.png")

    auto.SendKeys("{Esc}", waitTime=0.1)
    time.sleep(0.4)
    auto.SendKeys("{Esc}", waitTime=0.1)
    time.sleep(0.4)
    snap(hwnd, "p05_after_esc.png")

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
