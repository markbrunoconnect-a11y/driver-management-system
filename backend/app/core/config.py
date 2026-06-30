import os

class Settings:
    # DMS_DATABASE_URL checked first to avoid Railway auto-injection conflicts
    DATABASE_URL: str = os.environ.get("DMS_DATABASE_URL") or os.environ.get("DATABASE_URL", "sqlite:///./dms_dev.db")
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "change-me-in-production-dms")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12 hours

settings = Settings()
