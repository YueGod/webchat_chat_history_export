"""Extract encryption key from a running WeChat process via Mach API memory scan."""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)

_C_SOURCE = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <libproc.h>

static int is_hex(char c) {
    return (c>='0'&&c<='9')||(c>='a'&&c<='f')||(c>='A'&&c<='F');
}

int main(void) {
    pid_t target = 0;
    int pids[8192];
    int bytes = proc_listpids(PROC_ALL_PIDS, 0, pids, sizeof(pids));
    for (int i = 0; i < bytes/(int)sizeof(int); i++) {
        if (pids[i] == 0) continue;
        char name[256] = {0};
        proc_name(pids[i], name, sizeof(name));
        if (strcmp(name, "WeChat") == 0) { target = pids[i]; break; }
    }
    if (!target) { fprintf(stderr, "ERROR:WeChat not running\n"); return 1; }
    fprintf(stderr, "INFO:WeChat PID %d\n", target);

    mach_port_t task;
    kern_return_t kr = task_for_pid(mach_task_self(), target, &task);
    if (kr != KERN_SUCCESS) {
        fprintf(stderr, "ERROR:task_for_pid failed (%s). Disable SIP or grant permission.\n",
                mach_error_string(kr));
        return 1;
    }

    mach_vm_address_t addr = 0;
    mach_vm_size_t rsize;
    vm_region_basic_info_data_64_t info;
    mach_msg_type_number_t ic;
    mach_port_t obj;
    int nkeys = 0;
    char keys[512][97];

    while (1) {
        ic = VM_REGION_BASIC_INFO_COUNT_64;
        kr = mach_vm_region(task, &addr, &rsize, VM_REGION_BASIC_INFO_64,
                            (vm_region_info_t)&info, &ic, &obj);
        if (kr != KERN_SUCCESS) break;
        if (!(info.protection & VM_PROT_READ) || rsize > 512ULL*1024*1024) {
            addr += rsize; continue;
        }
        vm_offset_t data; mach_msg_type_number_t dc;
        if (mach_vm_read(task, addr, rsize, &data, &dc) == KERN_SUCCESS) {
            const char *b = (const char *)data;
            for (mach_msg_type_number_t i = 0; i+99 < dc; i++) {
                if (b[i]=='x' && b[i+1]=='\'' && b[i+98]=='\'') {
                    int ok = 1;
                    for (int j = 2; j < 98; j++) if (!is_hex(b[i+j])) { ok=0; break; }
                    if (!ok) continue;
                    char k[97]; memcpy(k, b+i+2, 96); k[96]=0;
                    int dup = 0;
                    for (int d = 0; d < nkeys; d++) if (!strcmp(keys[d],k)) { dup=1; break; }
                    if (!dup && nkeys < 512) {
                        memcpy(keys[nkeys], k, 97); nkeys++;
                        fprintf(stderr, "INFO:Found key #%d\n", nkeys);
                    }
                }
            }
            mach_vm_deallocate(mach_task_self(), data, dc);
        }
        addr += rsize;
    }
    for (int i = 0; i < nkeys; i++) printf("KEY:%s\n", keys[i]);
    fprintf(stderr, "INFO:Done, %d key(s)\n", nkeys);
    return nkeys > 0 ? 0 : 1;
}
"""

_HELPER_NAME = "wx_key_extract"


def _helper_path() -> str:
    return os.path.join(tempfile.gettempdir(), _HELPER_NAME)


def compile_helper() -> str:
    """Compile the C helper binary. Returns the path to the binary."""
    src = _helper_path() + ".c"
    out = _helper_path()
    with open(src, "w") as f:
        f.write(_C_SOURCE)
    r = subprocess.run(
        ["cc", "-O2", "-o", out, src],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"Compilation failed:\n{r.stderr}")
    os.chmod(out, 0o755)
    return out


def extract_keys(progress_cb=None) -> list[str]:
    """Extract all candidate 96-hex-char keys from WeChat memory.

    Requires admin privileges — shows a macOS password dialog.
    Returns a list of 96-char hex strings.
    """
    def _report(msg):
        if progress_cb:
            progress_cb(msg)

    _report("正在编译密钥提取工具…")
    helper = compile_helper()

    _report("正在提取密钥（需要管理员权限）…")
    escaped = helper.replace('"', '\\"')
    r = subprocess.run(
        [
            "osascript", "-e",
            f'do shell script "{escaped}" with administrator privileges',
        ],
        capture_output=True, text=True, timeout=120,
    )

    keys: list[str] = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("KEY:") and len(line) == 100:
            keys.append(line[4:])

    if not keys:
        err = r.stderr.strip() if r.stderr else "未知错误"
        raise RuntimeError(
            f"未能提取到密钥。\n{err}\n\n"
            "可能原因：\n"
            "1. 微信未在运行\n"
            "2. 需要关闭 SIP（系统完整性保护）\n"
            "3. 密码输入取消\n\n"
            "关闭 SIP 方法：重启按住电源键 → 恢复模式 → 终端 → csrutil disable"
        )

    _report(f"提取到 {len(keys)} 个候选密钥")
    return keys


def match_key_to_db(key_hex_96: str, db_path: str) -> bool:
    """Check if a key's salt matches a database file's salt (first 16 bytes)."""
    key_salt = key_hex_96[64:].lower()
    try:
        with open(db_path, "rb") as f:
            file_salt = f.read(16).hex().lower()
        return key_salt == file_salt
    except OSError:
        return False


def get_encryption_key(keys: list[str]) -> str:
    """All keys for one account share the same first 64 hex chars (the AES key).
    Returns the common 64-char encryption key."""
    prefixes = {k[:64].lower() for k in keys}
    if len(prefixes) == 1:
        return prefixes.pop()
    return max(prefixes, key=lambda p: sum(1 for k in keys if k[:64].lower() == p))


def build_full_key(enc_key_64: str, db_path: str) -> str | None:
    """Construct the full 96-char key for a specific database by reading its salt."""
    try:
        with open(db_path, "rb") as f:
            salt = f.read(16).hex().lower()
        return enc_key_64.lower() + salt
    except OSError:
        return None
