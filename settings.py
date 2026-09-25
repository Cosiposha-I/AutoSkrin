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
import re
import sys
import tempfile
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Общие сведения о приложении (используются в UI, сборке и установщике)
APP_NAME = "AutoSkrin"
APP_VERSION = "1.1.0"

# Режимы сохранения скриншота
CAPTURE_REGION = "region"   # только выбранная область
CAPTURE_SCREEN = "screen"   # весь монитор, на котором находится область
CAPTURE_ALL = "all"         # все мониторы целиком
CAPTURE_MODES = (CAPTURE_REGION, CAPTURE_SCREEN, CAPTURE_ALL)

# Поддерживаемые форматы файлов
IMAGE_FORMATS = ("png", "jpg")

# Режимы таймера автоматической остановки
TIMER_AFTER = "after"   # остановить через заданное время (например, 1:30)
TIMER_AT = "at"         # остановить в заданное время суток (например, 15:30)
TIMER_MODES = (TIMER_AFTER, TIMER_AT)

# Горячая клавиша паузы/старта. Раньше по умолчанию было Ctrl+Shift+S,
# но это сочетание занято «Сохранить как» и «Ножницами» Windows.
DEFAULT_HOTKEY = "Ctrl+Alt+S"
_OLD_DEFAULT_HOTKEY = "Ctrl+Shift+S"

# Файл с настройками, выбранными в установщике (лежит рядом с AutoSkrin.exe)
INSTALLER_DEFAULTS_FILE = "defaults.json"
_INSTALLER_META_KEYS = ("install_id", "apply_to_existing", "region", "applied_defaults_id")

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


def default_docx_path() -> str:
    """Документ Word по умолчанию: «Изображения/AutoSkrin/Конспект.docx»."""
    return str(Path(default_save_dir()) / "Конспект.docx")


def get_app_dir() -> Path:
    """Папка программы: рядом с AutoSkrin.exe (сборка) или с исходниками."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def parse_hhmm(text: str) -> tuple[int, int] | None:
    """«15:30» → (15, 30); None, если время записано неверно."""
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(text))
    if not match:
        return None
    hours, minutes = int(match.group(1)), int(match.group(2))
    return (hours, minutes) if hours < 24 and minutes < 60 else None


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

    # Куда сохранять: файлы в папку и/или документ Word (конспект)
    save_to_folder: bool = True
    save_to_docx: bool = False
    docx_path: str = field(default_factory=default_docx_path)
    docx_captions: bool = True          # подпись «Скриншот N — дата, время» над снимком

    # Таймер автоматической остановки мониторинга
    timer_enabled: bool = False
    timer_mode: str = TIMER_AFTER
    timer_minutes: int = 90             # «через»: 1 ч 30 мин
    timer_at: str = "18:00"             # «в»: время суток

    notifications_enabled: bool = True
    autostart_monitoring: bool = False
    minimize_to_tray: bool = True
    hotkey: str = DEFAULT_HOTKEY

    # Служебное: какие настройки установщика уже применены (см. load_settings)
    applied_defaults_id: str = ""

    # Допустимые диапазоны числовых параметров: (минимум, максимум)
    LIMITS = {
        "interval_sec": (0.1, 60.0),
        "threshold_percent": (0.01, 100.0),
        "pixel_tolerance": (0, 255),
        "min_interval_sec": (0.0, 3600.0),
        "jpeg_quality": (10, 100),
        "timer_minutes": (1, 23 * 60 + 59),
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
            if s.hotkey.replace(" ", "").lower() == _OLD_DEFAULT_HOTKEY.lower():
                s.hotkey = DEFAULT_HOTKEY  # старое значение по умолчанию — переводим на новое
        if isinstance(data.get("docx_path"), str) and data["docx_path"].strip():
            s.docx_path = data["docx_path"]
        if data.get("timer_mode") in TIMER_MODES:
            s.timer_mode = data["timer_mode"]
        if parse_hhmm(data.get("timer_at", "")):
            hours, minutes = parse_hhmm(data["timer_at"])
            s.timer_at = f"{hours:02d}:{minutes:02d}"
        if isinstance(data.get("applied_defaults_id"), str):
            s.applied_defaults_id = data["applied_defaults_id"]

        # Логические флаги
        for key in ("notifications_enabled", "autostart_monitoring", "minimize_to_tray",
                    "save_to_folder", "save_to_docx", "docx_captions", "timer_enabled"):
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

def _read_json(path: Path) -> Any:
    # utf-8-sig: файл, записанный установщиком или «Блокнотом», может начинаться с BOM
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def load_installer_defaults(path: Path | None = None) -> dict[str, Any] | None:
    """
    Настройки, выбранные в мастере установки (файл defaults.json рядом с exe).
    Кроме самих настроек в нём есть:
        install_id        — уникальная метка установки;
        apply_to_existing — применить и к уже настроенной программе
                            (пользователь снял «Оставить текущие настройки»).
    """
    path = path or get_app_dir() / INSTALLER_DEFAULTS_FILE
    if not path.exists():
        return None
    try:
        data = _read_json(path)
    except (OSError, ValueError) as exc:
        log.warning("Не удалось прочитать настройки установщика %s: %s", path, exc)
        return None
    return data if isinstance(data, dict) else None


def _without_meta(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if k not in _INSTALLER_META_KEYS}


def load_settings(path: Path | None = None, defaults_path: Path | None = None) -> Settings:
    """
    Загружает настройки пользователя из JSON.

    * Файла ещё нет (первый запуск) — берутся настройки из установщика,
      а если их нет — значения по умолчанию.
    * Файл есть, а в установщике выбрано «заменить настройки» — настройки
      установщика применяются один раз (выбранная область сохраняется).
    * Повреждённый файл переименовывается в *.bak, чтобы не потерять его.
    """
    path = path or get_config_path()
    defaults = load_installer_defaults(defaults_path)

    user_data = None
    if path.exists():
        try:
            user_data = _read_json(path)
        except (OSError, ValueError) as exc:
            log.warning("Не удалось прочитать настройки %s: %s", path, exc)
            try:
                os.replace(path, path.with_suffix(".json.bak"))
            except OSError:
                pass

    if not isinstance(user_data, dict):
        settings = Settings.from_dict(_without_meta(defaults) if defaults else {})
        if defaults:
            settings.applied_defaults_id = str(defaults.get("install_id", ""))
            log.info("Применены настройки из установщика")
        return settings

    settings = Settings.from_dict(user_data)
    install_id = str(defaults.get("install_id", "")) if defaults else ""
    if defaults and defaults.get("apply_to_existing") is True and install_id \
            and install_id != settings.applied_defaults_id:
        merged = {**user_data, **_without_meta(defaults)}
        settings = Settings.from_dict(merged)
        settings.applied_defaults_id = install_id
        log.info("Настройки заменены выбранными в установщике")
        try:
            save_settings(settings, path)
        except OSError as exc:
            log.warning("Не удалось сохранить настройки: %s", exc)
    return settings


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


def check_docx_target(path: str) -> str | None:
    """
    Проверяет, что в документ Word можно будет добавлять скриншоты.
    Возвращает текст ошибки или None, если всё в порядке.
    """
    if not path or not path.strip():
        return "Не выбран документ Word для скриншотов."
    if not path.lower().endswith(".docx"):
        return f"Документ «{path}» должен иметь расширение .docx."
    error = check_folder_writable(str(Path(path).parent))
    if error:
        return error
    if os.path.exists(path) and not zipfile.is_zipfile(path):
        return f"Файл «{path}» не является документом Word (.docx)."
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
