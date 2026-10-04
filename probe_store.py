"""M0 侦察第二步：打开门店部门，观察部门详情/成员/负责人（只查看不发送）。"""
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
    snap(hwnd, "s01_results.png")

    auto.Click(left + 283, top + 90)
    time.sleep(1.2)
    snap(hwnd, "s02_after_click_result.png")

    auto.Click(left + 1213, top + 524)
    time.sleep(1.0)
    snap(hwnd, "s03_dept_card.png")

    auto.SendKeys("{Esc}", waitTime=0.1)
    time.sleep(0.4)
    snap(hwnd, "s04_after_esc.png")

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
