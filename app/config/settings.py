from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "CashMyMobile API"
    APP_VERSION: str = "1.0.0"
    NODE_ENV: str = "development"
    PORT: int = 8000
    LOG_LEVEL: str = "info"

    # MongoDB
    MONGODB_URI: str = "mongodb://localhost:27017/test"

    # JWT
    JWT_SECRET: str = "your-super-secret-jwt-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE: str = "7d"  # e.g. "7d"

    # CORS
    CORS_ORIGIN: str = "*"

    # Admin
    # Recipients for internal notifications (e.g. counter-offer accepted/declined).
    # Defaults to the support inbox so notifications never silently fall back to a
    # personal address; override via the ADMIN_EMAILS env var (comma-separated).
    ADMIN_EMAILS: str = "support@cashmymobile.co.uk"  # comma-separated
    # Emails allowed to log into the admin panel (OTP login). Managed via the
    # ADMIN_LOGIN_EMAILS env var (comma-separated); also seeded as Admin
    # documents at startup.
    ADMIN_LOGIN_EMAILS: str = "sellyourfone@gmail.com,me.khushnood22@gmail.com,thekhushnoor@gmail.com,hameeduk1@yahoo.co.uk"
    OTP_EXPIRY_MINUTES: int = 10

    # AWS General (used for SES)
    AWS_REGION: str = "ap-south-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None

    # Brevo (transactional email provider — replaces AWS SES)
    BREVO_API_KEY: Optional[str] = None
    FROM_EMAIL_Brevo: str = "noreply@cashmymobile.co.uk"
    FROM_NAME_Brevo: str = "Cash My Mobile"

    # AWS SES (deprecated — kept so existing .env files don't break loading)
    AWS_SES_FROM_EMAIL: str = "noreply@cashmymobile.co.uk"
    AWS_SES_FROM_NAME: str = "Cash My Mobile"
    AWS_SES_VERIFIED_EMAIL: Optional[str] = None

    # AWS S3 (separate credentials)
    AWS_S3_ACCESS_KEY_ID: Optional[str] = None
    AWS_S3_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_S3_REGION: str = "ap-south-1"
    AWS_S3_BUCKET_NAME: str = "zennara-storage"

    # Frontend URLs
    FRONTEND_URL: str = "https://cashmymobile.co.uk/"
    ADMIN_PANEL_URL: str = "https://cashmymobile.co.uk/admin-cashmymobile"

    # Rate Limiting
    RATE_LIMIT_WINDOW_MS: int = 900000  # milliseconds
    RATE_LIMIT_MAX_REQUESTS: int = 100

    # API Gateway
    API_GATEWAY_ENABLED: bool = True

    # Support contact
    SUPPORT_EMAIL: str = "Support@cashmymobile.co.uk"
    SUPPORT_PHONE: str = "03333356679"

    @property
    def ENVIRONMENT(self) -> str:
        return self.NODE_ENV

    @property
    def RATE_LIMIT_WINDOW_SECONDS(self) -> int:
        return self.RATE_LIMIT_WINDOW_MS // 1000

    @property
    def JWT_EXPIRE_DAYS(self) -> int:
        """Parse JWT_EXPIRE like '7d' into integer days."""
        val = self.JWT_EXPIRE.strip()
        if val.endswith("d"):
            return int(val[:-1])
        return 7

    @property
    def DB_NAME(self) -> str:
        """Extract DB name from MONGODB_URI."""
        try:
            part = self.MONGODB_URI.split("/")[-1].split("?")[0]
            return part or "test"
        except Exception:
            return "test"

    @property
    def admin_login_emails_list(self) -> list:
        """ADMIN_LOGIN_EMAILS as a normalized (lowercased, deduped) list."""
        seen = []
        for e in self.ADMIN_LOGIN_EMAILS.split(","):
            email = e.strip().lower()
            if email and email not in seen:
                seen.append(email)
        return seen

    @property
    def cors_origins_list(self) -> list:
        if self.CORS_ORIGIN == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGIN.split(",")]

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
