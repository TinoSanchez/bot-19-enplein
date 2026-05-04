"""Persistance SQLite pour la liste des joueurs Gamdom / Discord."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from seed_list import INITIAL_ROWS, SYNTH_DISCORD_BASE


def _normalize_kyc(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s in ("oui", "yes", "o", "vrai"):
        return "Oui"
    if not s:
        return "—"
    return raw.strip() if raw.strip() else "—"


@dataclass(frozen=True)
class Player:
    discord_id: str
    discord_username: str
    gamdom_username: str
    gamdom_id: str
    kyc_level: str


class PlayerDB:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._lock = threading.Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS players (
                    discord_id TEXT PRIMARY KEY,
                    discord_username TEXT NOT NULL,
                    gamdom_username TEXT NOT NULL,
                    gamdom_id TEXT NOT NULL,
                    kyc_level TEXT NOT NULL
                )
                """
            )
            conn.commit()
            conn.close()

    def add(self, player: Player) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO players (discord_id, discord_username, gamdom_username, gamdom_id, kyc_level)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        player.discord_id,
                        player.discord_username,
                        player.gamdom_username,
                        player.gamdom_id,
                        player.kyc_level,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def update(self, discord_id: str, **fields: str) -> bool:
        allowed = {"discord_username", "gamdom_username", "gamdom_id", "kyc_level"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return False
        cols = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [discord_id]
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    f"UPDATE players SET {cols} WHERE discord_id = ?",
                    values,
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def delete(self, discord_id: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM players WHERE discord_id = ?", (discord_id,))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def get(self, discord_id: str) -> Optional[Player]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT discord_id, discord_username, gamdom_username, gamdom_id, kyc_level FROM players WHERE discord_id = ?",
                    (discord_id,),
                ).fetchone()
            finally:
                conn.close()
        if row is None:
            return None
        return Player(
            discord_id=row["discord_id"],
            discord_username=row["discord_username"],
            gamdom_username=row["gamdom_username"],
            gamdom_id=row["gamdom_id"],
            kyc_level=row["kyc_level"],
        )

    def list_all(self) -> List[Player]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT discord_id, discord_username, gamdom_username, gamdom_id, kyc_level FROM players ORDER BY discord_username COLLATE NOCASE"
                ).fetchall()
            finally:
                conn.close()
        return [
            Player(
                discord_id=r["discord_id"],
                discord_username=r["discord_username"],
                gamdom_username=r["gamdom_username"],
                gamdom_id=r["gamdom_id"],
                kyc_level=r["kyc_level"],
            )
            for r in rows
        ]

    def count_players(self) -> int:
        with self._lock:
            conn = self._connect()
            try:
                return int(conn.execute("SELECT COUNT(*) FROM players").fetchone()[0])
            finally:
                conn.close()

    def seed_if_empty(self) -> None:
        """Insère la liste initiale une seule fois si la table est vide."""
        with self._lock:
            conn = self._connect()
            try:
                n = int(conn.execute("SELECT COUNT(*) FROM players").fetchone()[0])
                if n > 0:
                    return
                for i, (nom, user_name, gamdom_id, kyc_raw) in enumerate(INITIAL_ROWS):
                    discord_id = str(SYNTH_DISCORD_BASE + i)
                    g_user = user_name.strip() if user_name.strip() else nom.strip()
                    g_id = gamdom_id.strip() if gamdom_id.strip() else "0"
                    conn.execute(
                        """
                        INSERT INTO players (discord_id, discord_username, gamdom_username, gamdom_id, kyc_level)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            discord_id,
                            nom.strip(),
                            g_user,
                            g_id,
                            _normalize_kyc(kyc_raw),
                        ),
                    )
                conn.commit()
            finally:
                conn.close()
