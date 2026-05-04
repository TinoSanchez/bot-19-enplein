"""
Liste initiale (Nom, pseudo Gamdom / user name, ID Gamdom, KYC).
Colonne « ID » du tableur = ID Gamdom (Gaylord 47780481, Onizuka 47720994, Tazer 47871236, etc.).
ID Discord côté bot = synthétique 9100… si inconnu.
Si tu avais déjà une base sans ces IDs : /affi modifier id_discord + id_gamdom, ou vider players.db pour re-seed.
"""

from typing import List, Tuple

# (pseudo affichage Discord / nom, pseudo Gamdom ou vide, ID Gamdom ou vide, KYC brut ou vide)
INITIAL_ROWS: List[Tuple[str, str, str, str]] = [
    ("Gaylord", "Gaylord", "47780481", "Oui"),
    ("Kane", "Kanekisk", "", "Oui"),
    ("Gunjir", "", "", ""),
    ("Solana", "", "", ""),
    ("Sullivan", "Sully", "", ""),
    ("dorian", "Dorian", "", ""),
    ("max", "Picsou", "", ""),
    ("megane", "Lamegs", "", ""),
    ("flash", "Flash", "", ""),
    ("oceane", "Océ", "", ""),
    ("raccouch", "Raccouch", "", ""),
    ("raph", "Raph", "", ""),
    ("Bastien", "lemilli", "", ""),
    ("Skygirl", "", "", ""),
    ("Jakkou", "", "", ""),
    ("Beubeu", "", "", ""),
    ("Teddy", "Stiff", "", ""),
    ("iggy", "error404", "", "Oui"),
    ("Quentin", "", "", ""),
    ("Onizuka", "19EpLeon", "47720994", "Oui"),
    ("larichesse", "", "", ""),
    ("piratho", "", "", ""),
    ("Tazer", "", "47871236", ""),
    ("isparta", "", "47873277", ""),
    ("danchoaenplein19", "", "47875305", ""),
    ("bixounours", "", "47877942", "oui"),
]

# Préfixe IDs Discord « placeholder » (chiffres uniquement, compatibles /affi fiche).
SYNTH_DISCORD_BASE = 910000000000000001
