"""Persistance SQLite pour la liste des joueurs Gamdom / Discord."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

from point_seed_list import POINT_INITIAL
from rank_seed_list import RANK_INITIAL, VALID_TIERS, tier_default_eur
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


@dataclass(frozen=True)
class PointEntry:
    player_key: str
    display_name: str
    points_rajouter: int
    total: int


class PointDB:
    """Table `point_players` dans le même fichier SQLite que les affiliés."""

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
                CREATE TABLE IF NOT EXISTS point_players (
                    player_key TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    points_rajouter INTEGER NOT NULL,
                    total INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.commit()
            conn.close()

    def add(self, entry: PointEntry) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO point_players (player_key, display_name, points_rajouter, total)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        entry.player_key,
                        entry.display_name,
                        entry.points_rajouter,
                        entry.total,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def update(
        self,
        player_key: str,
        *,
        display_name: Optional[str] = None,
        points_rajouter: Optional[int] = None,
        total: Optional[int] = None,
    ) -> bool:
        fields: dict[str, Any] = {}
        if display_name is not None and str(display_name).strip():
            fields["display_name"] = str(display_name).strip()
        if points_rajouter is not None:
            fields["points_rajouter"] = int(points_rajouter)
        if total is not None:
            fields["total"] = int(total)
        if not fields:
            return False
        cols = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [player_key]
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    f"UPDATE point_players SET {cols} WHERE player_key = ?",
                    values,
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def delete(self, player_key: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM point_players WHERE player_key = ?", (player_key,))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def get(self, player_key: str) -> Optional[PointEntry]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT player_key, display_name, points_rajouter, total FROM point_players WHERE player_key = ?",
                    (player_key,),
                ).fetchone()
            finally:
                conn.close()
        if row is None:
            return None
        return PointEntry(
            player_key=row["player_key"],
            display_name=row["display_name"],
            points_rajouter=int(row["points_rajouter"]),
            total=int(row["total"]),
        )

    def list_all(self) -> List[PointEntry]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT player_key, display_name, points_rajouter, total FROM point_players ORDER BY display_name COLLATE NOCASE"
                ).fetchall()
            finally:
                conn.close()
        return [
            PointEntry(
                player_key=r["player_key"],
                display_name=r["display_name"],
                points_rajouter=int(r["points_rajouter"]),
                total=int(r["total"]),
            )
            for r in rows
        ]

    def seed_points_if_empty(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                n = int(conn.execute("SELECT COUNT(*) FROM point_players").fetchone()[0])
                if n > 0:
                    return
                for key, display, bonus in POINT_INITIAL:
                    conn.execute(
                        """
                        INSERT INTO point_players (player_key, display_name, points_rajouter, total)
                        VALUES (?, ?, ?, ?)
                        """,
                        (key, display, bonus, 0),
                    )
                conn.commit()
            finally:
                conn.close()


@dataclass(frozen=True)
class RankEntry:
    player_key: str
    display_name: str
    tier: str
    montant_eur: int


class RankDB:
    """Table `rank_players` — rang Bronze / Argent / Gold / Emeraude."""

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
                CREATE TABLE IF NOT EXISTS rank_players (
                    player_key TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    montant_eur INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            try:
                conn.execute(
                    "ALTER TABLE rank_players ADD COLUMN montant_eur INTEGER NOT NULL DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass
            conn.commit()
            conn.close()

    def add(self, entry: RankEntry) -> None:
        if entry.tier not in VALID_TIERS:
            raise ValueError(f"tier invalide: {entry.tier}")
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO rank_players (player_key, display_name, tier, montant_eur)
                    VALUES (?, ?, ?, ?)
                    """,
                    (entry.player_key, entry.display_name, entry.tier, entry.montant_eur),
                )
                conn.commit()
            finally:
                conn.close()

    def update(
        self,
        player_key: str,
        *,
        display_name: Optional[str] = None,
        tier: Optional[str] = None,
        montant_eur: Optional[int] = None,
    ) -> bool:
        fields: dict[str, Any] = {}
        if display_name is not None and str(display_name).strip():
            fields["display_name"] = str(display_name).strip()
        if tier is not None:
            t = str(tier).strip().lower()
            if t not in VALID_TIERS:
                raise ValueError(f"tier invalide: {tier}")
            fields["tier"] = t
        if montant_eur is not None:
            fields["montant_eur"] = int(montant_eur)
        if not fields:
            return False
        cols = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [player_key]
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    f"UPDATE rank_players SET {cols} WHERE player_key = ?",
                    values,
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def delete(self, player_key: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM rank_players WHERE player_key = ?", (player_key,))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def get(self, player_key: str) -> Optional[RankEntry]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT player_key, display_name, tier, montant_eur FROM rank_players WHERE player_key = ?",
                    (player_key,),
                ).fetchone()
            finally:
                conn.close()
        if row is None:
            return None
        return RankEntry(
            player_key=row["player_key"],
            display_name=row["display_name"],
            tier=row["tier"],
            montant_eur=int(row["montant_eur"]),
        )

    def list_all(self) -> List[RankEntry]:
        order_sql = (
            "CASE tier "
            "WHEN 'emeraude' THEN 4 WHEN 'gold' THEN 3 WHEN 'argent' THEN 2 "
            "WHEN 'bronze' THEN 1 ELSE 0 END DESC, display_name COLLATE NOCASE"
        )
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    f"SELECT player_key, display_name, tier, montant_eur FROM rank_players ORDER BY {order_sql}"
                ).fetchall()
            finally:
                conn.close()
        return [
            RankEntry(
                player_key=r["player_key"],
                display_name=r["display_name"],
                tier=r["tier"],
                montant_eur=int(r["montant_eur"]),
            )
            for r in rows
        ]

    def seed_ranks_if_empty(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                n = int(conn.execute("SELECT COUNT(*) FROM rank_players").fetchone()[0])
                if n > 0:
                    return
                for key, display, tier in RANK_INITIAL:
                    if tier not in VALID_TIERS:
                        continue
                    conn.execute(
                        """
                        INSERT INTO rank_players (player_key, display_name, tier, montant_eur)
                        VALUES (?, ?, ?, ?)
                        """,
                        (key, display, tier, tier_default_eur(tier)),
                    )
                conn.commit()
            finally:
                conn.close()


@dataclass(frozen=True)
class GiveawayRecord:
    id: str
    guild_id: int
    channel_id: int
    message_id: int
    template_key: str
    amount_eur: int
    winner_count: int
    ends_at: float
    participants: List[int]
    ended: bool


class GiveawayDB:
    """Giveaways actifs / terminés (boutons persistants par `id`)."""

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
                CREATE TABLE IF NOT EXISTS giveaways (
                    id TEXT PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    template_key TEXT NOT NULL,
                    amount_eur INTEGER NOT NULL,
                    winner_count INTEGER NOT NULL,
                    ends_at REAL NOT NULL,
                    participants TEXT NOT NULL DEFAULT '[]',
                    ended INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.commit()
            conn.close()

    def create(
        self,
        gid: str,
        *,
        guild_id: int,
        channel_id: int,
        message_id: int,
        template_key: str,
        amount_eur: int,
        winner_count: int,
        ends_at: float,
    ) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO giveaways (
                        id, guild_id, channel_id, message_id, template_key,
                        amount_eur, winner_count, ends_at, participants, ended
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, '[]', 0)
                    """,
                    (
                        gid,
                        guild_id,
                        channel_id,
                        message_id,
                        template_key,
                        amount_eur,
                        winner_count,
                        ends_at,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get(self, gid: str) -> Optional[GiveawayRecord]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    """
                    SELECT id, guild_id, channel_id, message_id, template_key,
                           amount_eur, winner_count, ends_at, participants, ended
                    FROM giveaways WHERE id = ?
                    """,
                    (gid,),
                ).fetchone()
            finally:
                conn.close()
        if row is None:
            return None
        parts = json.loads(row["participants"] or "[]")
        pid_list = [int(x) for x in parts]
        return GiveawayRecord(
            id=row["id"],
            guild_id=int(row["guild_id"]),
            channel_id=int(row["channel_id"]),
            message_id=int(row["message_id"]),
            template_key=row["template_key"],
            amount_eur=int(row["amount_eur"]),
            winner_count=int(row["winner_count"]),
            ends_at=float(row["ends_at"]),
            participants=pid_list,
            ended=bool(row["ended"]),
        )

    def add_participant(self, gid: str, user_id: int) -> Tuple[bool, int]:
        """Ajoute un participant. Retourne (nouveau?, nombre total)."""
        import time

        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT participants, ended, ends_at FROM giveaways WHERE id = ?",
                    (gid,),
                ).fetchone()
                if row is None:
                    return False, 0
                if row["ended"]:
                    return False, len(json.loads(row["participants"] or "[]"))
                if float(row["ends_at"]) <= time.time():
                    return False, len(json.loads(row["participants"] or "[]"))
                parts = json.loads(row["participants"] or "[]")
                uid_str = str(user_id)
                ids = [str(x) for x in parts]
                if uid_str in ids:
                    n = len(ids)
                    return False, n
                parts.append(user_id)
                conn.execute(
                    "UPDATE giveaways SET participants = ? WHERE id = ?",
                    (json.dumps(parts), gid),
                )
                conn.commit()
                return True, len(parts)
            finally:
                conn.close()

    def mark_ended(self, gid: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "UPDATE giveaways SET ended = 1 WHERE id = ? AND ended = 0",
                    (gid,),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def list_unfinished(self) -> List[GiveawayRecord]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT id, guild_id, channel_id, message_id, template_key,
                           amount_eur, winner_count, ends_at, participants, ended
                    FROM giveaways WHERE ended = 0
                    """
                ).fetchall()
            finally:
                conn.close()
        out: List[GiveawayRecord] = []
        for row in rows:
            parts = json.loads(row["participants"] or "[]")
            out.append(
                GiveawayRecord(
                    id=row["id"],
                    guild_id=int(row["guild_id"]),
                    channel_id=int(row["channel_id"]),
                    message_id=int(row["message_id"]),
                    template_key=row["template_key"],
                    amount_eur=int(row["amount_eur"]),
                    winner_count=int(row["winner_count"]),
                    ends_at=float(row["ends_at"]),
                    participants=[int(x) for x in parts],
                    ended=bool(row["ended"]),
                )
            )
        return out
