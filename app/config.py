from pydantic_settings import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Relationship Calculator API"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "API for calculating genetic relationships and shared DNA"
    
    # Server Configuration
    HOST: str = "localhost"
    PORT: int = 8000
    API_BASE_URL: str = "http://localhost:8000"
    
    # CORS Configuration
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    # Database Configuration
    DATABASE_URL: str = "sqlite:///./sql_app.db"
    
    # Security
    SECRET_KEY: str = "your-secret-key-here"
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
    ENVIRONMENT: str = "development"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Create settings instance
settings = Settings()

# Get CORS origins as list
def get_cors_origins() -> List[str]:
    return settings.CORS_ORIGINS 