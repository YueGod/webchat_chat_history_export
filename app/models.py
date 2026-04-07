from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime


MSG_TYPE_NAMES = {
    1: "文本",
    3: "图片",
    34: "语音",
    42: "名片",
    43: "视频",
    47: "表情",
    48: "位置",
    49: "链接/文件",
    50: "通话",
    10000: "系统消息",
    10002: "撤回",
}


@dataclass
class Contact:
    user_name: str
    nick_name: str = ""
    remark: str = ""
    alias: str = ""

    @property
    def display_name(self) -> str:
        return self.remark or self.nick_name or self.alias or self.user_name


@dataclass
class Message:
    local_id: int
    msg_svr_id: int
    msg_type: int
    sub_type: int
    is_sender: bool
    timestamp: int
    content: str
    sender_id: str = ""
    sender_name: str = ""
    msg_source: str = ""
    display_content: str = ""

    @property
    def type_name(self) -> str:
        return MSG_TYPE_NAMES.get(self.msg_type, f"未知({self.msg_type})")

    @property
    def datetime_str(self) -> str:
        try:
            return datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, ValueError):
            return str(self.timestamp)

    @property
    def time_str(self) -> str:
        try:
            return datetime.fromtimestamp(self.timestamp).strftime("%H:%M")
        except (OSError, ValueError):
            return ""

    @property
    def date_str(self) -> str:
        try:
            return datetime.fromtimestamp(self.timestamp).strftime("%Y年%m月%d日")
        except (OSError, ValueError):
            return ""

    @property
    def display_text(self) -> str:
        if self.msg_type == 1:
            return self.content
        if self.msg_type == 3:
            return "[图片]"
        if self.msg_type == 34:
            return "[语音]"
        if self.msg_type == 42:
            return self._parse_contact_card()
        if self.msg_type == 43:
            return "[视频]"
        if self.msg_type == 47:
            return "[表情]"
        if self.msg_type == 48:
            return self._parse_location()
        if self.msg_type == 49:
            return self._parse_link()
        if self.msg_type == 50:
            return "[语音/视频通话]"
        if self.msg_type == 10000:
            return self.content or "[系统消息]"
        if self.msg_type == 10002:
            return "[消息已撤回]"
        return self.content or f"[{self.type_name}]"

    def _parse_link(self) -> str:
        try:
            root = ET.fromstring(self.content)
            appmsg = root.find("appmsg")
            if appmsg is not None:
                title = appmsg.findtext("title", "")
                if title:
                    return f"[链接] {title}"
        except ET.ParseError:
            pass
        return "[链接/文件]"

    def _parse_contact_card(self) -> str:
        try:
            root = ET.fromstring(self.content)
            nickname = root.get("nickname", "")
            if nickname:
                return f"[名片] {nickname}"
        except ET.ParseError:
            pass
        return "[名片]"

    def _parse_location(self) -> str:
        try:
            root = ET.fromstring(self.content)
            location = root.find("location")
            if location is not None:
                label = location.get("poiname", "") or location.get("label", "")
                if label:
                    return f"[位置] {label}"
        except ET.ParseError:
            pass
        return "[位置]"


@dataclass
class Conversation:
    chat_hash: str
    user_name: str = ""
    display_name: str = ""
    is_group: bool = False
    message_count: int = 0
    last_message_time: int = 0
    db_tables: list[tuple[str, str]] = field(default_factory=list)

    @property
    def last_time_str(self) -> str:
        if self.last_message_time:
            try:
                return datetime.fromtimestamp(self.last_message_time).strftime("%m-%d %H:%M")
            except (OSError, ValueError):
                pass
        return ""

    @property
    def sort_key(self) -> int:
        return -(self.last_message_time or 0)
