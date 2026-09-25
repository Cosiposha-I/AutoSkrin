"""
monitor.py — логика отслеживания изменений в выбранной области экрана.

Состав модуля:
    compute_change_percent() — сравнение двух кадров (numpy);
    ChangeDetector           — решает, когда делать снимок (порог + антиспам);
    save_image()             — сохранение PNG/JPG с временной меткой в имени;
    timer_deadline()         — когда остановить мониторинг по таймеру;
    ScreenMonitor            — поток QThread, который периодически
                               захватывает область и сохраняет скриншоты
                               в папку и/или документ Word (см. word_doc.py).

Работа с экраном идёт через mss в физических пикселях.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import mss
import numpy as np
from PIL import Image
from PyQt6.QtCore import QThread, pyqtSignal

from settings import (CAPTURE_ALL, CAPTURE_REGION, CAPTURE_SCREEN, TIMER_AT, Region, Settings,
                      parse_hhmm)
from word_doc import ADDED_TO_WORD, PENDING, WordDocumentWriter

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Захват экрана и сравнение кадров
# ---------------------------------------------------------------------------

def create_mss():
    """Создаёт объект захвата экрана (mss 10+ — класс MSS, старые версии — mss())."""
    factory = getattr(mss, "MSS", None) or mss.mss
    return factory()


def shot_to_array(shot) -> np.ndarray:
    """Снимок mss (BGRA) → массив numpy формы (высота, ширина, 4)."""
    return np.frombuffer(shot.bgra, dtype=np.uint8).reshape(shot.height, shot.width, 4)


def shot_to_image(shot) -> Image.Image:
    """Снимок mss → изображение Pillow в RGB."""
    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def compute_change_percent(prev: np.ndarray, cur: np.ndarray, pixel_tolerance: int = 0) -> float:
    """
    Процент изменившихся пикселей между двумя кадрами одинакового размера.

    Пиксель считается изменившимся, если хотя бы один из каналов (B, G, R)
    отличается больше чем на pixel_tolerance (0–255). Это отсекает шум
    сжатия видео и лёгкое мерцание. Альфа-канал не учитывается.
    """
    if prev.shape != cur.shape:
        return 100.0
    a = prev[..., :3]
    b = cur[..., :3]
    # |a - b| без переполнения uint8 и без перевода в более «тяжёлый» тип
    diff = np.maximum(a, b) - np.minimum(a, b)
    changed = diff.max(axis=2) > pixel_tolerance
    return 100.0 * np.count_nonzero(changed) / changed.size


@dataclass
class Decision:
    """Результат обработки очередного кадра детектором."""

    percent: float                # % изменённых пикселей относительно эталонного кадра
    changed: bool                 # превышен ли порог чувствительности на этом кадре
    take_screenshot: bool         # нужно сохранить скриншот прямо сейчас
    deferred: bool = False        # изменение отложено антиспам-защитой (сообщается один раз)
    trigger_percent: float = 0.0  # величина изменения, из-за которого делается снимок


class ChangeDetector:
    """
    Сравнивает каждый новый кадр с предыдущим и решает, когда делать снимок.

    Защита от спама: между снимками выдерживается min_interval_sec.
    Если изменение случилось во время паузы, оно не теряется — снимок
    будет сделан сразу после её окончания (с актуальным состоянием экрана).
    """

    def __init__(self, threshold_percent: float, pixel_tolerance: int, min_interval_sec: float):
        self.configure(threshold_percent, pixel_tolerance, min_interval_sec)
        self.prev: np.ndarray | None = None
        self.last_shot_time: float | None = None
        self.pending = False
        self._pending_percent = 0.0

    def configure(self, threshold_percent: float, pixel_tolerance: int, min_interval_sec: float) -> None:
        """Обновляет параметры «на лету», не сбрасывая предыдущий кадр."""
        self.threshold_percent = threshold_percent
        self.pixel_tolerance = pixel_tolerance
        self.min_interval_sec = min_interval_sec

    def reset(self) -> None:
        """Забывает предыдущий кадр (например, после смены области)."""
        self.prev = None
        self.pending = False
        self._pending_percent = 0.0

    def cooldown_left(self, now: float) -> float:
        """Сколько секунд осталось до конца антиспам-паузы."""
        if self.last_shot_time is None:
            return 0.0
        return max(0.0, self.min_interval_sec - (now - self.last_shot_time))

    def process(self, frame: np.ndarray, now: float) -> Decision:
        # Первый кадр (или изменился размер области) — просто запоминаем его
        if self.prev is None or self.prev.shape != frame.shape:
            self.prev = frame
            return Decision(0.0, False, False)

        percent = compute_change_percent(self.prev, frame, self.pixel_tolerance)
        changed = percent >= self.threshold_percent
        if changed:
            # Эталоном становится кадр с изменением. Пока изменений нет, эталон
            # не обновляется — так медленные мелкие изменения накапливаются
            # и в итоге будут замечены, а не потеряются между проверками.
            self.prev = frame

        if not (changed or self.pending):
            return Decision(percent, False, False)

        trigger = max(percent if changed else 0.0, self._pending_percent)
        if self.cooldown_left(now) <= 0:
            self.pending = False
            self._pending_percent = 0.0
            return Decision(percent, changed, True, trigger_percent=trigger)

        # Антиспам-пауза ещё идёт — откладываем снимок
        first_time = not self.pending
        self.pending = True
        self._pending_percent = trigger
        return Decision(percent, changed, False, deferred=changed and first_time,
                        trigger_percent=trigger)

    def mark_saved(self, now: float) -> None:
        """Сообщает детектору, что снимок успешно сохранён."""
        self.last_shot_time = now


# ---------------------------------------------------------------------------
# Сохранение файлов
# ---------------------------------------------------------------------------

def make_screenshot_path(folder: str | Path, ext: str, when: datetime | None = None) -> Path:
    """
    Имя вида screenshot_2024-01-15_14-30-25.png. Если за одну секунду
    делается несколько снимков, добавляется суффикс _1, _2, ...
    """
    when = when or datetime.now()
    folder = Path(folder)
    base = f"screenshot_{when:%Y-%m-%d_%H-%M-%S}"
    path = folder / f"{base}.{ext}"
    n = 1
    while path.exists():
        path = folder / f"{base}_{n}.{ext}"
        n += 1
    return path


def save_image(image: Image.Image, folder: str, image_format: str = "png",
               jpeg_quality: int = 90, when: datetime | None = None) -> Path:
    """Сохраняет изображение в папку. Бросает OSError при проблемах с доступом."""
    os.makedirs(folder, exist_ok=True)  # папку могли удалить во время работы
    ext = "jpg" if image_format == "jpg" else "png"
    path = make_screenshot_path(folder, ext, when)
    if ext == "jpg":
        image.convert("RGB").save(path, "JPEG", quality=int(jpeg_quality))
    else:
        # compress_level=3 — заметно быстрее значения по умолчанию при почти том же размере
        image.save(path, "PNG", compress_level=3)
    return path


def find_monitor(monitors: list[dict], region: Region) -> dict:
    """
    Монитор (из списка mss), на котором находится большая часть области.
    monitors[0] в mss — это все мониторы вместе, он используется как запасной.
    """
    best, best_area = monitors[0], 0
    for mon in monitors[1:]:
        w = min(region.left + region.width, mon["left"] + mon["width"]) - max(region.left, mon["left"])
        h = min(region.top + region.height, mon["top"] + mon["height"]) - max(region.top, mon["top"])
        if w > 0 and h > 0 and w * h > best_area:
            best, best_area = mon, w * h
    return best


# ---------------------------------------------------------------------------
# Таймер автоматической остановки
# ---------------------------------------------------------------------------

def timer_deadline(started: datetime, mode: str, minutes: int, at: str) -> datetime:
    """
    Момент автоматической остановки мониторинга.
    «через»: started + minutes; «в»: ближайшее наступление времени at (ЧЧ:ММ).
    """
    if mode == TIMER_AT:
        hours, mins = parse_hhmm(at) or (18, 0)
        deadline = started.replace(hour=hours, minute=mins, second=0, microsecond=0)
        if deadline <= started:
            deadline += timedelta(days=1)  # это время сегодня уже прошло — значит, завтра
        return deadline
    return started + timedelta(minutes=minutes)


def format_duration(delta: timedelta) -> str:
    """timedelta → «1:29:58»."""
    total = max(0, int(delta.total_seconds()))
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


# ---------------------------------------------------------------------------
# Поток мониторинга
# ---------------------------------------------------------------------------

class ScreenMonitor(QThread):
    """
    Фоновый поток: раз в interval_sec захватывает область, сравнивает кадры
    и сохраняет скриншоты. С интерфейсом общается только через сигналы,
    поэтому GUI никогда не «подвисает».
    """

    screenshot_saved = pyqtSignal(str, float, str)  # описание, % изменений, что открыть по щелчку
    frame_checked = pyqtSignal(float)            # % изменений на последней проверке
    log_message = pyqtSignal(str, str)           # текст, уровень: info / warning / error
    fatal_error = pyqtSignal(str)                # мониторинг остановлен из-за ошибки

    MAX_CAPTURE_ERRORS = 5  # столько ошибок захвата подряд — и мониторинг останавливается

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings.copy()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._writer: WordDocumentWriter | None = None  # создаётся в потоке мониторинга
        self._busy_warned = False

    # --- управление из GUI-потока ---

    def update_settings(self, settings: Settings) -> None:
        """Передаёт новые настройки; они применяются на следующей проверке."""
        with self._lock:
            self._settings = settings.copy()

    def stop(self) -> None:
        """Просит поток завершиться (завершится в течение одного интервала)."""
        self._stop_event.set()

    def _current_settings(self) -> Settings:
        with self._lock:
            return self._settings

    # --- тело потока ---

    def run(self) -> None:
        try:
            # Объект mss нужно создавать в том же потоке, где он используется
            with create_mss() as sct:
                self._loop(sct)
        except Exception as exc:  # noqa: BLE001 — любая ошибка должна дойти до GUI
            log.exception("Сбой потока мониторинга")
            self.fatal_error.emit(f"Сбой мониторинга: {exc}")
        finally:
            self._close_writer()

    def _loop(self, sct) -> None:
        cfg = self._current_settings()
        detector = ChangeDetector(cfg.threshold_percent, cfg.pixel_tolerance, cfg.min_interval_sec)
        region = cfg.region
        errors = 0

        while not self._stop_event.is_set():
            started = time.monotonic()
            cfg = self._current_settings()
            detector.configure(cfg.threshold_percent, cfg.pixel_tolerance, cfg.min_interval_sec)

            if cfg.region is None:
                self.fatal_error.emit("Не выбрана область для мониторинга.")
                return
            if cfg.region != region:
                region = cfg.region
                detector.reset()
                self.log_message.emit(f"Новая область: {region}", "info")

            # 1. Захват области
            try:
                shot = sct.grab(region.as_mss())
                errors = 0
            except Exception as exc:  # noqa: BLE001
                errors += 1
                self.log_message.emit(
                    f"Ошибка захвата области ({errors}/{self.MAX_CAPTURE_ERRORS}): {exc}", "warning")
                if errors >= self.MAX_CAPTURE_ERRORS:
                    self.fatal_error.emit(f"Не удаётся захватить область экрана: {exc}")
                    return
                self._sleep(cfg.interval_sec, started)
                continue

            # 2. Сравнение с предыдущим кадром
            decision = detector.process(shot_to_array(shot), time.monotonic())
            self.frame_checked.emit(decision.percent)
            if decision.deferred:
                wait = detector.cooldown_left(time.monotonic())
                self.log_message.emit(
                    f"Изменение {decision.trigger_percent:.2f}% во время антиспам-паузы — "
                    f"снимок будет сделан через {wait:.1f} с", "info")

            # 3. Сохранение скриншота
            if decision.take_screenshot and not self._stop_event.is_set():
                try:
                    saved = self._save(sct, cfg, region, shot)
                except _FatalSaveError as exc:
                    self.fatal_error.emit(str(exc))
                    return
                except Exception as exc:  # noqa: BLE001 — например, ошибка захвата всего экрана
                    self.log_message.emit(f"Не удалось сделать скриншот: {exc}", "error")
                else:
                    detector.mark_saved(time.monotonic())
                    self.screenshot_saved.emit(saved[0], decision.trigger_percent, saved[1])

            self._sleep(cfg.interval_sec, started)

    def _save(self, sct, cfg: Settings, region: Region, region_shot) -> tuple[str, str]:
        """
        Делает скриншот согласно режиму (область / экран / все мониторы) и
        сохраняет его в папку и/или документ Word.
        Возвращает (описание для журнала, путь для открытия по щелчку).
        """
        if cfg.capture_mode == CAPTURE_SCREEN:
            shot = sct.grab(find_monitor(sct.monitors, region))
        elif cfg.capture_mode == CAPTURE_ALL:
            shot = sct.grab(sct.monitors[0])
        else:
            shot = region_shot  # CAPTURE_REGION — сохраняем тот самый кадр, где нашли изменение
        image = shot_to_image(shot)
        when = datetime.now()
        parts: list[str] = []
        target = ""

        file_path = None
        if cfg.save_to_folder:
            try:
                file_path = save_image(image, cfg.save_dir, cfg.image_format, cfg.jpeg_quality, when)
            except OSError as exc:
                raise _FatalSaveError(
                    f"Не удалось сохранить скриншот в «{cfg.save_dir}»: {exc.strerror or exc}") from exc
            parts.append(file_path.name)
            target = str(file_path)

        if cfg.save_to_docx:
            doc_part = self._add_to_document(cfg, image, when, file_path)
            if doc_part:
                parts.append(doc_part)
                target = target or cfg.docx_path
        return " + ".join(parts) or "—", target

    # --- документ Word ---

    def _writer_for(self, cfg: Settings) -> WordDocumentWriter:
        """Объект записи в документ; пересоздаётся при смене документа."""
        if self._writer is not None and os.path.normcase(str(self._writer.path)) != \
                os.path.normcase(os.path.abspath(cfg.docx_path)):
            self._close_writer()
        if self._writer is None:
            self._writer = WordDocumentWriter(os.path.abspath(cfg.docx_path))
            self._busy_warned = False
        self._writer.captions = cfg.docx_captions
        self._writer.image_format = cfg.image_format
        self._writer.jpeg_quality = cfg.jpeg_quality
        return self._writer

    def _add_to_document(self, cfg: Settings, image, when: datetime, file_path: Path | None) -> str:
        writer = self._writer_for(cfg)
        name = writer.path.name
        try:
            status = writer.add(image, when, file_path)
        except Exception as exc:  # noqa: BLE001 — повреждённый документ, нет места на диске и т.п.
            log.exception("Ошибка записи в документ")
            message = f"Не удалось добавить скриншот в документ «{name}»: {exc}"
            if not cfg.save_to_folder:
                raise _FatalSaveError(message) from exc
            self.log_message.emit(message, "error")
            return ""
        if status == PENDING:
            if not self._busy_warned:
                self._busy_warned = True
                self.log_message.emit(
                    f"Документ «{name}» занят другой программой — скриншоты будут добавлены, "
                    "как только его закроют (или откройте его в Microsoft Word)", "warning")
            return f"{name} (в очереди: {len(writer.pending)})"
        if self._busy_warned:
            self._busy_warned = False
            self.log_message.emit(f"Отложенные скриншоты добавлены в «{name}»", "info")
        return f"{name} (открыт в Word)" if status == ADDED_TO_WORD else name

    def _close_writer(self) -> None:
        if self._writer is None:
            return
        writer, self._writer = self._writer, None
        try:
            left, rescue_dir = writer.close()
        except Exception as exc:  # noqa: BLE001
            self.log_message.emit(f"Ошибка при закрытии документа: {exc}", "error")
            return
        if left:
            where = f" Их файлы перенесены в «{rescue_dir}»." if rescue_dir else " Они есть в папке со скриншотами."
            self.log_message.emit(
                f"{left} скриншот(ов) не удалось добавить в «{writer.path.name}»: документ занят.{where}",
                "warning")

    def _sleep(self, interval: float, started: float) -> None:
        """Ждёт до следующей проверки, но сразу просыпается при stop()."""
        self._stop_event.wait(max(0.0, interval - (time.monotonic() - started)))


class _FatalSaveError(Exception):
    """Сохранить снимок некуда — мониторинг нужно остановить."""


__all__ = [
    "CAPTURE_ALL", "CAPTURE_REGION", "CAPTURE_SCREEN", "ChangeDetector", "Decision",
    "ScreenMonitor", "compute_change_percent", "create_mss", "find_monitor", "format_duration",
    "make_screenshot_path", "save_image", "shot_to_array", "shot_to_image", "timer_deadline",
]
