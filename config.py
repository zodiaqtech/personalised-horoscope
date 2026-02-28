from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Vedic Astro API
    VEDIC_ASTRO_API_KEY: str = "dcdb25dd-081c-5ee7-bfec-a986788bc4d2"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_TRANSIT_TTL: int = 86400  # 24 hours in seconds

    # MongoDB (stubbed — not used until explicitly enabled)
    MONGODB_URI: str = "mongodb+srv://amit:VOcXDFLPnB05seWk@cluster0.gwiaz9l.mongodb.net/myAppDB"
    MONGODB_DB_NAME: str = "myAppDB"
    MONGODB_ENABLED: bool = False  # Set True when ready to connect

    # Rules file path
    RULES_FILE: str = "rules/BPHS_Level2_200_Rules.json"

    class Config:
        env_file = ".env"
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
