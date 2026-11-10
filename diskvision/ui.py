import os
from threading import Event

from PySide6.QtCore import QItemSelectionModel, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSpinBox, QSplitter, QStackedWidget, QTableView, QVBoxLayout, QWidget,
)

from . import cleanup, duplicates, safe_files, storage
from .preferences import Preferences
from .theme import stylesheet
from .widgets import FilesModel, Treemap


class Job(QThread):
    progress = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, operation, args, parent):
        super().__init__(parent)
        self.stop = Event()
        self.operation = operation
        self.args = args

    def run(self):
        try:
            self.succeeded.emit(self.operation(*self.args, self.stop, self.progress.emit))
        except Exception as exc:
            self.failed.emit(str(exc))


def label(text="", name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, action, name=None):
    widget = QPushButton(text)
    widget.clicked.connect(action)
    if name:
        widget.setObjectName(name)
    return widget


class Window(QMainWindow):
    pages = ("Painel Geral", "Analisador de Discos", "Arquivos Grandes",
             "Duplicados", "Limpeza", "Configurações")
    subtitles = (
        "Capacidade e ocupação dos volumes conectados.",
        "Explore pastas e compare seus itens pelo espaço que ocupam.",
        "Filtre os arquivos da unidade analisada por tamanho mínimo.",
        "Compare todos os volumes já analisados por tamanho, hash e conteúdo.",
        "Revise temporários antigos e arquivos que podem merecer inspeção.",
        "Personalize a aparência e consulte o histórico local.",
    )

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DiskVision")
        self.resize(1250, 800)
        self.setMinimumSize(820, 590)
        self.prefs = Preferences()
        self.job = None
        self.result = None
        self.callback = None
        self.busy = False
        self.inventory = None
        self.snapshots = {}
        self.folders = []
        self.duplicate_rows = []
        self.cleanup_rows = []
        self.page = 0
        self.build()
        self.setStyleSheet(stylesheet(self.prefs.theme() != "Claro"))
        self.navigate(0)
        QTimer.singleShot(0, self.refresh_drives)
        self.drive_timer = QTimer(self)
        self.drive_timer.setInterval(5000)
        self.drive_timer.timeout.connect(self.poll_drives)
        self.drive_timer.start()

    def build(self):
        outer = QWidget()
        self.setCentralWidget(outer)
        layout = QHBoxLayout(outer)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)
        side = QFrame(objectName="sidebar")
        side.setFixedWidth(177)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(12, 16, 12, 14)
        side_layout.addWidget(label("DiskVision", "brand"))
        side_layout.addWidget(label("ARMAZENAMENTO LOCAL", "eyebrow"))
        side_layout.addSpacing(19)
        self.navigation = QButtonGroup(self)
        for i, title in enumerate(self.pages):
            item = button(title, lambda checked=False, page=i: self.navigate(page))
            item.setCheckable(True)
            self.navigation.addButton(item, i)
            side_layout.addWidget(item)
        side_layout.addStretch()
        side_layout.addWidget(label("Windows  /  v1.0", "muted"))
        layout.addWidget(side)

        content = QVBoxLayout()
        content.setSpacing(8)
        layout.addLayout(content, 1)
        content.addWidget(label("DISKVISION  /  ESTAÇÃO LOCAL", "eyebrow"))
        self.title = label("", "title")
        self.subtitle = label("", "muted")
        self.subtitle.setWordWrap(True)
        content.addWidget(self.title)
        content.addWidget(self.subtitle)
        toolbar = QFrame(objectName="toolbar")
        tools = QHBoxLayout(toolbar)
        tools.addWidget(label("Unidade"))
        self.drives = QComboBox()
        self.drives.setMinimumWidth(86)
        self.drives.currentIndexChanged.connect(self.change_drive)
        tools.addWidget(self.drives)
        self.refresh = button("Atualizar unidades", self.refresh_drives)
        tools.addWidget(self.refresh)
        self.analyze = button("Analisar unidade", self.scan_drive, "primary")
        tools.addWidget(self.analyze)
        tools.addStretch()
        self.cancel = button("Cancelar", self.cancel_job)
        tools.addWidget(self.cancel)
        content.addWidget(toolbar)

        self.stack = QStackedWidget()
        content.addWidget(self.stack, 1)
        dashboard = QScrollArea()
        dashboard.setWidgetResizable(True)
        dashboard_panel = QWidget()
        self.cards = QGridLayout(dashboard_panel)
        self.cards.setAlignment(Qt.AlignmentFlag.AlignTop)
        dashboard.setWidget(dashboard_panel)
        self.stack.addWidget(dashboard)

        files = QWidget()
        files_layout = QVBoxLayout(files)
        files_layout.setContentsMargins(0, 0, 0, 0)
        actions = QHBoxLayout()
        self.up = button("↑  Pasta acima", self.go_up)
        actions.addWidget(self.up)
        self.minimum = QSpinBox()
        self.minimum.setRange(0, 100_000_000)
        self.minimum.setValue(100)
        self.minimum.setPrefix("Mín. ")
        self.minimum.setSuffix(" MiB")
        self.minimum.valueChanged.connect(self.render)
        actions.addWidget(self.minimum)
        self.compute = button("Verificar", self.compute_page, "primary")
        actions.addWidget(self.compute)
        actions.addStretch()
        self.trash = button("Mover para a Lixeira…", self.confirm_recycle, "danger")
        actions.addWidget(self.trash)
        files_layout.addLayout(actions)
        self.context = label("", "muted")
        self.context.setWordWrap(True)
        files_layout.addWidget(self.context)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.treemap = Treemap()
        self.treemap.clicked.connect(self.select_tile)
        self.splitter.addWidget(self.treemap)
        self.table = QTableView()
        self.model = FilesModel()
        self.table.setModel(self.model)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(1, Qt.SortOrder.DescendingOrder)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in enumerate((185, 98, 74, 137, 230, 170)):
            self.table.setColumnWidth(column, width)
        self.table.doubleClicked.connect(self.open_row)
        self.table.selectionModel().selectionChanged.connect(self.selection_changed)
        self.splitter.addWidget(self.table)
        self.splitter.setSizes([240, 330])
        files_layout.addWidget(self.splitter, 1)
        self.selection_label = label("", "muted")
        files_layout.addWidget(self.selection_label)
        self.stack.addWidget(files)

        settings = QWidget()
        settings_layout = QVBoxLayout(settings)
        settings_layout.addWidget(label("APARÊNCIA", "eyebrow"))
        theme = QComboBox()
        theme.addItems(["Escuro", "Claro"])
        theme.setCurrentText(self.prefs.theme())
        theme.currentTextChanged.connect(self.change_theme)
        settings_layout.addWidget(theme, alignment=Qt.AlignmentFlag.AlignLeft)
        settings_layout.addSpacing(14)
        settings_layout.addWidget(label("ATIVIDADE RECENTE  /  UTC", "eyebrow"))
        log = QScrollArea()
        log.setWidgetResizable(True)
        self.history = label("", "muted")
        self.history.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.history.setWordWrap(True)
        log.setWidget(self.history)
        settings_layout.addWidget(log, 1)
        self.stack.addWidget(settings)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumHeight(7)
        content.addWidget(self.progress)
        self.status = label("Preparando o DiskVision…", "muted")
        self.status.setMinimumWidth(0)
        content.addWidget(self.status)

    def navigate(self, page):
        self.page = page
        self.navigation.button(page).setChecked(True)
        self.title.setText(self.pages[page])
        self.subtitle.setText(self.subtitles[page])
        self.stack.setCurrentIndex(0 if page == 0 else 2 if page == 5 else 1)
        if page == 5:
            self.history.setText("\n".join(
                f"{date}   {operation}   {detail}" for date, operation, detail in self.prefs.recent()
            ) or "O histórico ainda está vazio.")
        self.render()

    def change_theme(self, theme):
        self.prefs.save_theme(theme)
        self.setStyleSheet(stylesheet(theme == "Escuro"))

    def message(self, text):
        self.status.setToolTip(text)
        self.status.setText(self.status.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideMiddle, max(220, self.status.width())
        ))

    def set_controls(self):
        self.progress.setVisible(self.busy)
        self.cancel.setVisible(self.busy)
        self.cancel.setEnabled(self.busy)
        self.drives.setEnabled(not self.busy and self.drives.count() > 0)
        self.refresh.setEnabled(not self.busy)
        self.analyze.setEnabled(not self.busy and bool(self.root()))
        self.compute.setEnabled(not self.busy and (
            bool(self.snapshots) if self.page == 3 else self.root() in self.snapshots
        ))
        self.selection_changed()

    def start(self, operation, args, callback, message):
        if self.busy:
            return
        self.busy = True
        self.result = None
        self.callback = callback
        self.job = Job(operation, args, self)
        self.job.progress.connect(self.message)
        self.job.succeeded.connect(self.store_result)
        self.job.failed.connect(self.store_error)
        self.job.finished.connect(self.finish)
        self.set_controls()
        self.message(message)
        self.job.start()

    def store_result(self, value):
        self.result = (True, value)

    def store_error(self, message):
        self.result = (False, message)

    def finish(self):
        job, self.job = self.job, None
        callback = self.callback
        success, data = self.result or (False, "A operação terminou sem resultado.")
        self.result = None
        self.busy = False
        job.deleteLater()
        self.set_controls()
        if success:
            callback(data)
        else:
            self.message(data)
            QMessageBox.warning(self, "Operação indisponível", data)

    def cancel_job(self):
        if self.job:
            self.job.stop.set()
            self.cancel.setEnabled(False)
            self.message("Cancelando após a operação de E/S atual…")

    def root(self):
        return self.drives.currentData()

    def poll_drives(self):
        if not self.busy and self.inventory != tuple(storage.units()):
            self.refresh_drives()

    def refresh_drives(self):
        self.start(storage.capacities, (), self.set_drives, "Consultando unidades…")

    def set_drives(self, entries):
        self.inventory = tuple(root for root, _ in entries)
        previous = self.root()
        ready = {root for root, usage in entries if usage is not None}
        for root in self.snapshots.keys() - ready:
            del self.snapshots[root]
            self.duplicate_rows = []
        self.drives.blockSignals(True)
        self.drives.clear()
        while self.cards.count():
            widget = self.cards.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        for i, (root, usage) in enumerate(entries):
            if usage is not None:
                self.drives.addItem(root, root)
            card = QFrame(objectName="toolbar")
            card_layout = QVBoxLayout(card)
            card_layout.addWidget(label(f"UNIDADE  {root}", "eyebrow"))
            if usage is not None and usage.total:
                card_layout.addWidget(label(byte_text(usage.total), "title"))
                bar = QProgressBar()
                bar.setValue(round(100 * usage.used / usage.total))
                card_layout.addWidget(bar)
                caption = label(f"{byte_text(usage.used)} usados  ·  {byte_text(usage.free)} livres", "muted")
                caption.setWordWrap(True)
                card_layout.addWidget(caption)
                card_layout.addWidget(button("Explorar unidade", lambda checked=False, value=root: self.explore(value)))
            else:
                card_layout.addWidget(label("Volume sem mídia ou inacessível", "muted"))
            self.cards.addWidget(card, i // 2, i % 2)
        if not entries:
            self.cards.addWidget(label("Nenhuma unidade local disponível.", "muted"), 0, 0)
        index = self.drives.findData(previous)
        self.drives.setCurrentIndex(index if index >= 0 else (0 if self.drives.count() else -1))
        self.drives.blockSignals(False)
        if previous != self.root():
            self.change_drive()
        self.message(f"{len(entries)} unidade(s) detectada(s)  ·  {len(ready)} disponível(is) para análise")
        self.set_controls()

    def explore(self, root):
        if self.busy:
            return
        self.drives.setCurrentIndex(self.drives.findData(root))
        self.navigate(1)
        if root not in self.snapshots:
            self.scan_drive()

    def change_drive(self):
        scan = self.snapshots.get(self.root())
        self.folders = [scan.root] if scan else []
        self.cleanup_rows = []
        self.render()

    def scan_drive(self):
        if not self.root() or self.busy:
            return
        root = self.root()
        self.navigate(1)
        self.start(storage.scan, (root,), lambda scan: self.accept_scan(root, scan), "Iniciando varredura…")

    def accept_scan(self, root, scan, after=None):
        self.snapshots[root] = scan
        self.duplicate_rows = []
        if self.root() == root:
            self.change_drive()
        summary = (f"{scan.count:,} itens  ·  {scan.errors} erros de acesso  ·  {scan.skipped} ignorados"
                   + ("  ·  Resultado parcial" if scan.partial else ""))
        self.prefs.record("Análise", f"{root}  {summary}")
        self.message(summary)
        if after:
            after()

    def compute_page(self):
        if self.busy:
            return
        if self.page == 3:
            files = [scan.files for scan in self.snapshots.values()]
            self.start(self.find_duplicates, (files,), self.accept_duplicates, "Agrupando arquivos…")
        elif self.page == 4 and self.root() in self.snapshots:
            self.start(cleanup.classify, (self.snapshots[self.root()].files,),
                       self.accept_cleanup, "Classificando candidatos…")

    @staticmethod
    def find_duplicates(collections, stop, progress):
        from itertools import chain

        return duplicates.find(chain.from_iterable(collections), stop, progress)

    def accept_duplicates(self, result):
        groups, errors, partial = result
        self.duplicate_rows = [(entry, f"Grupo {i:05d}") for i, group in enumerate(groups, 1) for entry in group]
        summary = f"{len(groups)} grupo(s) confirmado(s)  ·  {errors} erro(s)" + ("  ·  Parcial" if partial else "")
        self.prefs.record("Duplicados", summary)
        self.message(summary)
        if self.page == 3:
            self.render()

    def accept_cleanup(self, result):
        temp, candidates, partial = result
        self.cleanup_rows = ([(entry, "Temp do usuário · 7+ dias") for entry in temp]
                             + [(entry, "Candidato por extensão") for entry in candidates])
        summary = f"{len(temp)} temporário(s)  ·  {len(candidates)} candidato(s)" + ("  ·  Parcial" if partial else "")
        self.prefs.record("Limpeza", summary)
        self.message(summary)
        if self.page == 4:
            self.render()

    def render(self, *_):
        page = self.page
        self.up.setVisible(page == 1)
        self.up.setEnabled(len(self.folders) > 1)
        self.treemap.setVisible(page == 1)
        self.minimum.setVisible(page == 2)
        self.compute.setVisible(page in (3, 4))
        self.compute.setText("Verificar duplicados" if page == 3 else "Classificar arquivos")
        self.table.setColumnHidden(5, page not in (3, 4))
        scan = self.snapshots.get(self.root())
        rows = []
        hint = "Selecione uma unidade e clique em Analisar unidade."
        if page == 1:
            entries = self.folders[-1].children if self.folders else []
            self.treemap.set_entries(entries)
            rows = [(item, "") for item in entries]
            if self.folders:
                hint = self.folders[-1].path + ("  ·  Varredura parcial" if scan.partial else "")
        elif page == 2 and scan:
            threshold = self.minimum.value() * 1024**2
            rows = [(item, "") for item in scan.files if item.size >= threshold]
            hint = f"{len(rows):,} arquivo(s)  ·  {self.root()}" + ("  ·  Varredura parcial" if scan.partial else "")
        elif page == 3:
            rows = self.duplicate_rows
            hint = "Ordene por Classificação para agrupar as cópias. Revise quais deseja conservar."
        elif page == 4:
            rows = self.cleanup_rows
            hint = "Temp do usuário inclui apenas itens antigos nessa pasta. Extensões sugerem candidatos e exigem revisão."
        if page in (1, 2, 3, 4):
            self.context.setText(hint)
            self.model.replace(rows)
        self.set_controls()

    def go_up(self):
        if len(self.folders) > 1:
            self.folders.pop()
            self.render()

    def open_row(self, index):
        entry, _ = self.model.rows[index.row()]
        if self.page == 1 and entry.folder:
            self.folders.append(entry)
            self.render()

    def select_tile(self, entry):
        if entry.folder:
            self.folders.append(entry)
            self.render()
            return
        for i, (item, _) in enumerate(self.model.rows):
            if item is entry:
                index = self.model.index(i, 0)
                self.table.selectionModel().setCurrentIndex(
                    index, QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows
                )
                self.table.scrollTo(index)
                return

    def selected(self):
        return [self.model.rows[index.row()][0] for index in self.table.selectionModel().selectedRows()]

    def selection_changed(self, *_):
        entries = safe_files.collapse(self.selected()) if self.page in (1, 2, 3, 4) else []
        size = byte_text(sum(entry.size for entry in entries))
        self.selection_label.setText(f"{len(entries):,} selecionado(s)  ·  {size} de tamanho lógico"
                                     if entries else "Ctrl ou Shift para selecionar vários itens.")
        self.trash.setEnabled(bool(entries) and not self.busy)

    def confirm_recycle(self):
        entries = safe_files.collapse(self.selected())
        if not entries or self.busy:
            return
        size = byte_text(sum(entry.size for entry in entries))
        prompt = QMessageBox(QMessageBox.Icon.Warning, "Confirmar envio à Lixeira",
                             f"Mover {len(entries)} item(ns) para a Lixeira?",
                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
        prompt.setDefaultButton(QMessageBox.StandardButton.No)
        prompt.setTextFormat(Qt.TextFormat.PlainText)
        prompt.setInformativeText(f"Tamanho lógico selecionado: {size}. A Lixeira ocupa espaço até ser esvaziada.")
        prompt.setDetailedText("\n".join(entry.path for entry in entries))
        prompt.button(QMessageBox.StandardButton.Yes).setText("Mover para a Lixeira")
        prompt.button(QMessageBox.StandardButton.No).setText("Voltar")
        if prompt.exec() == QMessageBox.StandardButton.Yes:
            self.start(safe_files.recycle, (entries,), self.accept_recycle, "Validando os itens selecionados…")

    def accept_recycle(self, result):
        sent, errors = result
        summary = f"{len(sent)} enviado(s) à Lixeira  ·  {len(errors)} recusado(s)"
        self.prefs.record("Lixeira", summary)
        self.message(summary)
        if errors:
            dialog = QMessageBox(QMessageBox.Icon.Warning, "Resultado do envio à Lixeira", summary,
                                 QMessageBox.StandardButton.Ok, self)
            dialog.setDetailedText("\n".join(errors))
            dialog.exec()
        affected = {os.path.splitdrive(path)[0] + os.sep for path in sent}
        if affected:
            for root in affected:
                self.snapshots.pop(root, None)
            self.duplicate_rows = []
            self.change_drive()
            self.rescan(list(sorted(affected)))

    def rescan(self, roots):
        if not roots:
            self.refresh_drives()
            return
        root, *remaining = roots
        self.start(storage.scan, (root,),
                   lambda scan: self.accept_scan(root, scan, lambda: self.rescan(remaining)),
                   "Atualizando a análise após o envio à Lixeira…")

    def closeEvent(self, event):
        if self.busy:
            self.cancel_job()
            self.message("Aguarde o cancelamento antes de fechar.")
            event.ignore()
        else:
            self.prefs.db.close()
            event.accept()


byte_text = storage.byte_text
