"""Python API bridge for pywebview — exposes backend to the JS frontend."""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from typing import Any

from .db_reader import DatabaseReader, DetectedAccount, detect_wechat_accounts
from .csv_exporter import export_to_csv

logger = logging.getLogger(__name__)

PAGE_SIZE = 200


class Api:
    def __init__(self, window=None):
        self._window = window
        self._reader: DatabaseReader | None = None
        self._accounts: list[DetectedAccount] = []
        self._current_messages: list[Any] = []
        self._decrypt_state: dict = {"running": False, "progress": "", "done": False, "error": ""}

    def set_window(self, window):
        self._window = window

    # ── Account detection ──

    def detect_accounts(self) -> list[dict]:
        self._accounts = detect_wechat_accounts()
        return [
            {
                "index": i,
                "label": a.label,
                "account_hash": a.account_hash,
                "path": a.path,
                "encrypted_msg_count": a.encrypted_msg_count,
                "total_db_count": a.total_db_count,
                "has_cached_decrypt": a.has_cached_decrypt,
                "cached_dir": a.cached_dir,
            }
            for i, a in enumerate(self._accounts)
        ]

    # ── Decrypt ──

    def start_decrypt(self, index: int) -> dict:
        if self._decrypt_state["running"]:
            return {"ok": False, "error": "Decrypt already running"}
        if index < 0 or index >= len(self._accounts):
            return {"ok": False, "error": "Invalid account"}

        self._decrypt_state = {"running": True, "progress": "Starting...", "done": False, "error": "", "result_dir": ""}
        acct = self._accounts[index]
        t = threading.Thread(target=self._decrypt_worker, args=(acct,), daemon=True)
        t.start()
        return {"ok": True}

    def get_decrypt_status(self) -> dict:
        return dict(self._decrypt_state)

    def _decrypt_worker(self, acct: DetectedAccount):
        try:
            import shutil
            from .key_extract import extract_keys
            from .decryptor import find_sqlcipher, install_sqlcipher, decrypt_all

            sc = find_sqlcipher()
            if not sc:
                self._decrypt_state["progress"] = "Installing sqlcipher..."
                if not install_sqlcipher():
                    self._decrypt_state.update(running=False, error="sqlcipher installation failed.\nRun: brew install sqlcipher")
                    return
                sc = find_sqlcipher()

            self._decrypt_state["progress"] = "Extracting keys from WeChat process..."
            keys = extract_keys(progress_cb=lambda m: self._decrypt_state.update(progress=m))
            self._decrypt_state["progress"] = f"Got {len(keys)} keys, decrypting..."

            out_dir = decrypt_all(
                data_dir=acct.path,
                keys=keys,
                account_hash=acct.account_hash,
                progress_cb=lambda m: self._decrypt_state.update(progress=m),
                sqlcipher_bin=sc,
            )
            self._decrypt_state.update(running=False, done=True, result_dir=out_dir, progress="Done")
        except Exception as exc:
            self._decrypt_state.update(running=False, error=str(exc))

    # ── Database loading ──

    def load_database(self, path: str) -> dict:
        try:
            self._reader = DatabaseReader(path)
            self._reader.load()
            n = len(self._reader.conversations)
            total = sum(c.message_count for c in self._reader.conversations)
            return {"ok": True, "conversations": n, "total_messages": total, "self_wxid": self._reader.self_wxid}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_conversations(self) -> list[dict]:
        if not self._reader:
            return []
        return [
            {
                "chat_hash": c.chat_hash,
                "user_name": c.user_name,
                "display_name": c.display_name,
                "is_group": c.is_group,
                "message_count": c.message_count,
                "last_time": c.last_time_str,
            }
            for c in self._reader.conversations
        ]

    def get_messages(self, chat_hash: str, start_date: str, end_date: str, page: int) -> dict:
        if not self._reader:
            return {"messages": [], "total": 0, "pages": 0, "page": 0}

        conv = None
        for c in self._reader.conversations:
            if c.chat_hash == chat_hash:
                conv = c
                break
        if not conv:
            return {"messages": [], "total": 0, "pages": 0, "page": 0}

        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp()) if start_date else 0
        end_ts = int(datetime.strptime(end_date + " 23:59:59", "%Y-%m-%d %H:%M:%S").timestamp()) if end_date else 0

        all_msgs = self._reader.get_messages(conv, start_time=start_ts, end_time=end_ts)
        self._current_messages = all_msgs
        total = len(all_msgs)
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, pages - 1)
        start = page * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        page_msgs = all_msgs[start:end]

        return {
            "messages": [self._msg_to_dict(m) for m in page_msgs],
            "total": total,
            "pages": pages,
            "page": page,
            "is_group": conv.is_group,
            "display_name": conv.display_name,
        }

    @staticmethod
    def _msg_to_dict(m) -> dict:
        return {
            "id": m.local_id,
            "type": m.msg_type,
            "type_name": m.type_name,
            "sub_type": m.sub_type,
            "is_sender": m.is_sender,
            "sender_name": m.sender_name,
            "timestamp": m.timestamp,
            "datetime": m.datetime_str,
            "time": m.time_str,
            "date": m.date_str,
            "content": m.display_text,
        }

    # ── Export ──

    def export_csv(self, chat_hash: str) -> dict:
        if not self._reader:
            return {"ok": False, "error": "No database loaded"}
        conv = None
        for c in self._reader.conversations:
            if c.chat_hash == chat_hash:
                conv = c
                break
        if not conv:
            return {"ok": False, "error": "Conversation not found"}

        if self._window:
            result = self._window.create_file_dialog(
                dialog_type=2,
                file_types=("CSV Files (*.csv)",),
                save_filename=f"{conv.display_name}.csv",
            )
        else:
            result = None

        if not result:
            return {"ok": False, "error": "cancelled"}

        path = result if isinstance(result, str) else result[0]
        msgs = self._current_messages if self._current_messages else self._reader.get_messages(conv)
        n = export_to_csv(msgs, path, conv.display_name)
        return {"ok": True, "count": n, "path": path}

    def export_all_csv(self) -> dict:
        if not self._reader:
            return {"ok": False, "error": "No database loaded"}

        if self._window:
            result = self._window.create_file_dialog(dialog_type=3)
        else:
            result = None

        if not result:
            return {"ok": False, "error": "cancelled"}

        folder = result if isinstance(result, str) else result[0]
        exported = 0
        for conv in self._reader.conversations:
            msgs = self._reader.get_messages(conv)
            if not msgs:
                continue
            safe = conv.display_name.replace("/", "_").replace("\\", "_")
            export_to_csv(msgs, os.path.join(folder, f"{safe}.csv"), conv.display_name)
            exported += 1
        return {"ok": True, "count": exported, "path": folder}

    def is_wechat_running(self) -> bool:
        import subprocess
        r = subprocess.run(["pgrep", "-x", "WeChat"], capture_output=True)
        return r.returncode == 0
