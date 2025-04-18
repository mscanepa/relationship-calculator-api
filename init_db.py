from database import engine, Base
from models import Relationship, Distribution
import json
import os

def init_db():
    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Load initial data from JSON files
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    
    # Load relationships
    with open(os.path.join(data_dir, "relationships.json"), "r") as f:
        relationships = json.load(f)
    
    # Load distributions
    with open(os.path.join(data_dir, "distribuciones.json"), "r") as f:
        distributions = json.load(f)

    # Create database session
    from sqlalchemy.orm import Session
    db = Session(bind=engine)

    try:
        # Insert relationships
        for rel in relationships:
            db_relationship = Relationship(
                code=rel["code"],
                name=rel["name"],
                description=rel.get("description", ""),
                min_cm=rel["min_cm"],
                max_cm=rel["max_cm"],
                promedio_cm=rel["promedio_cm"],
                generation=rel.get("generation", 0)
            )
            db.add(db_relationship)

        # Insert distributions
        for code, hist_data in distributions.items():
            for range_str, count in hist_data.items():
                range_start, range_end = map(float, range_str.split("-"))
                db_distribution = Distribution(
                    relationship_code=code,
                    range_start=range_start,
                    range_end=range_end,
                    count=count
                )
                db.add(db_distribution)

        db.commit()
        print("Database initialized successfully!")
    except Exception as e:
        db.rollback()
        print(f"Error initializing database: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    init_db() 