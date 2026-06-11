"""Dark modern theme: color palette and application stylesheet."""

# ---- Palette ----------------------------------------------------------------
BG_MAIN = "#15181e"          # window background
BG_PANEL = "#1d222a"         # sidebar / panel background
BG_PANEL_LIGHT = "#262c36"   # raised elements (buttons, rows)
BG_PANEL_HOVER = "#2f3742"
BORDER = "#333b47"

TEXT = "#d7dde6"
TEXT_MUTED = "#8b95a5"
TEXT_DIM = "#5d6675"

ACCENT = "#46b1e1"           # primary accent (blue)
ACCENT_DARK = "#2d7ea6"
GOOD = "#2dd4a0"             # teal-green (best move, white winning)
WARN = "#e8c468"
BAD = "#e06c75"

# Board colors (muted blue-grey, lichess-like, fits the dark UI)
SQ_LIGHT = "#dee3e6"
SQ_DARK = "#8ca2ad"
SQ_LAST_MOVE = "#9bc700"     # blended with alpha when drawn
SQ_SELECTED = "#46b1e1"
SQ_CHECK = "#e06c75"

# Suggestion arrow colors by rank (best → third)
ARROW_COLORS = ["#2dd4a0", "#46b1e1", "#c084fc"]

EVALBAR_WHITE = "#e8eaed"
EVALBAR_BLACK = "#2a2e36"


def build_stylesheet() -> str:
    return f"""
QWidget {{
    background-color: {BG_MAIN};
    color: {TEXT};
    font-size: 13px;
}}
QMainWindow, QDialog {{
    background-color: {BG_MAIN};
}}

/* ---- Panels ---- */
QFrame#SidePanel {{
    background-color: {BG_PANEL};
    border-radius: 10px;
}}
QFrame#Card {{
    background-color: {BG_PANEL};
    border-radius: 10px;
}}
QLabel#SectionTitle {{
    color: {TEXT_MUTED};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    background: transparent;
}}
QLabel#StatusLabel {{
    color: {TEXT};
    font-size: 14px;
    font-weight: 600;
    background: transparent;
}}
QLabel#SubtleLabel {{
    color: {TEXT_MUTED};
    background: transparent;
}}
QLabel {{
    background: transparent;
}}

/* ---- Buttons ---- */
QPushButton {{
    background-color: {BG_PANEL_LIGHT};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 7px 12px;
    color: {TEXT};
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {BG_PANEL_HOVER};
    border-color: {ACCENT_DARK};
}}
QPushButton:pressed {{
    background-color: {BG_PANEL};
}}
QPushButton:disabled {{
    color: {TEXT_DIM};
    background-color: {BG_PANEL};
    border-color: {BORDER};
}}
QPushButton#PrimaryButton {{
    background-color: {ACCENT_DARK};
    border: 1px solid {ACCENT};
    color: #ffffff;
}}
QPushButton#PrimaryButton:hover {{
    background-color: {ACCENT};
}}
QToolButton {{
    background-color: {BG_PANEL_LIGHT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 9px;
    color: {TEXT};
    font-weight: 600;
}}
QToolButton:hover {{
    background-color: {BG_PANEL_HOVER};
    border-color: {ACCENT_DARK};
}}
QToolButton:pressed, QToolButton:checked {{
    background-color: {ACCENT_DARK};
    color: #ffffff;
}}
QToolButton:disabled {{
    color: {TEXT_DIM};
}}

/* ---- Combo box ---- */
QComboBox {{
    background-color: {BG_PANEL_LIGHT};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 5px 10px;
    color: {TEXT};
}}
QComboBox:hover {{
    border-color: {ACCENT_DARK};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_MUTED};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_PANEL_LIGHT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {ACCENT_DARK};
    selection-color: #ffffff;
    outline: none;
}}

/* ---- Slider ---- */
QSlider::groove:horizontal {{
    height: 5px;
    background: {BG_PANEL_LIGHT};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT_DARK};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{
    background: #6cc6ec;
}}

/* ---- Checkbox ---- */
QCheckBox {{
    color: {TEXT};
    spacing: 8px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background-color: {BG_PANEL_LIGHT};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT_DARK};
    border-color: {ACCENT};
    image: none;
}}

/* ---- Table (move list) ---- */
QTableWidget {{
    background-color: {BG_PANEL};
    border: none;
    gridline-color: transparent;
    outline: none;
}}
QTableWidget::item {{
    padding: 3px 6px;
    border-radius: 4px;
}}
QTableWidget::item:selected {{
    background-color: {ACCENT_DARK};
    color: #ffffff;
}}
QHeaderView::section {{
    background-color: {BG_PANEL};
    color: {TEXT_MUTED};
    border: none;
    padding: 4px;
}}
QTableCornerButton::section {{
    background-color: {BG_PANEL};
    border: none;
}}

/* ---- Scrollbars ---- */
QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BG_PANEL_HOVER};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TEXT_DIM};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 9px;
}}
QScrollBar::handle:horizontal {{
    background: {BG_PANEL_HOVER};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ---- Menu ---- */
QMenuBar {{
    background-color: {BG_MAIN};
    color: {TEXT};
}}
QMenuBar::item {{
    padding: 5px 10px;
    background: transparent;
}}
QMenuBar::item:selected {{
    background: {BG_PANEL_LIGHT};
    border-radius: 5px;
}}
QMenu {{
    background-color: {BG_PANEL_LIGHT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 5px;
}}
QMenu::item {{
    padding: 6px 24px 6px 16px;
    border-radius: 5px;
}}
QMenu::item:selected {{
    background-color: {ACCENT_DARK};
    color: #ffffff;
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 5px 8px;
}}

/* ---- Tabs ---- */
QTabWidget::pane {{
    border: none;
    background: {BG_MAIN};
}}
QTabBar {{
    background: {BG_MAIN};
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 9px 18px;
    margin: 4px 2px 0 6px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    color: {TEXT};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT};
}}

/* ---- Tree (opening browser) ---- */
QTreeWidget {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
    outline: none;
    padding: 4px;
}}
QTreeWidget::item {{
    padding: 4px 2px;
    border-radius: 4px;
    color: {TEXT};
}}
QTreeWidget::item:hover {{
    background-color: {BG_PANEL_HOVER};
}}
QTreeWidget::item:selected {{
    background-color: {ACCENT_DARK};
    color: #ffffff;
}}
QTreeView::branch {{
    background: transparent;
}}

/* ---- Line edit (search) ---- */
QLineEdit {{
    background-color: {BG_PANEL_LIGHT};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 7px 10px;
    color: {TEXT};
}}
QLineEdit:focus {{
    border-color: {ACCENT_DARK};
}}

/* ---- Splitter ---- */
QSplitter::handle {{
    background: transparent;
}}
QSplitter::handle:horizontal {{
    width: 10px;
}}
QSplitter::handle:hover {{
    background: {BG_PANEL_LIGHT};
    border-radius: 4px;
}}

/* ---- Scroll area ---- */
QScrollArea {{
    background: transparent;
    border: none;
}}

/* ---- Tooltip ---- */
QToolTip {{
    background-color: {BG_PANEL_LIGHT};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 5px;
}}

/* ---- Message boxes / dialogs ---- */
QMessageBox {{
    background-color: {BG_PANEL};
}}
"""
