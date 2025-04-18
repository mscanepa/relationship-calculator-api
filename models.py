from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Relationship(Base):
    __tablename__ = "relationships"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    name = Column(String)
    description = Column(String)
    min_cm = Column(Float)
    max_cm = Column(Float)
    promedio_cm = Column(Float)
    generation = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Distribution(Base):
    __tablename__ = "distributions"

    id = Column(Integer, primary_key=True, index=True)
    relationship_code = Column(String, ForeignKey("relationships.code"))
    range_start = Column(Float)
    range_end = Column(Float)
    count = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    relationship = relationship("Relationship")

class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    cm_value = Column(Float)
    generation = Column(String, nullable=True)
    sex = Column(String, nullable=True)
    x_inheritance = Column(Boolean, nullable=True)
    segments = Column(Integer, nullable=True)
    largest_segment = Column(Float, nullable=True)
    endogamy_level = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
