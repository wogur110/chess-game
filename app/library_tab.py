"""Library tab: your archived games plus cross-game mistake insights.

Finished games land here automatically (GameController.gameFinished ->
GameLibrary.auto_save); reviews feed the MistakeLog. The insights panel
answers the question a coach would ask after flipping through your
scoresheets: "what do you keep getting wrong?"
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton,
                               QSplitter, QVBoxLayout, QWidget)

from . import APP_NAME
from .eval_utils import MOVE_LABELS
from .game_library import GameLibrary
from .i18n import tr
from .insights import PHASE_LABELS, TAG_LABELS, MistakeLog


class LibraryTab(QWidget):
    openRequested = Signal(str)   # path of the game to open in the Play tab

    def __init__(self, library: GameLibrary, log: MistakeLog,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.library = library
        self.log = log

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(0)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        root.addWidget(splitter)

        # Left: archived games
        games_panel = QWidget()
        games_layout = QVBoxLayout(games_panel)
        games_layout.setContentsMargins(0, 0, 0, 0)
        games_layout.setSpacing(8)
        title = QLabel(tr("GAMES"))
        title.setObjectName("SectionTitle")
        games_layout.addWidget(title)
        self.games_list = QListWidget()
        self.games_list.itemDoubleClicked.connect(self._on_open)
        games_layout.addWidget(self.games_list, 1)
        self.games_label = QLabel("")
        self.games_label.setObjectName("SubtleLabel")
        self.games_label.setWordWrap(True)
        games_layout.addWidget(self.games_label)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.open_button = QPushButton(tr("Open in Play tab"))
        self.open_button.setObjectName("PrimaryButton")
        self.open_button.clicked.connect(self._on_open)
        buttons.addWidget(self.open_button)
        self.delete_button = QPushButton(tr("Delete"))
        self.delete_button.clicked.connect(self._on_delete)
        buttons.addWidget(self.delete_button)
        games_layout.addLayout(buttons)
        splitter.addWidget(games_panel)

        # Right: cross-game insights
        insights_panel = QWidget()
        insights_layout = QVBoxLayout(insights_panel)
        insights_layout.setContentsMargins(16, 0, 0, 0)
        insights_layout.setSpacing(9)
        insights_title = QLabel(tr("TRAINING INSIGHTS"))
        insights_title.setObjectName("SectionTitle")
        insights_layout.addWidget(insights_title)
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("StatusLabel")
        self.summary_label.setWordWrap(True)
        insights_layout.addWidget(self.summary_label)
        self.insight_label = QLabel("")
        self.insight_label.setWordWrap(True)
        self.insight_label.setStyleSheet("font-weight: 600;")
        insights_layout.addWidget(self.insight_label)
        self.detail_label = QLabel("")
        self.detail_label.setObjectName("SubtleLabel")
        self.detail_label.setWordWrap(True)
        self.detail_label.setTextFormat(Qt.RichText)
        insights_layout.addWidget(self.detail_label)
        insights_layout.addStretch(1)
        splitter.addWidget(insights_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([560, 480])

        self.refresh()

    # ---- refresh ----

    def refresh(self):
        self.refresh_games()
        self.refresh_insights()

    def refresh_games(self):
        self.games_list.clear()
        entries = self.library.list_games()
        for entry in entries:
            parts = [entry.date or "?", f"{entry.white} — {entry.black}",
                     entry.result]
            if entry.plies:
                parts.append(tr("{n} plies", n=entry.plies))
            if entry.opening:
                parts.append(entry.opening)
            item = QListWidgetItem("  ·  ".join(parts))
            item.setData(Qt.UserRole, str(entry.path))
            self.games_list.addItem(item)
        has_games = bool(entries)
        self.open_button.setEnabled(has_games)
        self.delete_button.setEnabled(has_games)
        self.games_label.setText(
            tr("{n} archived game(s)", n=len(entries)) if has_games else
            tr("No games yet — finished games are saved here automatically."))

    def refresh_insights(self):
        summary = self.log.summary()
        if summary["total"] == 0:
            self.summary_label.setText(tr(
                "No insights yet — play and analyze games; your recurring "
                "mistake patterns will show up here."))
            self.insight_label.setText("")
            self.detail_label.setText("")
            return
        categories = "   ".join(
            f"{tr(MOVE_LABELS.get(key, key))} {count}"
            for key, count in sorted(summary["by_category"].items(),
                                     key=lambda kv: -kv[1]))
        self.summary_label.setText(
            tr("{total} analyzed mistakes — {categories}",
               total=summary["total"], categories=categories))

        top_tag = max(summary["by_tag"].items(), key=lambda kv: kv[1],
                      default=None)
        top_phase = max(summary["by_phase"].items(), key=lambda kv: kv[1],
                        default=None)
        if top_tag and top_phase:
            self.insight_label.setText(
                tr("Most common pattern: {tag} ({count}×), mostly in the "
                   "{phase}.",
                   tag=tr(TAG_LABELS.get(top_tag[0], top_tag[0])),
                   count=top_tag[1],
                   phase=tr(PHASE_LABELS.get(top_phase[0], top_phase[0]))))

        lines = [tr("By phase:") + " " + "   ".join(
            f"{tr(PHASE_LABELS.get(key, key))} {count}"
            for key, count in sorted(summary["by_phase"].items(),
                                     key=lambda kv: -kv[1]))]
        lines.append(tr("By pattern:"))
        for key, label in TAG_LABELS.items():
            count = summary["by_tag"].get(key)
            if count:
                lines.append(f"&nbsp;&nbsp;{tr(label)} — {count}")
        self.detail_label.setText("<br>".join(lines))

    # ---- actions ----

    def _selected_path(self) -> Optional[str]:
        item = self.games_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _on_open(self, *_args):
        path = self._selected_path()
        if path:
            self.openRequested.emit(path)

    def _on_delete(self):
        path = self._selected_path()
        if not path:
            return
        answer = QMessageBox.question(
            self, APP_NAME, tr("Delete this game from the library?"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self.library.delete(path)
        self.refresh_games()
