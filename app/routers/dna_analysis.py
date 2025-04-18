from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from .. import models

router = APIRouter()

@router.get("/dna-analysis")
def get_dna_analysis(db: Session = Depends(get_db)):
    return {"message": "DNA Analysis endpoint"} 