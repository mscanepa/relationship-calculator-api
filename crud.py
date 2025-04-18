from sqlalchemy.orm import Session
from models import Relationship, Distribution, Analysis
from typing import List, Optional
from datetime import datetime

# Relationship CRUD operations
def get_relationship(db: Session, code: str) -> Optional[Relationship]:
    return db.query(Relationship).filter(Relationship.code == code).first()

def get_relationships(db: Session, skip: int = 0, limit: int = 100) -> List[Relationship]:
    return db.query(Relationship).offset(skip).limit(limit).all()

def create_relationship(db: Session, relationship: dict) -> Relationship:
    db_relationship = Relationship(**relationship)
    db.add(db_relationship)
    db.commit()
    db.refresh(db_relationship)
    return db_relationship

# Distribution CRUD operations
def get_distribution(db: Session, relationship_code: str) -> List[Distribution]:
    return db.query(Distribution).filter(Distribution.relationship_code == relationship_code).all()

def create_distribution(db: Session, distribution: dict) -> Distribution:
    db_distribution = Distribution(**distribution)
    db.add(db_distribution)
    db.commit()
    db.refresh(db_distribution)
    return db_distribution

# Analysis CRUD operations
def create_analysis(db: Session, analysis: dict) -> Analysis:
    db_analysis = Analysis(**analysis)
    db.add(db_analysis)
    db.commit()
    db.refresh(db_analysis)
    return db_analysis

def get_analyses(db: Session, skip: int = 0, limit: int = 100) -> List[Analysis]:
    return db.query(Analysis).offset(skip).limit(limit).all()
