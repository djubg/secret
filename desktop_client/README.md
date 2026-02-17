# Desktop Client (PySide6)

## Run

```bash
pip install -r requirements.txt
set PRO_API_BASE_URL=http://127.0.0.1:8000   # URL definie par l'owner
set PYTHONPATH=..   # Windows
python main.py
```

## Features

- GUI professionnelle avec état runtime + modèle actif.
- Contrôles Start / Stop / Pause / Restart qui lancent réellement `../main.py`.
- Edition directe des paramètres `options.py` (model path, conf, iou, auto aim/shoot, show_window).
- Gestion licence locale AES + HMAC.
- Vérification licence serveur (HWID binding).
- Saisie de cle obligatoire au lancement si la licence n'est pas valide.
- Logs temps réel + export.
- Thème sombre/clair.
- Vérification de mise à jour.
