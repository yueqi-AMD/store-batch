"""全局暂停热键：Ctrl+Z（独占拦截）切换 暂停/继续。

实现：后台线程安装 WH_KEYBOARD_LL 低级键盘钩子，识别 Ctrl+Z。
- 仅 keydown 触发，忽略自动重复与自动化注入事件；
- 命中后吞掉该按键（其它程序收不到），避免触发撤销。
"""
import ctypes
import threading
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
VK_CONTROL = 0x11
VK_Z = 0x5A
LLKHF_INJECTED = 0x10


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short


class PauseSignal(Exception):
    """在安全点检测到暂停请求时抛出。"""


class Pauser:
    def __init__(self, enabled=True, log=None):
        self._paused = threading.Event()
        self._z_down = False
        self._running = True
        self._hook = None
        self._proc = None
        self._thread = None
        self._tid = None
        self._ready = threading.Event()
        self._log = log or (lambda msg: print(msg, flush=True))
        if enabled:
            self._install()

    # ------------------------------------------------------------ public API
    @property
    def paused(self):
        return self._paused.is_set()

    def toggle(self):
        if self._paused.is_set():
            self._paused.clear()
            self._log("[暂停键] 已恢复运行（Ctrl+Z 可再次暂停）")
        else:
            self._paused.set()
            self._log("[暂停键] 已暂停（Ctrl+Z 继续）")
        return self.paused

    def gate(self):
        """阻塞直到恢复运行。用于门店之间的安全等待。"""
        while self._paused.is_set():
            time.sleep(0.3)

    def checkpoint(self):
        """安全点检查；若处于暂停状态则抛出 PauseSignal。"""
        if self._paused.is_set():
            raise PauseSignal()

    def sleep(self, seconds):
        """分段睡眠，期间被暂停则提前返回（由 gate 负责阻塞）。"""
        end = time.time() + seconds
        while time.time() < end:
            if self._paused.is_set():
                return
            time.sleep(min(0.3, max(0.0, end - time.time())))

    def stop(self):
        self._running = False
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)

    # --------------------------------------------------------------- private
    def _install(self):
        try:
            self._proc = HOOKPROC(self._hook_proc)
            self._thread = threading.Thread(target=self._run, name="pause-hotkey", daemon=True)
            self._thread.start()
            self._ready.wait(3.0)
        except Exception as e:  # pragma: no cover - 极少数环境
            self._log(f"[暂停键] 安装失败: {e}（任务继续，可用 Ctrl+C 终止）")

    def _run(self):
        self._tid = kernel32.GetCurrentThreadId()
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if not self._hook:
            err = kernel32.GetLastError()
            self._log(f"[暂停键] 注册失败 code={err}（任务继续，可用 Ctrl+C 终止）")
            self._ready.set()
            return
        self._log("[暂停键] 就绪：Ctrl+Z 暂停 / 再按继续")
        self._ready.set()
        msg = MSG()
        while self._running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def _hook_proc(self, nCode, wParam, lParam):
        if nCode == 0:
            kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            injected = bool(kb.flags & LLKHF_INJECTED)
            if kb.vkCode == VK_Z and not injected:
                down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                up = wParam in (WM_KEYUP, WM_SYSKEYUP)
                ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                if down and ctrl:
                    if not self._z_down:
                        self._z_down = True
                        self.toggle()
                    return 1
                if up and self._z_down:
                    self._z_down = False
                    return 1
        return user32.CallNextHookEx(None, nCode, wParam, lParam)
