"""
Bot Discord — gestion liste joueurs (Discord + Gamdom + KYC) pour 19enplein.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from database import Player, PlayerDB, PointDB, PointEntry, RankDB, RankEntry
from point_seed_list import normalize_point_key
from rank_seed_list import tier_label

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID_RAW = os.getenv("GUILD_ID")
GUILD_ID = int(GUILD_ID_RAW) if GUILD_ID_RAW and GUILD_ID_RAW.isdigit() else None

ROOT = Path(__file__).resolve().parent
_db_override = os.getenv("PLAYERS_DB_PATH")
DB_PATH = Path(_db_override).resolve() if _db_override else ROOT / "players.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

intents = discord.Intents.default()

db = PlayerDB(DB_PATH)
db.seed_if_empty()

point_db = PointDB(DB_PATH)
point_db.seed_points_if_empty()

rank_db = RankDB(DB_PATH)
rank_db.seed_ranks_if_empty()


def _resolve_point_key(raw: str) -> Optional[str]:
    """Trouve le joueur par pseudo affiché ou par nom normalisé (ex. kane, Kane)."""
    s = (raw or "").strip()
    if not s:
        return None
    k = normalize_point_key(s)
    if point_db.get(k):
        return k
    for p in point_db.list_all():
        if normalize_point_key(p.display_name) == k or p.display_name.lower() == s.lower():
            return p.player_key
    return None


def _resolve_rank_key(raw: str) -> Optional[str]:
    """Trouve le joueur rank par pseudo affiché ou nom court (ex. Onizuka, oni)."""
    s = (raw or "").strip()
    if not s:
        return None
    k = normalize_point_key(s)
    if rank_db.get(k):
        return k
    for r in rank_db.list_all():
        if normalize_point_key(r.display_name) == k or r.display_name.lower() == s.lower():
            return r.player_key
    return None


# Limite Discord pour le contenu d’un message texte (pas 3900).
_DISCORD_TEXT_LIMIT = 2000

_RANK_CHOICES = [
    app_commands.Choice(name="— Aucun", value="none"),
    app_commands.Choice(name="Bronze 15€", value="bronze"),
    app_commands.Choice(name="Argent 30€", value="argent"),
    app_commands.Choice(name="Gold 50€", value="gold"),
    app_commands.Choice(name="Emeraude 100€", value="emeraude"),
]


async def _defer_send_list_text(
    interaction: discord.Interaction,
    text: str,
    empty_msg: str,
) -> None:
    """Après defer(), envoie le texte en morceaux respectant la limite Discord."""
    await interaction.response.defer()
    try:
        if not text.strip():
            await interaction.followup.send(empty_msg)
            return
        for i in range(0, len(text), _DISCORD_TEXT_LIMIT):
            chunk = text[i : i + _DISCORD_TEXT_LIMIT]
            await interaction.followup.send(chunk)
    except Exception as e:
        try:
            await interaction.followup.send(
                f"Erreur lors de l’envoi : `{e}`", ephemeral=True
            )
        except Exception:
            pass


def _player_embed(p: Player) -> discord.Embed:
    e = discord.Embed(title="Fiche joueur", color=0x5865F2)
    e.add_field(name="Pseudo Discord", value=p.discord_username, inline=True)
    e.add_field(name="ID Discord", value=p.discord_id, inline=True)
    e.add_field(name="\u200b", value="\u200b", inline=False)
    e.add_field(name="Pseudo Gamdom", value=p.gamdom_username, inline=True)
    e.add_field(name="ID Gamdom", value=p.gamdom_id, inline=True)
    e.add_field(name="Niveau KYC", value=p.kyc_level, inline=True)
    return e


class AffiCog(commands.Cog):
    affi = app_commands.Group(
        name="affi", description="Gérer la liste des affiliés (Gamdom / KYC)"
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @affi.command(name="ajouter", description="Ajouter un affilié à la liste")
    @app_commands.describe(
        pseudo_discord="Pseudo Discord (affichage)",
        id_discord="ID Discord du membre (chiffres)",
        pseudo_gamdom="Pseudo sur Gamdom",
        id_gamdom="Identifiant Gamdom",
        niveau_kyc="Niveau de vérification KYC (ex. 0, 1, 2…)",
    )
    async def affi_ajouter(
        self,
        interaction: discord.Interaction,
        pseudo_discord: str,
        id_discord: str,
        pseudo_gamdom: str,
        id_gamdom: str,
        niveau_kyc: str,
    ) -> None:
        id_discord = id_discord.strip()
        if not id_discord.isdigit():
            await interaction.response.send_message(
                "L’ID Discord doit contenir uniquement des chiffres.", ephemeral=True
            )
            return
        if db.get(id_discord):
            await interaction.response.send_message(
                "Ce joueur existe déjà (même ID Discord). Utilise `/affi modifier`.",
                ephemeral=True,
            )
            return
        player = Player(
            discord_id=id_discord,
            discord_username=pseudo_discord.strip(),
            gamdom_username=pseudo_gamdom.strip(),
            gamdom_id=id_gamdom.strip(),
            kyc_level=niveau_kyc.strip(),
        )
        try:
            db.add(player)
        except sqlite3.IntegrityError:
            await interaction.response.send_message(
                "Ce joueur existe déjà (ID Discord déjà enregistré).", ephemeral=True
            )
            return
        await interaction.response.send_message(embed=_player_embed(player))

    @affi.command(name="modifier", description="Mettre à jour un affilié (par ID Discord)")
    @app_commands.describe(
        id_discord="ID Discord du joueur à modifier",
        pseudo_discord="Nouveau pseudo Discord (laisser vide pour ne pas changer)",
        pseudo_gamdom="Nouveau pseudo Gamdom",
        id_gamdom="Nouvel ID Gamdom",
        niveau_kyc="Nouveau niveau KYC",
    )
    async def affi_modifier(
        self,
        interaction: discord.Interaction,
        id_discord: str,
        pseudo_discord: Optional[str] = None,
        pseudo_gamdom: Optional[str] = None,
        id_gamdom: Optional[str] = None,
        niveau_kyc: Optional[str] = None,
    ) -> None:
        id_discord = id_discord.strip()
        if not id_discord.isdigit():
            await interaction.response.send_message("ID Discord invalide.", ephemeral=True)
            return
        kwargs: Dict[str, str] = {}
        if pseudo_discord is not None and pseudo_discord.strip():
            kwargs["discord_username"] = pseudo_discord.strip()
        if pseudo_gamdom is not None and pseudo_gamdom.strip():
            kwargs["gamdom_username"] = pseudo_gamdom.strip()
        if id_gamdom is not None and id_gamdom.strip():
            kwargs["gamdom_id"] = id_gamdom.strip()
        if niveau_kyc is not None and niveau_kyc.strip():
            kwargs["kyc_level"] = niveau_kyc.strip()
        if not kwargs:
            await interaction.response.send_message(
                "Indique au moins un champ à modifier.", ephemeral=True
            )
            return
        if not db.update(id_discord, **kwargs):
            await interaction.response.send_message(
                "Aucun joueur avec cet ID Discord.", ephemeral=True
            )
            return
        p = db.get(id_discord)
        assert p is not None
        await interaction.response.send_message(embed=_player_embed(p))

    @affi.command(name="supprimer", description="Retirer un affilié de la liste")
    @app_commands.describe(id_discord="ID Discord du joueur à supprimer")
    async def affi_supprimer(self, interaction: discord.Interaction, id_discord: str) -> None:
        id_discord = id_discord.strip()
        if not id_discord.isdigit():
            await interaction.response.send_message("ID Discord invalide.", ephemeral=True)
            return
        if not db.delete(id_discord):
            await interaction.response.send_message(
                "Aucun joueur avec cet ID Discord.", ephemeral=True
            )
            return
        await interaction.response.send_message(f"Joueur supprimé (`{id_discord}`).")

    @affi.command(name="fiche", description="Afficher la fiche d’un affilié")
    @app_commands.describe(id_discord="ID Discord du joueur")
    async def affi_fiche(self, interaction: discord.Interaction, id_discord: str) -> None:
        id_discord = id_discord.strip()
        p = db.get(id_discord)
        if not p:
            await interaction.response.send_message(
                "Aucun joueur avec cet ID Discord.", ephemeral=True
            )
            return
        await interaction.response.send_message(embed=_player_embed(p))

    @affi.command(name="liste", description="Lister tous les affiliés enregistrés")
    async def affi_liste(self, interaction: discord.Interaction) -> None:
        players = db.list_all()
        if not players:
            await interaction.response.defer()
            await interaction.followup.send("La liste est vide.")
            return
        def _id_gamdom_aff(p: Player) -> str:
            g = (p.gamdom_id or "").strip()
            return g if g and g != "0" else "—"

        lines = [
            f"**{p.discord_username}** — Gamdom: `{p.gamdom_username}` — ID Gamdom: `{_id_gamdom_aff(p)}` — KYC: `{p.kyc_level}`"
            for p in players
        ]
        text = "\n".join(lines)
        await _defer_send_list_text(interaction, text, "La liste est vide.")


def _point_embed(p: PointEntry) -> discord.Embed:
    e = discord.Embed(title="Fiche points", color=0x57F287)
    e.add_field(name="Joueur", value=p.display_name, inline=True)
    e.add_field(name="\u200b", value="\u200b", inline=False)
    e.add_field(name="Points à rajouter", value=str(p.points_rajouter), inline=True)
    e.add_field(name="Total", value=str(p.total), inline=True)
    return e


class PointCog(commands.Cog):
    point = app_commands.Group(
        name="point", description="Gérer les points (liste stream / classement)"
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @point.command(name="ajouter", description="Ajouter un joueur dans le système de points")
    @app_commands.describe(
        joueur="Pseudo du joueur (sera aussi la référence interne, ex. gaylord)",
        nom_affichage="Nom affiché",
        points_rajouter="Points à rajouter (référence)",
        total="Total actuel (défaut 0)",
    )
    async def point_ajouter(
        self,
        interaction: discord.Interaction,
        joueur: str,
        nom_affichage: str,
        points_rajouter: int,
        total: int = 0,
    ) -> None:
        key = normalize_point_key(joueur)
        if not key:
            await interaction.response.send_message("Pseudo invalide.", ephemeral=True)
            return
        if point_db.get(key):
            await interaction.response.send_message(
                "Ce joueur existe déjà. Utilise `/point modifier`.", ephemeral=True
            )
            return
        entry = PointEntry(
            player_key=key,
            display_name=nom_affichage.strip(),
            points_rajouter=int(points_rajouter),
            total=int(total),
        )
        try:
            point_db.add(entry)
        except sqlite3.IntegrityError:
            await interaction.response.send_message(
                "Ce joueur existe déjà.", ephemeral=True
            )
            return
        await interaction.response.send_message(embed=_point_embed(entry))

    @point.command(name="modifier", description="Mettre à jour les points d’un joueur")
    @app_commands.describe(
        joueur="Pseudo du joueur (comme dans la liste)",
        nom_affichage="Nouveau nom affiché",
        points_rajouter="Nouvelle valeur « points à rajouter »",
        total="Nouveau total",
    )
    async def point_modifier(
        self,
        interaction: discord.Interaction,
        joueur: str,
        nom_affichage: Optional[str] = None,
        points_rajouter: Optional[int] = None,
        total: Optional[int] = None,
    ) -> None:
        key = _resolve_point_key(joueur)
        if not key:
            await interaction.response.send_message(
                "Joueur introuvable. Utilise le même pseudo que dans `/point liste`.",
                ephemeral=True,
            )
            return
        kwargs: Dict[str, Any] = {}
        if nom_affichage is not None and nom_affichage.strip():
            kwargs["display_name"] = nom_affichage.strip()
        if points_rajouter is not None:
            kwargs["points_rajouter"] = points_rajouter
        if total is not None:
            kwargs["total"] = total
        if not kwargs:
            await interaction.response.send_message(
                "Indique au moins un champ à modifier.", ephemeral=True
            )
            return
        if not point_db.update(key, **kwargs):
            await interaction.response.send_message("Joueur introuvable.", ephemeral=True)
            return
        p = point_db.get(key)
        assert p is not None
        await interaction.response.send_message(embed=_point_embed(p))

    @point.command(name="supprimer", description="Retirer un joueur du système de points")
    @app_commands.describe(joueur="Pseudo du joueur")
    async def point_supprimer(self, interaction: discord.Interaction, joueur: str) -> None:
        key = _resolve_point_key(joueur)
        if not key or not point_db.delete(key):
            await interaction.response.send_message(
                "Joueur introuvable.", ephemeral=True
            )
            return
        await interaction.response.send_message(f"Joueur supprimé ({joueur.strip()}).")

    @point.command(name="fiche", description="Afficher la fiche points d’un joueur")
    @app_commands.describe(joueur="Pseudo du joueur (ex: gaylord, Picsou)")
    async def point_fiche(self, interaction: discord.Interaction, joueur: str) -> None:
        key = _resolve_point_key(joueur)
        p = point_db.get(key) if key else None
        if not p:
            await interaction.response.send_message(
                "Joueur introuvable.", ephemeral=True
            )
            return
        await interaction.response.send_message(embed=_point_embed(p))

    @point.command(name="liste", description="Lister tous les joueurs et leurs points")
    async def point_liste(self, interaction: discord.Interaction) -> None:
        rows = point_db.list_all()
        if not rows:
            await interaction.response.defer()
            await interaction.followup.send("La liste est vide.")
            return
        lines = [
            f"**{p.display_name}** — +{p.points_rajouter} pts (réf.) — **total: {p.total}**"
            for p in rows
        ]
        text = "\n".join(lines)
        await _defer_send_list_text(interaction, text, "La liste est vide.")


def _rank_embed(r: RankEntry) -> discord.Embed:
    e = discord.Embed(title="Fiche rang", color=0xF1C40F)
    e.add_field(name="Joueur", value=r.display_name, inline=True)
    e.add_field(name="Statut", value=tier_label(r.tier), inline=True)
    e.add_field(name="Montant", value=f"{r.montant_eur} €", inline=True)
    return e


class RankCog(commands.Cog):
    rank = app_commands.Group(
        name="rank", description="Rangs Bronze / Argent / Gold / Emeraude"
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @rank.command(name="ajouter", description="Ajouter un joueur dans la liste des rangs")
    @app_commands.describe(
        joueur="Pseudo du joueur (référence, ex: kane, Kane)",
        nom_affichage="Nom affiché sur la fiche",
        rang="Statut le plus haut (Bronze, Gold…)",
        montant_euros="Montant en euros (défaut 0)",
    )
    @app_commands.choices(rang=_RANK_CHOICES)
    async def rank_ajouter(
        self,
        interaction: discord.Interaction,
        joueur: str,
        nom_affichage: str,
        rang: str,
        montant_euros: int = 0,
    ) -> None:
        key = normalize_point_key(joueur)
        if not key:
            await interaction.response.send_message("Pseudo invalide.", ephemeral=True)
            return
        if rank_db.get(key):
            await interaction.response.send_message(
                "Ce joueur existe déjà. Utilise `/rank modifier`.", ephemeral=True
            )
            return
        entry = RankEntry(
            player_key=key,
            display_name=nom_affichage.strip(),
            tier=rang,
            montant_eur=int(montant_euros),
        )
        try:
            rank_db.add(entry)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        except sqlite3.IntegrityError:
            await interaction.response.send_message("Ce joueur existe déjà.", ephemeral=True)
            return
        await interaction.response.send_message(embed=_rank_embed(entry))

    @rank.command(name="rang", description="Changer uniquement le rang (statut) d’un joueur")
    @app_commands.describe(
        joueur="Pseudo du joueur (ex: Kane, Onizuka)",
        statut="Nouveau rang : Bronze, Argent, Gold, Emeraude…",
    )
    @app_commands.choices(statut=_RANK_CHOICES)
    async def rank_rang(
        self,
        interaction: discord.Interaction,
        joueur: str,
        statut: str,
    ) -> None:
        key = _resolve_rank_key(joueur)
        if not key:
            await interaction.response.send_message(
                "Joueur introuvable. Essaie le pseudo affiché dans `/rank liste`.",
                ephemeral=True,
            )
            return
        try:
            ok = rank_db.update(key, tier=statut)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        if not ok:
            await interaction.response.send_message("Joueur introuvable.", ephemeral=True)
            return
        r = rank_db.get(key)
        assert r is not None
        await interaction.response.send_message(embed=_rank_embed(r))

    @rank.command(name="modifier", description="Mettre à jour rang, montant € ou nom affiché")
    @app_commands.describe(
        joueur="Pseudo du joueur (ex: Kane, kane, Onizuka)",
        rang="Nouveau rang / statut (Bronze, Gold…)",
        nom_affichage="Nouveau nom affiché",
        montant_euros="Nouveau montant en euros",
    )
    @app_commands.choices(rang=_RANK_CHOICES)
    async def rank_modifier(
        self,
        interaction: discord.Interaction,
        joueur: str,
        rang: Optional[str] = None,
        nom_affichage: Optional[str] = None,
        montant_euros: Optional[int] = None,
    ) -> None:
        key = _resolve_rank_key(joueur)
        if not key:
            await interaction.response.send_message(
                "Joueur introuvable. Essaie le pseudo affiché dans `/rank liste` (ex. Kane, Onizuka).",
                ephemeral=True,
            )
            return
        kwargs: Dict[str, Any] = {}
        if nom_affichage is not None and nom_affichage.strip():
            kwargs["display_name"] = nom_affichage.strip()
        if rang is not None:
            kwargs["tier"] = rang
        if montant_euros is not None:
            kwargs["montant_eur"] = montant_euros
        if not kwargs:
            await interaction.response.send_message(
                "Indique au moins un champ à modifier.", ephemeral=True
            )
            return
        try:
            ok = rank_db.update(key, **kwargs)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        if not ok:
            await interaction.response.send_message("Joueur introuvable.", ephemeral=True)
            return
        r = rank_db.get(key)
        assert r is not None
        await interaction.response.send_message(embed=_rank_embed(r))

    @rank.command(name="supprimer", description="Retirer un joueur de la liste des rangs")
    @app_commands.describe(joueur="Pseudo du joueur")
    async def rank_supprimer(self, interaction: discord.Interaction, joueur: str) -> None:
        key = _resolve_rank_key(joueur)
        if not key or not rank_db.delete(key):
            await interaction.response.send_message(
                "Joueur introuvable.", ephemeral=True
            )
            return
        await interaction.response.send_message(f"Joueur supprimé ({joueur.strip()}).")

    @rank.command(name="fiche", description="Afficher le rang d’un joueur")
    @app_commands.describe(joueur="Pseudo du joueur (ex: Kane, Onizuka)")
    async def rank_fiche(self, interaction: discord.Interaction, joueur: str) -> None:
        key = _resolve_rank_key(joueur)
        r = rank_db.get(key) if key else None
        if not r:
            await interaction.response.send_message(
                "Joueur introuvable.", ephemeral=True
            )
            return
        await interaction.response.send_message(embed=_rank_embed(r))

    @rank.command(name="liste", description="Lister tous les rangs")
    async def rank_liste(self, interaction: discord.Interaction) -> None:
        rows = rank_db.list_all()
        if not rows:
            await interaction.response.defer()
            await interaction.followup.send("La liste est vide.")
            return
        lines = [
            f"**{r.display_name}** — {tier_label(r.tier)} — **{r.montant_eur} €**"
            for r in rows
        ]
        text = "\n".join(lines)
        await _defer_send_list_text(interaction, text, "La liste est vide.")


class Bot19(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self) -> None:
        await self.add_cog(AffiCog(self))
        await self.add_cog(PointCog(self))
        await self.add_cog(RankCog(self))
        if GUILD_ID:
            await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        else:
            await self.tree.sync()


async def main() -> None:
    if not TOKEN:
        print("Définis DISCORD_TOKEN dans un fichier .env (voir .env.example).", file=sys.stderr)
        sys.exit(1)
    bot = Bot19()

    @bot.event
    async def on_ready() -> None:
        print(f"Connecté en tant que {bot.user} ({bot.user.id if bot.user else '?'})")

    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
