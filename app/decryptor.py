"""Decrypt SQLCipher v4 databases using the sqlcipher CLI."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Callable

logger = logging.getLogger(__name__)

CACHE_ROOT = os.path.expanduser("~/.wx-chathistory/decrypted")


def find_sqlcipher() -> str | None:
    """Return the path to sqlcipher binary, or None."""
    return shutil.which("sqlcipher")


def install_sqlcipher(progress_cb: Callable[[str], None] | None = None) -> bool:
    """Install sqlcipher via Homebrew."""
    if progress_cb:
        progress_cb("正在通过 Homebrew 安装 sqlcipher…")
    r = subprocess.run(
        ["brew", "install", "sqlcipher"],
        capture_output=True, text=True, timeout=300,
    )
    return r.returncode == 0


def decrypt_database(
    encrypted_path: str,
    decrypted_path: str,
    raw_key_96hex: str,
    sqlcipher_bin: str = "sqlcipher",
) -> bool:
    """Decrypt a single SQLCipher v4 database."""
    os.makedirs(os.path.dirname(decrypted_path) or ".", exist_ok=True)
    if os.path.exists(decrypted_path):
        os.remove(decrypted_path)

    esc_dec = decrypted_path.replace("'", "''")
    sql = (
        f"PRAGMA key = \"x'{raw_key_96hex}'\";\n"
        f"ATTACH DATABASE '{esc_dec}' AS plaintext KEY '';\n"
        "SELECT sqlcipher_export('plaintext');\n"
        "DETACH DATABASE plaintext;\n"
    )
    r = subprocess.run(
        [sqlcipher_bin, encrypted_path],
        input=sql, capture_output=True, text=True, timeout=600,
    )
    if r.returncode != 0:
        logger.warning("Decrypt failed for %s: %s", encrypted_path, r.stderr)
        if os.path.exists(decrypted_path):
            os.remove(decrypted_path)
        return False
    if not os.path.exists(decrypted_path) or os.path.getsize(decrypted_path) == 0:
        return False
    return True


def cache_dir_for(account_hash: str) -> str:
    """Return the cache directory for decrypted databases of a given account."""
    d = os.path.join(CACHE_ROOT, account_hash)
    os.makedirs(d, exist_ok=True)
    return d


def is_cached(account_hash: str) -> bool:
    """Check if we already have cached decrypted databases for this account."""
    d = cache_dir_for(account_hash)
    try:
        return any(f.endswith(".db") for f in os.listdir(d))
    except OSError:
        return False


def decrypt_all(
    data_dir: str,
    keys: list[str],
    account_hash: str,
    progress_cb: Callable[[str], None] | None = None,
    sqlcipher_bin: str = "sqlcipher",
) -> str:
    """Decrypt all encrypted .db files under *data_dir*.

    *keys* is the list of 96-hex-char keys extracted from memory.
    Each key's last 32 hex chars (salt) is matched to the database file's
    first 16 bytes.

    Returns the cache directory path containing decrypted databases.
    """
    out_dir = cache_dir_for(account_hash)

    salt_to_key: dict[str, str] = {}
    for k in keys:
        salt_to_key[k[64:].lower()] = k

    db_files: list[tuple[str, str]] = []
    for dirpath, _dirs, files in os.walk(data_dir):
        for f in sorted(files):
            if not f.endswith(".db"):
                continue
            full = os.path.join(dirpath, f)
            try:
                with open(full, "rb") as fh:
                    hdr = fh.read(6)
                if hdr == b"SQLite":
                    continue
            except OSError:
                continue
            rel = os.path.relpath(full, data_dir)
            db_files.append((full, rel))

    total = len(db_files)
    succeeded = 0
    for idx, (enc_path, rel) in enumerate(db_files, 1):
        base = rel.replace(os.sep, "_")
        dec_path = os.path.join(out_dir, base)

        if os.path.exists(dec_path) and os.path.getsize(dec_path) > 0:
            enc_mtime = os.path.getmtime(enc_path)
            dec_mtime = os.path.getmtime(dec_path)
            if dec_mtime >= enc_mtime:
                succeeded += 1
                continue

        if progress_cb:
            progress_cb(f"解密中 ({idx}/{total}): {base}")

        try:
            with open(enc_path, "rb") as fh:
                file_salt = fh.read(16).hex().lower()
        except OSError:
            continue

        matched_key = salt_to_key.get(file_salt)
        if not matched_key:
            logger.warning("No key matches salt for %s", enc_path)
            continue

        if decrypt_database(enc_path, dec_path, matched_key, sqlcipher_bin):
            succeeded += 1
        else:
            logger.warning("Failed to decrypt %s", enc_path)

    if progress_cb:
        progress_cb(f"解密完成: {succeeded}/{total}")

    return out_dir
