# License Backend (FastAPI)

## Run

```bash
pip install -r requirements.txt
cp .env.example .env
python run_server.py
```

## Admin token

Set `ADMIN_TOKEN` in `.env`, then use header:

`X-Admin-Token: <ADMIN_TOKEN>`

## API

- `POST /hub/generate_key`
- `POST /hub/activate`
- `POST /hub/validate`
- `POST /hub/license/{license_id}/extend`
- `POST /hub/license/{license_id}/revoke`
- `DELETE /hub/license/{license_id}`
- `POST /auth/register`
- `POST /auth/login`
- `GET /me`
- `PATCH /me/profile`
- `POST /me/avatar`
- `GET /patreon_auth`
- `GET /updates/latest`
- `GET /admin`
- `GET /admin/users`
- `POST /admin/license/{license_id}/extend`
- `POST /admin/license/{license_id}/revoke`
- `POST /admin/license/{license_id}/delete`
- `POST /admin/users/{user_id}/disable`
- `POST /admin/users/{user_id}/delete`

## Deploy on Render

1. Push this repository to GitHub.
2. In Render, create a new Web Service from the repo.
3. Render can use `render.yaml` at repo root (Blueprint) or manual settings:
   - Root Directory: `server`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. After first deploy, set `UPDATE_BASE_URL` and `releases.json` URLs to your Render domain:
   - `https://<your-service>.onrender.com/static/downloads/...`
5. Use `/health` to validate runtime.

Notes:
- Current default `DATABASE_URL` is SQLite. On free tiers, filesystem persistence may be limited.
- For production stability, migrate to a managed Postgres database.
