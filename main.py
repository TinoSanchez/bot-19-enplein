"""
Point d'entrée pour les hébergeurs (PebbleHost, etc.) qui lancent `main.py` par défaut.
"""
import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    runpy.run_path(str(root / "bot.py"), run_name="__main__")
