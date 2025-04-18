from sqlalchemy import Column, Integer, String, Float, JSON, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Relationship(Base):
    __tablename__ = "relationships"
    
    code = Column(String, primary_key=True)
    nombre = Column(String, nullable=False)
    abreviado = Column(String, nullable=False)
    promedio_cm = Column(Float, nullable=False)
    min_cm = Column(Float, nullable=False)
    max_cm = Column(Float, nullable=False)
    generacion = Column(Integer, nullable=False)  # Generación de la relación (1 para hermanos, 2 para primos, etc.)

class Distribution(Base):
    __tablename__ = "distributions"
    
    id = Column(Integer, primary_key=True)
    relationship_code = Column(String, ForeignKey("relationships.code"), nullable=False)
    range = Column(String, nullable=False)
    percentage = Column(Float, nullable=False)

class Probability(Base):
    __tablename__ = "probabilities"
    
    id = Column(Integer, primary_key=True)
    relationship_code = Column(String, ForeignKey("relationships.code"), nullable=False)
    cm = Column(Float, nullable=False)
    probability = Column(Float, nullable=False)

class XInheritance(Base):
    __tablename__ = "x_inheritance"
    
    id = Column(Integer, primary_key=True)
    relationship_code = Column(String, ForeignKey("relationships.code"), nullable=False)
    sex_combination = Column(String, nullable=False)  # Format: "F>M", "M>F", etc.
    can_share = Column(Boolean, nullable=False) 