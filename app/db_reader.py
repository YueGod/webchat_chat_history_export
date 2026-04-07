from __future__ import annotations

import hashlib
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Callable

from .models import Contact, Conversation, Message

logger = logging.getLogger(__name__)

_MSG_COLUMNS_LEGACY = (
    "localId", "TalkerId", "MsgSvrID", "Type", "SubType",
    "IsSender", "CreateTime", "Sequence", "StatusEx", "FlagEx",
    "Status", "MsgSource", "StrContent", "DisplayContent",
)
_MSG_COLUMNS_NEW = (
    "local_id", "real_sender_id", "server_id", "local_type",
    "origin_source", "create_time", "sort_seq", "status",
    "source", "message_content",
)

_WECHAT_CONTAINER = os.path.expanduser(
    "~/Library/Containers/com.tencent.xinWeChat/Data"
)
_LEGACY_BASE = os.path.join(
    _WECHAT_CONTAINER, "Library/Application Support/com.tencent.xinWeChat"
)
_NEW_BASE = os.path.join(
    _WECHAT_CONTAINER, "Documents/xwechat_files"
)


@dataclass
class DetectedAccount:
    path: str
    account_hash: str
    encrypted_msg_count: int
    total_db_count: int
    has_cached_decrypt: bool
    cached_dir: str
    label: str


def detect_wechat_accounts() -> list[DetectedAccount]:
    """Scan both legacy and new WeChat data directories for user accounts."""
    from .decryptor import cache_dir_for, is_cached

    results: list[DetectedAccount] = []
    _scan_new_path(results)
    _scan_legacy_path(results)
    return results


def _scan_new_path(results: list[DetectedAccount]) -> None:
    """Scan ~/…/Data/Documents/xwechat_files/wxid_*/ (WeChat 4.1+ layout)."""
    from .decryptor import cache_dir_for, is_cached

    if not os.path.isdir(_NEW_BASE):
        return
    for name in _safe_listdir(_NEW_BASE):
        if not name.startswith("wxid_"):
            continue
        data_dir = os.path.join(_NEW_BASE, name)
        db_storage = os.path.join(data_dir, "db_storage")
        if not os.path.isdir(db_storage):
            continue

        enc_msgs, total = _count_dbs_in_tree(db_storage)
        if total == 0:
            continue

        wxid = name.split("_f")[0] if "_f" in name else name
        account_hash = name
        cached = is_cached(account_hash)
        cached_dir = cache_dir_for(account_hash)

        label = f"{wxid} ({enc_msgs} 个消息库"
        label += ", 已有缓存解密)" if cached else ", 待解密)"

        results.append(DetectedAccount(
            path=db_storage,
            account_hash=account_hash,
            encrypted_msg_count=enc_msgs,
            total_db_count=total,
            has_cached_decrypt=cached,
            cached_dir=cached_dir,
            label=label,
        ))


def _scan_legacy_path(results: list[DetectedAccount]) -> None:
    """Scan ~/…/Application Support/com.tencent.xinWeChat/{ver}/{hash}/ (legacy)."""
    from .decryptor import cache_dir_for, is_cached

    if not os.path.isdir(_LEGACY_BASE):
        return
    known_paths = {r.path for r in results}

    for ver in _safe_listdir(_LEGACY_BASE):
        ver_dir = os.path.join(_LEGACY_BASE, ver)
        if not os.path.isdir(ver_dir):
            continue
        for whash in _safe_listdir(ver_dir):
            data_dir = os.path.join(ver_dir, whash)
            if not os.path.isdir(data_dir) or data_dir in known_paths:
                continue
            msg_dir = os.path.join(data_dir, "Message")
            if not os.path.isdir(msg_dir):
                continue

            enc_msgs, total = _count_dbs_in_tree(data_dir)
            if total == 0:
                continue

            cached = is_cached(whash)
            cached_dir = cache_dir_for(whash)
            label = f"{whash[:8]}… ({enc_msgs} 个消息库"
            label += ", 已有缓存解密)" if cached else ", 待解密)"

            results.append(DetectedAccount(
                path=data_dir,
                account_hash=whash,
                encrypted_msg_count=enc_msgs,
                total_db_count=total,
                has_cached_decrypt=cached,
                cached_dir=cached_dir,
                label=label,
            ))


def _safe_listdir(path: str) -> list[str]:
    try:
        return sorted(os.listdir(path))
    except PermissionError:
        return []


def _count_dbs_in_tree(root: str) -> tuple[int, int]:
    """Returns (encrypted_msg_count, total_db_count) of .db files."""
    enc_msgs = 0
    total = 0
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if not f.endswith(".db"):
                continue
            if f.endswith("-shm") or f.endswith("-wal"):
                continue
            total += 1
            if _is_message_db_name(f):
                full = os.path.join(dirpath, f)
                if not _is_valid_sqlite(full):
                    enc_msgs += 1
    return enc_msgs, total


def _is_message_db_name(name: str) -> bool:
    return bool(re.match(
        r"^(msg_|message_|decrypted_msg_|decrypted_message_|message_message_)\d+\.db$",
        name,
    ))


def _is_valid_sqlite(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(6) == b"SQLite"
    except OSError:
        return False


# ======================================================================
# DatabaseReader
# ======================================================================

class DatabaseReader:
    """Reads decrypted WeChat Mac 4.x SQLite databases.

    Works with both the legacy layout (Message/msg_0.db, Contact/wccontact_new2.db)
    and the new layout (message/message_0.db, contact/contact.db).
    """

    _CONTACT_NAMES = [
        "wccontact_new2.db", "contact.db",
        "decrypted_wccontact_new2.db", "decrypted_contact.db",
        "contact_wccontact_new2.db", "contact_contact.db",
    ]
    _GROUP_NAMES = [
        "group_new.db", "decrypted_group_new.db",
        "contact.db", "contact_contact.db",
    ]

    def __init__(self, db_dir: str, self_wxid: str = ""):
        self.db_dir = db_dir
        self.self_wxid = self_wxid or self._detect_self_wxid(db_dir)
        self.contacts: dict[str, Contact] = {}
        self.conversations: list[Conversation] = []
        self._hash_to_username: dict[str, str] = {}
        self._chat_locations: dict[str, list[tuple[str, str]]] = {}
        self._name2id_cache: dict[str, dict[int, str]] = {}

    @staticmethod
    def _detect_self_wxid(db_dir: str) -> str:
        """Detect the logged-in user's wxid from Name2Id tables.

        Each message database has a Name2Id table. We scan all of them and
        pick the wxid_ entry that appears most often at rowid=1 (which is
        usually the account owner for the current shard).
        """
        candidates: dict[str, int] = {}
        try:
            for f in sorted(os.listdir(db_dir)):
                if not f.endswith(".db"):
                    continue
                full = os.path.join(db_dir, f)
                if not _is_valid_sqlite(full):
                    continue
                try:
                    conn = sqlite3.connect(full)
                    tables = {r[0] for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )}
                    if "Name2Id" in tables:
                        for row in conn.execute(
                            "SELECT user_name, is_session FROM Name2Id "
                            "WHERE user_name LIKE 'wxid_%'"
                        ):
                            uid = row[0]
                            candidates[uid] = candidates.get(uid, 0) + 1
                    conn.close()
                except Exception:
                    pass
        except OSError:
            pass

        if candidates:
            return max(candidates, key=candidates.get)
        return ""

    def load(self, progress_cb: Callable[[str], None] | None = None) -> None:
        def _report(msg: str) -> None:
            if progress_cb:
                progress_cb(msg)

        _report("正在加载联系人…")
        self._load_contacts()

        _report("正在加载群聊信息…")
        self._load_groups()

        _report("正在扫描消息数据库…")
        self._scan_message_databases(_report)

        _report("正在构建会话列表…")
        self._build_conversations()

        _report(f"加载完成: {len(self.conversations)} 个会话")

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------

    def _load_contacts(self) -> None:
        db_path = self._find_any_db(self._CONTACT_NAMES)
        if not db_path:
            return
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "WCContact" in tables:
                self._load_contacts_legacy(conn)
            elif "contact" in tables:
                self._load_contacts_new_v2(conn)
            elif "Friend" in tables:
                self._load_contacts_new(conn, "Friend")
            else:
                for t in tables:
                    if "contact" in t.lower() or "friend" in t.lower():
                        self._load_contacts_auto(conn, t)
                        break
            conn.close()
        except Exception as exc:
            logger.warning("Failed to load contacts: %s", exc)

    def _load_contacts_legacy(self, conn: sqlite3.Connection) -> None:
        for row in conn.execute(
            "SELECT userName, NickName, Remark, Alias FROM WCContact"
        ):
            c = Contact(
                user_name=row["userName"] or "",
                nick_name=row["NickName"] or "",
                remark=row["Remark"] or "",
                alias=row["Alias"] or "",
            )
            self.contacts[c.user_name] = c

    def _load_contacts_new(self, conn: sqlite3.Connection, table: str) -> None:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info([{table}])")}
        uname_col = _pick(cols, "userName", "UserId", "wxid", "user_name")
        nick_col  = _pick(cols, "NickName", "nickname", "nick_name", "Nickname")
        remark_col = _pick(cols, "Remark", "remark", "RemarkName")
        alias_col  = _pick(cols, "Alias", "alias", "Wechatno")
        if not uname_col:
            return
        sel = [uname_col]
        if nick_col:   sel.append(nick_col)
        if remark_col: sel.append(remark_col)
        if alias_col:  sel.append(alias_col)
        for row in conn.execute(f"SELECT {','.join(sel)} FROM [{table}]"):
            uid = row[0] or ""
            if not uid:
                continue
            self.contacts[uid] = Contact(
                user_name=uid,
                nick_name=row[1] if len(row) > 1 else "",
                remark=row[2] if len(row) > 2 else "",
                alias=row[3] if len(row) > 3 else "",
            )

    def _load_contacts_new_v2(self, conn: sqlite3.Connection) -> None:
        """WeChat 4.1+ contact table: columns username, nick_name, remark, alias."""
        for row in conn.execute(
            "SELECT username, nick_name, remark, alias FROM contact"
        ):
            uid = row["username"] or ""
            if not uid:
                continue
            self.contacts[uid] = Contact(
                user_name=uid,
                nick_name=row["nick_name"] or "",
                remark=row["remark"] or "",
                alias=row["alias"] or "",
            )

    def _load_contacts_auto(self, conn: sqlite3.Connection, table: str) -> None:
        self._load_contacts_new(conn, table)

    def _load_groups(self) -> None:
        db_path = self._find_any_db(self._GROUP_NAMES)
        if db_path:
            self._load_groups_from(db_path)
        contact_db = self._find_any_db(self._CONTACT_NAMES)
        if contact_db and contact_db != db_path:
            self._load_groups_from(contact_db)

    def _load_groups_from(self, db_path: str) -> None:
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            for tbl, name_col, display_col in [
                ("ChatRoom", "ChatRoomName", "DisplayName"),
                ("chat_room", "chat_room_name", "remark"),
            ]:
                if tbl not in tables:
                    continue
                cols = {r[1] for r in conn.execute(f"PRAGMA table_info([{tbl}])")}
                if name_col not in cols:
                    continue
                disp = display_col if display_col in cols else None
                for row in conn.execute(f"SELECT * FROM [{tbl}]"):
                    name = row[name_col] if name_col in row.keys() else ""
                    if not name:
                        continue
                    display = (row[disp] if disp and disp in row.keys() else "") or name
                    if name not in self.contacts:
                        self.contacts[name] = Contact(
                            user_name=name, nick_name=display,
                        )
            conn.close()
        except Exception as exc:
            logger.warning("Failed to load groups from %s: %s", db_path, exc)

    # ------------------------------------------------------------------
    # Message database scanning
    # ------------------------------------------------------------------

    def _scan_message_databases(
        self, report: Callable[[str], None]
    ) -> None:
        self._hash_to_username = {}
        for uname in self.contacts:
            h = hashlib.md5(uname.encode("utf-8")).hexdigest()
            self._hash_to_username[h] = uname

        db_files = self._find_message_dbs()
        for idx, db_path in enumerate(db_files, 1):
            report(f"扫描数据库 ({idx}/{len(db_files)}): {os.path.basename(db_path)}")
            self._scan_single_db(db_path)

    def _scan_single_db(self, db_path: str) -> None:
        try:
            conn = sqlite3.connect(db_path)
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            ]
            for table in tables:
                if table.startswith("Chat_"):
                    chat_hash = table[5:]
                    self._chat_locations.setdefault(chat_hash, []).append(
                        (db_path, table)
                    )
                elif table.startswith("Msg_"):
                    chat_hash = table[4:]
                    self._chat_locations.setdefault(chat_hash, []).append(
                        (db_path, table)
                    )
            conn.close()
        except Exception as exc:
            logger.warning("Failed to scan %s: %s", db_path, exc)

    # ------------------------------------------------------------------
    # Build conversation list
    # ------------------------------------------------------------------

    def _build_conversations(self) -> None:
        self.conversations = []
        for chat_hash, locations in self._chat_locations.items():
            user_name = self._hash_to_username.get(chat_hash, "")
            is_group = user_name.endswith("@chatroom")

            if user_name and user_name in self.contacts:
                display_name = self.contacts[user_name].display_name
            else:
                display_name = user_name or f"会话_{chat_hash[:8]}"

            count, last_time = self._get_conversation_stats(locations)

            conv = Conversation(
                chat_hash=chat_hash,
                user_name=user_name,
                display_name=display_name,
                is_group=is_group,
                message_count=count,
                last_message_time=last_time,
                db_tables=locations,
            )
            self.conversations.append(conv)

        self.conversations.sort(key=lambda c: c.sort_key)

    def _get_conversation_stats(
        self, locations: list[tuple[str, str]]
    ) -> tuple[int, int]:
        total_count = 0
        max_time = 0
        for db_path, table in locations:
            try:
                conn = sqlite3.connect(db_path)
                cols = {r[1] for r in conn.execute(f"PRAGMA table_info([{table}])")}
                time_col = "create_time" if "create_time" in cols else "CreateTime"
                row = conn.execute(
                    f"SELECT COUNT(*), MAX({time_col}) FROM [{table}]"
                ).fetchone()
                if row:
                    total_count += row[0] or 0
                    max_time = max(max_time, row[1] or 0)
                conn.close()
            except Exception:
                pass
        return total_count, max_time

    # ------------------------------------------------------------------
    # Message loading
    # ------------------------------------------------------------------

    def get_messages(
        self,
        conversation: Conversation,
        start_time: int = 0,
        end_time: int = 0,
        limit: int = 0,
    ) -> list[Message]:
        messages: list[Message] = []
        for db_path, table in conversation.db_tables:
            messages.extend(
                self._load_table_messages(
                    db_path, table, conversation, start_time, end_time
                )
            )
        messages.sort(key=lambda m: m.timestamp)
        if limit > 0:
            messages = messages[:limit]
        return messages

    def _get_name2id(self, db_path: str, conn: sqlite3.Connection) -> dict[int, str]:
        """Load Name2Id mapping (rowid→username) for a message database."""
        if db_path in self._name2id_cache:
            return self._name2id_cache[db_path]
        mapping: dict[int, str] = {}
        try:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if "Name2Id" in tables:
                for row in conn.execute("SELECT rowid, user_name FROM Name2Id"):
                    mapping[row[0]] = row[1]
        except Exception:
            pass
        self._name2id_cache[db_path] = mapping
        return mapping

    def _load_table_messages(
        self,
        db_path: str,
        table: str,
        conv: Conversation,
        start_time: int,
        end_time: int,
    ) -> list[Message]:
        results: list[Message] = []
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row

            cols = {
                r["name"]
                for r in conn.execute(f"PRAGMA table_info([{table}])")
            }

            is_new = "create_time" in cols
            template = _MSG_COLUMNS_NEW if is_new else _MSG_COLUMNS_LEGACY
            time_col = "create_time" if is_new else "CreateTime"

            select_cols = [c for c in template if c in cols]
            if not select_cols:
                conn.close()
                return results

            name2id = self._get_name2id(db_path, conn) if is_new else {}

            query = f"SELECT {','.join(select_cols)} FROM [{table}] WHERE 1=1"
            params: list[int] = []
            if start_time:
                query += f" AND {time_col} >= ?"
                params.append(start_time)
            if end_time:
                query += f" AND {time_col} <= ?"
                params.append(end_time)
            query += f" ORDER BY {time_col} ASC"

            for row in conn.execute(query, params):
                if is_new:
                    msg = self._row_to_message_new(row, conv, name2id)
                else:
                    msg = self._row_to_message_legacy(row, conv)
                if msg:
                    results.append(msg)
            conn.close()
        except Exception as exc:
            logger.warning("Failed to load messages from %s [%s]: %s", db_path, table, exc)
        return results

    def _row_to_message_new(
        self, row: sqlite3.Row, conv: Conversation, name2id: dict[int, str],
    ) -> Message | None:
        """Parse a row from the new Msg_* schema (WeChat 4.1+ on macOS)."""
        try:
            keys = row.keys()
            raw_type = row["local_type"] if "local_type" in keys else 0
            msg_type = raw_type & 0xFFFF
            sub_type = (raw_type >> 32) if raw_type > 0xFFFF else 0

            content = row["message_content"] if "message_content" in keys else ""
            if isinstance(content, bytes):
                content = _decompress_wcdb(content)
            content = content or ""

            sender_rowid = row["real_sender_id"] if "real_sender_id" in keys else 0
            sender_wxid = name2id.get(sender_rowid, "")
            is_sender = (sender_wxid == self.self_wxid) if self.self_wxid else False

            if is_sender:
                sender_name = "我"
                sender_id = self.self_wxid
            elif ":\n" in content:
                parts = content.split(":\n", 1)
                sender_id = parts[0]
                content = parts[1]
                if sender_id in self.contacts:
                    sender_name = self.contacts[sender_id].display_name
                else:
                    sender_name = sender_id
            elif sender_wxid:
                sender_id = sender_wxid
                sender_name = self.contacts[sender_wxid].display_name if sender_wxid in self.contacts else sender_wxid
            elif conv.user_name:
                sender_id = conv.user_name
                sender_name = self.contacts[conv.user_name].display_name if conv.user_name in self.contacts else conv.user_name
            else:
                sender_id = ""
                sender_name = ""

            return Message(
                local_id=row["local_id"] if "local_id" in keys else 0,
                msg_svr_id=row["server_id"] if "server_id" in keys else 0,
                msg_type=msg_type,
                sub_type=sub_type,
                is_sender=is_sender,
                timestamp=row["create_time"] if "create_time" in keys else 0,
                content=content,
                sender_id=sender_id,
                sender_name=sender_name,
                msg_source=row["source"] if "source" in keys else "",
                display_content="",
            )
        except Exception as exc:
            logger.debug("Failed to parse new-schema row: %s", exc)
            return None

    def _row_to_message_legacy(self, row: sqlite3.Row, conv: Conversation) -> Message | None:
        """Parse a row from the legacy Chat_* schema."""
        try:
            keys = row.keys()
            msg_type = row["Type"]
            is_sender = bool(row["IsSender"])
            str_content = row["StrContent"] or ""

            sender_id = ""
            sender_name = ""
            if is_sender:
                sender_name = "我"
            elif conv.is_group and ":\n" in str_content:
                parts = str_content.split(":\n", 1)
                sender_id = parts[0]
                str_content = parts[1]
                if sender_id in self.contacts:
                    sender_name = self.contacts[sender_id].display_name
                else:
                    sender_name = sender_id
            elif conv.user_name:
                sender_id = conv.user_name
                if sender_id in self.contacts:
                    sender_name = self.contacts[sender_id].display_name
                else:
                    sender_name = sender_id

            return Message(
                local_id=row["localId"] if "localId" in keys else 0,
                msg_svr_id=row["MsgSvrID"] if "MsgSvrID" in keys else 0,
                msg_type=msg_type,
                sub_type=row["SubType"] if "SubType" in keys else 0,
                is_sender=is_sender,
                timestamp=row["CreateTime"],
                content=str_content,
                sender_id=sender_id,
                sender_name=sender_name,
                msg_source=row["MsgSource"] if "MsgSource" in keys else "",
                display_content=row["DisplayContent"] if "DisplayContent" in keys else "",
            )
        except Exception as exc:
            logger.debug("Failed to parse legacy row: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_any_db(self, candidates: list[str]) -> str | None:
        for root, _dirs, files in os.walk(self.db_dir):
            for f in files:
                if f in candidates:
                    full = os.path.join(root, f)
                    if _is_valid_sqlite(full):
                        return full
        return None

    def _find_message_dbs(self) -> list[str]:
        found: list[str] = []
        for root, _dirs, files in os.walk(self.db_dir):
            for f in sorted(files):
                if not f.endswith(".db"):
                    continue
                if _is_message_db_name(f):
                    full = os.path.join(root, f)
                    if _is_valid_sqlite(full):
                        found.append(full)
        if not found:
            for root, _dirs, files in os.walk(self.db_dir):
                for f in sorted(files):
                    if not f.endswith(".db"):
                        continue
                    full = os.path.join(root, f)
                    if self._has_chat_tables(full):
                        found.append(full)
        return found

    @staticmethod
    def _has_chat_tables(path: str) -> bool:
        try:
            conn = sqlite3.connect(path)
            row = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='table' AND (name LIKE 'Chat_%' OR name LIKE 'Msg_%')"
            ).fetchone()
            conn.close()
            return (row[0] or 0) > 0
        except Exception:
            return False


def _decompress_wcdb(data: bytes) -> str:
    """Decompress WCDB zstd-compressed content to string."""
    if not data:
        return ""
    try:
        import zstandard
        return zstandard.decompress(data).decode("utf-8", errors="replace")
    except Exception:
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return ""


def _pick(cols: set[str], *candidates: str) -> str | None:
    for c in candidates:
        if c in cols:
            return c
    return None
