"""
Liste initiale points : (clé normalisée, nom affiché, points à rajouter).
La colonne « total » en base commence à 0 ; tu la mets à jour avec /point modifier.
"""

from typing import List, Tuple

POINT_INITIAL: List[Tuple[str, str, int]] = [
    ("bweh", "bweh", 2),
    ("sulli", "sulli", 3),
    ("oni", "oni", 1),
    ("beubeu", "Beubeu", 1),
    ("danchoa", "Danchoa", 1),
    ("gaylord", "Gaylord", 2),
    ("leo", "Leo", 1),
    ("azopex", "Azopex", 1),
    ("solana", "solana", 1),
    ("sparta", "Sparta", 1),
    ("bxou", "bxou", 1),
    ("maxime", "Maxime", 1),
    ("boubou", "Boubou", 1),
]


def normalize_point_key(name: str) -> str:
    return name.strip().lower()
