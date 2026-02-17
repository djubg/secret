# Architecture Client-Serveur

## Vue d'ensemble

```mermaid
flowchart LR
    U[Utilisateur] --> GUI[Desktop GUI PySide6]
    GUI --> LC[license_client]
    GUI --> YC[yolo_engine]
    GUI --> UP[updater]
    GUI --> CFG[config]
    GUI --> CR[utils/crypto AES+HMAC]
    LC --> API[FastAPI Backend]
    UP --> API
    API --> DB[(SQLite/PostgreSQL)]
    ADM[Admin Dashboard] --> API
```

## Architecture backend

```mermaid
flowchart TD
    MAIN[app.main] --> ROUTER1[/generate_key]
    MAIN --> ROUTER2[/activate]
    MAIN --> ROUTER3[/validate]
    MAIN --> ROUTER4[/updates/latest]
    MAIN --> DASH[/admin]
    ROUTER1 --> LS[LicenseService]
    ROUTER2 --> LS
    ROUTER3 --> LS
    ROUTER4 --> US[UpdateService]
    LS --> SEC[Hash key + HWID hash]
    LS --> DB[(license_keys)]
```

## Flowchart Activation Licence

```mermaid
flowchart TD
    A[App launch] --> B{Local key exists?}
    B -- No --> C[Prompt user key]
    B -- Yes --> D[GET /validate with key + HWID]
    D --> E{Valid?}
    E -- Yes --> F[Full access]
    E -- No --> L[Block access + ask license key]
    C --> M[POST /activate]
    M --> N{Activation success?}
    N -- Yes --> O[Store key AES + HMAC]
    O --> F
    N -- No --> L
```
