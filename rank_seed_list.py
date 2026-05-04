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
