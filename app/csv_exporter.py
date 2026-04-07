from __future__ import annotations

import csv
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Message


def export_to_csv(
    messages: list[Message],
    output_path: str,
    conversation_name: str = "",
) -> int:
    """Export messages to a CSV file. Returns the number of rows written."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["会话", "时间", "发送者", "类型", "内容"])
        for msg in messages:
            writer.writerow([
                conversation_name,
                msg.datetime_str,
                msg.sender_name or msg.sender_id or ("我" if msg.is_sender else ""),
                msg.type_name,
                msg.display_text,
            ])
    return len(messages)
