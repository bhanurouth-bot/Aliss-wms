# src/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Pet Products ERP"
    DATABASE_URL: str = "sqlite:///./pet_erp.db"
    
    # --- ADD THESE JWT SETTINGS ---
    SECRET_KEY: str = "super_secret_erp_key_change_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120 # Tokens expire in 2 hours

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()