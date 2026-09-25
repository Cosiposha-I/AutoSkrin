"""
ui.py — графический интерфейс AutoSkrin (PyQt6).

Состав:
    make_icon_pixmap / app_icon — иконка приложения (рисуется кодом);
    GlobalHotkey                 — глобальная горячая клавиша (по умолчанию Ctrl+Alt+S);
    MainWindow                   — главное окно, иконка в трее, лог событий.
"""

from __future__ import annotations

import html
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import (QAbstractNativeEventFilter, QCoreApplication, QObject, QPointF, QRectF,
                          Qt, QTime, QTimer, QUrl, pyqtSignal)
from PyQt6.QtGui import (QAction, QColor, QDesktopServices, QIcon, QKeySequence, QLinearGradient,
                         QPainter, QPen, QPixmap, QShortcut)
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                             QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
                             QKeySequenceEdit, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
                             QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QStyle,
                             QSystemTrayIcon, QTimeEdit, QVBoxLayout, QWidget)

from monitor import ScreenMonitor, format_duration, timer_deadline
from region_selector import RegionHighlighter, RegionSelector, region_on_screens
from settings import (APP_NAME, APP_VERSION, CAPTURE_ALL, CAPTURE_REGION, CAPTURE_SCREEN,
                      DEFAULT_HOTKEY, TIMER_AFTER, TIMER_AT, Region, Settings, autorun_supported,
                      check_docx_target, check_folder_writable, get_config_path,
                      is_autorun_enabled, parse_hhmm, save_settings, set_autorun)
from word_doc import ensure_document

log = logging.getLogger(__name__)

# Подписи режимов сохранения для выпадающего списка
CAPTURE_LABELS = [
    (CAPTURE_REGION, "Только выбранную область"),
    (CAPTURE_SCREEN, "Весь экран (монитор с областью)"),
    (CAPTURE_ALL, "Все мониторы целиком"),
]

# Цвета записей в журнале событий
LOG_COLORS = {"info": None, "success": "#2E9E5B", "warning": "#C98A00", "error": "#D93025"}
LOG_LEVELS = {"info": logging.INFO, "success": logging.INFO,
              "warning": logging.WARNING, "error": logging.ERROR}


# ---------------------------------------------------------------------------
# Иконка приложения (рисуется программно, отдельные файлы не нужны)
# ---------------------------------------------------------------------------

def make_icon_pixmap(size: int, state: str | None = None) -> QPixmap:
    """
    Рисует иконку: синий квадрат с уголками рамки выделения и объективом.
    state: None — обычная иконка, "active" — зелёная точка, "paused" — серая.
    """
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(size)

    # Фон — скруглённый квадрат с градиентом
    grad = QLinearGradient(0, 0, 0, s)
    grad.setColorAt(0, QColor("#3B8CFF"))
    grad.setColorAt(1, QColor("#1D56CF"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(QRectF(0.02 * s, 0.02 * s, 0.96 * s, 0.96 * s), 0.22 * s, 0.22 * s)

    # Уголки рамки выделения (как в «Ножницах»)
    pen = QPen(QColor("white"), max(1.2, s * 0.075))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    m, ln = 0.2 * s, 0.2 * s
    for cx, cy, dx, dy in ((m, m, 1, 1), (s - m, m, -1, 1), (m, s - m, 1, -1), (s - m, s - m, -1, -1)):
        p.drawPolyline([QPointF(cx, cy + dy * ln), QPointF(cx, cy), QPointF(cx + dx * ln, cy)])

    # Объектив в центре
    c = QPointF(s / 2, s / 2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("white"))
    p.drawEllipse(c, 0.17 * s, 0.17 * s)
    p.setBrush(QColor("#1D56CF"))
    p.drawEllipse(c, 0.085 * s, 0.085 * s)

    # Индикатор состояния в правом нижнем углу
    if state:
        color = QColor("#2ECC71") if state == "active" else QColor("#9AA0A6")
        r = 0.2 * s
        center = QPointF(s - r - 0.02 * s, s - r - 0.02 * s)
        p.setBrush(QColor("white"))
        p.drawEllipse(center, r, r)
        p.setBrush(color)
        p.drawEllipse(center, r * 0.72, r * 0.72)
    p.end()
    return pm


def app_icon(state: str | None = None) -> QIcon:
    """Иконка сразу в нескольких размерах — Windows сам выберет подходящий."""
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(make_icon_pixmap(size, state))
    return icon


# ---------------------------------------------------------------------------
# Глобальная горячая клавиша
# ---------------------------------------------------------------------------

_MOD_ALIASES = {"ctrl": "ctrl", "control": "ctrl", "shift": "shift", "alt": "alt",
                "win": "win", "meta": "win", "cmd": "win", "super": "win"}


def parse_hotkey(text: str) -> tuple[list[str], str] | None:
    """
    «Ctrl+Shift+S» → (["ctrl", "shift"], "S"). Поддерживаются буквы A–Z,
    цифры и F1–F24. None — если сочетание записано неверно.
    """
    parts = [part.strip().lower() for part in text.split("+") if part.strip()]
    if len(parts) < 2:
        return None
    mods = []
    for part in parts[:-1]:
        if part not in _MOD_ALIASES:
            return None
        mods.append(_MOD_ALIASES[part])
    key = parts[-1]
    if len(key) == 1 and key.isascii() and key.isalnum():
        return mods, key.upper()
    if key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        return mods, key.upper()
    return None


class _WinHotkeyFilter(QAbstractNativeEventFilter):
    """Ловит системное сообщение WM_HOTKEY в очереди главного потока Qt."""

    WM_HOTKEY = 0x0312

    def __init__(self, hotkey_id: int, callback):
        super().__init__()
        self._id = hotkey_id
        self._callback = callback

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG" and message:
            import ctypes.wintypes
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == self.WM_HOTKEY and msg.wParam == self._id:
                self._callback()
                return True, 0
        return False, 0


class GlobalHotkey(QObject):
    """
    Глобальная горячая клавиша — срабатывает, даже если окно свёрнуто в трей.
    Windows: системная функция RegisterHotKey (не зависит от раскладки
    клавиатуры и не требует прав администратора).
    Linux/macOS: библиотека pynput.
    """

    activated = pyqtSignal()
    _HOTKEY_ID = 0xA51  # произвольный идентификатор нашей горячей клавиши
    _WIN_MODS = {"alt": 0x1, "ctrl": 0x2, "shift": 0x4, "win": 0x8}
    _MOD_NOREPEAT = 0x4000

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._win_filter: _WinHotkeyFilter | None = None
        self._pynput_listener = None
        self.error = ""

    def register(self, text: str) -> bool:
        self.unregister()
        parsed = parse_hotkey(text)
        if parsed is None:
            self.error = f"не удалось разобрать сочетание «{text}»"
            return False
        mods, key = parsed
        try:
            if sys.platform == "win32":
                return self._register_windows(mods, key)
            return self._register_pynput(mods, key)
        except Exception as exc:  # noqa: BLE001 — горячая клавиша не должна ронять программу
            self.error = str(exc)
            return False

    def _register_windows(self, mods: list[str], key: str) -> bool:
        import ctypes
        vk = ord(key) if len(key) == 1 else 0x6F + int(key[1:])  # VK_F1 = 0x70
        flags = self._MOD_NOREPEAT
        for mod in mods:
            flags |= self._WIN_MODS[mod]
        if not ctypes.windll.user32.RegisterHotKey(None, self._HOTKEY_ID, flags, vk):
            self.error = "сочетание уже занято другой программой"
            return False
        self._win_filter = _WinHotkeyFilter(self._HOTKEY_ID, self.activated.emit)
        QCoreApplication.instance().installNativeEventFilter(self._win_filter)
        return True

    def _register_pynput(self, mods: list[str], key: str) -> bool:
        try:
            from pynput import keyboard
        except Exception as exc:  # noqa: BLE001 — нет X-сервера, нет библиотеки и т.п.
            self.error = f"pynput недоступен: {exc}"
            return False
        names = {"win": "cmd"}
        combo = "+".join([f"<{names.get(m, m)}>" for m in mods]
                         + [key.lower() if len(key) == 1 else f"<{key.lower()}>"])
        self._pynput_listener = keyboard.GlobalHotKeys({combo: self.activated.emit})
        self._pynput_listener.daemon = True
        self._pynput_listener.start()
        return True

    def unregister(self) -> None:
        if self._win_filter is not None:
            import ctypes
            QCoreApplication.instance().removeNativeEventFilter(self._win_filter)
            ctypes.windll.user32.UnregisterHotKey(None, self._HOTKEY_ID)
            self._win_filter = None
        if self._pynput_listener is not None:
            self._pynput_listener.stop()
            self._pynput_listener = None


# ---------------------------------------------------------------------------
# Главное окно
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Главное окно: управление мониторингом, настройки, журнал событий, трей."""

    STYLE = """
        QPushButton#startButton {
            font-size: 11pt; font-weight: 600; color: white;
            background: #1E9E57; border: none; border-radius: 6px; padding: 8px 22px;
        }
        QPushButton#startButton:hover { background: #22B062; }
        QPushButton#startButton[running="true"] { background: #D64545; }
        QPushButton#startButton[running="true"]:hover { background: #E05656; }
        QLabel#statusLabel { font-size: 12pt; font-weight: 600; }
        QLabel#counterLabel { font-size: 12pt; }
    """

    def __init__(self, settings: Settings, persist: bool = True):
        super().__init__()
        self.settings = settings
        self._persist = persist  # False — не записывать настройки на диск (самопроверка)
        self.monitor: ScreenMonitor | None = None
        self._threads: set[ScreenMonitor] = set()   # потоки, которые ещё завершаются
        self.shot_count = 0
        self.last_target = ""                  # файл/документ последнего снимка (щелчок по уведомлению)
        self._monitor_started: datetime | None = None
        self._deadline: datetime | None = None  # когда остановить мониторинг по таймеру
        self._local_shortcut: QShortcut | None = None
        self._quitting = False
        self._loading = False
        self._tray_hint_shown = False
        self._start_after_select = False
        self._restore_after_select = False
        self._last_hotkey_time = 0.0
        self._highlighter: RegionHighlighter | None = None

        # Отложенное сохранение настроек (чтобы не писать файл на каждый щелчок спинбокса)
        self._save_timer = QTimer(self, singleShot=True, interval=400)
        self._save_timer.timeout.connect(self._save_settings_now)

        # Обратный отсчёт таймера автоматической остановки (раз в секунду)
        self._countdown = QTimer(self, interval=1000)
        self._countdown.timeout.connect(self._on_countdown)

        self._selector = RegionSelector(self)
        self._selector.region_selected.connect(self._on_region_selected)
        self._selector.cancelled.connect(self._on_selection_cancelled)

        self._icons = {True: app_icon("active"), False: app_icon("paused")}

        self.setWindowTitle(f"{APP_NAME} — автоскриншоты при изменении экрана")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(self.STYLE)
        self._build_ui()
        self._build_tray()
        self._load_values()
        self._update_state()
        self.resize(1060, 720)

        self._log(f"{APP_NAME} {APP_VERSION} запущен")
        self._log(f"Файл настроек: {get_config_path()}")
        self._setup_hotkey()

    # ================================================================ UI

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setSpacing(10)

        # --- Строка состояния и счётчик ---
        top = QHBoxLayout()
        self.status_label = QLabel(objectName="statusLabel")
        self.counter_label = QLabel(objectName="counterLabel")
        reset_btn = QPushButton("Сбросить")
        reset_btn.setToolTip("Обнулить счётчик скриншотов")
        reset_btn.clicked.connect(self._reset_counter)
        top.addWidget(self.status_label)
        top.addStretch()
        top.addWidget(self.counter_label)
        top.addWidget(reset_btn)
        root.addLayout(top)

        # --- Кнопки управления ---
        buttons = QHBoxLayout()
        self.start_btn = QPushButton(objectName="startButton")
        self.start_btn.setMinimumHeight(42)
        self.start_btn.clicked.connect(self.toggle_monitoring)
        self.select_btn = QPushButton("  Выбрать область")
        self.select_btn.setMinimumHeight(42)
        self.select_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMaxButton))
        self.select_btn.clicked.connect(self.select_region)
        self.show_region_btn = QPushButton("Показать область")
        self.show_region_btn.setMinimumHeight(42)
        self.show_region_btn.setToolTip("Подсветить выбранную область красной рамкой на пару секунд")
        self.show_region_btn.clicked.connect(self.highlight_region)
        buttons.addWidget(self.start_btn, 2)
        buttons.addWidget(self.select_btn, 2)
        buttons.addWidget(self.show_region_btn, 1)
        root.addLayout(buttons)
        root.addLayout(self._build_timer_row())

        # --- Две колонки: настройки слева (с прокруткой на маленьких экранах), журнал справа ---
        columns = QHBoxLayout()
        left_widget = QWidget()
        left = QVBoxLayout(left_widget)
        left.setContentsMargins(0, 0, 6, 0)
        left.addWidget(self._build_region_group())
        left.addWidget(self._build_save_group())
        left.addWidget(self._build_detection_group())
        left.addWidget(self._build_options_group())
        left.addStretch()
        scroll = QScrollArea()
        scroll.setWidget(left_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(left_widget.sizeHint().width() + 20)
        columns.addWidget(scroll, 5)
        columns.addWidget(self._build_log_group(), 6)
        root.addLayout(columns, 1)

        self.setCentralWidget(central)

        # --- Строка состояния внизу окна ---
        self.hotkey_label = QLabel()
        self.check_label = QLabel("Проверок ещё не было")
        self.statusBar().addWidget(self.hotkey_label)
        self.statusBar().addPermanentWidget(self.check_label)

    def _build_region_group(self) -> QGroupBox:
        box = QGroupBox("Область мониторинга")
        lay = QVBoxLayout(box)
        self.region_label = QLabel()
        self.region_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.region_label)
        return box

    def _build_timer_row(self) -> QHBoxLayout:
        """Таймер: автоматически остановить мониторинг через N часов/минут или в заданное время."""
        row = QHBoxLayout()
        self.timer_check = QCheckBox("Таймер: остановить мониторинг")
        self.timer_check.setToolTip(
            "Мониторинг выключится сам — например, через 1:30 (длительность лекции)\n"
            "или в 15:30. Отсчёт начинается при каждом нажатии «Старт».")
        self.timer_check.toggled.connect(self._on_timer_changed)
        self.timer_mode_combo = QComboBox()
        self.timer_mode_combo.addItem("через", TIMER_AFTER)
        self.timer_mode_combo.addItem("в", TIMER_AT)
        self.timer_mode_combo.currentIndexChanged.connect(self._on_timer_mode_changed)
        self.timer_edit = QTimeEdit(displayFormat="H:mm")
        self.timer_edit.timeChanged.connect(self._on_timer_changed)
        self.timer_hint = QLabel()
        self.timer_left_label = QLabel()
        self.timer_left_label.setStyleSheet("font-weight: 600;")
        row.addWidget(self.timer_check)
        row.addWidget(self.timer_mode_combo)
        row.addWidget(self.timer_edit)
        row.addWidget(self.timer_hint)
        row.addStretch()
        row.addWidget(self.timer_left_label)
        return row

    def _build_save_group(self) -> QGroupBox:
        box = QGroupBox("Куда сохранять")
        grid = QGridLayout(box)

        # Папка с отдельными файлами
        self.folder_check = QCheckBox("Файлы PNG/JPG в папку")
        self.folder_check.toggled.connect(self._on_targets_changed)
        self.folder_edit = QLineEdit(readOnly=True)
        self.choose_folder_btn = QPushButton("Выбрать папку…")
        self.choose_folder_btn.clicked.connect(self.choose_folder)
        self.open_folder_btn = QPushButton("Открыть")
        self.open_folder_btn.setToolTip("Открыть папку со скриншотами в проводнике")
        self.open_folder_btn.clicked.connect(self.open_folder)
        grid.addWidget(self.folder_check, 0, 0, 1, 4)
        grid.addWidget(QLabel("Папка:"), 1, 0)
        grid.addWidget(self.folder_edit, 1, 1, 1, 3)
        folder_buttons = QHBoxLayout()
        folder_buttons.addWidget(self.choose_folder_btn)
        folder_buttons.addWidget(self.open_folder_btn)
        folder_buttons.addStretch()
        grid.addLayout(folder_buttons, 2, 1, 1, 3)

        # Документ Word (конспект)
        self.docx_check = QCheckBox("Документ Word — конспект, который заполняется сам")
        self.docx_check.setToolTip(
            "Каждый скриншот дописывается в конец документа .docx.\n"
            "Если документ открыт в Microsoft Word, снимки появляются в нём сразу,\n"
            "и рядом можно печатать свои заметки.")
        self.docx_check.toggled.connect(self._on_targets_changed)
        self.docx_edit = QLineEdit(readOnly=True)
        self.choose_docx_btn = QPushButton("Выбрать документ…")
        self.choose_docx_btn.setToolTip("Выберите существующий документ или введите имя нового")
        self.choose_docx_btn.clicked.connect(self.choose_document)
        self.open_docx_btn = QPushButton("Открыть в Word")
        self.open_docx_btn.setToolTip("Открыть документ (если его ещё нет — он будет создан)")
        self.open_docx_btn.clicked.connect(self.open_document)
        self.captions_check = QCheckBox("Подписывать номер, дату и время")
        self.captions_check.toggled.connect(lambda v: self._set("docx_captions", v))
        grid.addWidget(self.docx_check, 3, 0, 1, 4)
        grid.addWidget(QLabel("Документ:"), 4, 0)
        grid.addWidget(self.docx_edit, 4, 1, 1, 3)
        docx_buttons = QHBoxLayout()
        docx_buttons.addWidget(self.choose_docx_btn)
        docx_buttons.addWidget(self.open_docx_btn)
        docx_buttons.addWidget(self.captions_check)
        docx_buttons.addStretch()
        grid.addLayout(docx_buttons, 5, 1, 1, 3)

        self.capture_combo = QComboBox()
        for mode, label in CAPTURE_LABELS:
            self.capture_combo.addItem(label, mode)
        self.capture_combo.currentIndexChanged.connect(self._on_capture_mode_changed)
        grid.addWidget(QLabel("Что снимать:"), 6, 0)
        grid.addWidget(self.capture_combo, 6, 1, 1, 3)

        self.format_combo = QComboBox()
        self.format_combo.addItem("PNG (без потерь)", "png")
        self.format_combo.addItem("JPG (меньше размер)", "jpg")
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        self.quality_spin = QSpinBox(minimum=10, maximum=100, suffix=" %")
        self.quality_spin.setToolTip("Качество JPG: больше — лучше картинка, но крупнее файл")
        self.quality_spin.valueChanged.connect(lambda v: self._set("jpeg_quality", v))
        grid.addWidget(QLabel("Формат:"), 7, 0)
        grid.addWidget(self.format_combo, 7, 1)
        grid.addWidget(QLabel("Качество JPG:"), 7, 2)
        grid.addWidget(self.quality_spin, 7, 3)
        grid.setColumnStretch(1, 1)
        return box

    def _build_detection_group(self) -> QGroupBox:
        box = QGroupBox("Детекция изменений")
        form = QFormLayout(box)

        self.interval_spin = QDoubleSpinBox(minimum=0.1, maximum=60, decimals=1,
                                            singleStep=0.5, suffix=" с")
        self.interval_spin.setToolTip("Как часто сравнивать область с предыдущим кадром")
        self.interval_spin.valueChanged.connect(lambda v: self._set("interval_sec", v))
        form.addRow("Интервал проверки:", self.interval_spin)

        self.threshold_spin = QDoubleSpinBox(minimum=0.01, maximum=100, decimals=2,
                                             singleStep=0.1, suffix=" %")
        self.threshold_spin.setToolTip(
            "Какой процент пикселей области должен измениться, чтобы сделать скриншот.\n"
            "Больше — меньше ложных срабатываний от мелких шумов.")
        self.threshold_spin.valueChanged.connect(lambda v: self._set("threshold_percent", v))
        form.addRow("Порог чувствительности:", self.threshold_spin)

        self.tolerance_spin = QSpinBox(minimum=0, maximum=255)
        self.tolerance_spin.setToolTip(
            "Насколько (0–255) должен измениться цвет пикселя, чтобы он считался изменённым.\n"
            "Помогает игнорировать шум сжатия видео и лёгкое мерцание. 0 — любое изменение.")
        self.tolerance_spin.valueChanged.connect(lambda v: self._set("pixel_tolerance", v))
        form.addRow("Допуск цвета пикселя:", self.tolerance_spin)

        self.min_interval_spin = QDoubleSpinBox(minimum=0, maximum=3600, decimals=1,
                                                singleStep=1, suffix=" с")
        self.min_interval_spin.setToolTip(
            "Защита от спама: минимальная пауза между двумя скриншотами.\n"
            "Изменение во время паузы не теряется — снимок будет сделан сразу после неё.")
        self.min_interval_spin.valueChanged.connect(lambda v: self._set("min_interval_sec", v))
        form.addRow("Мин. интервал между снимками:", self.min_interval_spin)
        return box

    def _build_options_group(self) -> QGroupBox:
        box = QGroupBox("Параметры")
        lay = QVBoxLayout(box)

        self.notify_check = QCheckBox("Уведомление в трее при каждом скриншоте")
        self.notify_check.setToolTip(
            "Если уведомления появляются внутри отслеживаемой области,\n"
            "они сами могут вызывать срабатывания — тогда отключите их.")
        self.notify_check.toggled.connect(lambda v: self._set("notifications_enabled", v))
        self.autostart_check = QCheckBox("Запускать мониторинг сразу при старте программы")
        self.autostart_check.toggled.connect(lambda v: self._set("autostart_monitoring", v))
        self.tray_check = QCheckBox("Сворачивать в трей при закрытии окна")
        self.tray_check.toggled.connect(lambda v: self._set("minimize_to_tray", v))
        for check in (self.notify_check, self.autostart_check, self.tray_check):
            lay.addWidget(check)

        self.winrun_check = QCheckBox("Запускать программу вместе с Windows (свёрнутой в трей)")
        self.winrun_check.setVisible(autorun_supported())
        self.winrun_check.toggled.connect(self._on_winrun_toggled)
        lay.addWidget(self.winrun_check)

        # Горячая клавиша паузы/старта
        row = QHBoxLayout()
        row.addWidget(QLabel("Горячая клавиша паузы/старта:"))
        self.hotkey_edit = QKeySequenceEdit()
        self.hotkey_edit.setMaximumSequenceLength(1)
        self.hotkey_edit.setToolTip("Щёлкните и нажмите новое сочетание, например Ctrl+Alt+S")
        self.hotkey_edit.editingFinished.connect(self._on_hotkey_edited)
        reset_hotkey_btn = QPushButton("По умолчанию")
        reset_hotkey_btn.setToolTip(f"Вернуть {DEFAULT_HOTKEY}")
        reset_hotkey_btn.clicked.connect(lambda: self._apply_hotkey(DEFAULT_HOTKEY))
        row.addWidget(self.hotkey_edit, 1)
        row.addWidget(reset_hotkey_btn)
        lay.addLayout(row)
        return box

    def _build_log_group(self) -> QGroupBox:
        box = QGroupBox("Журнал событий")
        lay = QVBoxLayout(box)
        self.log_view = QPlainTextEdit(readOnly=True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        lay.addWidget(self.log_view)
        row = QHBoxLayout()
        row.addStretch()
        clear_btn = QPushButton("Очистить журнал")
        clear_btn.clicked.connect(self.log_view.clear)
        row.addWidget(clear_btn)
        lay.addLayout(row)
        return box

    def _build_tray(self) -> None:
        """Иконка в системном трее с быстрым доступом к основным действиям."""
        self.tray: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self._icons[False], self)
        menu = QMenu(self)
        open_action = menu.addAction("Открыть окно")
        open_action.triggered.connect(self.show_window)
        menu.addSeparator()
        self.tray_toggle_action = menu.addAction("Старт")
        self.tray_toggle_action.triggered.connect(self.toggle_monitoring)
        menu.addAction("Выбрать область").triggered.connect(self.select_region)
        menu.addAction("Открыть папку со скриншотами").triggered.connect(self.open_folder)
        self.tray_notify_action = QAction("Уведомления о скриншотах", self, checkable=True)
        self.tray_notify_action.toggled.connect(self.notify_check.setChecked)
        menu.addAction(self.tray_notify_action)
        menu.addSeparator()
        menu.addAction("Выход").triggered.connect(self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.messageClicked.connect(self._on_tray_message_clicked)
        self.tray.show()

    @property
    def tray_available(self) -> bool:
        return self.tray is not None

    def _load_values(self) -> None:
        """Переносит значения настроек в элементы интерфейса."""
        s = self.settings
        self._loading = True
        try:
            self.folder_check.setChecked(s.save_to_folder)
            self.folder_edit.setText(s.save_dir)
            self.docx_check.setChecked(s.save_to_docx)
            self.docx_edit.setText(s.docx_path)
            self.captions_check.setChecked(s.docx_captions)
            self.timer_check.setChecked(s.timer_enabled)
            self.timer_mode_combo.setCurrentIndex(max(0, self.timer_mode_combo.findData(s.timer_mode)))
            self._show_timer_value()
            self.hotkey_edit.setKeySequence(QKeySequence(s.hotkey))
            self.capture_combo.setCurrentIndex(max(0, self.capture_combo.findData(s.capture_mode)))
            self.format_combo.setCurrentIndex(max(0, self.format_combo.findData(s.image_format)))
            self.quality_spin.setValue(s.jpeg_quality)
            self.quality_spin.setEnabled(s.image_format == "jpg")
            self.interval_spin.setValue(s.interval_sec)
            self.threshold_spin.setValue(s.threshold_percent)
            self.tolerance_spin.setValue(s.pixel_tolerance)
            self.min_interval_spin.setValue(s.min_interval_sec)
            self.notify_check.setChecked(s.notifications_enabled)
            self.autostart_check.setChecked(s.autostart_monitoring)
            self.tray_check.setChecked(s.minimize_to_tray)
            self.winrun_check.setChecked(is_autorun_enabled())
            if self.tray:
                self.tray_notify_action.setChecked(s.notifications_enabled)
        finally:
            self._loading = False
        self._update_region_label()
        self._update_target_widgets()

    # ================================================================ Состояние

    def _update_state(self) -> None:
        running = self.monitor is not None
        style = self.style()
        if running:
            self.status_label.setText("● Мониторинг активен")
            self.status_label.setStyleSheet("color: #1E9E57;")
            self.start_btn.setText("  Стоп")
            self.start_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        else:
            self.status_label.setText("● Мониторинг остановлен")
            self.status_label.setStyleSheet("color: #888888;")
            self.start_btn.setText("  Старт")
            self.start_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        # Перерисовываем кнопку, чтобы применился стиль для свойства running
        self.start_btn.setProperty("running", running)
        style.unpolish(self.start_btn)
        style.polish(self.start_btn)

        self.counter_label.setText(f"Скриншотов: <b>{self.shot_count}</b>")
        self.show_region_btn.setEnabled(self.settings.region is not None)
        if self.tray:
            self.tray.setIcon(self._icons[running])
            self.tray_toggle_action.setText("Пауза" if running else "Старт")
            state = "мониторинг активен" if running else "мониторинг остановлен"
            tip = f"{APP_NAME} — {state}\nСкриншотов: {self.shot_count}"
            if running and self._deadline:
                tip += f"\nОстановка по таймеру в {self._deadline:%H:%M}"
            self.tray.setToolTip(tip)

    def _update_region_label(self) -> None:
        region = self.settings.region
        if region is None:
            self.region_label.setText(
                '<span style="color:#C98A00">Область не выбрана — нажмите «Выбрать область»</span>')
        else:
            self.region_label.setText(
                f"<b>X:</b> {region.left} &nbsp; <b>Y:</b> {region.top} &nbsp;&nbsp; "
                f"<b>Ширина:</b> {region.width} px &nbsp; <b>Высота:</b> {region.height} px")
        self.show_region_btn.setEnabled(region is not None)

    def _reset_counter(self) -> None:
        self.shot_count = 0
        self._update_state()

    # ================================================================ Журнал и уведомления

    def _log(self, text: str, level: str = "info") -> None:
        """Добавляет запись в журнал событий (и в лог-файл)."""
        stamp = datetime.now().strftime("%H:%M:%S")
        body = html.escape(text)
        color = LOG_COLORS.get(level)
        if color:
            body = f'<span style="color:{color}">{body}</span>'
        self.log_view.appendHtml(f'<span style="color:#8a8a8a">[{stamp}]</span> {body}')
        log.log(LOG_LEVELS.get(level, logging.INFO), text)

    def _notify(self, title: str, text: str,
                icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information) -> None:
        """Всплывающее уведомление в трее (если трей доступен)."""
        if self.tray:
            self.tray.showMessage(title, text, icon, 3000)

    def _window_hidden(self) -> bool:
        return not self.isVisible() or self.isMinimized()

    # ================================================================ Мониторинг

    def toggle_monitoring(self) -> None:
        if self.monitor:
            self.stop_monitoring()
        else:
            self.start_monitoring(interactive=not self._window_hidden())

    def start_monitoring(self, interactive: bool = True) -> bool:
        """
        Запускает мониторинг после проверок. interactive=False — ошибки
        показываются уведомлением в трее, а не диалогом (автозапуск, горячая клавиша).
        """
        if self.monitor:
            return True
        s = self.settings

        # Проверка 1: выбрана ли область
        if s.region is None:
            self._log("Мониторинг не запущен: не выбрана область", "warning")
            if interactive:
                answer = QMessageBox.question(
                    self, APP_NAME, "Область для мониторинга ещё не выбрана.\n\nВыбрать её сейчас?")
                if answer == QMessageBox.StandardButton.Yes:
                    self._start_after_select = True
                    self.select_region()
            else:
                self._notify("Мониторинг не запущен", "Сначала выберите область экрана",
                             QSystemTrayIcon.MessageIcon.Warning)
            return False

        # Проверка 2: видна ли область на подключённых мониторах
        if not region_on_screens(s.region):
            msg = ("Выбранная область находится за пределами экранов "
                   "(возможно, монитор отключён). Выберите область заново.")
            self._log(msg, "warning")
            if interactive:
                QMessageBox.warning(self, APP_NAME, msg)
            else:
                self._notify("Мониторинг не запущен", msg, QSystemTrayIcon.MessageIcon.Warning)
            return False

        # Проверка 3: выбрано ли, куда сохранять, и доступно ли это для записи
        if not (s.save_to_folder or s.save_to_docx):
            return self._start_refused("Не выбрано, куда сохранять скриншоты: отметьте папку "
                                       "и/или документ Word.", interactive)
        if s.save_to_folder:
            error = check_folder_writable(s.save_dir)
            if error:
                if interactive:
                    self._log(error, "error")
                    answer = QMessageBox.warning(
                        self, APP_NAME, f"{error}\n\nВыбрать другую папку?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    if answer == QMessageBox.StandardButton.Yes and self.choose_folder():
                        return self.start_monitoring(interactive)
                    return False
                return self._start_refused(error, interactive)
        if s.save_to_docx:
            error = check_docx_target(s.docx_path)
            if error:
                return self._start_refused(error, interactive)

        monitor = ScreenMonitor(s, self)
        monitor.screenshot_saved.connect(self._on_screenshot_saved)
        monitor.frame_checked.connect(self._on_frame_checked)
        monitor.log_message.connect(self._log)
        monitor.fatal_error.connect(self._on_monitor_fatal)
        monitor.finished.connect(self._on_thread_finished)
        self._threads.add(monitor)
        self.monitor = monitor
        monitor.start()

        mode = dict(CAPTURE_LABELS)[s.capture_mode].lower()
        targets = []
        if s.save_to_folder:
            targets.append(f"папка «{s.save_dir}»")
        if s.save_to_docx:
            targets.append(f"документ «{Path(s.docx_path).name}»")
        self._log(f"Мониторинг запущен: интервал {s.interval_sec:g} с, порог {s.threshold_percent:g} %, "
                  f"снимать: {mode}, формат {s.image_format.upper()}, куда: {', '.join(targets)}",
                  "success")
        self._monitor_started = datetime.now()
        self._arm_timer(announce=True)
        self._update_state()
        return True

    def _start_refused(self, message: str, interactive: bool) -> bool:
        """Сообщает, почему мониторинг не запущен (диалог или уведомление в трее)."""
        self._log(message, "error")
        if interactive:
            QMessageBox.warning(self, APP_NAME, message)
        else:
            self._notify("Мониторинг не запущен", message, QSystemTrayIcon.MessageIcon.Critical)
        return False

    def stop_monitoring(self, message: str | None = "Мониторинг остановлен") -> None:
        if not self.monitor:
            return
        monitor, self.monitor = self.monitor, None
        monitor.stop()  # поток завершится сам в течение интервала проверки
        if message:
            self._log(message)
        self._monitor_started = None
        self._arm_timer()
        self.check_label.setText("Мониторинг остановлен")
        self._update_state()

    def _on_thread_finished(self) -> None:
        thread = self.sender()
        self._threads.discard(thread)
        if thread is self.monitor:  # поток завершился сам (после ошибки)
            self.monitor = None
            self._update_state()
        thread.deleteLater()

    def _on_screenshot_saved(self, description: str, percent: float, target: str) -> None:
        self.shot_count += 1
        self.last_target = target
        self._log(f"Скриншот сохранён: {description} (изменилось {percent:.2f} % области)", "success")
        self._update_state()
        if self.settings.notifications_enabled:
            what = "документ" if target.lower().endswith(".docx") else "папку"
            self._notify("Скриншот сохранён", f"{description}\nНажмите, чтобы открыть {what}")

    def _on_frame_checked(self, percent: float) -> None:
        self.check_label.setText(f"Проверка {datetime.now():%H:%M:%S}: изменилось {percent:.2f} % "
                                 f"(порог {self.settings.threshold_percent:g} %)")

    def _on_monitor_fatal(self, message: str) -> None:
        if self.sender() is not self.monitor:
            return  # ошибка от уже остановленного потока — неактуальна
        self._log(message, "error")
        self.stop_monitoring("Мониторинг остановлен из-за ошибки")
        self._notify("Мониторинг остановлен", message, QSystemTrayIcon.MessageIcon.Critical)
        if not self._window_hidden():
            QMessageBox.critical(self, APP_NAME, message)

    # ================================================================ Выбор области

    def select_region(self) -> None:
        if self._selector.is_active():
            return
        if self.monitor:
            # Затемнение экрана не должно попасть в скриншоты — ставим мониторинг на паузу
            self._start_after_select = True
            self.stop_monitoring("Мониторинг приостановлен на время выбора области")
        self._restore_after_select = self.isVisible() and not self.isMinimized()
        self.hide()
        # Небольшая пауза, чтобы окно успело исчезнуть до «стоп-кадра» экрана
        QTimer.singleShot(300, self._selector.start)

    def _finish_selection(self) -> None:
        if self._restore_after_select:
            self.show_window()

    def _on_region_selected(self, region: Region) -> None:
        self._finish_selection()
        self.settings.region = region
        self._update_region_label()
        self._settings_changed()
        self._log(f"Выбрана область: {region}")
        if self._start_after_select:
            self._start_after_select = False
            self.start_monitoring(interactive=not self._window_hidden())

    def _on_selection_cancelled(self) -> None:
        self._finish_selection()
        self._log("Выбор области отменён")
        # Возобновляем мониторинг, если он работал до выбора области
        if self._start_after_select and self.settings.region is not None:
            self.start_monitoring(interactive=not self._window_hidden())
        self._start_after_select = False

    def highlight_region(self) -> None:
        if self.settings.region is None:
            return
        self._highlighter = RegionHighlighter.show_region(self.settings.region)
        if self._highlighter is None:
            self._log("Область находится за пределами подключённых экранов", "warning")

    # ================================================================ Папка

    def choose_folder(self) -> bool:
        """Диалог выбора папки. Возвращает True, если папка выбрана и доступна."""
        folder = QFileDialog.getExistingDirectory(self, "Папка для скриншотов", self.settings.save_dir)
        if not folder:
            return False
        folder = os.path.normpath(folder)
        error = check_folder_writable(folder)
        if error:
            self._log(error, "error")
            QMessageBox.warning(self, APP_NAME, f"{error}\n\nВыберите другую папку.")
            return False
        self.settings.save_dir = folder
        self.folder_edit.setText(folder)
        self._settings_changed()
        self._log(f"Папка для скриншотов: {folder}")
        return True

    def open_folder(self) -> None:
        folder = self.settings.save_dir
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            self._log(f"Не удалось открыть папку «{folder}»: {exc.strerror or exc}", "error")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def choose_document(self) -> bool:
        """Выбор документа Word: существующего (скриншоты допишутся в конец) или нового."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Документ Word для скриншотов", self.settings.docx_path,
            "Документ Word (*.docx)", options=QFileDialog.Option.DontConfirmOverwrite)
        if not path:
            return False
        path = os.path.normpath(path)
        if not path.lower().endswith(".docx"):
            path += ".docx"
        error = check_docx_target(path)
        if error:
            self._log(error, "error")
            QMessageBox.warning(self, APP_NAME, error)
            return False
        self.settings.docx_path = path
        self.docx_edit.setText(path)
        if not self.docx_check.isChecked():
            self.docx_check.setChecked(True)  # выбрали документ — значит, хотят в него сохранять
        self._settings_changed()
        exists = "существующий, скриншоты будут дописаны в конец" if os.path.exists(path) else "новый"
        self._log(f"Документ для скриншотов: {path} ({exists})")
        return True

    def open_document(self) -> None:
        """Открывает документ в Word (создаёт пустой, если его ещё нет)."""
        path = self.settings.docx_path
        error = check_docx_target(path)
        if error:
            self._log(error, "error")
            QMessageBox.warning(self, APP_NAME, error)
            return
        try:
            ensure_document(path)
        except Exception as exc:  # noqa: BLE001
            self._log(f"Не удалось создать документ «{path}»: {exc}", "error")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _on_targets_changed(self) -> None:
        self._update_target_widgets()
        if self._loading:
            return
        self.settings.save_to_folder = self.folder_check.isChecked()
        self.settings.save_to_docx = self.docx_check.isChecked()
        self._settings_changed()

    def _update_target_widgets(self) -> None:
        folder, docx = self.folder_check.isChecked(), self.docx_check.isChecked()
        for widget in (self.folder_edit, self.choose_folder_btn, self.open_folder_btn):
            widget.setEnabled(folder)
        for widget in (self.docx_edit, self.choose_docx_btn, self.open_docx_btn, self.captions_check):
            widget.setEnabled(docx)

    # ================================================================ Таймер

    def _show_timer_value(self) -> None:
        """Показывает в поле значение для текущего режима таймера."""
        s = self.settings
        if self.timer_mode_combo.currentData() == TIMER_AT:
            hours, minutes = parse_hhmm(s.timer_at) or (18, 0)
            self.timer_hint.setText("(время суток)")
        else:
            hours, minutes = divmod(s.timer_minutes, 60)
            self.timer_hint.setText("(часы:минуты)")
        self.timer_edit.setTime(QTime(hours, minutes))

    def _on_timer_mode_changed(self, _index: int) -> None:
        was_loading, self._loading = self._loading, True
        try:
            self._show_timer_value()
        finally:
            self._loading = was_loading
        self._on_timer_changed()

    def _on_timer_changed(self, *_args) -> None:
        if self._loading:
            return
        s = self.settings
        s.timer_enabled = self.timer_check.isChecked()
        s.timer_mode = self.timer_mode_combo.currentData()
        value = self.timer_edit.time()
        if s.timer_mode == TIMER_AT:
            s.timer_at = f"{value.hour():02d}:{value.minute():02d}"
        else:
            s.timer_minutes = max(1, value.hour() * 60 + value.minute())
        self._settings_changed()
        self._arm_timer()

    def _arm_timer(self, announce: bool = False) -> None:
        """Пересчитывает момент остановки (при старте и при изменении настроек таймера)."""
        s = self.settings
        if self.monitor is None or not s.timer_enabled or self._monitor_started is None:
            self._deadline = None
            self._countdown.stop()
            self.timer_left_label.clear()
            return
        base = datetime.now() if s.timer_mode == TIMER_AT else self._monitor_started
        self._deadline = timer_deadline(base, s.timer_mode, s.timer_minutes, s.timer_at)
        if announce:
            left = format_duration(self._deadline - datetime.now())
            self._log(f"Таймер: мониторинг остановится в {self._deadline:%H:%M} (через {left})")
        self._countdown.start()
        self._on_countdown()

    def _on_countdown(self) -> None:
        if self._deadline is None:
            return
        left = self._deadline - datetime.now()
        if left.total_seconds() <= 0:
            count = self.shot_count
            self.stop_monitoring("Таймер: мониторинг остановлен автоматически")
            self._notify(APP_NAME, f"Мониторинг остановлен по таймеру. Скриншотов: {count}")
            return
        self.timer_left_label.setText(f"⏱ Осталось {format_duration(left)} (до {self._deadline:%H:%M})")

    # ================================================================ Настройки

    def _set(self, name: str, value) -> None:
        """Изменение одного параметра из интерфейса."""
        if self._loading:
            return
        setattr(self.settings, name, value)
        if name == "notifications_enabled" and self.tray:
            self.tray_notify_action.setChecked(value)
        self._settings_changed()

    def _on_capture_mode_changed(self, _index: int) -> None:
        self._set("capture_mode", self.capture_combo.currentData())

    def _on_format_changed(self, _index: int) -> None:
        fmt = self.format_combo.currentData()
        self.quality_spin.setEnabled(fmt == "jpg")
        self._set("image_format", fmt)

    def _on_winrun_toggled(self, enabled: bool) -> None:
        if self._loading:
            return
        try:
            set_autorun(enabled)
            self._log("Автозапуск вместе с Windows " + ("включён" if enabled else "выключен"))
        except OSError as exc:
            self._log(f"Не удалось изменить автозапуск: {exc}", "error")

    def _settings_changed(self) -> None:
        """Передаёт настройки работающему потоку и планирует запись в файл."""
        if self.monitor:
            self.monitor.update_settings(self.settings)
        self._save_timer.start()

    def _save_settings_now(self) -> None:
        self._save_timer.stop()
        if not self._persist:
            return
        try:
            save_settings(self.settings)
        except OSError as exc:
            self._log(f"Не удалось сохранить настройки: {exc}", "error")

    # ================================================================ Горячая клавиша

    def _setup_hotkey(self) -> None:
        self.hotkey = GlobalHotkey(self)
        self.hotkey.activated.connect(self._on_hotkey)
        self._register_hotkey(self.settings.hotkey)

    def _register_hotkey(self, combo: str) -> bool:
        """Регистрирует сочетание. Если глобально не вышло — работает только в окне программы."""
        if self._local_shortcut is not None:
            self._local_shortcut.setEnabled(False)
            self._local_shortcut.deleteLater()
            self._local_shortcut = None
        if self.hotkey.register(combo):
            self.hotkey_label.setText(f"Горячая клавиша {combo} — пауза/старт")
            self._log(f"Горячая клавиша {combo}: пауза/старт мониторинга")
            return True
        # Запасной вариант: сочетание работает, только когда окно активно
        self._local_shortcut = QShortcut(QKeySequence(combo), self)
        self._local_shortcut.activated.connect(self._on_hotkey)
        self.hotkey_label.setText(f"{combo} — пауза/старт (только в окне программы)")
        self._log(f"Глобальная горячая клавиша {combo} недоступна ({self.hotkey.error}). "
                  "Она будет работать только в окне программы.", "warning")
        return False

    def _on_hotkey_edited(self) -> None:
        combo = self.hotkey_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        if combo and combo != self.settings.hotkey:
            self._apply_hotkey(combo)

    def _apply_hotkey(self, combo: str) -> None:
        """Меняет горячую клавишу из интерфейса."""
        if parse_hotkey(combo) is None:
            self._log(f"Сочетание «{combo}» не подходит: нужна буква, цифра или F1–F24 "
                      "вместе с Ctrl, Alt, Shift или Win", "warning")
            self.hotkey_edit.setKeySequence(QKeySequence(self.settings.hotkey))
            return
        self.hotkey_edit.setKeySequence(QKeySequence(combo))
        if combo == self.settings.hotkey and self._local_shortcut is None:
            return
        self._set("hotkey", combo)
        self._register_hotkey(combo)

    def _on_hotkey(self) -> None:
        now = time.monotonic()
        if now - self._last_hotkey_time < 0.4:  # защита от двойного срабатывания
            return
        self._last_hotkey_time = now
        was_running = self.monitor is not None
        self.toggle_monitoring()
        if self._window_hidden() and was_running != (self.monitor is not None):
            text = "Мониторинг запущен" if self.monitor else "Мониторинг приостановлен"
            self._notify(APP_NAME, f"{text} ({self.settings.hotkey})")

    # ================================================================ Окно и трей

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.show_window()

    def _on_tray_message_clicked(self) -> None:
        if self.last_target.lower().endswith(".docx"):
            self.open_document()
        elif self.last_target:
            self.open_folder()
        else:
            self.show_window()

    def closeEvent(self, event) -> None:
        if self._quitting:
            event.accept()
            return
        if self.settings.minimize_to_tray and self.tray:
            event.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self._notify(APP_NAME, "Программа продолжает работать в трее. "
                                       "Для выхода используйте меню значка в трее.")
            return
        event.accept()
        self.quit_app()

    def quit_app(self) -> None:
        """Корректный выход: останавливаем поток, сохраняем настройки."""
        if self._quitting:
            return
        self._quitting = True
        self._selector.cancel()
        self.stop_monitoring(message=None)
        for thread in list(self._threads):
            thread.stop()
            thread.wait(5000)
        self.hotkey.unregister()
        self._save_settings_now()
        if self.tray:
            self.tray.hide()
        log.info("Выход из программы")
        QApplication.quit()
