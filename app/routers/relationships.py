from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from .. import models

router = APIRouter()

@router.get("/relationships")
def get_relationships(db: Session = Depends(get_db)):
    relationships = db.query(models.Relationship).all()
    return relationships 