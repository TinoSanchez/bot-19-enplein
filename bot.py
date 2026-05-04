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

from database import Player, PlayerDB, PointDB, PointEntry
from point_seed_list import normalize_point_key

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
            await interaction.response.send_message("La liste est vide.")
            return
        lines = [
            f"**{p.discord_username}** — Gamdom: `{p.gamdom_username}` — KYC: `{p.kyc_level}` — ID Discord: `{p.discord_id}`"
            for p in players
        ]
        text = "\n".join(lines)
        if len(text) <= 3900:
            await interaction.response.send_message(text)
            return
        await interaction.response.defer()
        chunk_size = 3800
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            if i == 0:
                await interaction.followup.send(chunk)
            else:
                await interaction.followup.send(chunk)


def _point_embed(p: PointEntry) -> discord.Embed:
    e = discord.Embed(title="Fiche points", color=0x57F287)
    e.add_field(name="Joueur", value=p.display_name, inline=True)
    e.add_field(name="Clé", value=f"`{p.player_key}`", inline=True)
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
        cle="Identifiant unique (ex: gaylord, sans espaces)",
        nom_affichage="Nom affiché",
        points_rajouter="Points à rajouter (référence)",
        total="Total actuel (défaut 0)",
    )
    async def point_ajouter(
        self,
        interaction: discord.Interaction,
        cle: str,
        nom_affichage: str,
        points_rajouter: int,
        total: int = 0,
    ) -> None:
        key = normalize_point_key(cle)
        if not key:
            await interaction.response.send_message("Clé invalide.", ephemeral=True)
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

    @point.command(name="modifier", description="Mettre à jour les points d’un joueur (par clé)")
    @app_commands.describe(
        cle="Clé du joueur (ex: gaylord)",
        nom_affichage="Nouveau nom affiché",
        points_rajouter="Nouvelle valeur « points à rajouter »",
        total="Nouveau total",
    )
    async def point_modifier(
        self,
        interaction: discord.Interaction,
        cle: str,
        nom_affichage: Optional[str] = None,
        points_rajouter: Optional[int] = None,
        total: Optional[int] = None,
    ) -> None:
        key = normalize_point_key(cle)
        if not key:
            await interaction.response.send_message("Clé invalide.", ephemeral=True)
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
            await interaction.response.send_message(
                "Aucun joueur avec cette clé.", ephemeral=True
            )
            return
        p = point_db.get(key)
        assert p is not None
        await interaction.response.send_message(embed=_point_embed(p))

    @point.command(name="supprimer", description="Retirer un joueur du système de points")
    @app_commands.describe(cle="Clé du joueur")
    async def point_supprimer(self, interaction: discord.Interaction, cle: str) -> None:
        key = normalize_point_key(cle)
        if not point_db.delete(key):
            await interaction.response.send_message(
                "Aucun joueur avec cette clé.", ephemeral=True
            )
            return
        await interaction.response.send_message(f"Joueur supprimé (`{key}`).")

    @point.command(name="fiche", description="Afficher la fiche points d’un joueur")
    @app_commands.describe(cle="Clé du joueur (ex: gaylord)")
    async def point_fiche(self, interaction: discord.Interaction, cle: str) -> None:
        key = normalize_point_key(cle)
        p = point_db.get(key)
        if not p:
            await interaction.response.send_message(
                "Aucun joueur avec cette clé.", ephemeral=True
            )
            return
        await interaction.response.send_message(embed=_point_embed(p))

    @point.command(name="liste", description="Lister tous les joueurs et leurs points")
    async def point_liste(self, interaction: discord.Interaction) -> None:
        rows = point_db.list_all()
        if not rows:
            await interaction.response.send_message("La liste est vide.")
            return
        lines = [
            f"**{p.display_name}** — +{p.points_rajouter} pts (réf.) — **total: {p.total}** — `{p.player_key}`"
            for p in rows
        ]
        text = "\n".join(lines)
        if len(text) <= 3900:
            await interaction.response.send_message(text)
            return
        await interaction.response.defer()
        chunk_size = 3800
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            if i == 0:
                await interaction.followup.send(chunk)
            else:
                await interaction.followup.send(chunk)


class Bot19(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self) -> None:
        await self.add_cog(AffiCog(self))
        await self.add_cog(PointCog(self))
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
