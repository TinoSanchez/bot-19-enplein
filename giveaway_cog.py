"""
Giveaways : message avec bouton « Participer », templates prédéfinis, tirage à la fin.
"""

from __future__ import annotations

import asyncio
import random
import re
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from database import GiveawayDB, PlayerDB
from giveaway_templates import (
    TEMPLATES,
    build_embed_fields,
    build_result_fields,
    footer_participants,
    template_defaults,
)

_TEMPLATE_CHOICES = [
    app_commands.Choice(name=str(v["choice_name"]), value=k)
    for k, v in TEMPLATES.items()
]
_BANNER_FILENAME = "giveaway_banner.png"
_EXTERNAL_BANNER_PATH = Path(
    r"C:\Users\mathi\.cursor\projects\c-Users-mathi-Desktop-bot-19\assets\c__Users_mathi_AppData_Roaming_Cursor_User_workspaceStorage_f7a4a39b924895bde9b0e1a5b57b7e8b_images_image-f8dba5a9-067f-4e18-b8a9-a187b5b5ffa9.png"
)
_LOCAL_BANNER_PATH = Path(__file__).resolve().parent / "assets" / "19enplein_logo.png"


class GiveawayParticipateButton(discord.ui.Button):
    def __init__(self, giveaway_id: str) -> None:
        super().__init__(
            label="Participer",
            style=discord.ButtonStyle.success,
            emoji="🎁",
            custom_id=f"gwy:{giveaway_id}",
        )
        self.giveaway_id = giveaway_id

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = interaction.client.get_cog("GiveawayCog")
        if cog is None:
            await interaction.response.send_message(
                "Giveaway indisponible.", ephemeral=True
            )
            return
        await cog.handle_participate(interaction, self.giveaway_id)


def build_giveaway_view(giveaway_id: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(GiveawayParticipateButton(giveaway_id))
    return view


class GiveawayCog(commands.Cog):
    """Slash `/win` + boutons persistants."""

    def __init__(self, bot: commands.Bot, db_path: Path) -> None:
        self.bot = bot
        self.db = GiveawayDB(db_path)
        self.player_db = PlayerDB(db_path)

    @staticmethod
    def _banner_path() -> Optional[Path]:
        """Retourne le chemin de bannière disponible (image fournie puis fallback local)."""
        if _EXTERNAL_BANNER_PATH.is_file():
            return _EXTERNAL_BANNER_PATH
        if _LOCAL_BANNER_PATH.is_file():
            return _LOCAL_BANNER_PATH
        return None

    @staticmethod
    def _attach_banner(embed: discord.Embed) -> None:
        embed.set_image(url=f"attachment://{_BANNER_FILENAME}")

    async def cog_load(self) -> None:
        for rec in self.db.list_unfinished():
            self.bot.add_view(build_giveaway_view(rec.id))
            remaining = rec.ends_at - time.time()
            if remaining > 0:
                asyncio.create_task(self._sleep_and_finalize(rec.id, remaining))
            else:
                asyncio.create_task(self._finalize_giveaway(rec.id))

    async def _sleep_and_finalize(self, gid: str, delay: float) -> None:
        await asyncio.sleep(delay)
        await self._finalize_giveaway(gid)

    @staticmethod
    def _parse_mentioned_user_ids(raw: str) -> List[int]:
        """Extrait les IDs depuis des mentions Discord: <@123> ou <@!123>."""
        if not raw:
            return []
        ids = re.findall(r"<@!?(\d+)>", raw)
        return [int(x) for x in ids]

    async def _resolve_forced_winners(
        self, guild: Optional[discord.Guild], raw: str
    ) -> Tuple[List[int], List[str], List[str]]:
        """
        Résout les gagnants forcés via mentions, IDs ou pseudo.
        Retourne: (ids résolus, introuvables, ambigus)
        """
        if not raw:
            return [], [], []

        # Mentions/IDs explicites
        ids: List[int] = self._parse_mentioned_user_ids(raw)

        cleaned = re.sub(r"<@!?\d+>", " ", raw)
        tokens = [
            t.strip()
            for t in re.split(r"[,\n;]+", cleaned)
            if t and t.strip()
        ]

        # Index des pseudos connus (serveur + base players)
        name_to_ids: Dict[str, Set[int]] = {}

        def _add_name(name: Optional[str], uid: int) -> None:
            if not name:
                return
            key = str(name).strip().lower()
            if not key:
                return
            bucket = name_to_ids.setdefault(key, set())
            bucket.add(int(uid))

        if guild:
            for m in guild.members:
                _add_name(m.name, m.id)
                _add_name(m.display_name, m.id)
                _add_name(getattr(m, "global_name", None), m.id)

        for p in self.player_db.list_all():
            if p.discord_id.isdigit():
                _add_name(p.discord_username, int(p.discord_id))

        unknown: List[str] = []
        ambiguous: List[str] = []
        for tok in tokens:
            if tok.isdigit():
                ids.append(int(tok))
                continue
            key = tok.lower()
            candidates = sorted(name_to_ids.get(key, set()))
            if len(candidates) == 1:
                ids.append(candidates[0])
            elif len(candidates) == 0:
                unknown.append(tok)
            else:
                ambiguous.append(tok)

        # Unicité + ordre de saisie
        unique_ids = list(dict.fromkeys(ids))
        return unique_ids, unknown, ambiguous

    @staticmethod
    def _pick_random_role_members(role: Optional[discord.Role], count: int) -> List[int]:
        """Tire au sort `count` membres (non-bots) ayant le rôle donné."""
        if role is None or count <= 0:
            return []
        candidates = [m.id for m in role.members if not m.bot]
        if not candidates:
            return []
        k = min(count, len(candidates))
        return random.sample(candidates, k=k)

    def _running_embed(self, rec) -> discord.Embed:
        title, desc, color = build_embed_fields(
            rec.template_key,
            amount_eur=rec.amount_eur,
            winner_count=rec.winner_count,
            ends_ts=int(rec.ends_at),
        )
        e = discord.Embed(title=title, description=desc, color=color)
        e.set_footer(text=footer_participants(len(rec.participants)))
        if self._banner_path():
            self._attach_banner(e)
        return e

    async def handle_participate(
        self, interaction: discord.Interaction, gid: str
    ) -> None:
        added, _ = self.db.add_participant(gid, interaction.user.id)
        rec = self.db.get(gid)
        if rec is None:
            await interaction.response.send_message(
                "Ce giveaway n’existe plus.", ephemeral=True
            )
            return
        if rec.ended:
            await interaction.response.send_message(
                "Ce giveaway est terminé.", ephemeral=True
            )
            return
        now = time.time()
        if now > rec.ends_at:
            await interaction.response.send_message(
                "Le temps est écoulé.", ephemeral=True
            )
            asyncio.create_task(self._finalize_giveaway(gid))
            return

        if added:
            try:
                ch = self.bot.get_channel(rec.channel_id)
                if isinstance(ch, discord.TextChannel):
                    msg = await ch.fetch_message(rec.message_id)
                    embed = self._running_embed(rec)
                    await msg.edit(embed=embed, view=build_giveaway_view(gid))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

        if added:
            await interaction.response.send_message(
                "Tu es inscrit au tirage !", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Tu participes déjà à ce giveaway.", ephemeral=True
            )

    async def _finalize_giveaway(
        self, gid: str, forced_winners: Optional[List[int]] = None
    ) -> None:
        rec = self.db.get(gid)
        if not rec or rec.ended:
            return
        winners: List[int] = []
        if forced_winners:
            uniq = list(dict.fromkeys(forced_winners))
            winners = uniq[: rec.winner_count]
        else:
            parts = list(rec.participants)
            if parts:
                k = min(rec.winner_count, len(parts))
                winners = random.sample(parts, k=k)

        if not self.db.mark_ended(gid):
            return

        if winners:
            winner_mentions = [f"<@{uid}>" for uid in winners]
            title, body, color = build_result_fields(
                rec.template_key,
                amount_eur=rec.amount_eur,
                winner_mentions=winner_mentions,
            )
        else:
            title = "Giveaway terminé"
            body = (
                f"**Lot : {rec.amount_eur} €**\n\n"
                "Aucun participant — pas de tirage."
            )
            color = 0x57F287

        embed = discord.Embed(
            title=title,
            description=body,
            color=color,
        )
        if self._banner_path():
            self._attach_banner(embed)
        try:
            ch = self.bot.get_channel(rec.channel_id)
            if isinstance(ch, discord.TextChannel):
                msg = await ch.fetch_message(rec.message_id)
                await msg.edit(embed=embed, view=None)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    async def _launch_giveaway(
        self,
        interaction: discord.Interaction,
        template: str,
        joueurs: Optional[str] = None,
        role: Optional[discord.Role] = None,
        montant_par_joueur: Optional[int] = None,
    ) -> None:
        try:
            # ACK immédiat pour éviter "L'application ne répond plus".
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True, thinking=True)

            if not interaction.channel or not isinstance(
                interaction.channel, discord.TextChannel
            ):
                await interaction.followup.send(
                    "Utilise cette commande dans un salon texte.", ephemeral=True
                )
                return

            amount_eur, winner_count, duration_minutes = template_defaults(template)
            if template == "premier" and montant_par_joueur is not None:
                if montant_par_joueur <= 0:
                    await interaction.followup.send(
                        "`montant_par_joueur` doit être supérieur à 0.",
                        ephemeral=True,
                    )
                    return
                amount_eur = int(montant_par_joueur)
            ends_at = time.time() + float(duration_minutes) * 60.0
            gid = uuid.uuid4().hex

            forced_winners, unknown_names, ambiguous_names = (
                await self._resolve_forced_winners(interaction.guild, joueurs or "")
            )
            if (joueurs or "").strip() and (unknown_names or ambiguous_names):
                details: List[str] = []
                if unknown_names:
                    details.append(
                        "Introuvable(s): " + ", ".join(f"`{n}`" for n in unknown_names)
                    )
                if ambiguous_names:
                    details.append(
                        "Ambigu(s): " + ", ".join(f"`{n}`" for n in ambiguous_names)
                    )
                await interaction.followup.send(
                    "Je n'ai pas pu identifier certains joueurs.\n"
                    + "\n".join(details)
                    + "\nUtilise des mentions (`@pseudo`) ou des IDs Discord pour éviter toute erreur.",
                    ephemeral=True,
                )
                return

            # Premier: si tu donnes plusieurs gagnants manuels, on les prend tous.
            if template == "premier" and forced_winners:
                winner_count = len(forced_winners)

            # Lundi/Vendredi: soit gagnants manuels, soit tirage aléatoire basé sur rôle.
            if template in {"lundi", "vendredi"} and not forced_winners:
                if role is None:
                    await interaction.followup.send(
                        "Pour ce template, choisis soit `joueurs`, soit `role` pour un tirage aléatoire par rôle.",
                        ephemeral=True,
                    )
                    return
                forced_winners = self._pick_random_role_members(role, winner_count)
                if not forced_winners:
                    await interaction.followup.send(
                        f"Aucun membre éligible trouvé dans le rôle {role.mention}.",
                        ephemeral=True,
                    )
                    return

            title, desc, color = build_embed_fields(
                template,
                amount_eur=amount_eur,
                winner_count=winner_count,
                ends_ts=int(ends_at),
            )
            embed = discord.Embed(title=title, description=desc, color=color)
            embed.set_footer(text=footer_participants(0))
            banner_path = self._banner_path()
            if banner_path:
                self._attach_banner(embed)

            view = build_giveaway_view(gid)
            try:
                if banner_path:
                    msg = await interaction.channel.send(
                        embed=embed,
                        view=view,
                        file=discord.File(banner_path, filename=_BANNER_FILENAME),
                    )
                else:
                    msg = await interaction.channel.send(embed=embed, view=view)
            except discord.Forbidden:
                await interaction.followup.send(
                    "Je ne peux pas envoyer de message dans ce salon.", ephemeral=True
                )
                return

            self.db.create(
                gid,
                guild_id=interaction.guild.id if interaction.guild else 0,
                channel_id=interaction.channel.id,
                message_id=msg.id,
                template_key=template,
                amount_eur=amount_eur,
                winner_count=winner_count,
                ends_at=ends_at,
            )
            self.bot.add_view(view)

            delay = ends_at - time.time()
            if forced_winners:
                asyncio.create_task(
                    self._finalize_giveaway(gid, forced_winners=forced_winners)
                )
            elif delay > 0:
                asyncio.create_task(self._sleep_and_finalize(gid, delay))
            else:
                asyncio.create_task(self._finalize_giveaway(gid))

            await interaction.followup.send(
                f"Giveaway publié · ID interne `{gid[:8]}…`",
                ephemeral=True,
            )
        except Exception as e:
            print(f"[giveaway] erreur: {e}", flush=True)
            await interaction.followup.send(
                f"Erreur giveaway: `{e}`",
                ephemeral=True,
            )

    @app_commands.command(
        name="win",
        description="Lancer un giveaway instant (stream/lundi/vendredi/mensuel)",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        template="Template giveaway",
        joueurs="Optionnel : gagnants forcés (mentions, IDs ou pseudos séparés par virgule)",
        role="Optionnel : rôle pour tirage aléatoire (lundi/vendredi)",
        montant_par_joueur="Optionnel : montant par joueur (uniquement template premier)",
    )
    @app_commands.choices(template=_TEMPLATE_CHOICES)
    async def win(
        self,
        interaction: discord.Interaction,
        template: str,
        joueurs: Optional[str] = None,
        role: Optional[discord.Role] = None,
        montant_par_joueur: Optional[int] = None,
    ) -> None:
        await self._launch_giveaway(
            interaction, template, joueurs, role, montant_par_joueur
        )
