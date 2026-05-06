"""
Templates de messages pour les giveaways (texte prédéfini + couleur).
Placeholders : montant €, nombre de gagnants, horaire de fin Discord.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# Clé → métadonnées affichées dans le sélecteur slash + rendu embed
TEMPLATES: Dict[str, Dict[str, Any]] = {
    "stream": {
        "choice_name": "stream",
        "default_amount": 5,
        "default_winners": 1,
        "default_duration_minutes": 0,
        "title": "🎰 Giveaway Stream",
        "description": (
            "🏆 Giveaway **STREAM** en cours ! 🏆\n\n"
            "💰 Gain : **{amount}$** cash\n"
            "👥 Gagnant(s) : **{winners}**\n"
            "⏱️ Fin : {ends_rel} ({ends_abs})\n\n"
            "Clique sur **Participer** pour t’inscrire au tirage."
        ),
        "color": 0xF9C80E,
        "result_title": "🏆 AND THE WINNER IS ! 🏆",
        "result_description": (
            "🏆 {winner_line} 🏆\n"
            "Félicitations au chanceux du jour sur le stream ! 🎰✨\n\n"
            "💰 Gain : {amount}$ cash crédités immédiatement !\n\n"
            "🔥 Statut : Que tu sois affilié ou non, la chance a tourné pour toi !\n\n"
            "🤑 GG à toi ! On se retrouve demain pour le prochain tirage au sort quotidien sur le chat ! 🍒🔔💎"
        ),
    },
    "lundi": {
        "choice_name": "Lundi",
        "default_amount": 50,
        "default_winners": 2,
        "default_duration_minutes": 0,
        "title": "🎰 Giveaway du Lundi",
        "description": (
            "🏆 Giveaway **LUNDI** en cours ! 🏆\n\n"
            "💰 Cash total : **{amount}$**\n"
            "👥 Gagnant(s) : **{winners}**\n"
            "💵 Gain par personne : **{per_winner}$**\n"
            "⏱️ Fin : {ends_rel}\n\n"
            "Clique sur **Participer** pour entrer dans le tirage."
        ),
        "color": 0x00D4FF,
        "result_title": "🏆 LES GAGNANTS DU LUNDI ! 🏆",
        "result_description": (
            "🏆 {winner_line} !!! 🏆\n"
            "Le tirage au sort vient de rendre son verdict pour le giveaway de {amount}$ ! 🎰✨\n\n"
            "💰 Le Cash : Félicitations aux vainqueurs ! Chaque personne gagne {per_winner}$.\n\n"
            "✅ Condition validée : Bravo à nos affiliés KYC 2 pour leur victoire !\n\n"
            "🤑 GG AUX GAGNANTS ! 💸🔥\n"
            "Rendez-vous lundi prochain pour remettre ça ! 🍒🔔💎🎰"
        ),
    },
    "vendredi": {
        "choice_name": "vendredi",
        "default_amount": 75,
        "default_winners": 3,
        "default_duration_minutes": 0,
        "title": "🎰 Giveaway du Vendredi",
        "description": (
            "🏆 Giveaway **VENDREDI** en cours ! 🏆\n\n"
            "💰 Cash total : **{amount}$**\n"
            "👥 Gagnant(s) : **{winners}**\n"
            "💵 Gain par personne : **{per_winner}$**\n"
            "⏱️ Fin : {ends_rel}\n\n"
            "Clique sur **Participer** pour entrer dans le tirage."
        ),
        "color": 0xF38BA8,
        "result_title": "🏆 LES GAGNANTS DU VENDREDI ! 🏆",
        "result_description": (
            "🏆 {winner_line} ! 🏆\n"
            "Le tirage au sort vient de désigner les chanceux de la semaine pour le giveaway de {amount}$ ! 🎰✨\n\n"
            "💰 Le Butin : Félicitations aux vainqueurs ! Chaque personne gagne {per_winner}$.\n\n"
            "✅ La Condition : Bravo à nos affiliés KYC 2 qui ont été tirés au sort !\n\n"
            "🤑 GG AUX GAGNANTS ! QUEL BEAU DÉBUT DE WEEK-END ! 💸🔥\n"
            "Rendez-vous vendredi prochain pour remettre ça ! 🍒🔔💎🎰"
        ),
    },
    "mensuel": {
        "choice_name": "mensuel",
        "default_amount": 90,
        "default_winners": 3,
        "default_duration_minutes": 0,
        "title": "🎰 Giveaway Mensuel",
        "description": (
            "🏆 Giveaway **MENSUEL** en cours ! 🏆\n\n"
            "💰 Cagnotte : **{amount}$**\n"
            "👥 Classement gagnant : **{winners}** place(s)\n"
            "⏱️ Fin : {ends_rel}\n\n"
            "Clique sur **Participer** pour être dans le tirage final."
        ),
        "color": 0xA6E3A1,
        "result_title": "🏆 LES CHAMPIONS DU MOIS ! 🏆",
        "result_description": (
            "🏆 LES CHAMPIONS DU MOIS ! 🏆\n"
            "Le classement final du Giveaway Mensuel est tombé ! La fidélité sur le stream a payé ! 🎰✨\n\n"
            "Voici nos grands vainqueurs :\n{monthly_lines}\n\n"
            "✨ Bravo à tous, affiliés et non-affiliés, pour votre présence active !\n\n"
            "🤑 GG AUX GAGNANTS ! On remet les compteurs à zéro pour le mois prochain, alors soyez prêts à taper les mots clés sur le chat ! 🎰🍒🔔🤑"
        ),
    },
    "premier": {
        "choice_name": "premier",
        "default_amount": 30,
        "default_winners": 1,
        "default_duration_minutes": 0,
        "title": "🎰 Giveaway Premier",
        "description": (
            "🏆 Giveaway **PREMIER** en cours ! 🏆\n\n"
            "💰 Butin : **{amount}$**\n"
            "👥 Gagnant(s) : **{winners}**\n"
            "⏱️ Fin : {ends_rel}\n\n"
            "Clique sur **Participer** pour entrer dans le tirage."
        ),
        "color": 0xFFD166,
        "result_title": "🏆 ALERTE GAGNANT GAMDOM ! 🏆",
        "result_description": (
            "🏆 ALERTE GAGNANT GAMDOM AUJOURD'HUI C'EST {winner_line} ! 🏆\n"
            "La rapidité a payé cette semaine ! ⚡🎰\n\n"
            "💰 Le Butin : Félicitations au(x) premier(s) 19EP visible(s) dans le chat Gamdom qui remporte(nt) chacun {amount}$ !\n\n"
            "🎰 Type de Giveaway : Un tirage aléatoire par semaine qui récompense les plus réactifs !\n\n"
            "🌍 Info : Ce gain était ouvert à tous, affiliés ou non !\n\n"
            "🤑 GG À TOI ! Reste bien attentif sur le chat Gamdom pour le prochain drop ! 🍒🔔💎🤑"
        ),
    },
    "tournoi": {
        "choice_name": "tournoi",
        "default_amount": 60,
        "default_winners": 2,
        "default_duration_minutes": 0,
        "title": "🎰 Tournoi du Dimanche",
        "description": (
            "🏆 Tournoi **DIMANCHE** en cours ! 🏆\n\n"
            "💰 Cash total : **{amount}$**\n"
            "👥 Gagnant(s) : **{winners}**\n"
            "⏱️ Fin : {ends_rel}\n\n"
            "Clique sur **Participer** pour entrer dans le tournoi."
        ),
        "color": 0x9B59B6,
        "result_title": "🏆 LES GAGNANTS DU DIMANCHE ! 🏆",
        "result_description": (
            "🏆 LES GAGNANTS DU DIMANCHE ! 🏆\n"
            "🏆 {winner_line} !!! 🏆\n"
            "Le verdict est tombé pour le tournoi de bonus par équipe ! 🎰✨\n\n"
            "{tournoi_cash_line}\n\n"
            "✅ Bravo à tous pour votre participation dans ce tournoi !\n\n"
            "🤑 GG AUX GAGNANTS ! 💸🔥\n"
            "Rendez-vous dimanche prochain pour le prochain tournoi ! 🍒🔔💎🎰"
        ),
    },
}


def template_defaults(template_key: str) -> Tuple[int, int, int]:
    """
    Retourne (amount_eur, winner_count, duration_minutes) pour un template.
    """
    t = TEMPLATES.get(template_key) or TEMPLATES["stream"]
    amount = int(t.get("default_amount", 5))
    winners = int(t.get("default_winners", 1))
    duration = int(t.get("default_duration_minutes", 60))
    return amount, winners, duration


def _ends_tags(ends_ts: int) -> Tuple[str, str]:
    """Ligne relative + absolue (Discord auto-format horaires)."""
    rel = f"<t:{ends_ts}:R>"
    abs_ = f"<t:{ends_ts}:f>"
    return rel, abs_


def _format_per_winner(amount_eur: int, winner_count: int) -> str:
    """Retourne le montant gagné par personne, formaté proprement."""
    n = max(1, int(winner_count))
    value = float(amount_eur) / float(n)
    return str(int(value)) if value.is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")


def build_embed_fields(
    template_key: str,
    *,
    amount_eur: int,
    winner_count: int,
    ends_ts: int,
) -> Tuple[str, str, int]:
    """Retourne (title, description, color) pour discord.Embed."""
    t = TEMPLATES.get(template_key) or TEMPLATES["stream"]
    ends_rel, ends_abs = _ends_tags(ends_ts)
    desc = str(t["description"]).format(
        amount=amount_eur,
        winners=winner_count,
        per_winner=_format_per_winner(amount_eur, winner_count),
        ends_rel=ends_rel,
        ends_abs=ends_abs,
    )
    return str(t["title"]), desc, int(t["color"])


def build_result_fields(
    template_key: str,
    *,
    amount_eur: int,
    winner_mentions: List[str],
) -> Tuple[str, str, int]:
    t = TEMPLATES.get(template_key) or TEMPLATES["stream"]
    if not winner_mentions:
        winner_line = "personne"
    elif len(winner_mentions) == 1:
        winner_line = winner_mentions[0]
    elif len(winner_mentions) == 2:
        winner_line = f"{winner_mentions[0]} et {winner_mentions[1]}"
    else:
        winner_line = ", ".join(winner_mentions[:-1]) + f" et {winner_mentions[-1]}"
    monthly_prizes = [50, 25, 15]
    monthly_medals = ["🥇", "🥈", "🥉"]
    monthly_lines = []
    for i, mention in enumerate(winner_mentions[:3]):
        prize = monthly_prizes[i]
        medal = monthly_medals[i]
        monthly_lines.append(f"{medal} Place {i + 1} : {mention} Repart avec {prize}$ !")
    if not monthly_lines:
        monthly_lines.append("Aucun participant ce mois-ci.")
    tournoi_cash_line = (
        "💰 Le Cash : Félicitations au gagnant ! tu repars avec 60$ ( C'est énorme !!! )"
        if len(winner_mentions) <= 1
        else "💰 Le Cash : Félicitations à l'équipe victorieuse ! Vous repartez avec 60$ à vous partager."
    )
    desc = str(t.get("result_description", "Gagnant(s) : {winner_line}")).format(
        amount=amount_eur,
        winner_line=winner_line,
        per_winner=_format_per_winner(amount_eur, len(winner_mentions)),
        tournoi_cash_line=tournoi_cash_line,
        monthly_lines="\n\n".join(monthly_lines),
    )
    title = str(t.get("result_title", "Giveaway terminé"))
    return title, desc, int(t["color"])


def footer_participants(n: int) -> str:
    if n <= 0:
        return "Aucun participant pour l’instant · Clique sur Participer"
    if n == 1:
        return "1 participant"
    return f"{n} participants"
