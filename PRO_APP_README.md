# Pro Desktop License Suite

Implémentation complète demandée:

- Client desktop GUI professionnel (PySide6)
- Système de licence sécurisé (activation HWID + expiration + stockage AES + HMAC)
- Flux licence uniquement par cle (sans fallback externe)
- Backend FastAPI + base de données SQLAlchemy (SQLite/PostgreSQL)
- Dashboard admin web
- Système de mise à jour
- Build EXE via PyInstaller

## Arborescence

```
server/
  app/
    api/
    core/
    db/
    models/
    schemas/
    services/
    templates/
    static/
  run_server.py
  schema.sql

desktop_client/
  gui/
  license_client/
  yolo_engine/
  updater/
  utils/crypto/
  config/
  main.py
  build_exe.ps1
```

## Démarrage rapide

1. Lancer le backend: voir `docs/INSTALL_BUILD.md`.
2. Lancer le client desktop.
3. Générer une clé via `POST /generate_key` avec `X-Admin-Token`.
4. Activer la clé dans le client.

## Documentation

- Architecture + flowchart: `docs/ARCHITECTURE.md`
- Installation/build: `docs/INSTALL_BUILD.md`

