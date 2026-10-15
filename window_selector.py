"""
window_selector.py — выбор окна для отслеживания (как список окон в OBS)
и выбор области внутри этого окна (как фильтр «Обрезка» в OBS).

WindowPickerDialog — открытые окна в виде «[программа.exe] Заголовок», поиск
                     и превью выбранного окна;
WindowCropDialog   — снимок окна, на котором мышью выделяется нужная часть
                     (например, область со слайдами в окне Zoom).
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QVBoxLayout,
                             QWidget)

from settings import Crop
from window_capture import WindowInfo, default_api, match_window

PREVIEW_SIZE = (420, 280)


def frame_to_pixmap(frame) -> QPixmap:
    """Кадр numpy (BGRA) → QPixmap для превью."""
    height, width = frame.shape[:2]
    data = frame.tobytes()
    # BGRA в памяти — это формат RGB32 в Qt (альфа-канал игнорируется)
    image = QImage(data, width, height, width * 4, QImage.Format.Format_RGB32)
    return QPixmap.fromImage(image.copy())  # copy — данные кадра больше не нужны


class WindowPickerDialog(QDialog):
    """Список открытых окон с поиском и превью."""

    def __init__(self, parent=None, current: tuple[str, str, str] | None = None, api=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор окна для отслеживания")
        self.resize(860, 460)
        self._api = api if api is not None else default_api()
        self._current = current            # (заголовок, класс, программа) выбранного ранее окна
        self._windows: list[WindowInfo] = []

        self.search_edit = QLineEdit(placeholderText="Поиск по названию окна или программы")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._show_preview)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.accept())
        refresh_btn = QPushButton("Обновить список")
        refresh_btn.clicked.connect(self.refresh)

        self.preview = QLabel("Выберите окно в списке")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedSize(*PREVIEW_SIZE)
        self.preview.setStyleSheet("background: #202020; color: #cccccc; border-radius: 6px;")
        self.preview.setWordWrap(True)
        hint = QLabel("Окно снимается, даже если его перекрывают другие окна. "
                      "Свёрнутое окно снять нельзя — мониторинг подождёт, пока его развернут. "
                      "Если программу закрыть и открыть снова, окно найдётся само.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #808080;")

        self.crop_requested = False  # после выбора окна сразу выбрать область в нём
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                        | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Всё окно")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setToolTip(
            "Отслеживать окно целиком")
        self.crop_button = self.buttons.addButton("Окно и область в нём…",
                                                  QDialogButtonBox.ButtonRole.ActionRole)
        self.crop_button.setToolTip("Выбрать окно, а затем выделить в нём нужную часть "
                                    "(например, только область со слайдами)")
        self.crop_button.clicked.connect(self._request_crop)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        left = QVBoxLayout()
        left.addWidget(self.search_edit)
        left.addWidget(self.list_widget, 1)
        left.addWidget(refresh_btn, 0, Qt.AlignmentFlag.AlignLeft)
        right = QVBoxLayout()
        right.addWidget(self.preview)
        right.addWidget(hint)
        right.addStretch()
        columns = QHBoxLayout()
        columns.addLayout(left, 1)
        columns.addLayout(right)
        root = QVBoxLayout(self)
        root.addLayout(columns, 1)
        root.addWidget(self.buttons)

        self.refresh()

    # --- список окон ---

    def refresh(self) -> None:
        """Перечитывает список окон, сохраняя выделение."""
        selected = self.selected_window()
        self._windows = self._api.list_windows() if self._api is not None else []
        self.list_widget.clear()
        for info in self._windows:
            text = info.label() + ("   (свёрнуто)" if info.minimized else "")
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, info)
            item.setToolTip(f"Программа: {info.exe or '—'}\nЗаголовок: {info.title}\n"
                            f"Класс окна: {info.class_name}")
            self.list_widget.addItem(item)

        # Что выделить: прежний выбор в этом диалоге или окно из настроек
        target = None
        if selected is not None:
            target = match_window(self._windows, selected.title, selected.class_name,
                                  selected.exe, selected.hwnd)
        elif self._current is not None:
            target = match_window(self._windows, *self._current)
        for row in range(self.list_widget.count()):
            if target is not None and self.list_widget.item(row).data(Qt.ItemDataRole.UserRole) == target:
                self.list_widget.setCurrentRow(row)
                break
        if self._api is None:
            self.preview.setText("Выбор окна доступен только в Windows")
        elif not self._windows:
            self.preview.setText("Открытых окон не найдено")
        self._apply_filter(self.search_edit.text())
        self._update_ok_button()

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        first_visible = None
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            item.setHidden(bool(needle) and needle not in item.text().lower())
            if first_visible is None and not item.isHidden():
                first_visible = item
        # Выделенное окно скрыто поиском — выделяем первое подходящее
        current = self.list_widget.currentItem()
        if (current is None or current.isHidden()) and first_visible is not None:
            self.list_widget.setCurrentItem(first_visible)
        self._update_ok_button()

    def selected_window(self) -> WindowInfo | None:
        item = self.list_widget.currentItem()
        if item is None or item.isHidden():
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _request_crop(self) -> None:
        self.crop_requested = True
        self.accept()

    def _update_ok_button(self) -> None:
        enabled = self.selected_window() is not None
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(enabled)
        self.crop_button.setEnabled(enabled)

    # --- превью ---

    def _show_preview(self, *_args) -> None:
        self._update_ok_button()
        info = self.selected_window()
        if info is None:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Выберите окно в списке")
            return
        if info.minimized:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Окно свёрнуто.\nРазверните его, чтобы увидеть превью.")
            return
        frame = None
        try:
            frame = self._api.capture(info.hwnd)
        except Exception:  # noqa: BLE001 — превью не должно ломать выбор
            frame = None
        if frame is None or not frame[..., :3].any():
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Превью недоступно — это окно не отдаёт своё изображение.\n"
                                 "Его можно снимать с экрана (галочка в главном окне).")
            return
        pixmap = frame_to_pixmap(frame).scaled(
            self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.preview.setPixmap(pixmap)


# ---------------------------------------------------------------------------
# Выбор области внутри окна
# ---------------------------------------------------------------------------

class _CropCanvas(QWidget):
    """Снимок окна, на котором мышью выделяется прямоугольник (в пикселях окна)."""

    changed = pyqtSignal()
    DIM = QColor(0, 0, 0, 130)
    ACCENT = QColor(0, 162, 255)

    def __init__(self, pixmap: QPixmap, box: tuple[int, int, int, int] | None):
        super().__init__()
        self._pixmap = pixmap
        self._origin: QPointF | None = None
        self._selection = QRectF(*box) if box else None
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 200)

    # --- пересчёт координат: виджет ↔ пиксели окна ---

    def _layout(self) -> tuple[float, float, float]:
        """Масштаб и смещение картинки внутри виджета (картинка вписана по центру)."""
        iw, ih = self._pixmap.width(), self._pixmap.height()
        scale = min(self.width() / iw, self.height() / ih)
        return scale, (self.width() - iw * scale) / 2, (self.height() - ih * scale) / 2

    def _to_image(self, pos: QPointF) -> QPointF:
        scale, dx, dy = self._layout()
        x = min(max((pos.x() - dx) / scale, 0.0), float(self._pixmap.width()))
        y = min(max((pos.y() - dy) / scale, 0.0), float(self._pixmap.height()))
        return QPointF(x, y)

    def _to_widget(self, rect: QRectF) -> QRectF:
        scale, dx, dy = self._layout()
        return QRectF(dx + rect.x() * scale, dy + rect.y() * scale,
                      rect.width() * scale, rect.height() * scale)

    # --- результат ---

    def box(self) -> tuple[int, int, int, int] | None:
        """Выделение (x, y, ширина, высота) в пикселях окна; None — выделения нет."""
        if self._selection is None:
            return None
        r = self._selection.normalized()
        x, y = round(r.left()), round(r.top())
        w, h = round(r.right()) - x, round(r.bottom()) - y
        if w < Crop.MIN_SIZE or h < Crop.MIN_SIZE:
            return None
        return x, y, w, h

    def clear(self) -> None:
        self._selection = None
        self.update()
        self.changed.emit()

    # --- отрисовка и мышь ---

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(32, 32, 32))
        image_rect = self._to_widget(QRectF(0, 0, self._pixmap.width(), self._pixmap.height()))
        p.drawPixmap(image_rect, self._pixmap, QRectF(self._pixmap.rect()))
        if self._selection is not None:
            sel = self._to_widget(self._selection.normalized())
            mask = QPainterPath()
            mask.addRect(image_rect)
            hole = QPainterPath()
            hole.addRect(sel)
            p.fillPath(mask.subtracted(hole), self.DIM)
            p.setPen(QPen(self.ACCENT, 2))
            p.drawRect(sel)
            box = self.box()
            if box:
                text = f"{box[2]} × {box[3]} px"
                p.setPen(QColor(255, 255, 255))
                label = QRectF(sel.left(), max(0.0, sel.top() - 22), 140, 20)
                p.fillRect(label, QColor(20, 20, 20, 220))
                p.drawText(label, Qt.AlignmentFlag.AlignCenter, text)
        p.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = self._to_image(event.position())
            self._selection = QRectF(self._origin, self._origin)
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._origin is not None:
            self._selection = QRectF(self._origin, self._to_image(event.position())).normalized()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        self._origin = None
        if self.box() is None:
            self._selection = None  # случайный щелчок — выделения нет
        self.update()
        self.changed.emit()


class WindowCropDialog(QDialog):
    """Выбор части окна: на снимке окна выделяется нужная область."""

    def __init__(self, parent, frame, crop: Crop | None, title: str):
        super().__init__(parent)
        self.setWindowTitle("Область в окне")
        height, width = frame.shape[:2]
        self._size = (width, height)
        self.canvas = _CropCanvas(frame_to_pixmap(frame), crop.box(width, height) if crop else None)
        self.canvas.changed.connect(self._update_info)

        header = QLabel(f"<b>{title}</b>")
        header.setTextFormat(Qt.TextFormat.RichText)
        hint = QLabel("Выделите мышью часть окна, которую нужно отслеживать — например, область "
                      "со слайдами без чата и видео участников. Если окно потом растянуть, "
                      "выделенная часть растянется вместе с ним.")
        hint.setWordWrap(True)
        self.info = QLabel()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Готово")
        whole = buttons.addButton("Всё окно", QDialogButtonBox.ButtonRole.ResetRole)
        whole.setToolTip("Снять выделение и отслеживать окно целиком")
        whole.clicked.connect(self.canvas.clear)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(header)
        root.addWidget(hint)
        root.addWidget(self.canvas, 1)
        root.addWidget(self.info)
        root.addWidget(buttons)

        # Размер диалога: снимок окна в натуральную величину, но не больше 85 % экрана
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(min(width + 40, int(screen.width() * 0.85)),
                    min(height + 170, int(screen.height() * 0.85)))
        self._update_info()

    def _update_info(self) -> None:
        box = self.canvas.box()
        if box is None:
            self.info.setText(f"Выделения нет — будет отслеживаться всё окно ({self._size[0]} × "
                              f"{self._size[1]} px)")
        else:
            self.info.setText(f"Выделено: X {box[0]}, Y {box[1]} — {box[2]} × {box[3]} px "
                              f"(окно {self._size[0]} × {self._size[1]} px)")

    def crop(self) -> Crop | None:
        """Выбранная часть окна (None — всё окно)."""
        box = self.canvas.box()
        if box is None:
            return None
        crop = Crop.from_box(*box, *self._size)
        return None if crop.is_whole() else crop
