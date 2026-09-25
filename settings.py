"""
settings.py — работа с конфигурационным файлом приложения.

Настройки хранятся в JSON-файле в папке пользователя:
    Windows: %APPDATA%\\AutoSkrin\\settings.json
    Linux:   ~/.config/AutoSkrin/settings.json
    macOS:   ~/Library/Application Support/AutoSkrin/settings.json

Модуль не зависит от Qt, поэтому его легко тестировать отдельно.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Общие сведения о приложении (используются в UI, сборке и установщике)
APP_NAME = "AutoSkrin"
APP_VERSION = "1.0.0"

# Режимы сохранения скриншота
CAPTURE_REGION = "region"   # только выбранная область
CAPTURE_SCREEN = "screen"   # весь монитор, на котором находится область
CAPTURE_ALL = "all"         # все мониторы целиком
CAPTURE_MODES = (CAPTURE_REGION, CAPTURE_SCREEN, CAPTURE_ALL)

# Поддерживаемые форматы файлов
IMAGE_FORMATS = ("png", "jpg")

# Имя параметра автозапуска в реестре Windows
_AUTORUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Пути
# ---------------------------------------------------------------------------

def get_config_dir() -> Path:
    """Возвращает папку для конфига и лог-файла (создаётся при необходимости)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_config_path() -> Path:
    """Полный путь к файлу settings.json."""
    return get_config_dir() / "settings.json"


def default_save_dir() -> str:
    """Папка для скриншотов по умолчанию: «Изображения/AutoSkrin»."""
    pictures = Path.home() / "Pictures"
    return str((pictures if pictures.is_dir() else Path.home()) / APP_NAME)


# ---------------------------------------------------------------------------
# Модель данных
# ---------------------------------------------------------------------------

@dataclass
class Region:
    """Прямоугольная область экрана в физических пикселях (как у mss)."""

    left: int
    top: int
    width: int
    height: int

    def is_valid(self) -> bool:
        """Область имеет смысл, только если у неё положительные размеры."""
        return self.width > 0 and self.height > 0

    def as_mss(self) -> dict[str, int]:
        """Словарь в формате, который принимает mss.grab()."""
        return {"left": self.left, "top": self.top,
                "width": self.width, "height": self.height}

    def center(self) -> tuple[int, int]:
        return self.left + self.width // 2, self.top + self.height // 2

    def __str__(self) -> str:
        return (f"X: {self.left}, Y: {self.top}, "
                f"ширина: {self.width}, высота: {self.height} px")

    @classmethod
    def from_dict(cls, data: Any) -> Region | None:
        """Безопасно создаёт область из словаря конфига (или None при ошибке)."""
        if not isinstance(data, dict):
            return None
        try:
            region = cls(*(int(data[k]) for k in ("left", "top", "width", "height")))
        except (KeyError, TypeError, ValueError):
            return None
        return region if region.is_valid() else None


@dataclass
class Settings:
    """Все настройки приложения со значениями по умолчанию."""

    save_dir: str = field(default_factory=default_save_dir)
    region: Region | None = None
    interval_sec: float = 1.0          # как часто проверять область
    threshold_percent: float = 1.0     # сколько % пикселей должно измениться
    pixel_tolerance: int = 12          # насколько (0–255) должен измениться пиксель
    min_interval_sec: float = 5.0      # защита от спама: пауза между снимками
    capture_mode: str = CAPTURE_REGION
    image_format: str = "png"
    jpeg_quality: int = 90
    notifications_enabled: bool = True
    autostart_monitoring: bool = False
    minimize_to_tray: bool = True
    hotkey: str = "Ctrl+Shift+S"

    # Допустимые диапазоны числовых параметров: (минимум, максимум)
    LIMITS = {
        "interval_sec": (0.1, 60.0),
        "threshold_percent": (0.01, 100.0),
        "pixel_tolerance": (0, 255),
        "min_interval_sec": (0.0, 3600.0),
        "jpeg_quality": (10, 100),
    }

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["region"] = asdict(self.region) if self.region else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        """
        Создаёт настройки из словаря. Неизвестные ключи игнорируются,
        некорректные значения заменяются значениями по умолчанию,
        числа ограничиваются допустимым диапазоном.
        """
        s = cls()
        if not isinstance(data, dict):
            return s

        # Строковые параметры
        if isinstance(data.get("save_dir"), str) and data["save_dir"].strip():
            s.save_dir = data["save_dir"]
        if data.get("capture_mode") in CAPTURE_MODES:
            s.capture_mode = data["capture_mode"]
        fmt = str(data.get("image_format", "")).lower().replace("jpeg", "jpg")
        if fmt in IMAGE_FORMATS:
            s.image_format = fmt
        if isinstance(data.get("hotkey"), str) and data["hotkey"].strip():
            s.hotkey = data["hotkey"].strip()

        # Логические флаги
        for key in ("notifications_enabled", "autostart_monitoring", "minimize_to_tray"):
            if isinstance(data.get(key), bool):
                setattr(s, key, data[key])

        # Числовые параметры с ограничением диапазона
        for key, (lo, hi) in cls.LIMITS.items():
            value = data.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            default = getattr(s, key)
            value = type(default)(value)
            setattr(s, key, min(max(value, lo), hi))

        s.region = Region.from_dict(data.get("region"))
        return s

    def copy(self) -> Settings:
        """Независимая копия (передаётся в поток мониторинга)."""
        return Settings.from_dict(self.to_dict())


# ---------------------------------------------------------------------------
# Загрузка и сохранение
# ---------------------------------------------------------------------------

def load_settings(path: Path | None = None) -> Settings:
    """
    Загружает настройки из JSON. Если файла нет — возвращает значения
    по умолчанию. Повреждённый файл переименовывается в *.bak,
    чтобы пользователь не потерял его содержимое.
    """
    path = path or get_config_path()
    if not path.exists():
        return Settings()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        log.warning("Не удалось прочитать настройки %s: %s", path, exc)
        try:
            os.replace(path, path.with_suffix(".json.bak"))
        except OSError:
            pass
        return Settings()
    return Settings.from_dict(data)


def save_settings(settings: Settings, path: Path | None = None) -> None:
    """
    Атомарно сохраняет настройки: сначала пишет во временный файл,
    затем подменяет им основной. Так конфиг не повредится, если
    программа упадёт посреди записи.
    """
    path = path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(settings.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def check_folder_writable(folder: str) -> str | None:
    """
    Проверяет, что в папку можно сохранять файлы (создаёт её при необходимости).
    Возвращает текст ошибки или None, если всё в порядке.
    """
    if not folder:
        return "Папка для сохранения не указана."
    try:
        os.makedirs(folder, exist_ok=True)
        fd, probe = tempfile.mkstemp(prefix=".write-test-", dir=folder)
        os.close(fd)
        os.remove(probe)
    except OSError as exc:
        return f"Нет доступа к папке «{folder}»: {exc.strerror or exc}"
    return None


# ---------------------------------------------------------------------------
# Автозапуск вместе с Windows (раздел реестра HKCU\...\Run)
# ---------------------------------------------------------------------------

def autorun_supported() -> bool:
    return sys.platform == "win32"


def _autorun_command() -> str:
    """Команда запуска программы свёрнутой в трей."""
    if getattr(sys, "frozen", False):
        # Собранный exe (PyInstaller)
        return f'"{sys.executable}" --minimized'
    # Запуск из исходников: используем pythonw.exe, чтобы не было консоли
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    main_py = Path(__file__).resolve().with_name("main.py")
    return f'"{pythonw if pythonw.exists() else exe}" "{main_py}" --minimized'


def is_autorun_enabled() -> bool:
    if not autorun_supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTORUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except OSError:
        return False


def set_autorun(enabled: bool) -> None:
    """Включает/выключает запуск программы при входе в Windows."""
    if not autorun_supported():
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTORUN_KEY, 0,
                        winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _autorun_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
