"""
Bot Discord — gestion liste joueurs (Discord + Gamdom + KYC) pour 19enplein.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import sys
from urllib import error as urlerror
from urllib import request as urlrequest
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from database import Player, PlayerDB, PointDB, PointEntry, RankDB, RankEntry
from giveaway_cog import GiveawayCog
from point_seed_list import normalize_point_key
from rank_seed_list import effective_montant_eur, tier_name_only

try:
    from PIL import Image, ImageDraw, ImageFont

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID_RAW = os.getenv("GUILD_ID")
GUILD_ID = int(GUILD_ID_RAW) if GUILD_ID_RAW and GUILD_ID_RAW.isdigit() else None

ROOT = Path(__file__).resolve().parent
_db_override = os.getenv("PLAYERS_DB_PATH")
DB_PATH = Path(_db_override).resolve() if _db_override else ROOT / "players.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Logo bannière listes (défaut : `assets/19enplein_logo.png`) — sur Pebble : chemin absolu optionnel
_env_logo = (os.getenv("BRAND_LOGO_PATH") or "").strip()
_LOGO_PATH = (
    Path(_env_logo).expanduser().resolve()
    if _env_logo
    else ROOT / "assets" / "19enplein_logo.png"
)

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


# ——— Thème visuel 19ENPLEIN CASINO (logo) ———
_CLR_CYAN = 0x00D4FF
_CLR_GOLD = 0xF9C80E
_CLR_NEON = 0x76FF03
_BRAND = "19ENPLEIN CASINO"
_ALLOWED_ROLE_IDS = {
    1435766360167677973,
    1435761344979664956,
    1435763980139368539,
}
_DEFAULT_RUMBLE_ANNOUNCE_CHANNEL_ID = 1435738454733623549
_RUMBLE_BANNER_PATH = ROOT / "bot en plein.png"
_SESSION_CHANNEL_ID = 1501638278070141019
_SESSION_ROLE_ID = 1501617952376754196
_SESSION_NAME_ON = "🟢💎call💎🟢"
_SESSION_NAME_OFF = "🔴💎call💎🔴"
_SLOTS_SOURCE_JSON = ROOT / "gamdom_slots.json"


def _truncate_cell(s: str, max_len: int) -> str:
    s = str(s).replace("\n", " ").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _table_two_cols(
    rows: List[Tuple[str, str]],
    *,
    key_w: int = 18,
    val_w: int = 28,
) -> str:
    """Tableau monospace type « casino » (bordures Unicode)."""
    top = "╔" + "═" * (key_w + 2) + "╦" + "═" * (val_w + 2) + "╗"
    sep = "╠" + "═" * (key_w + 2) + "╬" + "═" * (val_w + 2) + "╣"
    bot = "╚" + "═" * (key_w + 2) + "╩" + "═" * (val_w + 2) + "╝"
    out: List[str] = [top]
    for i, (k, v) in enumerate(rows):
        kk = _truncate_cell(k, key_w).ljust(key_w)
        vv = _truncate_cell(v, val_w).ljust(val_w)
        out.append(f"║ {kk} ║ {vv} ║")
        if i < len(rows) - 1:
            out.append(sep)
    out.append(bot)
    return "\n".join(out)


def _embed_branded(
    *,
    title: str,
    table_rows: List[Tuple[str, str]],
    accent: int = _CLR_CYAN,
    emoji_title: str = "💸",
    footer_hint: str = "Tableau dynamique",
) -> discord.Embed:
    e = discord.Embed(
        title=f"{emoji_title} **{_BRAND}**",
        description=f"**{title}**\n```\n{_table_two_cols(table_rows)}\n```",
        color=accent,
    )
    e.set_footer(text=f"🔥 {_BRAND} · {footer_hint}")
    return e


def _embed_ok(message: str) -> discord.Embed:
    return discord.Embed(
        title=f"✅ {message}",
        description=f"*{_BRAND}*",
        color=_CLR_NEON,
    )


# Taille max du contenu entre ```…``` (la description d’embed inclut aussi titre + en-têtes, reste < 4096).
_LIST_EMBED_PART_MAX = 3000

# Rendu liste en PNG (LIST_TEXT_ONLY=1 pour rester en texte embed).
# Facteur demandé : ×6 puis ×4 → ×24 (police/marges vs base 10/13/920px).
_LIST_PNG_SCALE = 24
_PNG_MAX_SIDE = 8192  # plafond largeur/hauteur (évite PNG gigantesques / crash mémoire)
_LIST_PNG_FONT_BODY = 10 * _LIST_PNG_SCALE
_LIST_PNG_FONT_HEAD = 13 * _LIST_PNG_SCALE
_LIST_PNG_WIDTH = min(920 * _LIST_PNG_SCALE, _PNG_MAX_SIDE)
_LIST_PNG_PAD = min(14 * _LIST_PNG_SCALE, 160)
_LIST_PNG_LINE_EXTRA = min(4 * _LIST_PNG_SCALE, 48)
_LIST_PNG_HEAD_GAP = min(10 * _LIST_PNG_SCALE, 120)
# Garde-fou hauteur totale (liste entière sur une image) — sinon fallback texte.
_LIST_PNG_MAX_HEIGHT = 120_000
_LIST_PNG_BG = (10, 14, 20)
_LIST_PNG_TEXT = (230, 235, 245)
_LIST_PNG_HEAD = (249, 200, 14)
# Liste /rank : colonnes Joueur + Rang + Montant (PNG)
_LIST_PNG_RANK_TIER = (249, 200, 14)
_LIST_PNG_RANK_EUR = (130, 230, 255)


def _list_codeblock_plain(part: str) -> str:
    return f"```\n{part}\n```"

# Discord ne permet pas d’afficher une police plus « petite » : on compacte chaque entrée sur une ligne
# (troncature avec …) pour limiter les retours à la ligne automatiques du client.
_LIST_LINE_HARD_MAX = 132


def _list_one_line(s: str, max_chars: int) -> str:
    s = (s or "").replace("\n", " ").replace("\r", "").strip()
    if len(s) <= max_chars:
        return s
    if max_chars <= 1:
        return "…"
    return s[: max_chars - 1] + "…"


def _fmt_list_line_affi(p: Player, gid_display: str) -> str:
    line = (
        f"{_list_one_line(p.discord_username, 34)} · "
        f"{_list_one_line(p.gamdom_username, 24)} · "
        f"{_list_one_line(gid_display, 18)} · "
        f"{_list_one_line(str(p.kyc_level), 10)}"
    )
    return _list_one_line(line, _LIST_LINE_HARD_MAX)


def _fmt_list_line_point(p: PointEntry) -> str:
    line = (
        f"{_list_one_line(p.display_name, 36)} · "
        f"+{p.points_rajouter}"
    )
    return _list_one_line(line, _LIST_LINE_HARD_MAX)


def _fmt_list_line_rank(r: RankEntry) -> str:
    tier = _list_one_line(tier_name_only(r.tier), 18)
    mont = f"{effective_montant_eur(r.tier, r.montant_eur)} €"
    line = (
        f"{_list_one_line(r.display_name, 30)} · "
        f"{tier} · "
        f"{mont}"
    )
    return _list_one_line(line, _LIST_LINE_HARD_MAX)


_RANK_CHOICES = [
    app_commands.Choice(name="— Aucun", value="none"),
    app_commands.Choice(name="Bronze 15€", value="bronze"),
    app_commands.Choice(name="Argent 30€", value="argent"),
    app_commands.Choice(name="Gold 50€", value="gold"),
    app_commands.Choice(name="Emeraude 100€", value="emeraude"),
]


def _split_list_body(s: str, max_part: int = _LIST_EMBED_PART_MAX) -> List[str]:
    """
    Découpe en plusieurs messages sans jamais tronquer au milieu d’une ligne
    (sinon un pseudo comme « Bastien » peut être coupé entre deux embeds).
    """
    s = s.strip()
    if not s:
        return []
    lines = s.split("\n")
    chunks: List[str] = []
    buf: List[str] = []
    buf_len = 0
    for line in lines:
        add = len(line) if not buf else 1 + len(line)
        if buf and buf_len + add > max_part:
            chunks.append("\n".join(buf))
            buf = [line]
            buf_len = len(line)
        else:
            if not buf:
                buf = [line]
                buf_len = len(line)
            else:
                buf.append(line)
                buf_len += add
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def _list_render_prefers_png() -> bool:
    """PNG = seule option pour une police réellement plus petite ; désactivable avec LIST_TEXT_ONLY=1."""
    if not _HAS_PIL:
        return False
    v = (os.getenv("LIST_TEXT_ONLY") or "").strip().lower()
    return v not in ("1", "true", "oui", "yes", "on")


def _load_png_font(size: int) -> Any:
    paths = [
        ROOT / "assets" / "DejaVuSansMono.ttf",
        Path("C:/Windows/Fonts/consola.ttf"),
        Path("C:/Windows/Fonts/cour.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf"),
    ]
    for p in paths:
        if p.is_file():
            try:
                return ImageFont.truetype(str(p), size)
            except OSError:
                continue
    return ImageFont.load_default()


_LIST_COL_SEP = " · "


def _png_split_row_cells(row: str) -> List[str]:
    if _LIST_COL_SEP not in row:
        return [row]
    return [c.strip() for c in row.split(_LIST_COL_SEP)]


def _png_column_headers_for_heading(heading: str) -> Optional[List[str]]:
    h = heading.lower()
    if "affilié" in h:
        return ["Discord", "Plateforme", "Réf.", "KYC"]
    if "point" in h:
        return ["Joueur", "Pts +"]
    if "rang" in h:
        return ["Joueur", "Rang", "Montant (€)"]
    return None


def _monospace_column_block(lines: List[str], heading: str) -> str:
    """Aligne les colonnes dans un bloc monospace (mode LIST_TEXT_ONLY / fallback sans PNG)."""
    if not lines:
        return ""
    rows_cells = [_png_split_row_cells(r) for r in lines]
    max_cols = max((len(r) for r in rows_cells), default=1)
    if max_cols <= 1:
        return "\n".join(lines)

    hdr = _png_column_headers_for_heading(heading)
    if hdr:
        while len(hdr) < max_cols:
            hdr.append("")
        hdr = hdr[:max_cols]
    else:
        hdr = []

    col_widths = [2] * max_cols
    if hdr:
        for i, h in enumerate(hdr):
            col_widths[i] = max(col_widths[i], len(h))
    for cells in rows_cells:
        for i in range(min(len(cells), max_cols)):
            col_widths[i] = max(col_widths[i], len(cells[i]))

    cap = 48
    col_widths = [min(w, cap) for w in col_widths]

    sep = " │ "

    def _trim_cell(s: str, w: int) -> str:
        s = (s or "").replace("\n", " ").strip()
        if len(s) <= w:
            return s
        if w <= 1:
            return "…"
        return s[: w - 1] + "…"

    def _format_row(cells: List[str]) -> str:
        parts = []
        for i in range(max_cols):
            c = cells[i] if i < len(cells) else ""
            parts.append(_trim_cell(c, col_widths[i]).ljust(col_widths[i]))
        return sep.join(parts)

    out: List[str] = []
    if hdr:
        out.append(_format_row(hdr))
        rule_len = sum(col_widths) + len(sep) * (max_cols - 1)
        out.append("─" * rule_len)
    for cells in rows_cells:
        while len(cells) < max_cols:
            cells.append("")
        out.append(_format_row(cells[:max_cols]))
    return "\n".join(out)


def _fit_png_line(draw: Any, text: str, font: Any, max_px: float) -> str:
    def tl(t: str) -> float:
        if hasattr(draw, "textlength"):
            return float(draw.textlength(t, font=font))
        b = draw.textbbox((0, 0), t, font=font)
        return float(b[2] - b[0])

    if tl(text) <= max_px:
        return text
    ell = "…"
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        cand = text[:mid] + ell
        if tl(cand) <= max_px:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + ell if lo > 0 else ell


def _png_fill_rank_column(col_idx: int) -> Tuple[int, int, int]:
    """Couleur cellule pour liste rang : col 1 = rang, col 2 = euros."""
    if col_idx == 1:
        return _LIST_PNG_RANK_TIER
    if col_idx == 2:
        return _LIST_PNG_RANK_EUR
    return _LIST_PNG_TEXT


def _render_list_png_small(lines: List[str], heading: str) -> BytesIO:
    """Une seule image ; lignes découpées par « · » → colonnes alignées + en-têtes selon le titre."""
    W = _LIST_PNG_WIDTH
    pad = _LIST_PNG_PAD
    font = _load_png_font(_LIST_PNG_FONT_BODY)
    font_h = _load_png_font(_LIST_PNG_FONT_HEAD)

    tmp = Image.new("RGB", (W, 64), _LIST_PNG_BG)
    td = ImageDraw.Draw(tmp)
    bbox = td.textbbox((0, 0), "Hg", font=font)
    line_h = bbox[3] - bbox[1] + _LIST_PNG_LINE_EXTRA
    hb = td.textbbox((0, 0), heading, font=font_h)
    head_h = hb[3] - hb[1]

    rows_cells = [_png_split_row_cells(r) for r in lines]
    max_cols = max((len(r) for r in rows_cells), default=1)

    hdr_raw = _png_column_headers_for_heading(heading)
    hdr_f: Optional[List[str]] = None
    if hdr_raw and max_cols >= 2:
        hdr_f = list(hdr_raw)
        while len(hdr_f) < max_cols:
            hdr_f.append("")
        hdr_f = hdr_f[:max_cols]

    sep_block = 0
    if hdr_f and max_cols >= 2:
        sep_block = line_h + max(8, _LIST_PNG_SCALE // 2)

    n = len(lines)
    needed_h = (
        pad + head_h + _LIST_PNG_HEAD_GAP + sep_block + n * line_h + pad + 24
    )
    if needed_h > _LIST_PNG_MAX_HEIGHT:
        raise RuntimeError("LIST_IMAGE_TOO_TALL")

    img = Image.new("RGB", (W, needed_h), _LIST_PNG_BG)
    draw = ImageDraw.Draw(img)
    y = float(pad)
    draw.text((pad, y), heading, fill=_LIST_PNG_HEAD, font=font_h)
    y += head_h + _LIST_PNG_HEAD_GAP

    inner_w = float(W - 2 * pad)
    max_txt = inner_w

    if max_cols <= 1:
        for row in lines:
            fitted = _fit_png_line(draw, row, font, max_txt)
            draw.text((pad, y), fitted, fill=_LIST_PNG_TEXT, font=font)
            y += line_h
    else:
        col_gap = float(min(72, max(20, _LIST_PNG_SCALE * 3)))
        col_w = (inner_w - col_gap * (max_cols - 1)) / max_cols

        is_rank_list = "rang" in heading.lower() and max_cols >= 3

        if hdr_f:
            for ci in range(max_cols):
                x = pad + ci * (col_w + col_gap)
                cell = hdr_f[ci] if ci < len(hdr_f) else ""
                fitted = _fit_png_line(draw, cell, font, col_w)
                hf = _LIST_PNG_HEAD
                if is_rank_list and ci == 1:
                    hf = _LIST_PNG_RANK_TIER
                elif is_rank_list and ci == 2:
                    hf = _LIST_PNG_RANK_EUR
                draw.text((x, y), fitted, fill=hf, font=font)
            y += line_h
            rule_y = int(y)
            rule_w = max(1, _LIST_PNG_SCALE // 12)
            draw.line(
                [(int(pad), rule_y), (int(W - pad), rule_y)],
                fill=(65, 72, 88),
                width=rule_w,
            )
            y += float(rule_w + max(6, _LIST_PNG_SCALE // 4))

        for row in lines:
            cells = _png_split_row_cells(row)
            while len(cells) < max_cols:
                cells.append("")
            cells = cells[:max_cols]
            for ci in range(max_cols):
                x = pad + ci * (col_w + col_gap)
                fitted = _fit_png_line(draw, cells[ci], font, col_w)
                fill = (
                    _png_fill_rank_column(ci)
                    if is_rank_list
                    else _LIST_PNG_TEXT
                )
                draw.text((x, y), fitted, fill=fill, font=font)
            y += line_h

    y += pad
    img = img.crop((0, 0, W, int(y)))
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


async def _followup_send_branded_list(
    interaction: discord.Interaction,
    *,
    list_heading: str,
    accent: int,
    emoji: str,
    footer_hint: str,
    text: str,
    empty_msg: str,
    align_columns_text: bool = False,
) -> None:
    """Listes : image PNG en petite police, ou texte si LIST_TEXT_ONLY=1 / sans Pillow."""
    has_logo = _LOGO_PATH.is_file()
    fn = _LOGO_PATH.name

    def _one_embed_text(
        part: str,
        *,
        index: int,
        total: int,
        with_logo_banner: bool,
    ) -> discord.Embed:
        sub = ""
        if total > 1:
            sub = f"\n`▰▰▰` **{index}** / **{total}** `▰▰▰`\n"

        def _build_desc(p: str) -> str:
            return f"**{list_heading}**{sub}\n{_list_codeblock_plain(p)}"

        body = _build_desc(part)
        while len(body) > 4090 and "\n" in part:
            part = part.rsplit("\n", 1)[0]
            body = _build_desc(part)
        if len(body) > 4090:
            part = _list_one_line(part.replace("\n", " "), 3500)
            body = _build_desc(part)
        e = discord.Embed(
            title=f"{emoji} **{_BRAND}**",
            description=body,
            color=accent,
            timestamp=discord.utils.utcnow(),
        )
        foot = f"🔥 {_BRAND} · {footer_hint}"
        if total > 1:
            foot += f" · {index}/{total}"
        e.set_footer(text=foot)
        if with_logo_banner and has_logo:
            e.set_image(url=f"attachment://{fn}")
        return e

    try:
        if not text.strip():
            e = discord.Embed(
                title=f"{emoji} **{_BRAND}**",
                description=f"**{list_heading}**\n\n✦ *{empty_msg}* ✦",
                color=accent,
                timestamp=discord.utils.utcnow(),
            )
            e.set_footer(text=f"🔥 {_BRAND} · {footer_hint}")
            if has_logo:
                e.set_image(url=f"attachment://{fn}")
                await interaction.followup.send(
                    embed=e,
                    file=discord.File(_LOGO_PATH, filename=fn),
                )
            else:
                await interaction.followup.send(embed=e)
            return

        raw_lines = text.strip().split("\n")
        display_text = (
            _monospace_column_block(raw_lines, list_heading)
            if align_columns_text
            else text.strip()
        )

        if _list_render_prefers_png():
            try:
                png_buf = _render_list_png_small(raw_lines, list_heading)
                desc = f"**{list_heading}**"
                e = discord.Embed(
                    title=f"{emoji} **{_BRAND}**",
                    description=desc,
                    color=accent,
                    timestamp=discord.utils.utcnow(),
                )
                e.set_footer(text=f"🔥 {_BRAND} · {footer_hint}")
                e.set_image(url="attachment://liste.png")
                list_f = discord.File(png_buf, filename="liste.png")
                if has_logo:
                    e.set_thumbnail(url=f"attachment://{fn}")
                    await interaction.followup.send(
                        embed=e,
                        files=[
                            discord.File(_LOGO_PATH, filename=fn),
                            list_f,
                        ],
                    )
                else:
                    await interaction.followup.send(embed=e, files=[list_f])
                return
            except Exception:
                pass

        parts = _split_list_body(display_text)
        n = len(parts)
        for i, part in enumerate(parts):
            idx = i + 1
            e = _one_embed_text(
                part,
                index=idx,
                total=n,
                with_logo_banner=(i == 0),
            )
            if i == 0 and has_logo:
                await interaction.followup.send(
                    embed=e,
                    file=discord.File(_LOGO_PATH, filename=fn),
                )
            else:
                await interaction.followup.send(embed=e)
    except Exception as e:
        try:
            await interaction.followup.send(
                f"Erreur lors de l’envoi : `{e}`", ephemeral=True
            )
        except Exception:
            pass


def _player_embed(p: Player) -> discord.Embed:
    gid = (p.gamdom_id or "").strip()
    if not gid or gid == "0":
        gid = "—"
    rows = [
        ("Pseudo Discord", p.discord_username),
        ("ID Discord", p.discord_id),
        ("Réf. compte", gid),
        ("Niveau KYC", p.kyc_level or "—"),
    ]
    return _embed_branded(
        title="Fiche affilié",
        table_rows=rows,
        accent=_CLR_CYAN,
        emoji_title="🎰",
        footer_hint="Affiliation & KYC",
    )


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
        await interaction.response.send_message(
            embed=_embed_ok(f"Joueur supprimé · ID `{id_discord}`")
        )

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
        # defer tout de suite : Discord impose ~3 s avant réponse, sinon « application ne répond plus »
        await interaction.response.defer()
        try:
            players = db.list_all()
        except Exception as e:
            await interaction.followup.send(f"Erreur base de données : `{e}`", ephemeral=True)
            return
        if not players:
            await interaction.followup.send("La liste est vide.")
            return

        def _id_gamdom_aff(p: Player) -> str:
            g = (p.gamdom_id or "").strip()
            return g if g and g != "0" else "—"

        lines = [_fmt_list_line_affi(p, _id_gamdom_aff(p)) for p in players]
        text = "\n".join(lines)
        await _followup_send_branded_list(
            interaction,
            list_heading="Liste des affiliés",
            accent=_CLR_CYAN,
            emoji="🎰",
            footer_hint="Affiliation & KYC",
            text=text,
            empty_msg="La liste est vide.",
            align_columns_text=True,
        )


def _point_embed(p: PointEntry) -> discord.Embed:
    rows = [
        ("Joueur", p.display_name),
        ("Points (réf.)", str(p.points_rajouter)),
    ]
    return _embed_branded(
        title="Points stream",
        table_rows=rows,
        accent=_CLR_NEON,
        emoji_title="💸",
        footer_hint="Classement points",
    )


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
        await interaction.response.send_message(
            embed=_embed_ok(f"Joueur supprimé · **{joueur.strip()}**")
        )

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
        await interaction.response.defer()
        try:
            rows = point_db.list_all()
        except Exception as e:
            await interaction.followup.send(f"Erreur base de données : `{e}`", ephemeral=True)
            return
        if not rows:
            await interaction.followup.send("La liste est vide.")
            return
        lines = [_fmt_list_line_point(p) for p in rows]
        text = "\n".join(lines)
        await _followup_send_branded_list(
            interaction,
            list_heading="Liste des points",
            accent=_CLR_NEON,
            emoji="💸",
            footer_hint="Classement points",
            text=text,
            empty_msg="La liste est vide.",
            align_columns_text=True,
        )


def _rank_embed(r: RankEntry) -> discord.Embed:
    rows = [
        ("Joueur", r.display_name),
        ("Rang", tier_name_only(r.tier)),
        ("Montant (€)", f"{effective_montant_eur(r.tier, r.montant_eur)} €"),
    ]
    return _embed_branded(
        title="Rang & statut",
        table_rows=rows,
        accent=_CLR_GOLD,
        emoji_title="🏆",
        footer_hint="Bronze · Argent · Gold · Emeraude",
    )


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
        await interaction.response.send_message(
            embed=_embed_ok(f"Joueur supprimé · **{joueur.strip()}**")
        )

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
        await interaction.response.defer()
        try:
            rows = rank_db.list_all()
        except Exception as e:
            await interaction.followup.send(f"Erreur base de données : `{e}`", ephemeral=True)
            return
        if not rows:
            await interaction.followup.send("La liste est vide.")
            return
        lines = [_fmt_list_line_rank(r) for r in rows]
        text = "\n".join(lines)
        await _followup_send_branded_list(
            interaction,
            list_heading="Liste des rangs",
            accent=_CLR_GOLD,
            emoji="🏆",
            footer_hint="Bronze · Argent · Gold · Emeraude",
            text=text,
            empty_msg="La liste est vide.",
            align_columns_text=True,
        )


class SessionCog(commands.Cog):
    session = app_commands.Group(
        name="session", description="Gérer la session call (start / stop)"
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.active: bool = False
        self.used_users: Set[int] = set()
        self.slot_catalog: List[Dict[str, str]] = self._load_slot_catalog()

    @staticmethod
    def _load_slot_catalog() -> List[Dict[str, str]]:
        """Charge la liste des slots depuis jeux.json (nom/provider/image)."""
        try:
            raw = _SLOTS_SOURCE_JSON.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, list):
                return []
            seen: Set[Tuple[str, str]] = set()
            out: List[Dict[str, str]] = []
            for row in data:
                if not isinstance(row, dict):
                    continue
                sid = str(row.get("id", "")).strip()
                nom = str(row.get("nom", "")).strip()
                provider = str(row.get("provider", "")).strip()
                image = str(row.get("image", "")).strip()
                if not sid or not nom:
                    continue
                key = (nom.lower(), provider.lower())
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "id": sid,
                        "nom": nom,
                        "provider": provider or "Inconnu",
                        "image": image,
                    }
                )
            out.sort(key=lambda x: (x["nom"].lower(), x["provider"].lower()))
            return out
        except Exception as e:
            print(f"[session] impossible de charger jeux.json: {e}", flush=True)
            return []

    def _slot_by_id(self, slot_id: str) -> Optional[Dict[str, str]]:
        sid = (slot_id or "").strip()
        if not sid:
            return None
        return next((s for s in self.slot_catalog if s["id"] == sid), None)

    def _slot_by_name_contains(self, query: str) -> Optional[Dict[str, str]]:
        q = (query or "").strip().lower()
        if not q:
            return None
        return next((s for s in self.slot_catalog if q in s["nom"].lower()), None)

    @staticmethod
    def _is_staff(member: Optional[discord.Member]) -> bool:
        if member is None:
            return False
        if member.guild_permissions.administrator:
            return True
        role_ids = {r.id for r in member.roles}
        return bool(role_ids.intersection(_ALLOWED_ROLE_IDS))

    @staticmethod
    def _is_admin(member: Optional[discord.Member]) -> bool:
        if member is None:
            return False
        perms = member.guild_permissions
        return bool(perms.administrator or perms.manage_guild)

    @staticmethod
    def _session_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
        ch = guild.get_channel(_SESSION_CHANNEL_ID)
        return ch if isinstance(ch, discord.TextChannel) else None

    async def _configure_channel_for_session(
        self, channel: discord.TextChannel, enabled: bool
    ) -> None:
        guild = channel.guild
        everyone = guild.default_role
        kyc_role = guild.get_role(_SESSION_ROLE_ID)

        overwrites = channel.overwrites
        ow_everyone = overwrites.get(everyone, discord.PermissionOverwrite())
        ow_everyone.view_channel = True
        ow_everyone.send_messages = False
        overwrites[everyone] = ow_everyone

        # KYC: 1 seul message géré côté listener, pas de suppression de messages.
        if kyc_role is not None:
            ow_kyc = overwrites.get(kyc_role, discord.PermissionOverwrite())
            ow_kyc.view_channel = True
            ow_kyc.read_message_history = True
            ow_kyc.send_messages = True if enabled else False
            ow_kyc.manage_messages = False
            overwrites[kyc_role] = ow_kyc

        # Staff whitelist: peuvent faire ce qu'ils veulent dans ce salon.
        for rid in _ALLOWED_ROLE_IDS:
            staff_role = guild.get_role(rid)
            if staff_role is None:
                continue
            ow_staff = overwrites.get(staff_role, discord.PermissionOverwrite())
            ow_staff.view_channel = True
            ow_staff.read_message_history = True
            ow_staff.send_messages = True
            ow_staff.manage_messages = True
            ow_staff.manage_channels = True
            overwrites[staff_role] = ow_staff

        new_name = _SESSION_NAME_ON if enabled else _SESSION_NAME_OFF
        await channel.edit(name=new_name, overwrites=overwrites)

    @session.command(name="start", description="Démarrer la session call")
    @app_commands.guild_only()
    async def session_start(self, interaction: discord.Interaction) -> None:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Démarrage de la session en cours...", ephemeral=True
            )
        if not self._is_admin(interaction.user if isinstance(interaction.user, discord.Member) else None):
            await interaction.followup.send(
                "Commande réservée aux admins.", ephemeral=True
            )
            return
        if interaction.guild is None:
            await interaction.followup.send(
                "Commande disponible uniquement en serveur.", ephemeral=True
            )
            return
        channel = self._session_channel(interaction.guild)
        if channel is None:
            await interaction.followup.send(
                f"Salon introuvable: `{_SESSION_CHANNEL_ID}`", ephemeral=True
            )
            return
        self.used_users.clear()
        self.active = True
        try:
            await self._configure_channel_for_session(channel, enabled=True)
        except (discord.Forbidden, discord.HTTPException) as e:
            self.active = False
            await interaction.followup.send(
                f"Impossible de démarrer la session: `{e}`",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            f"Session démarrée dans {channel.mention}. Les membres du rôle <@&{_SESSION_ROLE_ID}> peuvent envoyer 1 message chacun.",
            ephemeral=True,
        )

    @session.command(name="stop", description="Stopper la session call et nettoyer")
    @app_commands.guild_only()
    async def session_stop(self, interaction: discord.Interaction) -> None:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Arrêt de la session en cours...", ephemeral=True
            )
        if not self._is_admin(interaction.user if isinstance(interaction.user, discord.Member) else None):
            await interaction.followup.send(
                "Commande réservée aux admins.", ephemeral=True
            )
            return
        if interaction.guild is None:
            await interaction.followup.send(
                "Commande disponible uniquement en serveur.", ephemeral=True
            )
            return
        channel = self._session_channel(interaction.guild)
        if channel is None:
            await interaction.followup.send(
                f"Salon introuvable: `{_SESSION_CHANNEL_ID}`", ephemeral=True
            )
            return

        self.active = False
        self.used_users.clear()

        # Purge tous les messages visibles du salon.
        try:
            await channel.purge(limit=None)
        except (discord.Forbidden, discord.HTTPException) as e:
            await interaction.followup.send(
                f"Je n'ai pas pu supprimer les messages du salon: `{e}`",
                ephemeral=True,
            )
            return

        try:
            await self._configure_channel_for_session(channel, enabled=False)
        except (discord.Forbidden, discord.HTTPException) as e:
            await interaction.followup.send(
                f"Session stoppée mais renommage/permissions impossible: `{e}`",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            f"Session arrêtée, salon nettoyé et renommé en `{_SESSION_NAME_OFF}`.",
            ephemeral=True,
        )

    @app_commands.command(name="call", description="Call une machine pendant la session")
    @app_commands.guild_only()
    @app_commands.describe(machine="Machine (liste issue de jeux.json)")
    async def call(self, interaction: discord.Interaction, machine: str) -> None:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member is None or interaction.guild is None:
            await interaction.response.send_message(
                "Commande disponible uniquement en serveur.", ephemeral=True
            )
            return
        if interaction.channel_id != _SESSION_CHANNEL_ID:
            await interaction.response.send_message(
                f"Utilise cette commande dans <#{_SESSION_CHANNEL_ID}>.",
                ephemeral=True,
            )
            return
        if not self.active:
            await interaction.response.send_message(
                "Aucune session active. Utilise `/session start` avant les calls.",
                ephemeral=True,
            )
            return

        role_ids = {r.id for r in member.roles}
        is_staff = self._is_staff(member)
        is_kyc = _SESSION_ROLE_ID in role_ids
        if not (is_staff or is_kyc):
            await interaction.response.send_message(
                "Tu n'as pas le rôle autorisé pour faire un call.",
                ephemeral=True,
            )
            return
        if (not is_staff) and member.id in self.used_users:
            await interaction.response.send_message(
                "Tu as déjà utilisé ton unique call pour cette session.",
                ephemeral=True,
            )
            return

        slot = self._slot_by_id(machine) or self._slot_by_name_contains(machine)
        if slot is None:
            await interaction.response.send_message(
                "Machine introuvable dans `jeux.json`. Commence à taper pour utiliser l'autocomplétion.",
                ephemeral=True,
            )
            return

        if not is_staff:
            self.used_users.add(member.id)

        embed = discord.Embed(
            title="🎰 CALL MACHINE",
            description=f"👤 Caller: {member.mention}\n💎 Machine: **{slot['nom']}**",
            color=_CLR_CYAN,
        )
        embed.add_field(name="Provider", value=slot["provider"], inline=True)
        if slot.get("image"):
            embed.set_image(url=slot["image"])
        if _RUMBLE_BANNER_PATH.is_file():
            embed.set_thumbnail(url="attachment://call_banner.png")
            await interaction.response.send_message(
                embed=embed,
                file=discord.File(_RUMBLE_BANNER_PATH, filename="call_banner.png"),
            )
            return
        await interaction.response.send_message(embed=embed)

    @call.autocomplete("machine")
    async def call_machine_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        q = (current or "").strip().lower()
        if not self.slot_catalog:
            return []
        if not q:
            out: List[app_commands.Choice[str]] = []
            for s in self.slot_catalog[:25]:
                label = f"{s['nom']} · {s['provider']}"
                out.append(app_commands.Choice(name=label[:100], value=s["id"]))
            return out
        out: List[app_commands.Choice[str]] = []
        for s in self.slot_catalog:
            if q in s["nom"].lower() or q in s["provider"].lower():
                label = f"{s['nom']} · {s['provider']}"
                out.append(app_commands.Choice(name=label[:100], value=s["id"]))
            if len(out) >= 25:
                break
        return out

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not self.active:
            return
        if message.channel.id != _SESSION_CHANNEL_ID:
            return
        if not isinstance(message.author, discord.Member):
            return

        if message.author.guild_permissions.administrator:
            return

        role_ids = {r.id for r in message.author.roles}
        if role_ids.intersection(_ALLOWED_ROLE_IDS):
            return

        if _SESSION_ROLE_ID not in role_ids:
            try:
                await message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

        if message.author.id in self.used_users:
            try:
                await message.delete()
                await message.author.send(
                    "Tu as déjà utilisé ton unique message pour cette session call."
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

        self.used_users.add(message.author.id)


class Bot19(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self._guild_sync_done = False
        self._rumble_task: Optional[asyncio.Task] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Autorise les commandes uniquement aux rôles whitelistés ou admin."""
        if interaction.guild is None:
            return False
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member is None:
            return False
        if member.guild_permissions.administrator:
            return True
        # Exception: /call autorisé aussi au rôle KYC session.
        cmd = interaction.command.qualified_name if interaction.command else ""
        if cmd == "call":
            role_ids = {r.id for r in member.roles}
            if _SESSION_ROLE_ID in role_ids:
                return True
        role_ids = {r.id for r in member.roles}
        return bool(role_ids.intersection(_ALLOWED_ROLE_IDS))

    async def _sync_for_guild(self, guild_id: int) -> None:
        """Copie les commandes globales vers la guilde puis synchronise."""
        guild_obj = discord.Object(id=guild_id)
        self.tree.copy_global_to(guild=guild_obj)
        synced = await self.tree.sync(guild=guild_obj)
        print(f"[sync guild] guild={guild_id} cmds={len(synced)}", flush=True)

    @staticmethod
    def _extract_rumble_live_url(html: str) -> Optional[str]:
        """Extrait l'URL live Rumble si la page indique un live en cours."""
        if not html:
            return None
        lowered = html.lower()
        live_markers = (
            '"is_live":true',
            '"livestream_status":1',
            '"video_type":"live"',
            "watching now",
            "en direct",
            "is live",
        )
        if not any(m in lowered for m in live_markers):
            return None

        # Cherche une URL vidéo Rumble (vxxxxx) dans le HTML.
        match = re.search(r"https://rumble\.com/v[0-9a-z]+[^\"' <]*\.html", html, re.I)
        if match:
            return match.group(0)
        return None

    async def _fetch_rumble_live_url(self, source_url: str) -> Optional[str]:
        def _blocking_fetch() -> Optional[str]:
            req = urlrequest.Request(
                source_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0 Safari/537.36"
                    )
                },
            )
            with urlrequest.urlopen(req, timeout=20) as resp:
                raw = resp.read()
            html = raw.decode("utf-8", errors="ignore")
            return self._extract_rumble_live_url(html)

        try:
            return await asyncio.to_thread(_blocking_fetch)
        except (urlerror.URLError, TimeoutError, ValueError) as e:
            print(f"[rumble] erreur fetch: {e}", flush=True)
            return None

    def _resolve_rumble_announce_channel(self) -> Optional[discord.TextChannel]:
        chan_raw = (os.getenv("RUMBLE_ANNOUNCE_CHANNEL_ID") or "").strip()
        channel_id = (
            int(chan_raw) if chan_raw.isdigit() else _DEFAULT_RUMBLE_ANNOUNCE_CHANNEL_ID
        )
        ch = self.get_channel(channel_id)
        if isinstance(ch, discord.TextChannel):
            return ch
        for g in self.guilds:
            if g.system_channel and isinstance(g.system_channel, discord.TextChannel):
                perms = g.system_channel.permissions_for(g.me) if g.me else None
                if perms and perms.send_messages:
                    return g.system_channel
            for ch in g.text_channels:
                perms = ch.permissions_for(g.me) if g.me else None
                if perms and perms.send_messages:
                    return ch
        return None

    def _build_rumble_live_embed(self, live_url: str) -> discord.Embed:
        e = discord.Embed(
            title="🔴🎰 19ENPLEIN EST EN LIVE SUR RUMBLE 🚀",
            description=(
                "🔥 Le live vient de commencer !\n"
                f"👉🎥 [Rejoindre le live maintenant]({live_url})\n"
                "💬 Viens spammer le chat avec la team !"
            ),
            color=_CLR_GOLD,
            timestamp=discord.utils.utcnow(),
        )
        e.add_field(name="📺 Plateforme", value="Rumble", inline=True)
        e.add_field(name="🔗 Lien", value=live_url, inline=False)
        e.set_footer(text="19ENPLEIN CASINO · Notification live 🔔")
        if _RUMBLE_BANNER_PATH.is_file():
            e.set_thumbnail(url="attachment://rumble_live_banner.png")
        return e

    async def _send_rumble_announcement(
        self, channel: discord.TextChannel, live_url: str, *, ping_everyone: bool
    ) -> None:
        embed = self._build_rumble_live_embed(live_url)
        content = (
            "@everyone 🚨🔴 LIVE EN COURS ! GO GO GO ! 🎰"
            if ping_everyone
            else "🚨 TEST LIVE (sans mention)"
        )
        kwargs: Dict[str, Any] = {
            "content": content,
            "embed": embed,
            "allowed_mentions": discord.AllowedMentions(everyone=ping_everyone),
        }
        if _RUMBLE_BANNER_PATH.is_file():
            kwargs["file"] = discord.File(_RUMBLE_BANNER_PATH, filename="rumble_live_banner.png")
        await channel.send(**kwargs)

    async def _rumble_live_loop(self) -> None:
        await self.wait_until_ready()
        source_url = (
            os.getenv("RUMBLE_CHANNEL_URL")
            or "https://rumble.com/user/19enplein"
        ).strip()
        poll_seconds_raw = (os.getenv("RUMBLE_POLL_SECONDS") or "90").strip()
        poll_seconds = int(poll_seconds_raw) if poll_seconds_raw.isdigit() else 90
        poll_seconds = max(30, poll_seconds)

        while not self.is_closed():
            try:
                live_url = await self._fetch_rumble_live_url(source_url)
                was_live = point_db.get_meta("rumble_live_state") == "1"
                last_url = point_db.get_meta("rumble_live_url") or ""

                if live_url:
                    if (not was_live) or (live_url != last_url):
                        ch = self._resolve_rumble_announce_channel()
                        if ch is not None:
                            await self._send_rumble_announcement(
                                ch, live_url, ping_everyone=True
                            )
                            print(f"[rumble] annonce envoyée: {live_url}", flush=True)
                        point_db.set_meta("rumble_live_state", "1")
                        point_db.set_meta("rumble_live_url", live_url)
                else:
                    if was_live:
                        print("[rumble] live terminé", flush=True)
                    point_db.set_meta("rumble_live_state", "0")
                    point_db.set_meta("rumble_live_url", "")
            except Exception as e:
                print(f"[rumble] erreur loop: {e}", flush=True)
            await asyncio.sleep(poll_seconds)

    async def setup_hook(self) -> None:
        await self.add_cog(AffiCog(self))
        await self.add_cog(PointCog(self))
        await self.add_cog(RankCog(self))
        await self.add_cog(SessionCog(self))
        await self.add_cog(GiveawayCog(self, DB_PATH))
        if self._rumble_task is None or self._rumble_task.done():
            self._rumble_task = asyncio.create_task(self._rumble_live_loop())
        if GUILD_ID:
            try:
                await self._sync_for_guild(GUILD_ID)
            except discord.HTTPException as e:
                print(f"[sync setup_hook] erreur guild={GUILD_ID}: {e}", flush=True)
        else:
            # Sync global (peut prendre du temps à apparaître côté Discord).
            try:
                synced = await self.tree.sync()
                print(f"[sync setup_hook] global cmds={len(synced)}", flush=True)
            except discord.HTTPException as e:
                print(f"[sync setup_hook] erreur global: {e}", flush=True)


async def main() -> None:
    if not TOKEN:
        print("Définis DISCORD_TOKEN dans un fichier .env (voir .env.example).", file=sys.stderr)
        sys.exit(1)
    bot = Bot19()

    @bot.event
    async def on_ready() -> None:
        if not bot._guild_sync_done:
            for g in bot.guilds:
                try:
                    await bot._sync_for_guild(g.id)
                except discord.HTTPException as e:
                    print(f"[sync on_ready] erreur guild={g.id}: {e}", flush=True)
            bot._guild_sync_done = True
        print(f"Connecté en tant que {bot.user} ({bot.user.id if bot.user else '?'})")

    @bot.tree.error
    async def on_app_command_error(
        interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        print(f"[app_command_error] {error}", flush=True)
        msg = f"Erreur commande: `{error}`"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
