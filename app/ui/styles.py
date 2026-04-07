"""Notion-inspired design system for WeChat Chat Viewer."""

# Palette
_BG          = "#FFFFFF"
_BG_WARM     = "#F7F6F3"
_BG_HOVER    = "#F1F1EF"
_BG_ACTIVE   = "#E8E7E4"
_TEXT         = "#37352F"
_TEXT_SEC     = "#787774"
_TEXT_TER     = "#ACABA9"
_BORDER       = "#E9E9E7"
_ACCENT       = "#2EAADC"
_ACCENT_HOVER = "#238EAF"
_PRIMARY      = "#37352F"
_GREEN        = "#0F7B6C"
_GREEN_BG     = "#DBEDDB"
_RED_TEXT      = "#EB5757"

STYLESHEET = f"""
/* ===================================================
   Global  –  Fusion style; palette handles defaults.
   Only set font here, NOT color (palette does that).
   =================================================== */
QMainWindow {{
    background-color: {_BG};
}}
QWidget {{
    font-family: -apple-system, "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 13px;
}}
QToolTip {{
    background-color: {_PRIMARY};
    color: #FFFFFF;
    border: none;
    padding: 5px 8px;
    font-size: 12px;
}}

/* ===================================================
   Menus  –  explicit light bg + dark text
   =================================================== */
QMenuBar {{
    background-color: {_BG};
    color: {_TEXT};
    border-bottom: 1px solid {_BORDER};
}}
QMenuBar::item:selected {{
    background-color: {_BG_HOVER};
}}
QMenu {{
    background-color: {_BG};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    padding: 4px 0;
}}
QMenu::item {{
    padding: 5px 28px 5px 20px;
}}
QMenu::item:selected {{
    background-color: {_ACCENT};
    color: #FFFFFF;
}}
QMenu::separator {{
    height: 1px;
    background-color: {_BORDER};
    margin: 4px 12px;
}}

/* ===================================================
   Splitter handle
   =================================================== */
QSplitter::handle {{
    background-color: {_BORDER};
    width: 1px;
}}

/* ===================================================
   Sidebar  –  warm light bg, dark text
   =================================================== */
#sidebar {{
    background-color: {_BG_WARM};
    border: none;
}}

#sidebarTitle {{
    font-size: 13px;
    font-weight: 700;
    color: {_TEXT_SEC};
    padding: 0;
}}

/* Primary CTA — dark fill, WHITE text */
#primaryBtn {{
    background-color: {_PRIMARY};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 8px 0;
    font-size: 13px;
    font-weight: 600;
}}
#primaryBtn:hover {{
    background-color: #4B4A48;
    color: #FFFFFF;
}}
#primaryBtn:pressed {{
    background-color: #2D2C2A;
    color: #FFFFFF;
}}
#primaryBtn:disabled {{
    background-color: {_TEXT_TER};
    color: #FFFFFF;
}}

/* Secondary — ghost, light bg, dark text */
#secondaryBtn {{
    background-color: {_BG};
    color: {_TEXT_SEC};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 7px 0;
    font-size: 13px;
}}
#secondaryBtn:hover {{
    background-color: {_BG_HOVER};
    color: {_TEXT};
}}
#secondaryBtn:pressed {{
    background-color: {_BG_ACTIVE};
    color: {_TEXT};
}}

/* Search — white bg, dark text */
#searchInput {{
    background-color: {_BG};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 7px 10px;
    font-size: 13px;
    color: {_TEXT};
}}
#searchInput:focus {{
    border-color: {_ACCENT};
}}

/* Conversation list — transparent bg, dark text */
#convList {{
    background-color: transparent;
    color: {_TEXT};
    border: none;
    outline: none;
}}
#convList::item {{
    padding: 10px 12px;
    border-radius: 6px;
    margin: 1px 4px;
    color: {_TEXT};
}}
#convList::item:selected {{
    background-color: {_BG_ACTIVE};
    color: {_TEXT};
}}
#convList::item:hover:!selected {{
    background-color: {_BG_HOVER};
    color: {_TEXT};
}}

/* ===================================================
   Right pane — white bg, dark text
   =================================================== */
#rightPane {{
    background-color: {_BG};
    color: {_TEXT};
}}

#chatHeader {{
    background-color: {_BG};
    border-bottom: 1px solid {_BORDER};
    min-height: 46px;
}}

#convTitle {{
    font-size: 15px;
    font-weight: 600;
    color: {_TEXT};
}}

#convSubtitle {{
    font-size: 12px;
    color: {_TEXT_TER};
    padding-left: 8px;
}}

/* Filter bar — warm bg, dark text */
#filterBar {{
    background-color: {_BG_WARM};
    color: {_TEXT};
    border-bottom: 1px solid {_BORDER};
}}

#filterLabel {{
    font-size: 12px;
    color: {_TEXT_SEC};
}}

QDateEdit {{
    background-color: {_BG};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
    color: {_TEXT};
    min-width: 106px;
}}
QDateEdit:focus {{
    border-color: {_ACCENT};
}}
QDateEdit::drop-down {{
    border: none;
    width: 20px;
}}

/* Calendar popup — explicit light */
QCalendarWidget {{
    background-color: {_BG};
    color: {_TEXT};
}}
QCalendarWidget QAbstractItemView {{
    background-color: {_BG};
    color: {_TEXT};
    selection-background-color: {_ACCENT};
    selection-color: #FFFFFF;
}}
QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background-color: {_BG_WARM};
    color: {_TEXT};
}}
QCalendarWidget QToolButton {{
    background-color: {_BG};
    color: {_TEXT};
    border: none;
    padding: 4px 8px;
}}
QCalendarWidget QToolButton:hover {{
    background-color: {_BG_HOVER};
}}

#filterBtn {{
    background-color: {_BG};
    color: {_TEXT_SEC};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    padding: 4px 14px;
    font-size: 12px;
}}
#filterBtn:hover {{
    background-color: {_BG_HOVER};
    color: {_TEXT};
}}

#exportBtn {{
    background-color: {_BG};
    color: {_ACCENT};
    border: 1px solid {_ACCENT};
    border-radius: 4px;
    padding: 4px 14px;
    font-size: 12px;
    font-weight: 600;
}}
#exportBtn:hover {{
    background-color: #EBF5FB;
    color: {_ACCENT_HOVER};
}}

/* Chat browser — warm bg */
#chatBrowser {{
    background-color: {_BG_WARM};
    color: {_TEXT};
    border: none;
    font-size: 14px;
    selection-background-color: #B4D5FE;
    selection-color: {_TEXT};
}}

/* Page bar — white bg */
#pageBar {{
    background-color: {_BG};
    border-top: 1px solid {_BORDER};
}}
#pageLabel {{
    font-size: 12px;
    color: {_TEXT_TER};
}}
#pageBtn {{
    background-color: {_BG};
    color: {_TEXT_SEC};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    padding: 3px 12px;
    font-size: 12px;
}}
#pageBtn:hover {{
    background-color: {_BG_HOVER};
    color: {_TEXT};
}}
#pageBtn:disabled {{
    background-color: {_BG};
    color: {_TEXT_TER};
    border-color: {_BG_HOVER};
}}

/* ===================================================
   Scrollbars — subtle
   =================================================== */
QScrollBar:vertical {{
    background-color: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background-color: #D1D1CF;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {_TEXT_TER};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

/* ===================================================
   Status bar — white bg
   =================================================== */
QStatusBar {{
    background-color: {_BG};
    color: {_TEXT_TER};
    font-size: 11px;
    border-top: 1px solid {_BORDER};
    padding: 2px 8px;
}}
QStatusBar QLabel {{
    color: {_TEXT_TER};
}}

/* ===================================================
   Dialogs — explicit light
   =================================================== */
QMessageBox, QInputDialog {{
    background-color: {_BG};
    color: {_TEXT};
}}
QMessageBox QLabel, QInputDialog QLabel {{
    color: {_TEXT};
}}
"""

CHAT_HTML_CSS = f"""
body {{
    background-color: {_BG_WARM};
    margin: 0;
    padding: 16px 12px;
    font-family: -apple-system, "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 14px;
    color: {_TEXT};
    line-height: 1.5;
}}
.date-sep {{
    color: {_TEXT_TER};
    font-size: 11px;
    margin: 20px 0 12px 0;
}}
.date-sep-inner {{
    background-color: {_BG_ACTIVE};
    padding: 3px 12px;
}}
.sys {{
    color: {_TEXT_TER};
    font-size: 12px;
    margin: 6px 0;
}}
.msg-row {{
    margin: 3px 0;
}}
.bubble-sent {{
    background-color: #D3E5EF;
    padding: 8px 14px;
    font-size: 14px;
    color: {_TEXT};
}}
.bubble-recv {{
    background-color: #FFFFFF;
    padding: 8px 14px;
    font-size: 14px;
    color: {_TEXT};
}}
.time-r {{
    color: {_TEXT_TER};
    font-size: 11px;
}}
.time-l {{
    color: {_TEXT_TER};
    font-size: 11px;
}}
.sender-name {{
    color: {_ACCENT};
    font-size: 12px;
    font-weight: 500;
}}
.empty {{
    color: {_TEXT_TER};
    font-size: 14px;
    margin-top: 80px;
}}

.info-title {{
    color: {_TEXT};
    font-size: 18px;
    font-weight: 600;
    margin-top: 60px;
}}
.info-body {{
    color: {_TEXT_SEC};
    font-size: 13px;
    line-height: 2.0;
    margin-top: 12px;
}}
.info-hint {{
    color: {_TEXT_TER};
    font-size: 12px;
    margin-top: 20px;
}}
"""
