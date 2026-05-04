"""
Rangs (Bronze → Emeraude) — données initiales depuis le tableau stream.
tiers: none | bronze | argent | gold | emeraude
"""

from typing import Dict, List, Tuple

from point_seed_list import normalize_point_key

TIER_LABELS: Dict[str, str] = {
    "none": "— Aucun",
    "bronze": "Bronze 15€",
    "argent": "Argent 30€",
    "gold": "Gold 50€",
    "emeraude": "Emeraude 100€",
}

VALID_TIERS = frozenset(TIER_LABELS.keys())


def tier_label(tier: str) -> str:
    return TIER_LABELS.get(tier, tier)


# Libellé sans montant (pour listes : colonne « Rang » distincte de « Montant »).
TIER_NAME_ONLY: Dict[str, str] = {
    "none": "— Aucun",
    "bronze": "Bronze",
    "argent": "Argent",
    "gold": "Gold",
    "emeraude": "Emeraude",
}


def tier_name_only(tier: str) -> str:
    return TIER_NAME_ONLY.get(tier, str(tier))


# Montant « canonique » par palier (quand la base a 0 ou pas encore renseigné).
TIER_DEFAULT_EUR: Dict[str, int] = {
    "none": 0,
    "bronze": 15,
    "argent": 30,
    "gold": 50,
    "emeraude": 100,
}


def tier_default_eur(tier: str) -> int:
    return int(TIER_DEFAULT_EUR.get(tier, 0))


def effective_montant_eur(tier: str, montant_stored: int) -> int:
    """Affichage : montant en base si > 0, sinon seuil du palier (15 / 30 / 50 / 100)."""
    if montant_stored > 0:
        return int(montant_stored)
    return tier_default_eur(tier)


# (clé, nom affiché, rang le plus haut atteint selon le tableau)
RANK_INITIAL: List[Tuple[str, str, str]] = [
    ("gaylord", "Gaylord", "argent"),
    ("oni", "Oni", "bronze"),
    ("kane", "Kane", "gold"),
    ("dorian", "Dorian", "argent"),
    ("sullivan", "sullivan", "argent"),
    ("tazer", "Tazer", "bronze"),
    ("isparta", "isparta", "argent"),
    ("danchoa", "Danchoa", "none"),
    ("bxouu", "bxouu", "none"),
]


def normalize_rank_key(name: str) -> str:
    return normalize_point_key(name)
