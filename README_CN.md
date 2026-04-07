# 微信聊天记录导出工具

一款 macOS 桌面工具，用于解密、浏览和导出微信本地存储的聊天记录。

![Platform](https://img.shields.io/badge/平台-macOS-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

[English](README.md)

## 下载安装

**[v1.0.0 正式版](https://github.com/YueGod/webchat_chat_history_export/releases/tag/v1.0.0)** — 已打包的 macOS 应用，下载即用：

| 文件 | 说明 |
|---|---|
| [微信聊天记录查看器-1.0.0.dmg](https://github.com/YueGod/webchat_chat_history_export/releases/download/v1.0.0/微信聊天记录查看器-1.0.0.dmg) | macOS 应用安装包（arm64），双击安装 |
| Source code (zip / tar.gz) | 源码版本，需 Python 环境运行 |

> DMG 版本无需安装 Python，打开 `.dmg` 后将应用拖入「应用程序」文件夹即可使用。

## 概述

Mac 版微信将聊天消息存储在 SQLCipher 加密的 SQLite 数据库中。本工具实现了完整的自动化流程——从微信进程内存中提取加密密钥、解密数据库，到提供完整的聊天记录浏览器和 CSV 导出功能。

### 核心功能

- **一键解密** — 通过 macOS Mach API 自动从运行中的微信进程提取 AES 密钥，使用 SQLCipher 解密全部消息数据库。
- **自动检测账号** — 同时扫描旧版（`com.tencent.xinWeChat`）和新版微信 4.x（`xwechat_files/wxid_*`）的数据目录。
- **聊天浏览器** — 深色主题 UI，支持会话列表、消息气泡、日期筛选和分页浏览。
- **CSV 导出** — 支持导出单个会话或一键导出全部会话为 CSV 文件（UTF-8 with BOM，Excel 兼容）。
- **多消息类型** — 展示文本、图片、语音、视频、表情、位置、链接/文件、名片、语音/视频通话、系统消息和撤回消息。
- **解密缓存** — 已解密的数据库缓存在 `~/.wx-chathistory/decrypted/`，再次启动时无需重复解密。

## 项目结构

```
main.py                   # 入口文件 — 启动 pywebview 窗口
app/
├── api.py                # Python ↔ JS 桥接层（pywebview js_api）
├── models.py             # 数据模型：Contact, Message, Conversation
├── db_reader.py          # 解密后数据库的 SQLite 读取器
├── decryptor.py          # SQLCipher 解密逻辑
├── key_extract.py        # 内存扫描 C 辅助程序，提取 AES 密钥
├── csv_exporter.py       # CSV 导出工具
└── web/
    ├── index.html        # 前端页面
    ├── style.css         # 深色主题样式
    ├── app.js            # 前端交互逻辑
    └── icon.png          # 应用图标
build_mac.sh              # PyInstaller 构建脚本，生成 .app / .dmg
```

### 工作原理

1. **密钥提取** — 运行时编译一个 C 辅助程序，以管理员权限执行。通过 `mach_vm_region` / `mach_vm_read` 遍历微信进程的虚拟内存区域，搜索 96 字符十六进制密钥模式（`x'...'`）。
2. **盐值匹配** — 每个密钥的后 32 个十六进制字符是数据库特有的盐值（salt）。工具将盐值与每个加密 `.db` 文件的前 16 字节进行匹配。
3. **解密** — 匹配成功的数据库通过 `sqlcipher` 命令行工具，使用 `PRAGMA key` 和 `sqlcipher_export` 进行解密。
4. **读取** — `DatabaseReader` 加载联系人、群聊信息，并扫描所有解密数据库中的 `Chat_*` / `Msg_*` 消息表。WCDB zstd 压缩的内容会自动解压。

## 环境要求

| 要求 | 说明 |
|---|---|
| **macOS** | 仅支持 macOS（使用 Mach API 和微信 Mac 版数据路径） |
| **Python 3.10+** | 需要类型注解语法支持（`X \| None`） |
| **Mac 版微信** | 需要已安装并至少登录过一次 |
| **关闭 SIP** | 内存密钥提取需要关闭系统完整性保护 |
| **sqlcipher** | 会通过 Homebrew 自动安装，也可手动执行 `brew install sqlcipher` |

### 关闭 SIP（系统完整性保护）

密钥提取需要读取微信进程内存，该操作被 SIP 阻止：

1. 重启 Mac，按住电源键进入恢复模式。
2. 从「实用工具」菜单打开**终端**。
3. 执行 `csrutil disable`，然后重启。

## 快速开始

```bash
# 克隆仓库
git clone git@github.com:YueGod/webchat_chat_history_export.git
cd webchat_chat_history_export

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 确保微信正在运行，然后启动工具
python main.py
```

## 使用方法

1. **启动** — 应用会在启动时自动检测微信账号。
2. **解密** — 如果检测到加密数据库，点击 **「一键解密」**，在弹出的对话框中输入管理员密码。
3. **浏览** — 从左侧边栏选择会话，使用日期范围筛选器缩小查看范围。
4. **导出** — 点击 **「导出 CSV」** 保存当前会话，或点击 **「全部导出」** 导出所有会话。

## 构建 macOS 应用

```bash
# 仅构建 .app
./build_mac.sh

# 构建 .app + .dmg 安装包
./build_mac.sh --dmg
```

构建产物位于 `dist/` 目录下。

## 依赖说明

| 包名 | 用途 |
|---|---|
| [pywebview](https://pywebview.flowrl.com/) | 原生桌面窗口，内嵌 Web UI |
| [zstandard](https://github.com/indygreg/python-zstandard) | 解压 WCDB zstd 压缩的消息内容 |
| [PyInstaller](https://pyinstaller.org/) | 打包为独立的 macOS `.app` 应用 |

运行时依赖（自动安装）：

| 工具 | 用途 |
|---|---|
| [sqlcipher](https://github.com/nickel-mern/sqlcipher) | 解密 SQLCipher v4 数据库 |

## 已知限制

- **仅限 macOS** — 密钥提取和数据路径逻辑为 macOS 专用。
- **需要关闭 SIP** — 读取进程内存的前提条件。
- **微信必须在运行** — 密钥从运行中的进程内存提取。
- **不导出媒体文件** — 仅提取文本内容和元数据，图片/视频/语音以占位符形式显示。

## 许可证

MIT
