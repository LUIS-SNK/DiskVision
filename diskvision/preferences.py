import os
import sqlite3
from pathlib import Path

from PySide6.QtCore import QStandardPaths


class Preferences:
    def __init__(self):
        local = os.environ.get("LOCALAPPDATA")
        path = (Path(local) / "DiskVision" if local else
                Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)))
        path.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path / "diskvision.sqlite3")
        with self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            self.db.execute("""CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY, time TEXT DEFAULT CURRENT_TIMESTAMP,
                operation TEXT NOT NULL, detail TEXT NOT NULL)""")

    def theme(self):
        row = self.db.execute("SELECT value FROM settings WHERE key='theme'").fetchone()
        return row[0] if row else "Escuro"

    def save_theme(self, theme):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO settings VALUES ('theme', ?)", (theme,))

    def record(self, operation, detail):
        with self.db:
            self.db.execute("INSERT INTO history(operation, detail) VALUES (?, ?)", (operation, detail))

    def recent(self):
        return self.db.execute("SELECT time, operation, detail FROM history ORDER BY id DESC LIMIT 20").fetchall()
