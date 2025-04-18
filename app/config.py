from pydantic_settings import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    # API Configuration
    API_V1_STR: str = os.getenv("API_V1_STR", "/api/v1")
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "Family Calculator API")
    API_DOCS_URL: str = os.getenv("API_DOCS_URL", "/docs")
    API_REDOC_URL: str = os.getenv("API_REDOC_URL", "/redoc")
    
    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    API_BASE_URL: str = os.getenv("API_BASE_URL", f"http://{HOST}:{PORT}")
    
    # CORS Configuration
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"
    
    # Database Configuration
    DATABASE_URL: str
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    
    # Data Files
    RELATIONSHIPS_FILE: str = "data/relationships.json"
    DISTRIBUTIONS_FILE: str = "data/distributions.json"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "app.log"
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Create settings instance
settings = Settings()

# Get CORS origins as list
def get_cors_origins() -> List[str]:
    return settings.CORS_ORIGINS.split(",") 