"""
Giveaways : message avec bouton « Participer », templates prédéfinis, tirage à la fin.
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from database import GiveawayDB
from giveaway_templates import TEMPLATES, build_embed_fields, footer_participants

_TEMPLATE_CHOICES = [
    app_commands.Choice(name=str(v["choice_name"]), value=k)
    for k, v in TEMPLATES.items()
]


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
    """Slash `/giveaway creer` + boutons persistants."""

    giveaway = app_commands.Group(
        name="giveaway",
        description="Giveaways : bouton Participer, tirage automatique",
    )

    def __init__(self, bot: commands.Bot, db_path: Path) -> None:
        self.bot = bot
        self.db = GiveawayDB(db_path)

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

    def _running_embed(self, rec) -> discord.Embed:
        title, desc, color = build_embed_fields(
            rec.template_key,
            amount_eur=rec.amount_eur,
            winner_count=rec.winner_count,
            ends_ts=int(rec.ends_at),
        )
        e = discord.Embed(title=title, description=desc, color=color)
        e.set_footer(text=footer_participants(len(rec.participants)))
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

    async def _finalize_giveaway(self, gid: str) -> None:
        rec = self.db.get(gid)
        if not rec or rec.ended:
            return
        parts = list(rec.participants)
        winners: list[int] = []
        if parts:
            k = min(rec.winner_count, len(parts))
            winners = random.sample(parts, k=k)

        if not self.db.mark_ended(gid):
            return

        if winners:
            mentions = "\n".join(f"• <@{uid}>" for uid in winners)
            body = f"**Lot : {rec.amount_eur} €**\n\n**Gagnant(s) :**\n{mentions}"
        else:
            body = (
                f"**Lot : {rec.amount_eur} €**\n\n"
                "Aucun participant — pas de tirage."
            )

        embed = discord.Embed(
            title="Giveaway terminé",
            description=body,
            color=0x57F287,
        )
        try:
            ch = self.bot.get_channel(rec.channel_id)
            if isinstance(ch, discord.TextChannel):
                msg = await ch.fetch_message(rec.message_id)
                await msg.edit(embed=embed, view=None)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    @giveaway.command(
        name="creer",
        description="Lancer un giveaway (message + bouton Participer)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        template="Modèle de message",
        montant="Montant à gagner (€)",
        duree_minutes="Durée avant fin du giveaway (minutes)",
        gagnants="Nombre de gagnants tirés au sort",
    )
    @app_commands.choices(template=_TEMPLATE_CHOICES)
    async def giveaway_creer(
        self,
        interaction: discord.Interaction,
        template: str,
        montant: app_commands.Range[int, 1, 50000],
        duree_minutes: app_commands.Range[int, 1, 10080],
        gagnants: app_commands.Range[int, 1, 25],
    ) -> None:
        if not interaction.channel or not isinstance(
            interaction.channel, discord.TextChannel
        ):
            await interaction.response.send_message(
                "Utilise cette commande dans un salon texte.", ephemeral=True
            )
            return

        ends_at = time.time() + float(duree_minutes) * 60.0
        gid = uuid.uuid4().hex

        title, desc, color = build_embed_fields(
            template,
            amount_eur=int(montant),
            winner_count=int(gagnants),
            ends_ts=int(ends_at),
        )
        embed = discord.Embed(title=title, description=desc, color=color)
        embed.set_footer(text=footer_participants(0))

        view = build_giveaway_view(gid)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
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
            amount_eur=int(montant),
            winner_count=int(gagnants),
            ends_at=ends_at,
        )
        self.bot.add_view(view)

        delay = ends_at - time.time()
        if delay > 0:
            asyncio.create_task(self._sleep_and_finalize(gid, delay))

        await interaction.followup.send(
            f"Giveaway publié · ID interne `{gid[:8]}…`",
            ephemeral=True,
        )
