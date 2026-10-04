"""企业微信桌面客户端 UI 自动化：搜索门店 -> 定位店长 -> 发图片+话术 -> 截取会话。"""
import ctypes
import sys
import time
from io import BytesIO
from pathlib import Path

import win32clipboard
import win32con
import win32gui
import uiautomation as auto
from PIL import Image

user32 = ctypes.windll.user32
ROOT = Path(__file__).resolve().parent

_ocr_engine = None


class WeComError(RuntimeError):
    pass


def ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _ocr_engine = RapidOCR()
    return _ocr_engine


def ocr_region(image_path, region):
    img = Image.open(image_path).crop(region)
    res, _ = ocr_engine()(img)
    lines = []
    if res:
        for box, text, score in res:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            lines.append({
                "text": text,
                "x": int(min(xs)) + region[0],
                "y": int(min(ys)) + region[1],
                "w": int(max(xs) - min(xs)),
                "h": int(max(ys) - min(ys)),
                "score": float(score),
            })
    return lines


def enum_wework_windows():
    found = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            cls = win32gui.GetClassName(hwnd)
            title = win32gui.GetWindowText(hwnd)
            if cls == "WeWorkWindow" and "企业微信" in title:
                found.append((hwnd, cls, title))
        return True

    win32gui.EnumWindows(cb, None)
    return found


def bring_to_front(hwnd):
    kernel32 = ctypes.windll.kernel32
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    cur_thread = kernel32.GetCurrentThreadId()
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
    tgt_thread = user32.GetWindowThreadProcessId(hwnd, None)
    user32.AttachThreadInput(cur_thread, tgt_thread, True)
    user32.AttachThreadInput(fg_thread, tgt_thread, True)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    user32.AttachThreadInput(fg_thread, tgt_thread, False)
    user32.AttachThreadInput(cur_thread, tgt_thread, False)
    time.sleep(0.3)
    if user32.GetForegroundWindow() != hwnd:
        user32.keybd_event(0x12, 0, 0, 0)
        user32.SetForegroundWindow(hwnd)
        user32.keybd_event(0x12, 0, 2, 0)
        time.sleep(0.3)
    return user32.GetForegroundWindow() == hwnd


def window_rect(hwnd):
    return win32gui.GetWindowRect(hwnd)


def is_maximized(hwnd):
    placement = win32gui.GetWindowPlacement(hwnd)
    return placement[1] == win32con.SW_SHOWMAXIMIZED


def save_screen_shot(bbox, path):
    from PIL import ImageGrab

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img = ImageGrab.grab(bbox=bbox, all_screens=True)
    img.save(path)
    return path


def capture_window(hwnd, path):
    import win32ui

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    w, h = right - left, bottom - top
    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfc_dc, w, h)
    save_dc.SelectObject(bmp)
    user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
    info = bmp.GetInfo()
    bits = bmp.GetBitmapBits(True)
    img = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRX", 0, 1)
    img.save(path)
    win32gui.DeleteObject(bmp.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)
    return path


def set_clipboard_text(text):
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()


def set_clipboard_image(png_path):
    img = Image.open(png_path).convert("RGB")
    buf = BytesIO()
    img.save(buf, "BMP")
    data = buf.getvalue()[14:]
    buf.close()
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    win32clipboard.CloseClipboard()


class WeCom:
    def __init__(self, cfg, work_dir=None):
        self.cfg = cfg
        self.work_dir = Path(work_dir) if work_dir else ROOT
        self.shot_dir = self.work_dir / "shots" / "chat"
        self.debug_dir = self.work_dir / "logs" / "debug"
        self.hwnd = None
        self.left = 0
        self.top = 0
        self.width = 0
        self.height = 0

    def ensure_ready(self, wait_sec=90):
        wins = []
        deadline = time.time() + wait_sec
        while time.time() < deadline:
            wins = enum_wework_windows()
            if wins:
                break
            time.sleep(2)
        if not wins:
            raise WeComError("企业微信主窗口未找到（可能未登录、正在重启或需要安全验证扫码）")
        self.hwnd = wins[0][0]
        if not bring_to_front(self.hwnd):
            raise WeComError("无法将企业微信窗口置前")
        if not is_maximized(self.hwnd):
            win32gui.ShowWindow(self.hwnd, win32con.SW_MAXIMIZE)
            time.sleep(1.0)
        left, top, right, bottom = window_rect(self.hwnd)
        self.left, self.top = left, top
        self.width, self.height = right - left, bottom - top

    def snap(self, name):
        path = self.debug_dir / name
        for attempt in range(3):
            capture_window(self.hwnd, path)
            try:
                img = Image.open(path).convert("L")
                lo, hi = img.getextrema()
                if hi - lo > 8:
                    return path
            except Exception:
                pass
            time.sleep(0.5)
        return path

    def _click(self, x, y, wait=0.6):
        auto.Click(self.left + x, self.top + y)
        time.sleep(wait)

    def _type_into_search(self, text):
        auto.SendKeys("{Ctrl}a", waitTime=0.1)
        set_clipboard_text(text)
        auto.SendKeys("{Ctrl}v", waitTime=0.1)
        time.sleep(1.4)

    def search_store(self, store, tag=""):
        self._click(60, 443, 0.8)
        self._click(330, 38, 0.4)
        self._type_into_search(store)
        shot = self.snap(f"{tag}01_results.png")
        box = " ".join(l["text"] for l in ocr_region(shot, (200, 15, 660, 60)))
        coverage = self._char_coverage(store, box)
        if coverage < 0.7 or len(box) < len(store) * 0.4:
            raise WeComError(f"搜索框文本校验失败: {box!r} coverage={coverage:.2f}")
        lines = ocr_region(shot, (200, 55, 620, 180))
        hit, best = None, 0.0
        for l in lines:
            cov = self._char_coverage(store, self._norm(l["text"]))
            if cov > best:
                best, hit = cov, l
        if hit is None or best < 0.7:
            raise WeComError(
                f"通讯录未搜到门店部门: {store} (OCR={[l['text'] for l in lines]})"
            )
        return hit

    def _member_lines(self, store, dept, tag):
        last_lines = []
        for attempt in range(3):
            shot = self.snap(f"{tag}02_members_a{attempt}.png")
            lines = ocr_region(shot, (200, 80, 660, 580))
            dept_row = next((l for l in lines if l["text"].strip() == store), None) or dept
            last_lines = lines
            if dept_row and any(l["y"] > dept_row["y"] + 30 for l in lines):
                return lines
            if dept_row:
                self._click(dept_row["x"] + 30, dept_row["y"] + 10, 1.4)
            else:
                break
        raise WeComError(f"部门成员列表未能展开: {store} (OCR={[l['text'] for l in last_lines][:20]})")

    @staticmethod
    def _norm(text):
        return "".join(text.split())

    @staticmethod
    def _char_coverage(needle, haystack):
        if not needle:
            return 0.0
        return sum(1 for ch in needle if ch in haystack) / len(needle)

    def _fuzzy_hit(self, needle, texts, ratio=0.7):
        return any(self._char_coverage(needle, t) >= ratio for t in texts)

    def _rank_name_candidates(self, lines, manager):
        mgr = self._norm(manager)
        candidates = []
        for nm in lines:
            name = self._norm(nm["text"])
            if not name or name in ("无", "联营店长", "店长"):
                continue
            exact = name == mgr
            prefix = mgr.startswith(name) or name.startswith(mgr)
            fuzzy = len(mgr) >= 3 and self._char_coverage(mgr, name) >= 0.8
            if not (exact or prefix or fuzzy):
                continue
            below = [l for l in lines if nm["y"] < l["y"] < nm["y"] + 42]
            title = min(below, key=lambda l: l["y"]) if below else None
            has_title = bool(title and "店长" in title["text"])
            backup = "备用" in name
            score = (0 if exact else 2) + (0 if has_title else 1) + (5 if backup else 0)
            candidates.append((score, nm))
        candidates.sort(key=lambda x: (x[0], x[1]["y"]))
        return [c[1] for c in candidates]

    def _fallback_person_candidates(self, store, manager, tag):
        self._click(60, 443, 0.8)
        self._click(330, 38, 0.4)
        self._type_into_search(manager)
        shot = self.snap(f"{tag}02c_person_search.png")
        lines = ocr_region(shot, (200, 55, 660, 580))
        mgr = self._norm(manager)
        rows = []
        for nm in lines:
            name = self._norm(nm["text"])
            if not name or name in ("无", "店长", "联营店长"):
                continue
            fuzzy = len(mgr) >= 3 and self._char_coverage(mgr, name) >= 0.8
            if name == mgr or mgr.startswith(name) or name.startswith(mgr) or fuzzy:
                below = [l for l in lines if nm["y"] < l["y"] < nm["y"] + 32]
                subtitle = min(below, key=lambda l: l["y"])["text"] if below else ""
                rows.append((0 if store in subtitle else 1, nm))
        rows.sort(key=lambda r: (r[0], r[1]["y"]))
        return [r[1] for r in rows]

    def open_manager_chat(self, store, manager, tag="", dept=None):
        lines, candidates = [], []
        try:
            lines = self._member_lines(store, dept, tag)
            candidates = self._rank_name_candidates(lines, manager)
        except WeComError:
            candidates = []
        if not candidates:
            candidates = self._fallback_person_candidates(store, manager, tag)
        if not candidates:
            raise WeComError(
                f"部门成员中未找到店长: {manager} (OCR={[l['text'] for l in lines][:24]})"
            )
        last_card = []
        for idx, nm in enumerate(candidates[:4]):
            self._click(nm["x"] + 15, nm["y"] + 10, 1.3)
            shot2 = self.snap(f"{tag}03_profile_{idx}.png")
            card = ocr_region(shot2, (850, 80, 2100, 780))
            last_card = card
            texts = [self._norm(l["text"]) for l in card]
            name_ok = any((manager in t) or (t and t in manager) for t in texts) or \
                self._fuzzy_hit(manager, texts, 0.75)
            dept_ok = any(store in t for t in texts) or self._fuzzy_hit(store, texts, 0.7)
            if name_ok and dept_ok:
                btn = next((l for l in card if "发消息" in l["text"]), None)
                if not btn:
                    raise WeComError("个人卡片上未找到发消息按钮")
                self._click(btn["x"] + btn["w"] // 2, btn["y"] + btn["h"] // 2, 2.0)
                shot3 = self.snap(f"{tag}04_chat_open.png")
                head = ocr_region(shot3, (450, 5, 1400, 60))
                head_texts = [self._norm(l["text"]) for l in head]
                if not (any(manager in t or (t and t in manager) for t in head_texts)
                        or self._fuzzy_hit(manager, head_texts, 0.75)):
                    raise WeComError(f"会话标题校验失败: {[l['text'] for l in head]}")
                return
            auto.SendKeys("{Esc}", waitTime=0.1)
            time.sleep(0.4)
        raise WeComError(
            f"候选人都未通过个人卡片校验: {manager} card={[l['text'] for l in last_card][:12]}"
        )

    def _input_point(self):
        return int(self.width * 0.50), self.height - 110

    def _composer_region(self):
        return (
            int(self.width * 0.22),
            self.height - 160,
            int(self.width * 0.85),
            self.height - 15,
        )

    def send_text(self, text, tag=""):
        x, y = self._input_point()
        self._click(x, y, 0.5)
        auto.SendKeys("{Ctrl}a", waitTime=0.1)
        set_clipboard_text(text)
        auto.SendKeys("{Ctrl}v", waitTime=0.1)
        time.sleep(0.7)
        shot = self.snap(f"{tag}05_text_composer.png")
        lines = ocr_region(shot, self._composer_region())
        joined = "".join(l["text"] for l in lines)
        probes = (text[1:15], text[:8], text[8:28], text[len(text) // 2:len(text) // 2 + 15])
        if not any(p and p in joined for p in probes):
            raise WeComError(f"输入框文本校验失败: OCR={joined[:60]!r}")
        auto.SendKeys("{Enter}", waitTime=0.1)
        time.sleep(1.2)

    def _region_changed(self, before_path, after_path, region, threshold=0.002):
        from PIL import ImageChops

        a = Image.open(before_path).crop(region).convert("L")
        b = Image.open(after_path).crop(region).convert("L")
        diff = ImageChops.difference(a, b)
        hist = diff.histogram()
        changed = sum(hist[30:])
        total = diff.size[0] * diff.size[1]
        return changed / total > threshold

    def send_image(self, png_path, tag=""):
        x, y = self._input_point()
        region = self._composer_region()
        last_error = None
        for attempt in range(2):
            before = self.snap(f"{tag}06a_composer_before_{attempt}.png")
            self._click(x, y, 0.5)
            set_clipboard_image(png_path)
            auto.SendKeys("{Ctrl}v", waitTime=0.2)
            time.sleep(1.6)
            after = self.snap(f"{tag}06b_image_composer_{attempt}.png")
            if self._region_changed(before, after, region):
                auto.SendKeys("{Enter}", waitTime=0.1)
                time.sleep(2.5)
                return
            last_error = WeComError("图片粘贴后输入区未见变化")
            auto.SendKeys("{Esc}", waitTime=0.1)
            time.sleep(0.5)
        raise last_error

    def capture_chat(self, out_path, tag=""):
        auto.SetCursorPos(self.left + int(self.width * 0.45), self.top + int(self.height * 0.25))
        time.sleep(0.3)
        win_shot = self.snap(f"{tag}07_chat_final.png")
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.open(win_shot).save(out_path)
        return out_path


def probe():
    wins = enum_wework_windows()
    print(f"main windows: {len(wins)}")
    for hwnd, cls, title in wins:
        rect = window_rect(hwnd)
        print(f"  hwnd={hwnd} cls={cls} title={title!r} rect={rect}")
    if not wins:
        return 1
    hwnd = wins[0][0]
    bring_to_front(hwnd)
    time.sleep(0.6)
    rect = window_rect(hwnd)
    out = save_screen_shot(rect, ROOT / "shots" / "search" / "wecom_probe_main.png")
    print(f"saved main shot: {out} rect={rect}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(probe())
