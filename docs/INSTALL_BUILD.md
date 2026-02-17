# Installation et Build

## 1. Backend serveur

```bash
cd server
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env  # Windows
# cp .env.example .env  # Linux/Mac
python run_server.py
```

API disponible sur `http://127.0.0.1:8000`.

## 2. Client desktop

```bash
cd desktop_client
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate
pip install -r requirements.txt
set PRO_API_BASE_URL=http://127.0.0.1:8000   # URL backend fixee par l'owner
set PYTHONPATH=..        # Windows
# export PYTHONPATH=..   # Linux/Mac
python main.py
```

Le client pilote `../main.py` (application principale) et sauvegarde les réglages moteur dans `../options.py`.

## 3. Génération checksums anti-tamper

```bash
cd desktop_client
set PYTHONPATH=..        # Windows
python tools/generate_checksums.py
```

## 4. Build EXE / App

### Windows (EXE)

```powershell
cd desktop_client
.venv\Scripts\activate
.\build_exe.ps1
```

Résultat: `desktop_client/dist/ProLicenseDesktop.exe`

### Linux / Mac

```bash
cd desktop_client
source .venv/bin/activate
bash build_app.sh
```

Résultat: `desktop_client/dist/ProLicenseDesktop`

## 5. Endpoints REST

- `POST /generate_key` (admin, header `X-Admin-Token`)
- `POST /activate`
- `GET /validate`
- `GET /updates/latest`
- `GET /admin` (dashboard)

## 6. Sécurité incluse

- Hash serveur des clés + hash HWID côté backend.
- Liaison 1 machine / 1 clé (activation unique).
- Expiration `1h`, `1d`, `30d`, `lifetime`.
- Stockage local client chiffré AES-GCM.
- Signature HMAC locale de la clé.
- Détection debugger basique + vérification checksums.
