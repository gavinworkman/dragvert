import math
import os
from pathlib import Path

from PIL import ImageEnhance
from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal, QPointF, QRectF, QUrl
from PyQt5.QtGui import QColor, QCursor, QDesktopServices, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDialog,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu,
    QMessageBox, QPlainTextEdit, QPushButton, QSlider, QSpinBox, QSystemTrayIcon,
    QVBoxLayout, QWidget)

from . import core
from .x11 import PointerMonitor

STYLE = '''
QWidget { background: #161c27; color: #edf2fb; font-family: "DejaVu Sans"; font-size: 13px; }
QMainWindow, QDialog { background: #161c27; }
QLabel#title { font-size: 32px; font-weight: bold; }
QLabel#muted { color: #a8b4c9; }
QPushButton { background: #293449; border: 1px solid #3c4960; border-radius: 8px; padding: 10px 16px; }
QPushButton:hover { background: #3b4963; border-color: #edb578; }
QPushButton:disabled { color: #67748a; }
QPushButton#primary { background: #edb578; color: #1b2230; font-weight: bold; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit { background: #101621; border: 1px solid #3c4960; border-radius: 6px; padding: 6px; }
QSlider::groove:horizontal { background: #3c4960; height: 5px; }
QSlider::handle:horizontal { background: #edb578; width: 16px; margin: -6px 0; border-radius: 8px; }
QMenu { border: 1px solid #3c4960; padding: 6px; }
QMenu::item { padding: 8px 20px; }
QMenu::item:selected { background: #3b4963; }
'''


def pixmap(image):
    image = image.convert('RGBA')
    data = image.tobytes('raw', 'RGBA')
    return QPixmap.fromImage(QImage(data, image.width, image.height, image.width * 4, QImage.Format_RGBA8888).copy())


def button(text, slot, primary=False):
    b = QPushButton(text)
    if primary:
        b.setObjectName('primary')
    b.clicked.connect(slot)
    return b


def local_files(mime):
    return [Path(u.toLocalFile()) for u in mime.urls() if u.isLocalFile() and Path(u.toLocalFile()).is_file()]


class Worker(QThread):
    completed = pyqtSignal(list, list)

    def __init__(self, paths, operation, parent=None):
        super().__init__(parent)
        self.paths, self.operation = list(paths), operation

    def run(self):
        outputs, errors = [], []
        for path in self.paths:
            try:
                outputs.extend(self.operation(path))
            except Exception as exc:
                errors.append(f'{path.name}: {exc}')
        self.completed.emit(outputs, errors)


class RadialMenu(QWidget):
    chosen = pyqtSignal(str, list)
    actions = [('Convert', '↗'), ('Metadata', 'i'), ('Edit', '±'), ('Annotate', 'T'),
               ('Add BG', '▧'), ('Crop', '⌗'), ('Redact', '▬'), ('Compress', '↓')]

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFixedSize(390, 390)
        self.paths, self.hover = [], -1
        self.autohide = QTimer(self)
        self.autohide.setSingleShot(True)
        self.autohide.timeout.connect(self.hide)

    def popup(self, paths=(), position=None):
        self.paths, self.hover = list(paths), -1
        pos = position or QCursor.pos()
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(max(area.left(), min(pos.x() - 195, area.right() - 390)),
                  max(area.top(), min(pos.y() - 195, area.bottom() - 390)))
        self.show()
        self.raise_()
        self.autohide.start(15000)
        self.update()

    def sector(self, pos):
        x, y = pos.x() - 195, pos.y() - 195
        if not 64 < math.hypot(x, y) < 186:
            return -1
        return int(((math.degrees(math.atan2(y, x)) + 112.5) % 360) // 45)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(12, 16, 23, 235))
        p.drawEllipse(QPointF(195, 195), 190, 190)
        for i, (label, icon) in enumerate(self.actions):
            start = 112.5 - i * 45
            path = QPainterPath()
            outer, inner = QRectF(11, 11, 368, 368), QRectF(129, 129, 132, 132)
            path.arcMoveTo(outer, start - 2)
            path.arcTo(outer, start - 2, -41)
            end = math.radians(start - 43)
            path.lineTo(195 + 66 * math.cos(end), 195 - 66 * math.sin(end))
            path.arcTo(inner, start - 43, 41)
            path.closeSubpath()
            p.setBrush(QColor('#edb578' if i == self.hover else '#303c50'))
            p.drawPath(path)
            a = math.radians(-90 + i * 45)
            x, y = 195 + 123 * math.cos(a), 195 + 123 * math.sin(a)
            p.setPen(QColor('#182030' if i == self.hover else '#f5e8d9'))
            p.setFont(QFont('DejaVu Sans', 20))
            p.drawText(QRectF(x - 46, y - 30, 92, 30), Qt.AlignCenter, icon)
            p.setFont(QFont('DejaVu Sans', 10, QFont.Bold))
            p.drawText(QRectF(x - 49, y + 4, 98, 22), Qt.AlignCenter, label)
            p.setPen(Qt.NoPen)
        p.setPen(QColor('#edb578'))
        p.setFont(QFont('DejaVu Sans', 12, QFont.Bold))
        p.drawText(QRectF(132, 163, 126, 28), Qt.AlignCenter, 'DRAGVERT')
        p.setPen(QColor('#bbc7da'))
        p.setFont(QFont('DejaVu Sans', 9))
        p.drawText(QRectF(134, 194, 122, 42), Qt.AlignCenter | Qt.TextWordWrap,
                   f'{len(self.paths)} selected' if self.paths else 'Drop on a tool')

    def mouseMoveEvent(self, event):
        self.hover = self.sector(event.pos())
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            self.hide()
            return
        index = self.sector(event.pos())
        if index >= 0 and self.paths:
            self.choose(index)
        elif index < 0:
            self.hide()

    def choose(self, index):
        self.hide()
        self.chosen.emit(self.actions[index][0], self.paths)

    def dragEnterEvent(self, event):
        if local_files(event.mimeData()):
            self.autohide.stop()
            event.setDropAction(Qt.CopyAction)
            event.accept()

    def dragMoveEvent(self, event):
        self.hover = self.sector(event.pos())
        self.update()
        event.setDropAction(Qt.CopyAction)
        event.accept()

    def dragLeaveEvent(self, event):
        self.hover = -1
        self.update()
        self.autohide.start(1800)

    def dropEvent(self, event):
        self.paths = local_files(event.mimeData())
        index = self.sector(event.pos())
        event.setDropAction(Qt.CopyAction)
        event.accept()
        if index >= 0:
            # Let Dolphin finish its drag loop before opening a modal editor.
            QTimer.singleShot(0, lambda: self.choose(index))
        else:
            self.update()
            self.autohide.start(15000)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()


class Canvas(QWidget):
    selectionChanged = pyqtSignal(tuple)

    def __init__(self, image):
        super().__init__()
        self.image = image
        self.selection, self.origin = None, None
        self.setMinimumSize(480, 300)
        self.setCursor(Qt.CrossCursor)

    def image_rect(self):
        scale = min((self.width() - 28) / self.image.width, (self.height() - 28) / self.image.height)
        w, h = self.image.width * scale, self.image.height * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def image_point(self, pos):
        r = self.image_rect()
        return (max(0, min(self.image.width, (pos.x() - r.x()) * self.image.width / r.width())),
                max(0, min(self.image.height, (pos.y() - r.y()) * self.image.height / r.height())))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = self.image_rect()
        p.drawPixmap(r.toRect(), pixmap(self.image))
        if self.selection:
            x1, y1, x2, y2 = self.selection
            sx, sy = r.width() / self.image.width, r.height() / self.image.height
            box = QRectF(r.x() + x1 * sx, r.y() + y1 * sy, (x2-x1)*sx, (y2-y1)*sy)
            p.setPen(QPen(QColor('#edb578'), 2, Qt.DashLine))
            p.setBrush(QColor(237, 181, 120, 30))
            p.drawRect(box)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.origin = self.image_point(event.pos())
            self.selection = (*self.origin, *self.origin)
            self.update()

    def mouseMoveEvent(self, event):
        if self.origin and event.buttons() & Qt.LeftButton:
            end = self.image_point(event.pos())
            self.selection = (min(self.origin[0], end[0]), min(self.origin[1], end[1]),
                              max(self.origin[0], end[0]), max(self.origin[1], end[1]))
            self.update()

    def mouseReleaseEvent(self, event):
        if self.selection:
            self.selectionChanged.emit(self.selection)
        self.origin = None


class ImageEditor(QDialog):
    def __init__(self, path, mode, parent=None):
        super().__init__(parent)
        self.path, self.mode = path, mode
        self.original = core.load_image(path)
        self.current = self.original.copy()
        self.output = None
        self.colors = ('#ffb35c', '#7061e8')
        self.setWindowTitle(f'{mode} — {path.name}')
        self.resize(820, 740)
        layout = QVBoxLayout(self)
        hints = {'Crop': 'Drag a rectangle, then apply the crop.',
                 'Redact': 'Draw a rectangle, then apply. Repeat for more areas. Exports a flattened PNG.',
                 'Annotate': 'Click the image to position your text, then apply.',
                 'Edit': 'Rotate or adjust brightness and contrast, then save a copy.',
                 'Add BG': 'Frame your image with a gradient, rounded corners, and shadow.'}
        hint = QLabel(hints[mode])
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.canvas = Canvas(self.current)
        layout.addWidget(self.canvas, 1)
        self.form = QFormLayout()
        layout.addLayout(self.form)
        self.controls = {}
        if mode == 'Add BG':
            self.slider('Padding', 0, 500, 80, self.preview)
            self.slider('Corners', 0, 200, 24, self.preview)
            self.slider('Shadow', 0, 100, 24, self.preview)
            row = QHBoxLayout()
            row.addWidget(button('Gradient start', lambda: self.pick_color(0)))
            row.addWidget(button('Gradient end', lambda: self.pick_color(1)))
            self.form.addRow('Colors', row)
            self.preview()
        if mode == 'Annotate':
            self.text = QLineEdit('Your annotation')
            self.form.addRow('Text', self.text)
            self.slider('Text size', 12, 240, 40)
        if mode == 'Edit':
            self.slider('Brightness', 25, 200, 100, self.preview)
            self.slider('Contrast', 25, 200, 100, self.preview)
            self.form.addRow(button('Rotate 90°', self.rotate))
        row = QHBoxLayout()
        row.addWidget(button('Reset', self.reset))
        row.addStretch()
        if mode in {'Crop', 'Redact', 'Annotate'}:
            row.addWidget(button('Apply ' + mode.lower(), self.apply))
        row.addWidget(button('Cancel', self.reject))
        row.addWidget(button('Save copy', self.save, True))
        layout.addLayout(row)

    def slider(self, name, low, high, value, slot=None):
        slider = QSlider(Qt.Horizontal)
        slider.setRange(low, high)
        slider.setValue(value)
        self.controls[name] = slider
        row = QHBoxLayout()
        row.addWidget(slider)
        number = QLabel(str(value))
        number.setMinimumWidth(35)
        row.addWidget(number)
        slider.valueChanged.connect(lambda v: number.setText(str(v)))
        if slot:
            slider.valueChanged.connect(slot)
        self.form.addRow(name, row)

    def values(self):
        return {k: v.value() for k, v in self.controls.items()}

    def pick_color(self, index):
        c = QColorDialog.getColor(QColor(self.colors[index]), self)
        if c.isValid():
            colors = list(self.colors)
            colors[index] = c.name()
            self.colors = tuple(colors)
            self.preview()

    def render(self, image, scale=1):
        v = self.values()
        if self.mode == 'Add BG':
            return core.background(image, round(v['Padding'] * scale), round(v['Corners'] * scale),
                                   round(v['Shadow'] * scale), self.colors)
        if self.mode == 'Edit':
            return ImageEnhance.Contrast(ImageEnhance.Brightness(image).enhance(v['Brightness']/100)).enhance(v['Contrast']/100)
        return image

    def preview(self):
        sample = self.current.copy()
        sample.thumbnail((1000, 700))
        self.canvas.image = self.render(sample, sample.width / self.current.width)
        self.canvas.update()

    def rotate(self):
        self.current = self.current.rotate(90, expand=True)
        self.preview()

    def reset(self):
        self.current = self.original.copy()
        self.canvas.selection = None
        if self.mode in {'Add BG', 'Edit'}:
            defaults = {'Padding': 80, 'Corners': 24, 'Shadow': 24, 'Brightness': 100, 'Contrast': 100}
            for name, control in self.controls.items():
                control.setValue(defaults[name])
            self.preview()
        else:
            self.canvas.image = self.current
            self.canvas.update()

    def apply(self):
        box = self.canvas.selection
        try:
            if not box:
                raise ValueError('Select a position or rectangle on the image first.')
            if self.mode == 'Crop':
                self.current = core.crop_image(self.current, box)
            elif self.mode == 'Redact':
                if box[2] - box[0] < 1 or box[3] - box[1] < 1:
                    raise ValueError('Draw a rectangle with a nonzero area.')
                self.current = core.redact_image(self.current, box)
            elif self.mode == 'Annotate':
                self.current = core.annotate_image(self.current, self.text.text(), box[:2], self.values()['Text size'])
            self.canvas.selection = None
            self.canvas.image = self.current
            self.canvas.update()
            return True
        except Exception as exc:
            QMessageBox.warning(self, 'Cannot apply', str(exc))
            return False

    def save(self):
        if self.canvas.selection and self.mode in {'Crop', 'Redact', 'Annotate'}:
            if not self.apply():
                return
        try:
            self.output = core.save_image(self.render(self.current), self.path, ' ' + self.mode.replace('Add BG', 'With Background'))
            self.accept()
        except Exception as exc:
            QMessageBox.warning(self, 'Cannot save', str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.paths, self.outputs, self.worker = [], [], None
        self.radial = RadialMenu()
        self.radial.chosen.connect(self.action)
        self.setWindowTitle('Dragvert — File tools at your fingertips')
        self.resize(660, 650)
        self.setAcceptDrops(True)
        self.monitor = PointerMonitor()
        self.trigger_held = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(70)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        title = QLabel('Dragvert')
        title.setObjectName('title')
        layout.addWidget(title)
        subtitle = QLabel('A little gesture. A whole toolkit.')
        subtitle.setObjectName('muted')
        layout.addWidget(subtitle)
        self.drop = QLabel('Drop files here\n\nConvert · Crop · Compress · Create')
        self.drop.setAlignment(Qt.AlignCenter)
        self.drop.setMinimumHeight(140)
        self.drop.setStyleSheet('border: 2px dashed #56647a; border-radius: 18px; color: #edb578; font-size: 17px; background: #1e2736;')
        layout.addWidget(self.drop)
        row = QHBoxLayout()
        row.addWidget(button('Choose files…', self.browse, True))
        row.addWidget(button('Open tool wheel', self.open_wheel))
        layout.addLayout(row)
        self.selected = QLabel('No files selected')
        self.selected.setWordWrap(True)
        layout.addWidget(self.selected)
        self.gesture = QCheckBox('Enable Shift + drag tool wheel (X11)')
        self.gesture.setChecked(bool(self.monitor.display))
        self.gesture.setEnabled(bool(self.monitor.display))
        layout.addWidget(self.gesture)
        hint = QLabel('Dolphin: right-click files → Actions → Open in Dragvert.\n'
                      'X11: start dragging, hold Shift, then drop on a tool.\n'
                      'Wayland: use the Dolphin action or drop files into this window.')
        hint.setObjectName('muted')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.status = QLabel('Ready · Files stay on your computer · Originals preserved')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText('Your exported files will appear here.')
        layout.addWidget(self.log, 1)
        self.reveal = button('Show last output in Dolphin', self.show_output)
        self.reveal.setEnabled(False)
        layout.addWidget(self.reveal)
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            icon = QIcon.fromTheme('document-save-as')
            if icon.isNull():
                icon = self.style().standardIcon(self.style().SP_DialogSaveButton)
            self.tray = QSystemTrayIcon(icon, self)
            self.tray.setToolTip('Dragvert — Shift + drag to transform files')
            menu = QMenu()
            menu.addAction('Open Dragvert', self.showNormal)
            menu.addAction('Tool wheel', lambda: self.radial.popup(self.paths))
            menu.addSeparator()
            menu.addAction('Quit', self.quit)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self.showNormal() if reason == QSystemTrayIcon.Trigger else None)
            self.tray.show()

    def poll(self):
        state = self.monitor.state() if self.gesture.isChecked() else None
        held = bool(state and state[2])
        if held and not self.trigger_held and not QApplication.activeModalWidget() and not self.worker:
            # QCursor uses Qt logical pixels, unlike XQueryPointer on HiDPI screens.
            self.radial.popup(position=QCursor.pos())
        self.trigger_held = held

    def set_paths(self, paths):
        self.paths = [Path(p).absolute() for p in paths if Path(p).is_file()]
        names = ', '.join(p.name for p in self.paths[:4])
        self.selected.setText(f'{len(self.paths)} file(s): {names}' if self.paths else 'No files selected')

    def browse(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Choose files')
        if paths:
            self.set_paths(paths)
            self.open_wheel()

    def open_wheel(self):
        if not self.paths:
            self.browse()
            return
        self.radial.popup(self.paths, self.mapToGlobal(self.rect().center()))

    def dragEnterEvent(self, event):
        if local_files(event.mimeData()):
            event.setDropAction(Qt.CopyAction)
            event.accept()

    def dropEvent(self, event):
        self.set_paths(local_files(event.mimeData()))
        event.setDropAction(Qt.CopyAction)
        event.accept()
        QTimer.singleShot(0, self.open_wheel)

    def action(self, name, paths):
        if self.worker:
            self.showNormal()
            QMessageBox.information(self, 'Working', 'Wait for the current conversion to finish.')
            return
        self.set_paths(paths)
        if not self.paths:
            return
        self.showNormal()
        try:
            if name == 'Convert':
                self.convert_dialog()
            elif name == 'Compress':
                if any(p.suffix.lower() not in core.IMAGES for p in self.paths):
                    raise ValueError('Select still images for compression. Output is JPG (WEBP for WEBP inputs); size reduction depends on the source.')
                self.start(lambda p: core.compress(p))
            elif name == 'Metadata':
                d = QDialog(self)
                d.setWindowTitle('File metadata')
                d.resize(650, 500)
                layout = QVBoxLayout(d)
                text = QPlainTextEdit()
                text.setReadOnly(True)
                text.setPlainText('\n\n'.join(core.metadata(p) for p in self.paths))
                layout.addWidget(text)
                layout.addWidget(button('Close', d.accept))
                d.exec_()
            else:
                if len(self.paths) != 1 or self.paths[0].suffix.lower() not in core.IMAGES:
                    raise ValueError('Select one image for this tool. For a PDF, convert its pages to PNG or JPG first.')
                editor = ImageEditor(self.paths[0], name, self)
                if editor.exec_() == QDialog.Accepted:
                    self.finished([editor.output], [])
        except Exception as exc:
            QMessageBox.warning(self, 'Dragvert', str(exc))

    def convert_dialog(self):
        formats = core.targets(self.paths[0])
        formats = [f for f in formats if all(f in core.targets(p) for p in self.paths)]
        if not formats:
            raise ValueError('These files have no common supported output format. Select files of the same type.')
        d = QDialog(self)
        d.setWindowTitle('Convert files')
        layout = QVBoxLayout(d)
        layout.addWidget(QLabel(f'Convert {len(self.paths)} file(s) beside the originals.'))
        combo = QComboBox()
        combo.addItems(formats)
        layout.addWidget(combo)
        note = QLabel('PDF: exports all pages at 150 DPI.\nAnimated/multipage images: exports the first frame.\nJPG/PDF/BMP: transparency becomes white.\nOffice conversion requires LibreOffice.')
        note.setObjectName('muted')
        layout.addWidget(note)
        layout.addWidget(button('Convert', d.accept, True))
        layout.addWidget(button('Cancel', d.reject))
        if d.exec_() == QDialog.Accepted:
            target = combo.currentText()
            self.start(lambda p: core.convert(p, target))

    def start(self, operation):
        self.status.setText('Working… Large files can take a few minutes.')
        self.worker = Worker(self.paths, operation, self)
        self.worker.completed.connect(self.finished)
        self.worker.finished.connect(self.worker_done)
        self.worker.start()

    def worker_done(self):
        self.worker.deleteLater()
        self.worker = None

    def finished(self, outputs, errors):
        self.outputs.extend(outputs)
        for path in outputs:
            self.log.appendPlainText(str(path))
        for error in errors:
            self.log.appendPlainText('ERROR: ' + error)
        self.reveal.setEnabled(bool(self.outputs))
        self.status.setText(f'Finished · {len(outputs)} output(s) · {len(errors)} error(s)')
        if self.tray and not self.isVisible():
            self.tray.showMessage('Dragvert', self.status.text())

    def show_output(self):
        import shutil
        from PyQt5.QtCore import QProcess
        path = str(self.outputs[-1])
        if shutil.which('dolphin'):
            QProcess.startDetached('dolphin', ['--select', path])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    def quit(self):
        if self.worker:
            QMessageBox.information(self, 'Conversion in progress', 'Let the current conversion finish before quitting.')
            return
        self.monitor.close()
        QApplication.quit()

    def closeEvent(self, event):
        if self.tray:
            self.hide()
            event.ignore()
        elif self.worker:
            QMessageBox.information(self, 'Conversion in progress', 'Let the current conversion finish before closing.')
            event.ignore()
        else:
            self.monitor.close()
            self.radial.close()
            event.accept()
