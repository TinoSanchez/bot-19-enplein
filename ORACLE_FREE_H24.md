## Hebergement gratuit H24 (Oracle Cloud)

Ce projet contient un script automatique: `scripts/oracle_setup.sh`.

### 1) Creer une VM gratuite Oracle
- Oracle Cloud -> Compute -> Instances -> Create instance
- Image: Ubuntu 22.04
- Shape: Always Free (Ampere ou Micro selon disponibilite)
- Ouvrir le port SSH (22) dans la VCN/Security List
- Se connecter en SSH a la VM

### 2) Sur la VM, executer
```bash
git clone https://github.com/TinoSanchez/bot-19-enplein.git
cd bot-19-enplein
sudo bash scripts/oracle_setup.sh
```

Le script demande:
- URL du repo GitHub
- `GUILD_ID` (optionnel)
- `DISCORD_TOKEN` (obligatoire)

### 3) Verifier
```bash
systemctl status bot19 --no-pager
journalctl -u bot19 -f
```

### 4) Mise a jour du bot plus tard
```bash
cd /opt/bot19
sudo -u ubuntu git pull --ff-only
sudo systemctl restart bot19
```
