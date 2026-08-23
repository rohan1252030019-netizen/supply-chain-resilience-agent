"""
app/config.py
Owner: Developer 2 (Backend / Simulation)

Centralized settings object. Every other module should import `settings` from here
instead of calling os.getenv() directly.

SETTINGS GROUPS:
  - Database (MongoDB Atlas)
  - n8n Integration (URLs, shared API key)
  - Groq LLM (provider, model, temperature — served to n8n via /api/v1/config/n8n)
  - Email Notifications (from/to addresses — served to n8n via /api/v1/config/n8n)
  - Business Logic (autonomous approval limit)
  - CORS / Security / Observability

RECEIVES: values from .env (root) or backend/.env
DELIVERS: a singleton `settings` instance used by database.py, api/, routers/, etc.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Database (MongoDB Atlas) ───────────────────────────────────────────────
    MONGO_URI: str = "mongodb://127.0.0.1:27017"
    MONGO_DB_NAME: str = "supplychaindb"

    # ── FastAPI Host / Port ────────────────────────────────────────────────────
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    # URL that n8n uses to reach the backend inside the Docker network.
    # Set to http://backend:8000 in production; http://localhost:8000 for local dev.
    BACKEND_URL: str = "http://backend:8000"

    # ── n8n Integration ────────────────────────────────────────────────────────
    N8N_BASE_URL: str = "http://localhost:5678"
    # Shared secret for n8n ↔ backend authentication (X-API-Key header).
    BACKEND_API_KEY: str = "changeme-secret-key"

    # ── Business Logic ─────────────────────────────────────────────────────────
    # Recovery plans costing MORE than this (USD) require human approval.
    AUTONOMOUS_APPROVAL_LIMIT_USD: float = 50000.0

    # ── Email Notifications ────────────────────────────────────────────────────
    # Served to n8n via GET /api/v1/config/n8n so email addresses are not
    # hard-coded inside workflow node parameters.
    NOTIFY_FROM_EMAIL: str = ""
    APPROVAL_NOTIFY_EMAIL: str = ""
    OPS_ALERT_EMAIL: str = ""

    # ── Groq AI — Post-Analysis LLM Layer ─────────────────────────────────────
    # These are served to n8n via GET /api/v1/config/n8n.
    # GROQ_API_KEY must ALSO be configured as an n8n Credential (Groq API node).
    LLM_PROVIDER: str = "groq"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_TEMPERATURE: float = 0.1

    # ── CORS ───────────────────────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:5173"
    CORS_ALLOWED_METHODS: str = "GET,POST,PUT,DELETE,OPTIONS"

    # ── Security ───────────────────────────────────────────────────────────────
    # Legacy API_KEY: used as fallback by routes_integrations.verify_api_key.
    # Prefer BACKEND_API_KEY for all new endpoints.
    API_KEY: str = ""

    # ── JWT Authentication ─────────────────────────────────────────────────────
    # MUST be set to a strong random secret in production.
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    JWT_SECRET: str = "supply-chain-jwt-secret-change-in-production-abc123xyz"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Controls whether Swagger UI (/docs) and /openapi.json are publicly accessible.
    DOCS_ENABLED: bool = True

    # ── Rate Limiting & Proxy ──────────────────────────────────────────────────
    # Comma-separated trusted reverse-proxy IPs (X-Forwarded-For ignored otherwise).
    TRUSTED_PROXY_IPS: str = ""
    GENERAL_RATE_LIMIT_MAX: int = 60
    GENERAL_RATE_LIMIT_WINDOW: int = 60

    # ── Misc ───────────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def cors_allowed_methods_list(self) -> list[str]:
        return [m.strip().upper() for m in self.CORS_ALLOWED_METHODS.split(",") if m.strip()]

    @property
    def trusted_proxy_ip_list(self) -> list[str]:
        return [ip.strip() for ip in self.TRUSTED_PROXY_IPS.split(",") if ip.strip()]


settings = Settings()
