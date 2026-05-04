"""
Templates de messages pour les giveaways (texte prédéfini + couleur).
Placeholders : montant €, nombre de gagnants, horaire de fin Discord.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

# Clé → métadonnées affichées dans le sélecteur slash + rendu embed
TEMPLATES: Dict[str, Dict[str, Any]] = {
    "casino": {
        "choice_name": "Casino 19ENPLEIN",
        "title": "🎰 Giveaway · 19ENPLEIN CASINO",
        "description": (
            "### 💰 **{amount} €** à gagner\n\n"
            "🏆 **{winners}** gagnant(s)\n"
            "⏱️ Se termine : {ends_rel} ({ends_abs})\n\n"
            "Clique sur **Participer** pour t’inscrire au tirage."
        ),
        "color": 0xF9C80E,
    },
    "stream": {
        "choice_name": "Live / Stream",
        "title": "📺 Giveaway stream",
        "description": (
            "**Lot : {amount} €** · **{winners}** gagnant(s)\n\n"
            "Fin {ends_rel}\n\n"
            "Bouton **Participer** ci-dessous 👇"
        ),
        "color": 0x00D4FF,
    },
    "minimal": {
        "choice_name": "Simple",
        "title": "Giveaway",
        "description": (
            "{amount} € · {winners} gagnant(s) · fin {ends_rel}"
        ),
        "color": 0x2B2D31,
    },
}


def template_keys() -> Tuple[str, ...]:
    return tuple(TEMPLATES.keys())


def template_choice_name(key: str) -> str:
    t = TEMPLATES.get(key)
    return str(t["choice_name"]) if t else key


def _ends_tags(ends_ts: int) -> Tuple[str, str]:
    """Ligne relative + absolue (Discord auto-format horaires)."""
    rel = f"<t:{ends_ts}:R>"
    abs_ = f"<t:{ends_ts}:f>"
    return rel, abs_


def build_embed_fields(
    template_key: str,
    *,
    amount_eur: int,
    winner_count: int,
    ends_ts: int,
) -> Tuple[str, str, int]:
    """Retourne (title, description, color) pour discord.Embed."""
    t = TEMPLATES.get(template_key) or TEMPLATES["casino"]
    ends_rel, ends_abs = _ends_tags(ends_ts)
    desc = str(t["description"]).format(
        amount=amount_eur,
        winners=winner_count,
        ends_rel=ends_rel,
        ends_abs=ends_abs,
    )
    return str(t["title"]), desc, int(t["color"])


def footer_participants(n: int) -> str:
    if n <= 0:
        return "Aucun participant pour l’instant · Clique sur Participer"
    if n == 1:
        return "1 participant"
    return f"{n} participants"
