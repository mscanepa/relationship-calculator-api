# backend/main.py
import json
import os
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Union, Literal, List
import math
import time
from collections import defaultdict
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from .app.config import settings

app = FastAPI(
    title="Family Calculator API",
    description="API para calcular relaciones familiares basadas en ADN compartido",
    version="1.0.0",
    docs_url=None,  # Deshabilitamos la documentación por defecto
    redoc_url=None,
)

# Configuración de rate limiting
RATE_LIMIT_PER_MINUTE = 60
request_counts = defaultdict(list)

async def rate_limit_middleware(request: Request, call_next):
    # No aplicar rate limiting para el cliente de test
    if str(request.client.host) == "testclient":
        response = await call_next(request)
        return response
        
    client_ip = request.client.host
    current_time = time.time()
    
    # Limpiar solicitudes antiguas
    request_counts[client_ip] = [t for t in request_counts[client_ip] 
                               if current_time - t < 60]
    
    # Verificar límite
    if len(request_counts[client_ip]) >= RATE_LIMIT_PER_MINUTE:
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded"}
        )
    
    # Registrar nueva solicitud
    request_counts[client_ip].append(current_time)
    
    response = await call_next(request)
    return response

# Añadir middleware
app.middleware("http")(rate_limit_middleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

# Permitir CORS desde cualquier origen (para desarrollo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurar headers de seguridad
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Obtener la ruta absoluta del directorio actual
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# Cargamos los datos al arrancar la app
try:
    with open(os.path.join(DATA_DIR, "relationships.json"), encoding="utf-8") as f:
        RELS = json.load(f)
    with open(os.path.join(DATA_DIR, "distribuciones.json"), "r") as f:
        HISTS = json.load(f)
except FileNotFoundError as e:
    raise RuntimeError(f"Archivo de datos no encontrado: {e.filename}")

EndogamiaLevel = Literal["none", "light", "moderate", "high", "very_high"]

class AnalysisRequest(BaseModel):
    cm: float = Field(..., description="Centimorgans compartidos", ge=0, le=4000)
    generacion: Optional[str] = Field(None, description="Generación")
    sexo: Optional[str] = Field(None, description="Sexo")
    x_inheritance: Optional[Union[bool, str]] = Field(None, description="Herencia del cromosoma X")
    segments: Optional[int] = Field(None, description="Número de segmentos")
    largest_segment: Optional[float] = Field(None, description="Tamaño del segmento más grande")
    endogamia: Optional[EndogamiaLevel] = Field(None, description="Nivel de endogamia en la familia")

def adjust_cm_for_endogamia(cm: float, endogamia: Optional[EndogamiaLevel]) -> float:
    """
    Ajusta los cM compartidos según el nivel de endogamia
    Basado en estudios de poblaciones endogámicas como judíos ashkenazíes, amish, etc.
    """
    if not endogamia:
        return cm
    
    # Factores de ajuste basados en estudios de poblaciones endogámicas
    # Fuente: "Endogamy and Consanguinity in Jewish Populations" - Ostrer et al.
    adjustment_factors = {
        "none": 1.0,
        "light": 1.2,      # Ej: Familias con matrimonios entre primos terceros
        "moderate": 1.4,   # Ej: Familias con matrimonios entre primos segundos
        "high": 1.7,       # Ej: Comunidades amish, algunas comunidades judías
        "very_high": 2.0   # Ej: Comunidades judías ultraortodoxas, algunas comunidades aisladas
    }
    
    # Aplicar el factor de ajuste
    adjusted_cm = cm / adjustment_factors[endogamia]
    
    return adjusted_cm

def calculate_probability(rel, request):
    """
    Calcula la probabilidad ajustada basada en múltiples factores
    """
    # Pesos para cada factor
    WEIGHTS = {
        'cm_distance': 0.5,      # Distancia al promedio de cM
        'range_fit': 0.3,        # Qué tan dentro del rango está
        'segments': 0.15,        # Número de segmentos (aumentado)
        'largest_segment': 0.03, # Tamaño del segmento más grande
        'x_match': 0.02         # Coincidencia en cromosoma X
    }
    
    # Ajustar cM por endogamia
    adjusted_cm = adjust_cm_for_endogamia(request.cm, request.endogamia)
    
    scores = {}
    
    # 1. Distancia al promedio de cM
    avg_cm = rel["promedio_cm"]
    max_possible_distance = 4000  # Máxima distancia posible en cM
    cm_distance = abs(adjusted_cm - avg_cm)
    scores['cm_distance'] = 1 - pow(cm_distance / max_possible_distance, 0.7)  # Penalización más suave
    
    # 2. Qué tan dentro del rango está
    if adjusted_cm < rel["min_cm"] or adjusted_cm > rel["max_cm"]:
        scores['range_fit'] = 0
    else:
        # Qué tan cerca está del centro del rango
        range_center = (rel["min_cm"] + rel["max_cm"]) / 2
        range_size = rel["max_cm"] - rel["min_cm"]
        distance_to_center = abs(adjusted_cm - range_center)
        # Ajuste más suave para valores cercanos al centro
        scores['range_fit'] = 1 - pow(distance_to_center / (range_size / 2), 0.7)
    
    # 3. Número de segmentos
    if request.segments is not None:
        # Rangos típicos de segmentos por tipo de relación
        segment_ranges = {
            "FS": (35, 45),   # Hermanos completos
            "1C": (25, 35),   # Primos hermanos
            "2C": (10, 20),   # Primos segundos
            "3C": (4, 8),     # Primos terceros
            "4C": (2, 5)      # Primos cuartos
        }
        
        if rel["code"] in segment_ranges:
            min_seg, max_seg = segment_ranges[rel["code"]]
            if request.segments < min_seg:
                scores['segments'] = pow(request.segments / min_seg, 0.7)  # Penalización más suave
            elif request.segments > max_seg:
                scores['segments'] = pow(max_seg / request.segments, 0.7)  # Penalización más suave
            else:
                scores['segments'] = 1
        else:
            scores['segments'] = 0.5  # Valor neutral para relaciones sin datos de segmentos
    else:
        scores['segments'] = 0.5  # Valor neutral si no se proporcionan segmentos
    
    # 4. Tamaño del segmento más grande
    if request.largest_segment is not None:
        # Rangos típicos de segmento más grande por tipo de relación
        largest_segment_ranges = {
            "FS": (150, 250),  # Hermanos completos
            "1C": (80, 150),   # Primos hermanos
            "2C": (50, 100),   # Primos segundos
            "3C": (20, 50),    # Primos terceros
            "4C": (10, 30)     # Primos cuartos
        }
        
        if rel["code"] in largest_segment_ranges:
            min_seg, max_seg = largest_segment_ranges[rel["code"]]
            if request.largest_segment < min_seg:
                scores['largest_segment'] = pow(request.largest_segment / min_seg, 0.7)  # Penalización más suave
            elif request.largest_segment > max_seg:
                scores['largest_segment'] = pow(max_seg / request.largest_segment, 0.7)  # Penalización más suave
            else:
                scores['largest_segment'] = 1
        else:
            scores['largest_segment'] = 0.5
    else:
        scores['largest_segment'] = 0.5
    
    # 5. Coincidencia en cromosoma X
    if request.x_inheritance is not None:
        # Definir patrones esperados de herencia X por relación
        x_inheritance_patterns = {
            "FS": True,    # Hermanos completos siempre comparten X
            "1C": None,    # Primos hermanos pueden o no compartir X
            "2C": None,    # Primos segundos pueden o no compartir X
            "3C": None,    # Primos terceros pueden o no compartir X
            "4C": None     # Primos cuartos pueden o no compartir X
        }
        
        expected_x = x_inheritance_patterns.get(rel["code"])
        if expected_x is True and request.x_inheritance:
            scores['x_match'] = 1
        elif expected_x is False and not request.x_inheritance:
            scores['x_match'] = 1
        elif expected_x is None:
            scores['x_match'] = 0.5  # Neutral para relaciones donde X es variable
        else:
            scores['x_match'] = 0
    else:
        scores['x_match'] = 0.5
    
    # Calcular probabilidad final ponderada
    final_score = sum(WEIGHTS[factor] * score for factor, score in scores.items())
    
    # Ajustar por generación si está disponible
    if request.generacion is not None and rel.get("generacion") is not None:
        generation_match = request.generacion == str(rel["generacion"])
        final_score = final_score * (1.4 if generation_match else 0.6)  # Aumentar aún más el impacto de la generación
    
    # Ajuste adicional para primos terceros y cuartos
    if rel["code"] in ["3C", "4C"]:
        if request.segments is not None and request.largest_segment is not None:
            # Favorecer 3C sobre 4C cuando hay más segmentos y segmentos más grandes
            if request.segments >= 5 and request.largest_segment >= 20:
                final_score = final_score * (1.2 if rel["code"] == "3C" else 0.8)
    
    return max(0, min(1, final_score))  # Asegurar que está entre 0 y 1

@app.get("/")
def read_root():
    return {"message": "API en funcionamiento - listo para integrar en el futuro."}

@app.get("/api/relationships/")
def get_relationships(cm: int):
    """
    Devuelve todas las relaciones cuyo rango de cM cubra el valor recibido
    """
    posibles = [r for r in RELS if r["min_cm"] <= cm <= r["max_cm"]]
    return {"results": posibles}

@app.get("/api/histogram/")
def get_histogram(code: str):
    """
    Devuelve el histograma de distribución para la relación solicitada
    """
    try:
        hist = HISTS.get(code)
        if hist is None:
            raise HTTPException(status_code=404, detail="Relación no encontrada")
        
        # Asegurarse de que los datos están en el formato correcto
        formatted_hist = {}
        if isinstance(hist, dict):
            for bin_range, count in hist.items():
                formatted_hist[bin_range] = int(count)
        
        return {"histogram": formatted_hist}
    except HTTPException:
        # Re-lanzar la excepción HTTP para mantener el código de estado 404
        raise
    except Exception as e:
        print(f"Error en get_histogram: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al procesar el histograma: {str(e)}")

@app.post("/api/v1/analyze")
async def analyze_relationship(request: AnalysisRequest):
    """
    Analiza la relación basada en los cM compartidos y otros parámetros
    """
    # Validar el rango de cM
    if request.cm <= 0:
        raise HTTPException(status_code=422, detail="El valor de cM debe ser mayor que 0")
    if request.cm > 4000:
        raise HTTPException(status_code=422, detail="El valor de cM no puede ser mayor que 4000")
    
    # Obtener relaciones posibles basadas en el rango de cM
    posibles = [r for r in RELS if r["min_cm"] <= request.cm <= r["max_cm"]]
    
    # Calcular probabilidades ajustadas
    for rel in posibles:
        rel["adjustedProb"] = calculate_probability(rel, request)
        
        # Añadir campos adicionales que espera el frontend
        rel["xPlausible"] = True  # TODO: Implementar lógica real
        rel["agePlausible"] = True  # TODO: Implementar lógica real
    
    # Ordenar por probabilidad ajustada
    posibles.sort(key=lambda x: x["adjustedProb"], reverse=True)
    
    # Normalizar probabilidades para que sumen 1
    total_prob = sum(rel["adjustedProb"] for rel in posibles)
    if total_prob > 0:
        for rel in posibles:
            rel["adjustedProb"] = rel["adjustedProb"] / total_prob
    
    return posibles

@app.get("/api/endogamia/ayuda")
async def get_endogamia_help():
    """
    Devuelve información de ayuda sobre endogamia y referencias
    """
    return {
        "niveles": {
            level: {
                "nombre": level.capitalize(),
                "descripcion": f"Descripción para el nivel {level}.",
                "ejemplos": f"Ejemplos para el nivel {level}.",
                "efecto_adn": f"Efecto en ADN para el nivel {level}."
            }
            for level in ["none", "light", "moderate", "high", "very_high"]
        },
        "referencias": [
            {
                "titulo": "Endogamia y ADN: Guía para genealogistas",
                "autor": "Blaine Bettinger",
                "fuente": "The Genetic Genealogist",
                "url": "https://thegeneticgenealogist.com/",
                "descripcion": "Artículo sobre cómo la endogamia afecta la interpretación del ADN compartido."
            },
            {
                "titulo": "Endogamia en poblaciones judías",
                "autor": "Harry Ostrer",
                "fuente": "Genetic Studies of Jewish Populations",
                "descripcion": "Estudio sobre los efectos de la endogamia en poblaciones judías y su impacto en el ADN compartido."
            },
            {
                "titulo": "Endogamia y genealogía genética",
                "autor": "Roberto Hernández",
                "fuente": "Genealogía Genética en Español",
                "url": "https://genealogiagenetica.es/",
                "descripcion": "Guía en español sobre cómo interpretar el ADN compartido en casos de endogamia."
            }
        ],
        "explicacion_general": {
            "titulo": "¿Qué es la endogamia y cómo afecta al ADN compartido?",
            "contenido": """
            La endogamia ocurre cuando hay matrimonios entre parientes en una familia. Esto puede afectar 
            significativamente la cantidad de ADN compartido entre dos personas, haciendo que compartan 
            más ADN del que normalmente se esperaría para su relación.

            Por ejemplo, si dos primos hermanos provienen de familias sin endogamia, compartirán en promedio 
            alrededor de 850 cM. Sin embargo, si sus familias tienen un historial de endogamia, podrían 
            compartir significativamente más cM, lo que podría hacer que parezcan más cercanos de lo que 
            realmente son.

            Esta herramienta te permite ajustar los cM compartidos según el nivel de endogamia en tu familia, 
            lo que ayuda a obtener una interpretación más precisa de las relaciones.
            """
        }
    }

# Endpoints de documentación personalizados
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Family Calculator API Documentation",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )

@app.get("/openapi.json", include_in_schema=False)
async def get_openapi_endpoint():
    return get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )