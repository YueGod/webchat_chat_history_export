from __future__ import annotations

import html
import logging
import os
import shutil
from datetime import datetime

from PySide6.QtCore import QDate, QThread, Signal, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import (
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..csv_exporter import export_to_csv
from ..db_reader import DatabaseReader, DetectedAccount, detect_wechat_accounts
from ..models import Conversation, Message
from .styles import CHAT_HTML_CSS, STYLESHEET

logger = logging.getLogger(__name__)

PAGE_SIZE = 500


# ──────────────────────────────────────────────────────────────────────
# Worker threads
# ──────────────────────────────────────────────────────────────────────

class _LoaderThread(QThread):
    progress = Signal(str)
    finished_ok = Signal()
    finished_err = Signal(str)

    def __init__(self, reader: DatabaseReader):
        super().__init__()
        self._reader = reader

    def run(self) -> None:
        try:
            self._reader.load(progress_cb=self.progress.emit)
            self.finished_ok.emit()
        except Exception as exc:
            self.finished_err.emit(str(exc))


class _DecryptThread(QThread):
    progress = Signal(str)
    finished_ok = Signal(str)
    finished_err = Signal(str)

    def __init__(self, account: DetectedAccount):
        super().__init__()
        self._account = account

    def run(self) -> None:
        try:
            from ..key_extract import extract_keys
            from ..decryptor import find_sqlcipher, install_sqlcipher, decrypt_all

            sc = find_sqlcipher()
            if not sc:
                self.progress.emit("正在安装 sqlcipher…")
                if not install_sqlcipher(self.progress.emit):
                    self.finished_err.emit(
                        "sqlcipher 安装失败。\n请手动运行: brew install sqlcipher"
                    )
                    return
                sc = find_sqlcipher()
                if not sc:
                    self.finished_err.emit("sqlcipher 安装后仍未找到。")
                    return

            self.progress.emit("正在从微信进程提取密钥…")
            keys = extract_keys(progress_cb=self.progress.emit)
            self.progress.emit(f"密钥提取成功，共 {len(keys)} 个密钥")

            out_dir = decrypt_all(
                data_dir=self._account.path,
                keys=keys,
                account_hash=self._account.account_hash,
                progress_cb=self.progress.emit,
                sqlcipher_bin=sc,
            )
            self.finished_ok.emit(out_dir)
        except Exception as exc:
            self.finished_err.emit(str(exc))


# ──────────────────────────────────────────────────────────────────────
# Main Window
# ──────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("微信聊天记录查看器")
        self.resize(1120, 740)
        self.setStyleSheet(STYLESHEET)

        self._reader: DatabaseReader | None = None
        self._current_conv: Conversation | None = None
        self._current_messages: list[Message] = []
        self._loader: _LoaderThread | None = None
        self._decrypt_thread: _DecryptThread | None = None
        self._detected_accounts: list[DetectedAccount] = []

        self._build_menu()
        self._build_ui()
        QTimer.singleShot(100, self._auto_detect)

    # ==================================================================
    # UI
    # ==================================================================

    def _build_menu(self) -> None:
        mb = self.menuBar()
        fm = mb.addMenu("文件")

        a = QAction("手动选择数据库目录…", self)
        a.setShortcut(QKeySequence("Ctrl+O"))
        a.triggered.connect(self._on_open_folder)
        fm.addAction(a)

        a = QAction("重新检测微信数据", self)
        a.setShortcut(QKeySequence("Ctrl+R"))
        a.triggered.connect(self._auto_detect)
        fm.addAction(a)

        fm.addSeparator()

        a = QAction("导出当前会话为 CSV…", self)
        a.setShortcut(QKeySequence("Ctrl+E"))
        a.triggered.connect(self._on_export_csv)
        fm.addAction(a)

        a = QAction("导出所有会话为 CSV…", self)
        a.triggered.connect(self._on_export_all_csv)
        fm.addAction(a)

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # ── Sidebar ──
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(12, 16, 12, 12)
        sl.setSpacing(8)

        title = QLabel("WECHAT VIEWER")
        title.setObjectName("sidebarTitle")
        sl.addWidget(title)
        sl.addSpacing(4)

        self._decrypt_btn = QPushButton("一键解密")
        self._decrypt_btn.setObjectName("primaryBtn")
        self._decrypt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._decrypt_btn.clicked.connect(self._on_decrypt_clicked)
        self._decrypt_btn.setVisible(False)
        sl.addWidget(self._decrypt_btn)

        self._open_btn = QPushButton("手动选择目录")
        self._open_btn.setObjectName("secondaryBtn")
        self._open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_btn.clicked.connect(self._on_open_folder)
        sl.addWidget(self._open_btn)

        sl.addSpacing(4)

        self._search_input = QLineEdit()
        self._search_input.setObjectName("searchInput")
        self._search_input.setPlaceholderText("搜索会话…")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_search_changed)
        sl.addWidget(self._search_input)

        self._conv_list = QListWidget()
        self._conv_list.setObjectName("convList")
        self._conv_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._conv_list.currentRowChanged.connect(self._on_conv_selected)
        sl.addWidget(self._conv_list)

        sidebar.setMinimumWidth(240)
        sidebar.setMaximumWidth(340)

        # ── Right pane ──
        right = QWidget()
        right.setObjectName("rightPane")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        # Header
        header = QWidget()
        header.setObjectName("chatHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 10, 20, 10)
        self._conv_title = QLabel("")
        self._conv_title.setObjectName("convTitle")
        hl.addWidget(self._conv_title)
        self._conv_subtitle = QLabel("")
        self._conv_subtitle.setObjectName("convSubtitle")
        hl.addWidget(self._conv_subtitle)
        hl.addStretch()
        rl.addWidget(header)

        # Filter bar
        fb = QWidget()
        fb.setObjectName("filterBar")
        fbl = QHBoxLayout(fb)
        fbl.setContentsMargins(20, 6, 20, 6)
        fbl.setSpacing(8)

        lbl = QLabel("时间范围")
        lbl.setObjectName("filterLabel")
        fbl.addWidget(lbl)

        self._date_start = QDateEdit()
        self._date_start.setCalendarPopup(True)
        self._date_start.setDisplayFormat("yyyy-MM-dd")
        self._date_start.setDate(QDate(2020, 1, 1))
        fbl.addWidget(self._date_start)

        dash = QLabel("—")
        dash.setObjectName("filterLabel")
        fbl.addWidget(dash)

        self._date_end = QDateEdit()
        self._date_end.setCalendarPopup(True)
        self._date_end.setDisplayFormat("yyyy-MM-dd")
        self._date_end.setDate(QDate.currentDate())
        fbl.addWidget(self._date_end)

        btn = QPushButton("筛选")
        btn.setObjectName("filterBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._on_filter)
        fbl.addWidget(btn)

        fbl.addStretch()

        btn = QPushButton("导出 CSV")
        btn.setObjectName("exportBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._on_export_csv)
        fbl.addWidget(btn)

        rl.addWidget(fb)

        # Chat
        self._chat_browser = QTextBrowser()
        self._chat_browser.setObjectName("chatBrowser")
        self._chat_browser.setOpenExternalLinks(True)
        rl.addWidget(self._chat_browser)

        # Page bar
        pb = QWidget()
        pb.setObjectName("pageBar")
        pbl = QHBoxLayout(pb)
        pbl.setContentsMargins(20, 5, 20, 5)
        pbl.addStretch()

        self._prev_btn = QPushButton("上一页")
        self._prev_btn.setObjectName("pageBtn")
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.clicked.connect(self._on_prev_page)
        self._prev_btn.setVisible(False)
        pbl.addWidget(self._prev_btn)

        self._page_label = QLabel("")
        self._page_label.setObjectName("pageLabel")
        pbl.addWidget(self._page_label)

        self._next_btn = QPushButton("下一页")
        self._next_btn.setObjectName("pageBtn")
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.clicked.connect(self._on_next_page)
        self._next_btn.setVisible(False)
        pbl.addWidget(self._next_btn)

        pbl.addStretch()
        rl.addWidget(pb)

        splitter.addWidget(sidebar)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([270, 850])

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._page = 0
        self._total_pages = 0

    # ==================================================================
    # Auto-detect
    # ==================================================================

    def _auto_detect(self) -> None:
        self._status.showMessage("正在检测微信数据目录…")
        self._detected_accounts = detect_wechat_accounts()

        cached = [a for a in self._detected_accounts if a.has_cached_decrypt]
        if cached:
            acct = self._pick_account(cached, "检测到已解密的缓存数据")
            if acct:
                self._decrypt_btn.setVisible(True)
                self._decrypt_btn.setText("重新解密")
                self._load_database(acct.cached_dir)
                return

        needs_decrypt = [a for a in self._detected_accounts if a.encrypted_msg_count > 0]
        if needs_decrypt:
            acct = needs_decrypt[0] if len(needs_decrypt) == 1 else None
            if len(needs_decrypt) > 1:
                acct = self._pick_account(needs_decrypt, "检测到多个微信账号")
            self._decrypt_btn.setVisible(True)
            if acct:
                self._decrypt_btn.setText(f"一键解密 ({acct.encrypted_msg_count} 个消息库)")
                self._decrypt_btn.setProperty("account", acct)
            else:
                self._decrypt_btn.setText("一键解密")

            sc = shutil.which("sqlcipher")
            wechat_running = self._is_wechat_running()
            checks = ""
            if wechat_running:
                checks += '<tr><td style="color:#0F7B6C;">&#10003;</td><td>微信正在运行</td></tr>'
            else:
                checks += '<tr><td style="color:#EB5757;">&#10007;</td><td>微信未运行 — 请先启动微信</td></tr>'
            if sc:
                checks += '<tr><td style="color:#0F7B6C;">&#10003;</td><td>sqlcipher 已安装</td></tr>'
            else:
                checks += '<tr><td style="color:#ACABA9;">&#9679;</td><td>sqlcipher 未安装（点击解密时自动安装）</td></tr>'

            self._show_info(
                "检测到加密的微信数据库",
                f'发现 {acct.encrypted_msg_count if acct else "?"} 个加密消息数据库，需要解密后才能查看。'
                f'<br><br><table cellspacing="6">{checks}</table><br>'
                '点击左侧「一键解密」开始<br>'
                '<span style="color:#ACABA9;">需要管理员密码以读取微信内存中的密钥</span>',
            )
            return

        if not self._detected_accounts:
            self._decrypt_btn.setVisible(False)
            self._show_info(
                "未检测到微信数据",
                "请确认已安装并登录过 WeChat for Mac 4.x<br>"
                "或点击「手动选择目录」加载已解密的数据库",
            )

    def _pick_account(self, accounts: list[DetectedAccount], title: str) -> DetectedAccount | None:
        if len(accounts) == 1:
            return accounts[0]
        labels = [a.label for a in accounts]
        chosen, ok = QInputDialog.getItem(self, title, "请选择账号:", labels, 0, False)
        if ok and chosen:
            return accounts[labels.index(chosen)]
        return None

    @staticmethod
    def _is_wechat_running() -> bool:
        import subprocess
        r = subprocess.run(["pgrep", "-x", "WeChat"], capture_output=True)
        return r.returncode == 0

    def _show_info(self, title: str, body: str) -> None:
        self._conv_title.setText("")
        self._conv_subtitle.setText("")
        self._chat_browser.setHtml(
            f'<html><head><style>{CHAT_HTML_CSS}</style></head><body>'
            f'<p align="center" class="info-title">{title}</p>'
            f'<p align="center" class="info-body">{body}</p>'
            '</body></html>'
        )

    # ==================================================================
    # Decrypt
    # ==================================================================

    def _on_decrypt_clicked(self) -> None:
        acct = self._decrypt_btn.property("account")
        if not acct:
            needs = [a for a in self._detected_accounts if a.encrypted_msg_count > 0]
            acct = self._pick_account(needs, "选择要解密的账号") if needs else None
        if not acct:
            return
        if not self._is_wechat_running():
            QMessageBox.warning(self, "提示", "请先启动微信，密钥提取需要微信在运行状态。")
            return

        self._decrypt_btn.setEnabled(False)
        self._decrypt_btn.setText("解密中…")
        self._open_btn.setEnabled(False)

        self._decrypt_thread = _DecryptThread(acct)
        self._decrypt_thread.progress.connect(lambda m: self._status.showMessage(m))
        self._decrypt_thread.finished_ok.connect(self._on_decrypt_ok)
        self._decrypt_thread.finished_err.connect(self._on_decrypt_err)
        self._decrypt_thread.start()

    def _on_decrypt_ok(self, decrypted_dir: str) -> None:
        self._decrypt_btn.setEnabled(True)
        self._decrypt_btn.setText("重新解密")
        self._open_btn.setEnabled(True)
        self._status.showMessage(f"解密完成: {decrypted_dir}")
        self._load_database(decrypted_dir)

    def _on_decrypt_err(self, err: str) -> None:
        self._decrypt_btn.setEnabled(True)
        self._decrypt_btn.setText("一键解密（重试）")
        self._open_btn.setEnabled(True)
        QMessageBox.critical(self, "解密失败", err)

    # ==================================================================
    # Open / Load
    # ==================================================================

    def _on_open_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择已解密的微信数据库目录")
        if folder:
            self._load_database(folder)

    def _load_database(self, folder: str) -> None:
        self._reader = DatabaseReader(folder)
        self._open_btn.setEnabled(False)
        self._status.showMessage(f"正在加载: {folder}")
        self._loader = _LoaderThread(self._reader)
        self._loader.progress.connect(lambda m: self._status.showMessage(m))
        self._loader.finished_ok.connect(self._on_load_finished)
        self._loader.finished_err.connect(self._on_load_error)
        self._loader.start()

    def _on_load_finished(self) -> None:
        self._open_btn.setEnabled(True)
        self._populate_conversation_list()
        n = len(self._reader.conversations) if self._reader else 0
        total = sum(c.message_count for c in self._reader.conversations) if self._reader else 0
        self._status.showMessage(f"已加载 {n} 个会话，共 {total:,} 条消息")
        if n == 0:
            self._show_info(
                "未找到聊天记录",
                "当前目录下没有发现有效的聊天数据。<br>"
                "请确认数据库已正确解密，或点击「一键解密」重新解密。",
            )

    def _on_load_error(self, err: str) -> None:
        self._open_btn.setEnabled(True)
        QMessageBox.warning(self, "加载失败", f"数据库加载出错:\n{err}")

    # ==================================================================
    # Conversation list
    # ==================================================================

    def _populate_conversation_list(self) -> None:
        self._conv_list.clear()
        if not self._reader:
            return
        for conv in self._reader.conversations:
            display = conv.display_name
            meta_parts = [f"{conv.message_count} 条"]
            if conv.last_time_str:
                meta_parts.append(conv.last_time_str)
            meta = "  ·  ".join(meta_parts)

            item = QListWidgetItem(f"{display}\n{meta}")
            item.setData(Qt.ItemDataRole.UserRole, conv)
            item.setToolTip(f"{conv.user_name or conv.chat_hash}")

            font = QFont()
            font.setPointSize(12)
            item.setFont(font)

            self._conv_list.addItem(item)

    def _on_search_changed(self, text: str) -> None:
        q = text.strip().lower()
        for i in range(self._conv_list.count()):
            item = self._conv_list.item(i)
            if not q:
                item.setHidden(False)
            else:
                conv: Conversation = item.data(Qt.ItemDataRole.UserRole)
                item.setHidden(
                    q not in conv.display_name.lower()
                    and q not in conv.user_name.lower()
                )

    def _on_conv_selected(self, row: int) -> None:
        if row < 0:
            return
        item = self._conv_list.item(row)
        if not item:
            return
        conv: Conversation = item.data(Qt.ItemDataRole.UserRole)
        self._current_conv = conv
        self._conv_title.setText(conv.display_name)
        group_tag = "群聊" if conv.is_group else "私聊"
        self._conv_subtitle.setText(f"{group_tag} · {conv.message_count} 条消息")
        self._page = 0
        self._load_messages()

    # ==================================================================
    # Messages
    # ==================================================================

    def _get_time_range(self) -> tuple[int, int]:
        sd = self._date_start.date()
        ed = self._date_end.date()
        s = int(datetime(sd.year(), sd.month(), sd.day()).timestamp())
        e = int(datetime(ed.year(), ed.month(), ed.day(), 23, 59, 59).timestamp())
        return s, e

    def _on_filter(self) -> None:
        self._page = 0
        self._load_messages()

    def _load_messages(self) -> None:
        if not self._reader or not self._current_conv:
            return
        s, e = self._get_time_range()
        self._current_messages = self._reader.get_messages(
            self._current_conv, start_time=s, end_time=e,
        )
        total = len(self._current_messages)
        self._total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        self._page = min(self._page, self._total_pages - 1)
        self._render_page()

    def _render_page(self) -> None:
        total = len(self._current_messages)
        a = self._page * PAGE_SIZE
        b = min(a + PAGE_SIZE, total)
        page = self._current_messages[a:b]

        multi = self._total_pages > 1
        self._prev_btn.setVisible(multi)
        self._next_btn.setVisible(multi)
        self._prev_btn.setEnabled(self._page > 0)
        self._next_btn.setEnabled(self._page < self._total_pages - 1)
        if multi:
            self._page_label.setText(
                f"第 {self._page+1}/{self._total_pages} 页  ·  共 {total} 条"
            )
        else:
            self._page_label.setText(f"共 {total} 条消息" if total else "")

        grp = self._current_conv.is_group if self._current_conv else False
        self._chat_browser.setHtml(self._build_chat_html(page, grp))
        self._chat_browser.verticalScrollBar().setValue(0)

    def _on_prev_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._render_page()

    def _on_next_page(self) -> None:
        if self._page < self._total_pages - 1:
            self._page += 1
            self._render_page()

    # ==================================================================
    # HTML rendering
    # ==================================================================

    def _build_chat_html(self, messages: list[Message], is_group: bool) -> str:
        p: list[str] = [
            f'<html><head><style>{CHAT_HTML_CSS}</style></head><body>'
        ]
        last_date = ""
        for m in messages:
            d = m.date_str
            if d != last_date:
                last_date = d
                p.append(
                    f'<p align="center" class="date-sep">'
                    f'<span class="date-sep-inner">{html.escape(d)}</span></p>'
                )

            if m.msg_type == 10000:
                p.append(
                    f'<p align="center" class="sys">{html.escape(m.display_text)}</p>'
                )
                continue

            txt = html.escape(m.display_text)
            ts = html.escape(m.time_str)

            if m.is_sender:
                p.append(
                    '<table width="100%" class="msg-row" cellpadding="0" cellspacing="0"><tr>'
                    '<td width="20%"></td>'
                    '<td align="right" style="padding:3px 4px;">'
                    f'<table align="right" cellpadding="0" cellspacing="0"><tr>'
                    f'<td class="bubble-sent">{txt}</td>'
                    '</tr></table>'
                    f'<br><span class="time-r">{ts}</span>'
                    '</td></tr></table>'
                )
            else:
                sender = ""
                if is_group and m.sender_name and m.sender_name != "我":
                    sender = (
                        f'<span class="sender-name">'
                        f'{html.escape(m.sender_name)}</span><br>'
                    )
                p.append(
                    '<table width="100%" class="msg-row" cellpadding="0" cellspacing="0"><tr>'
                    '<td align="left" style="padding:3px 4px;">'
                    f'{sender}'
                    f'<table cellpadding="0" cellspacing="0"><tr>'
                    f'<td class="bubble-recv">{txt}</td>'
                    '</tr></table>'
                    f'<br><span class="time-l">{ts}</span>'
                    '</td>'
                    '<td width="20%"></td></tr></table>'
                )

        if not messages:
            p.append(
                '<p align="center" class="empty">当前时间范围内没有消息</p>'
            )

        p.append('</body></html>')
        return "\n".join(p)

    # ==================================================================
    # CSV export
    # ==================================================================

    def _on_export_csv(self) -> None:
        if not self._current_conv or not self._current_messages:
            QMessageBox.information(self, "提示", "请先选择一个会话并加载消息")
            return
        name = f"{self._current_conv.display_name}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", name, "CSV (*.csv)")
        if not path:
            return
        n = export_to_csv(self._current_messages, path, self._current_conv.display_name)
        self._status.showMessage(f"已导出 {n} 条消息到 {os.path.basename(path)}")
        QMessageBox.information(self, "导出成功", f"已导出 {n} 条消息到:\n{path}")

    def _on_export_all_csv(self) -> None:
        if not self._reader or not self._reader.conversations:
            QMessageBox.information(self, "提示", "请先加载数据库")
            return
        folder = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if not folder:
            return
        s, e = self._get_time_range()
        exported = 0
        for conv in self._reader.conversations:
            msgs = self._reader.get_messages(conv, start_time=s, end_time=e)
            if not msgs:
                continue
            safe = conv.display_name.replace("/", "_").replace("\\", "_")
            export_to_csv(msgs, os.path.join(folder, f"{safe}.csv"), conv.display_name)
            exported += 1
            self._status.showMessage(
                f"导出中… ({exported}/{len(self._reader.conversations)})"
            )
        self._status.showMessage(f"全部导出完成: {exported} 个会话")
        QMessageBox.information(self, "导出成功", f"已导出 {exported} 个会话到:\n{folder}")
