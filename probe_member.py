"""M0 侦察第三步：点开门店部门里的店长，观察个人卡片/发消息入口（不发送消息）。"""
import ctypes
import sys
import time
from pathlib import Path

import win32clipboard
import win32gui
import uiautomation as auto

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wecom  # noqa: E402

SHOT = wecom.ROOT / "shots" / "search"
user32 = ctypes.windll.user32


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
    member_y = int(sys.argv[2]) if len(sys.argv) > 2 else 267
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
    set_clipboard(query)
    auto.SendKeys("{Ctrl}v", waitTime=0.1)
    time.sleep(1.5)
    auto.Click(left + 283, top + 90)
    time.sleep(1.2)
    snap(hwnd, "m01_expanded.png")

    auto.Click(left + 225, top + member_y)
    time.sleep(1.2)
    snap(hwnd, "m02_member_click.png")

    auto.Click(left + 225, top + member_y)
    auto.Click(left + 225, top + member_y, waitTime=0.2)
    time.sleep(1.2)
    snap(hwnd, "m03_member_dblclick.png")

    auto.SendKeys("{Esc}", waitTime=0.1)
    time.sleep(0.4)
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
