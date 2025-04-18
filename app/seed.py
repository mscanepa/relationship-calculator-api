import json
from sqlalchemy.orm import Session
from . import models
import os

def load_json_data():
    base_path = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(os.path.dirname(base_path), 'data')
    
    with open(os.path.join(data_path, 'relationships.json'), 'r') as f:
        relationships = json.load(f)
    
    with open(os.path.join(data_path, 'distribuciones.json'), 'r') as f:
        distributions = json.load(f)
    
    with open(os.path.join(data_path, 'probabilidades.json'), 'r') as f:
        probabilities = json.load(f)
    
    with open(os.path.join(data_path, 'xInheritance.json'), 'r') as f:
        x_inheritance = json.load(f)
    
    return relationships, distributions, probabilities, x_inheritance

def seed_database(db: Session):
    relationships, distributions, probabilities, x_inheritance = load_json_data()
    
    # Seed relationships first
    print("Seeding relationships...")
    for rel in relationships:
        db_relationship = models.Relationship(
            code=rel['code'],
            nombre=rel['nombre'],
            abreviado=rel['abreviado'],
            promedio_cm=rel['promedio_cm'],
            min_cm=rel['min_cm'],
            max_cm=rel['max_cm']
        )
        db.add(db_relationship)
    db.commit()
    
    # Seed distributions
    print("Seeding distributions...")
    for code, ranges in distributions.items():
        for range_str, percentage in ranges.items():
            db_distribution = models.Distribution(
                relationship_code=code,
                range=range_str,
                percentage=percentage
            )
            db.add(db_distribution)
    db.commit()
    
    # Seed probabilities
    print("Seeding probabilities...")
    for code, curve in probabilities.items():
        for point in curve:
            db_probability = models.Probability(
                relationship_code=code,
                cm=point['cm'],
                probability=point['p']
            )
            db.add(db_probability)
    db.commit()
    
    # Seed x-inheritance
    print("Seeding x-inheritance...")
    for code, combinations in x_inheritance.items():
        for sex_combination, can_share in combinations.items():
            db_x_inheritance = models.XInheritance(
                relationship_code=code,
                sex_combination=sex_combination,
                can_share=can_share
            )
            db.add(db_x_inheritance)
    db.commit()
    
    print("Database seeding completed successfully!") 