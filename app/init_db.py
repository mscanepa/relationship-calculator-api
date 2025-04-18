from sqlalchemy import create_engine
from .models import Base
from .database import SQLALCHEMY_DATABASE_URL

def init_db():
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db() 