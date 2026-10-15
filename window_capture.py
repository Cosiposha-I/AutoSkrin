"""
window_capture.py — захват конкретного окна программы (как «Захват окна» в OBS).

Windows:
  * список окон — EnumWindows (те же окна, что видны по Alt+Tab);
  * снимок содержимого — PrintWindow с флагом PW_RENDERFULLCONTENT: окно
    снимается, даже если его перекрывают другие окна; рамка и заголовок не
    попадают в снимок (только клиентская область);
  * свёрнутое окно снять нельзя (у него нет изображения) — мониторинг ждёт.

Можно отслеживать не всё окно, а его часть (Crop — отступы от краёв окна,
как фильтр «Обрезка» в OBS).

Выбранное окно запоминается по заголовку, классу окна и имени программы.
Если программу закрыли и открыли снова, окно находится заново: сначала по
точному заголовку, затем по «типу» окна (класс + программа) — как в OBS.

На других системах захват окна недоступен (WINDOW_CAPTURE_SUPPORTED = False).
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from dataclasses import dataclass

import numpy as np

from settings import Crop, Region

log = logging.getLogger(__name__)

WINDOW_CAPTURE_SUPPORTED = sys.platform == "win32"

# Состояния отслеживаемого окна
FOUND = "found"          # окно есть и его можно снимать
MINIMIZED = "minimized"  # окно свёрнуто или скрыто
MISSING = "missing"      # окна нет (программа закрыта)


@dataclass(frozen=True)
class WindowInfo:
    """Сведения об окне верхнего уровня."""

    hwnd: int
    title: str
    class_name: str
    exe: str                 # имя файла программы, например chrome.exe
    minimized: bool = False

    def label(self) -> str:
        """Подпись как в OBS: «[chrome.exe] Лекция — Google Chrome»."""
        return f"[{self.exe}] {self.title}" if self.exe else self.title


def window_label(title: str, exe: str) -> str:
    return f"[{exe}] {title}" if exe else title


def match_window(windows: list[WindowInfo], title: str, class_name: str, exe: str,
                 last_hwnd: int | None = None) -> WindowInfo | None:
    """
    Находит запомненное окно среди открытых:
      1) то же самое окно (тот же дескриптор) той же программы;
      2) окно той же программы с точно таким же заголовком;
      3) окно той же программы и того же класса (заголовок мог смениться,
         например у браузера при переключении вкладки) — несвёрнутое в приоритете.
    """
    same_exe = [w for w in windows if not exe or w.exe.lower() == exe.lower()]
    if last_hwnd is not None:
        for w in same_exe:
            if w.hwnd == last_hwnd:
                return w
    for w in same_exe:
        if title and w.title == title:
            return w
    if class_name:
        candidates = [w for w in same_exe if w.class_name == class_name]
        for w in candidates:
            if not w.minimized:
                return w
        if candidates:
            return candidates[0]
    return None


def bgra_has_content(frame: np.ndarray) -> bool:
    """False, если кадр полностью чёрный (так выглядит неудачный снимок окна)."""
    return bool(frame[..., :3].any())


def crop_frame(frame: np.ndarray, crop: Crop | None) -> tuple[np.ndarray, bool]:
    """
    Вырезает выбранную часть из снимка окна.
    Второй элемент — удалось ли (False: окно стало слишком маленьким, возвращён весь снимок).
    """
    if crop is None:
        return frame, True
    height, width = frame.shape[:2]
    box = crop.box(width, height)
    if box is None:
        return frame, False
    x, y, w, h = box
    return frame[y:y + h, x:x + w], True


def cropped_area(area: Region, crop: Crop | None) -> tuple[Region, bool]:
    """Где на экране находится выбранная часть окна (area — всё окно)."""
    if crop is None:
        return area, True
    box = crop.box(area.width, area.height)
    if box is None:
        return area, False
    x, y, w, h = box
    return Region(area.left + x, area.top + y, w, h), True


class WindowTracker:
    """
    Следит за выбранным окном: находит его (в том числе после перезапуска
    программы), сообщает, свёрнуто ли оно, и снимает его содержимое.
    api — объект с методами list_windows/window_info/client_region/capture
    (в Windows — WinApi; в тестах можно подставить заглушку).
    """

    def __init__(self, title: str, class_name: str, exe: str, api=None):
        self.title = title
        self.class_name = class_name
        self.exe = exe
        self.api = api if api is not None else default_api()
        self.window: WindowInfo | None = None

    def label(self) -> str:
        return window_label(self.title, self.exe)

    def update(self) -> str:
        """Обновляет сведения об окне. Возвращает FOUND, MINIMIZED или MISSING."""
        if self.api is None:
            self.window = None
            return MISSING
        info = None
        if self.window is not None:
            info = self.api.window_info(self.window.hwnd)
            # Дескриптор мог достаться окну другой программы
            if info is not None and self.exe and info.exe.lower() != self.exe.lower():
                info = None
        if info is None:
            info = match_window(self.api.list_windows(), self.title, self.class_name, self.exe)
        self.window = info
        if info is None:
            return MISSING
        return MINIMIZED if info.minimized else FOUND

    def capture(self) -> np.ndarray | None:
        """Содержимое окна (BGRA), даже если оно перекрыто. None — не удалось."""
        if self.window is None:
            return None
        return self.api.capture(self.window.hwnd)

    def screen_region(self) -> Region | None:
        """Где окно (его клиентская область) находится на экране, в физических пикселях."""
        if self.window is None:
            return None
        return self.api.client_region(self.window.hwnd)


# ---------------------------------------------------------------------------
# Реализация для Windows (ctypes, без дополнительных библиотек)
# ---------------------------------------------------------------------------

_api_instance = None


def default_api():
    """Объект WinApi (один на программу) или None, если система не Windows."""
    global _api_instance
    if not WINDOW_CAPTURE_SUPPORTED:
        return None
    if _api_instance is None:
        _api_instance = WinApi()
    return _api_instance


class WinApi:
    """Тонкая обёртка над функциями Windows для работы с окнами."""

    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_APPWINDOW = 0x00040000
    GW_OWNER = 4
    DWMWA_CLOAKED = 14
    PW_CLIENTONLY = 0x1
    PW_RENDERFULLCONTENT = 0x2
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def __init__(self):
        from ctypes import wintypes as wt
        self.wt = wt
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        try:
            self.dwmapi = ctypes.WinDLL("dwmapi")
        except OSError:
            self.dwmapi = None
        self.own_pid = os.getpid()

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                        ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                        ("biClrImportant", wt.DWORD)]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]

        self.BITMAPINFOHEADER, self.BITMAPINFO = BITMAPINFOHEADER, BITMAPINFO
        self.EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        self._declare_functions()

    def _declare_functions(self) -> None:
        """Типы аргументов и результатов — обязательно для 64-битных дескрипторов."""
        wt, u, g, k = self.wt, self.user32, self.gdi32, self.kernel32
        sig = [
            (u.EnumWindows, [self.EnumWindowsProc, wt.LPARAM], wt.BOOL),
            (u.IsWindow, [wt.HWND], wt.BOOL),
            (u.IsWindowVisible, [wt.HWND], wt.BOOL),
            (u.IsIconic, [wt.HWND], wt.BOOL),
            (u.GetWindowTextLengthW, [wt.HWND], ctypes.c_int),
            (u.GetWindowTextW, [wt.HWND, wt.LPWSTR, ctypes.c_int], ctypes.c_int),
            (u.GetClassNameW, [wt.HWND, wt.LPWSTR, ctypes.c_int], ctypes.c_int),
            (u.GetWindowThreadProcessId, [wt.HWND, ctypes.POINTER(wt.DWORD)], wt.DWORD),
            (u.GetWindow, [wt.HWND, wt.UINT], wt.HWND),
            (u.GetWindowLongW, [wt.HWND, ctypes.c_int], wt.LONG),
            (u.GetClientRect, [wt.HWND, ctypes.POINTER(wt.RECT)], wt.BOOL),
            (u.ClientToScreen, [wt.HWND, ctypes.POINTER(wt.POINT)], wt.BOOL),
            (u.GetDC, [wt.HWND], wt.HDC),
            (u.ReleaseDC, [wt.HWND, wt.HDC], ctypes.c_int),
            (u.PrintWindow, [wt.HWND, wt.HDC, wt.UINT], wt.BOOL),
            (g.CreateCompatibleDC, [wt.HDC], wt.HDC),
            (g.CreateDIBSection, [wt.HDC, ctypes.c_void_p, wt.UINT,
                                  ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD], wt.HBITMAP),
            (g.SelectObject, [wt.HDC, wt.HGDIOBJ], wt.HGDIOBJ),
            (g.DeleteObject, [wt.HGDIOBJ], wt.BOOL),
            (g.DeleteDC, [wt.HDC], wt.BOOL),
            (g.GdiFlush, [], wt.BOOL),
            (k.OpenProcess, [wt.DWORD, wt.BOOL, wt.DWORD], wt.HANDLE),
            (k.QueryFullProcessImageNameW, [wt.HANDLE, wt.DWORD, wt.LPWSTR,
                                            ctypes.POINTER(wt.DWORD)], wt.BOOL),
            (k.CloseHandle, [wt.HANDLE], wt.BOOL),
        ]
        if self.dwmapi is not None:
            sig.append((self.dwmapi.DwmGetWindowAttribute,
                        [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD], ctypes.c_long))
        for func, argtypes, restype in sig:
            func.argtypes, func.restype = argtypes, restype

    # --- сведения об окнах ---

    def _text(self, hwnd: int) -> str:
        length = self.user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    def _class_name(self, hwnd: int) -> str:
        buf = ctypes.create_unicode_buffer(256)
        self.user32.GetClassNameW(hwnd, buf, 256)
        return buf.value

    def _pid(self, hwnd: int) -> int:
        pid = self.wt.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def _exe_name(self, pid: int) -> str:
        handle = self.kernel32.OpenProcess(self.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = self.wt.DWORD(1024)
            if self.kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value)
            return ""
        finally:
            self.kernel32.CloseHandle(handle)

    def _is_cloaked(self, hwnd: int) -> bool:
        """«Скрытые» окна Windows 10/11 (приложения из Магазина в фоне, другие рабочие столы)."""
        if self.dwmapi is None:
            return False
        cloaked = self.wt.DWORD(0)
        result = self.dwmapi.DwmGetWindowAttribute(hwnd, self.DWMWA_CLOAKED, ctypes.byref(cloaked),
                                                   ctypes.sizeof(cloaked))
        return result == 0 and cloaked.value != 0

    def _is_app_window(self, hwnd: int) -> bool:
        """Окно, которое показывается по Alt+Tab: видимое, с заголовком, без владельца."""
        u = self.user32
        if not u.IsWindowVisible(hwnd) or u.GetWindowTextLengthW(hwnd) <= 0:
            return False
        ex_style = u.GetWindowLongW(hwnd, self.GWL_EXSTYLE)
        if ex_style & self.WS_EX_TOOLWINDOW and not ex_style & self.WS_EX_APPWINDOW:
            return False
        if u.GetWindow(hwnd, self.GW_OWNER) and not ex_style & self.WS_EX_APPWINDOW:
            return False
        return not self._is_cloaked(hwnd)

    def _describe(self, hwnd: int, exe_cache: dict[int, str] | None = None) -> WindowInfo:
        pid = self._pid(hwnd)
        if exe_cache is not None and pid in exe_cache:
            exe = exe_cache[pid]
        else:
            exe = self._exe_name(pid)
            if exe_cache is not None:
                exe_cache[pid] = exe
        minimized = bool(self.user32.IsIconic(hwnd)) or not self.user32.IsWindowVisible(hwnd)
        return WindowInfo(int(hwnd), self._text(hwnd), self._class_name(hwnd), exe, minimized)

    def list_windows(self, include_own: bool = False) -> list[WindowInfo]:
        """Окна программ в порядке «сверху вниз» (последние активные — первыми)."""
        result: list[WindowInfo] = []
        exe_cache: dict[int, str] = {}

        def callback(hwnd, _lparam):
            try:
                if hwnd and self._is_app_window(hwnd) and (include_own or self._pid(hwnd) != self.own_pid):
                    result.append(self._describe(hwnd, exe_cache))
            except Exception:  # noqa: BLE001 — одно «странное» окно не должно мешать остальным
                log.debug("Окно пропущено", exc_info=True)
            return True

        self.user32.EnumWindows(self.EnumWindowsProc(callback), 0)
        return result

    def window_info(self, hwnd: int) -> WindowInfo | None:
        """Свежие сведения об окне по дескриптору (None — окна больше нет)."""
        if not hwnd or not self.user32.IsWindow(hwnd):
            return None
        return self._describe(hwnd)

    # --- геометрия и снимок ---

    def _client_size(self, hwnd: int) -> tuple[int, int]:
        rect = self.wt.RECT()
        if not self.user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return 0, 0
        return rect.right - rect.left, rect.bottom - rect.top

    def client_region(self, hwnd: int) -> Region | None:
        width, height = self._client_size(hwnd)
        if width <= 0 or height <= 0:
            return None
        origin = self.wt.POINT(0, 0)
        self.user32.ClientToScreen(hwnd, ctypes.byref(origin))
        return Region(origin.x, origin.y, width, height)

    def capture(self, hwnd: int) -> np.ndarray | None:
        """Снимок клиентской области окна через PrintWindow (BGRA, сверху вниз)."""
        width, height = self._client_size(hwnd)
        if width <= 0 or height <= 0:
            return None
        u, g = self.user32, self.gdi32
        screen_dc = u.GetDC(None)
        memory_dc = g.CreateCompatibleDC(screen_dc)
        info = self.BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(self.BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height       # отрицательная высота — строки сверху вниз
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        bits = ctypes.c_void_p()
        bitmap = g.CreateDIBSection(screen_dc, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
        try:
            if not bitmap or not bits.value:
                return None
            previous = g.SelectObject(memory_dc, bitmap)
            try:
                if not u.PrintWindow(hwnd, memory_dc, self.PW_CLIENTONLY | self.PW_RENDERFULLCONTENT):
                    return None
                g.GdiFlush()
                data = ctypes.string_at(bits.value, width * height * 4)
            finally:
                g.SelectObject(memory_dc, previous)
        finally:
            if bitmap:
                g.DeleteObject(bitmap)
            g.DeleteDC(memory_dc)
            u.ReleaseDC(None, screen_dc)
        return np.frombuffer(data, dtype=np.uint8).reshape(height, width, 4)
