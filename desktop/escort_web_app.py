"""Offline Windows window for the local escort ledger."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import webview

from desktop.escort_data import LocalEscortStore


def ui_path() -> Path:
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS) / "ui" / "index.html"
    return Path(__file__).parent / "ui" / "index.html"


class DesktopApi:
    def __init__(self):
        self.store = LocalEscortStore()
        self._window = None

    def get_state(self, selected_day: str = "") -> dict:
        days = self.store.days()
        selected_day = selected_day if selected_day in days else days[0] if days else date.today().isoformat()
        game_dir = self.store.setting("game_dir", r"D:\asktao")
        chat = Path(game_dir)
        if chat.name.lower() != "chat":
            chat = chat / "chat"
        return {
            "game_dir": game_dir,
            "chat_dir": str(chat),
            "chat_exists": chat.is_dir(),
            "auto_scan": self.store.setting("auto_scan") == "1",
            "days": days,
            "selected_day": selected_day,
            "day": self.store.day(selected_day) if selected_day in days else None,
            "history": self.store.history(),
        }

    def choose_directory(self) -> str | None:
        current = Path(self.store.setting("game_dir", r"D:\asktao"))
        paths = self._window.create_file_dialog(
            webview.FOLDER_DIALOG,
            directory=str(current if current.is_dir() else Path.home()),
        )
        return paths[0] if paths else None

    def save_settings(self, game_dir: str, auto_scan: bool) -> dict:
        game_dir = game_dir.strip()
        if not game_dir:
            raise ValueError("请输入游戏目录")
        self.store.set_setting("game_dir", game_dir)
        self.store.set_setting("auto_scan", "1" if auto_scan else "0")
        return self.get_state()

    def scan(self, game_dir: str) -> dict:
        game_dir = game_dir.strip()
        if not game_dir:
            raise ValueError("请输入游戏目录")
        self.store.set_setting("game_dir", game_dir)
        result = self.store.scan(Path(game_dir))
        return {
            "scan": {
                "scanned": result.scanned,
                "saved": result.saved,
                "skipped": result.skipped,
                "warnings": result.warnings,
            },
            "state": self.get_state(result.dates[0] if result.dates else ""),
        }

    def set_role(self, source_key: str, role_id: int, selected_day: str, team_id: str) -> dict:
        self.store.set_role(source_key, int(role_id), selected_day, team_id)
        return self.get_state(selected_day)


def main():
    api = DesktopApi()
    window = webview.create_window(
        "押镖账本", ui_path().as_uri(), js_api=api,
        width=1160, height=810, min_size=(860, 640),
        background_color="#eef3f1", text_select=True,
    )
    api._window = window
    webview.start(gui="edgechromium")


if __name__ == "__main__":
    main()
