# Tripoora Travel Platform

Tripoora is a Flask-based multi-role travel platform for travelers, hotel owners, transport providers, travel agencies, and admins.

## Production-Ready Setup

### 1) Create and activate virtual environment

```bash
python -m venv .venv
```

Windows PowerShell:

```bash
.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Configure environment

Copy `.env.example` to `.env` and update values:

- `SECRET_KEY` with a long random string
- `DATABASE_URL` with your PostgreSQL credentials
- API keys (`GEMINI_API_KEY`, `UNSPLASH_ACCESS_KEY`, `RAPIDAPI_KEY`) if used
- `AUTO_CREATE_TABLES=0` in production

### 4) Run locally (development)

```bash
python run_app.py
```

### 5) Run in production

```bash
gunicorn --bind 0.0.0.0:5000 wsgi:app
```

The included `Procfile` supports PaaS deployment where `$PORT` is injected.

## Deployment Checklist

- Use managed PostgreSQL with backups enabled
- Set `APP_ENV=production` and `FLASK_DEBUG=0`
- Set `SESSION_COOKIE_SECURE=1` behind HTTPS
- Keep secrets only in environment variables
- Disable `AUTO_CREATE_TABLES` in production
- Run schema/data migration scripts before release
- Add monitoring and error logging in your hosting platform

## Notes

- The application includes many utility scripts (`create_*`, `migrate_*`, `fix_*`) for database/data setup.
- For long-term maintainability, consider moving to a formal migration workflow (for example Alembic/Flask-Migrate).
