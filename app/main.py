from fastapi import FastAPI, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List, Optional, Callable
from . import models, database
from .database import get_db
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import time
from app.config import settings
from app.logger import logger
from app.exceptions import APIException, RateLimitError
from app.routers import relationships, dna_analysis

app = FastAPI(
    title="Genealogy DNA Analysis API",
    description="API for analyzing DNA relationships and shared cM values",
    version="1.0.0",
    docs_url=None,  # Disable default docs
    redoc_url=None,  # Disable default redoc
)

# Rate Limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security Headers Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Request Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    logger.info(
        "Request processed",
        method=request.method,
        url=str(request.url),
        status_code=response.status_code,
        process_time=process_time
    )
    
    return response

# Error Handler
@app.exception_handler(APIException)
async def api_exception_handler(request: Request, exc: APIException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "error_code": exc.error_code
        }
    )

# Custom Swagger UI
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Genealogy DNA Analysis API - Swagger UI",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )

# OpenAPI Schema
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Genealogy DNA Analysis API",
        version="1.0.0",
        description="API for analyzing DNA relationships and shared cM values",
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Include routers
app.include_router(relationships.router, prefix="/api/v1", tags=["relationships"])
app.include_router(dna_analysis.router, prefix="/api/v1", tags=["dna-analysis"])

@app.get("/")
async def root():
    return {"message": "Welcome to the Genealogy DNA Analysis API"}

# Pydantic models for request/response
class RelationshipBase(BaseModel):
    code: str
    nombre: str
    abreviado: str
    promedio_cm: float
    min_cm: float
    max_cm: float

class DistributionBase(BaseModel):
    range: str
    percentage: float

class ProbabilityBase(BaseModel):
    cm: float
    probability: float

class XInheritanceBase(BaseModel):
    sex_combination: str
    can_share: bool

class RelationshipResponse(RelationshipBase):
    distributions: List[DistributionBase]
    probabilities: List[ProbabilityBase]
    x_inheritance: List[XInheritanceBase]

class RelationshipCalculationRequest(BaseModel):
    cm: float = Field(..., gt=0, description="Centimorgans must be greater than 0")
    generacion: Optional[int] = Field(None, ge=0, description="Generation must be non-negative")
    sexo: Optional[str] = Field(None, pattern="^[MF]$", description="Sex must be either M or F")
    x_inheritance: Optional[bool] = None

class RelationshipCalculationResponse(BaseModel):
    code: str
    nombre: str
    abreviado: str
    promedio_cm: float
    min_cm: float
    max_cm: float
    probabilidad: float

class HistogramResponse(BaseModel):
    bins: List[float]
    counts: List[int]

# Endpoints
@app.get("/api/relationships", response_model=List[RelationshipResponse])
def get_relationships(cm: float, db: Session = Depends(get_db)):
    relationships = db.query(models.Relationship).filter(
        models.Relationship.min_cm <= cm,
        models.Relationship.max_cm >= cm
    ).all()
    
    result = []
    for rel in relationships:
        distributions = db.query(models.Distribution).filter(models.Distribution.relationship_code == rel.code).all()
        probabilities = db.query(models.Probability).filter(models.Probability.relationship_code == rel.code).all()
        x_inheritance = db.query(models.XInheritance).filter(models.XInheritance.relationship_code == rel.code).all()
        
        result.append(RelationshipResponse(
            **rel.__dict__,
            distributions=[DistributionBase(range=d.range, percentage=d.percentage) for d in distributions],
            probabilities=[ProbabilityBase(cm=p.cm, probability=p.probability) for p in probabilities],
            x_inheritance=[XInheritanceBase(sex_combination=x.sex_combination, can_share=x.can_share) for x in x_inheritance]
        ))
    return result

@app.post("/api/relationships/calculate", response_model=List[RelationshipCalculationResponse])
def calculate_relationships(request: RelationshipCalculationRequest, db: Session = Depends(get_db)):
    # Get all relationships that match the cM range
    relationships = db.query(models.Relationship).filter(
        models.Relationship.min_cm <= request.cm,
        models.Relationship.max_cm >= request.cm
    ).all()
    
    if not relationships:
        raise HTTPException(status_code=404, detail="No relationships found for the given cM value")
    
    results = []
    for rel in relationships:
        # Get probability curve
        probabilities = db.query(models.Probability).filter(
            models.Probability.relationship_code == rel.code
        ).order_by(models.Probability.cm).all()
        
        # Calculate base probability
        base_prob = 0
        for i in range(len(probabilities) - 1):
            if request.cm >= probabilities[i].cm and request.cm <= probabilities[i+1].cm:
                A = probabilities[i]
                B = probabilities[i+1]
                base_prob = A.probability + ((request.cm - A.cm)/(B.cm - A.cm))*(B.probability - A.probability)
                break
        
        # Adjust probability based on generation if provided
        if request.generacion is not None:
            # Simple adjustment: reduce probability for mismatched generations
            if abs(rel.generacion - request.generacion) > 1:
                base_prob *= 0.5
        
        # Adjust probability based on X inheritance if provided
        if request.x_inheritance is not None:
            x_inheritance = db.query(models.XInheritance).filter(
                models.XInheritance.relationship_code == rel.code
            ).first()
            if x_inheritance and not x_inheritance.can_share and request.x_inheritance:
                base_prob *= 0.1
        
        results.append(RelationshipCalculationResponse(
            code=rel.code,
            nombre=rel.nombre,
            abreviado=rel.abreviado,
            promedio_cm=rel.promedio_cm,
            min_cm=rel.min_cm,
            max_cm=rel.max_cm,
            probabilidad=base_prob
        ))
    
    return results

@app.get("/api/relationships/{code}/histogram", response_model=HistogramResponse)
def get_histogram(code: str, db: Session = Depends(get_db)):
    # Get the relationship
    relationship = db.query(models.Relationship).filter(models.Relationship.code == code).first()
    if not relationship:
        raise HTTPException(status_code=404, detail="Relationship not found")
    
    # Get all probabilities for this relationship
    probabilities = db.query(models.Probability).filter(
        models.Probability.relationship_code == code
    ).order_by(models.Probability.cm).all()
    
    # Create histogram data
    bins = [p.cm for p in probabilities]
    counts = [int(p.probability * 1000) for p in probabilities]  # Scale probabilities for visualization
    
    return HistogramResponse(bins=bins, counts=counts)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    ) 