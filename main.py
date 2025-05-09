# backend/main.py
import json
import os
import logging
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
from app.config import settings

# Configurar el logger
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=settings.LOG_FILE
)
logger = logging.getLogger(__name__)

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
    person1_age: Optional[int] = Field(None, description="Edad de la primera persona")
    person2_age: Optional[int] = Field(None, description="Edad de la segunda persona")
    generacion: Optional[str] = Field(None, description="Generación")
    sexo: Optional[str] = Field(None, description="Sexo")
    x_inheritance: Optional[Union[bool, str]] = Field(None, description="Herencia del cromosoma X")
    segments: Optional[int] = Field(None, description="Número de segmentos")
    largest_segment: Optional[float] = Field(None, description="Tamaño del segmento más grande")
    endogamia: Optional[EndogamiaLevel] = Field(None, description="Nivel de endogamia en la familia")

def adjust_cm_for_endogamia(cm: float, endogamia: Optional[EndogamiaLevel], relationship_code: str) -> float:
    """
    Ajusta los cM compartidos según el nivel de endogamia y tipo de relación
    """
    if not endogamia:
        return float(cm)
    
    # Factores de ajuste actualizados según tipo de relación
    close_relationship_factors = {
        "none": 1.0,
        "light": 1.1,
        "moderate": 1.2,
        "high": 1.3,
        "very_high": 1.4
    }
    
    distant_relationship_factors = {
        "none": 1.0,
        "light": 1.3,
        "moderate": 1.5,
        "high": 1.8,
        "very_high": 2.0
    }
    
    # Determinar si es una relación cercana o lejana
    close_relationships = {"FS", "1C", "2C", "HS", "PC", "GP", "AU"}
    is_close_relationship = relationship_code in close_relationships
    
    # Seleccionar el factor de ajuste apropiado
    adjustment_factors = close_relationship_factors if is_close_relationship else distant_relationship_factors
    
    # Aplicar el factor de ajuste y asegurar que el resultado sea un float
    adjusted_cm = float(cm) / float(adjustment_factors[endogamia])
    
    return adjusted_cm

def calculate_age_probability(rel, request):
    """
    Calcula la probabilidad basada en la diferencia de edad
    """
    if request.person1_age is None or request.person2_age is None:
        return 0.5  # Valor neutral si no hay información de edad
    
    age_diff = abs(float(request.person1_age) - float(request.person2_age))
    
    # Definir rangos típicos de diferencia de edad por relación
    age_diff_ranges = {
        "FS": (0, 5),      # Hermanos completos
        "1C": (0, 10),     # Primos hermanos
        "2C": (0, 20),     # Primos segundos
        "3C": (0, 30),     # Primos terceros
        "4C": (0, 40),     # Primos cuartos
        "GAU": (20, 40),   # Tío/a abuelo/a
        "GGAU": (40, 60),  # Tío/a bisabuelo/a
        "1C1R": (15, 35),  # Primo hermano una vez removido
        "1C2R": (30, 50),  # Primo hermano dos veces removido
        "H1C": (0, 15)     # Medio primo hermano
    }
    
    if rel["code"] not in age_diff_ranges:
        return 0.5
    
    min_diff, max_diff = age_diff_ranges[rel["code"]]
    
    # Si la diferencia de edad está dentro del rango esperado
    if min_diff <= age_diff <= max_diff:
        # Calcular qué tan cerca está del centro del rango
        range_center = float(min_diff + max_diff) / 2.0
        range_size = float(max_diff - min_diff)
        distance_to_center = abs(age_diff - range_center)
        return float(1.0 - (distance_to_center / (range_size / 2.0)))
    
    # Si está fuera del rango, penalizar más cuanto más lejos esté
    if age_diff < min_diff:
        return float(max(0.0, 1.0 - (min_diff - age_diff) / 10.0))
    else:
        return float(max(0.0, 1.0 - (age_diff - max_diff) / 10.0))

def calculate_probability(rel, request):
    """
    Calcula la probabilidad ajustada basada en múltiples factores
    """
    # Pesos actualizados según nuevas especificaciones
    WEIGHTS = {
        'cm_distance': 0.30,     # 30% - Distancia al promedio de cM
        'range_fit': 0.20,       # 20% - Qué tan dentro del rango está
        'segments': 0.20,        # 20% - Número de segmentos
        'largest_segment': 0.15, # 15% - Tamaño del segmento más grande
        'x_match': 0.05,        # 5% - Coincidencia en cromosoma X
        'age_match': 0.10       # 10% - Coincidencia de edad
    }
    
    # Ajustar cM por endogamia según tipo de relación
    adjusted_cm = float(adjust_cm_for_endogamia(request.cm, request.endogamia, rel["code"]))
    
    scores = {}
    
    # 1. Distancia al promedio de cM con nuevo sistema de suavizado y colchón
    avg_cm = float(rel["promedio_cm"])
    diferencia = abs(adjusted_cm - avg_cm) / avg_cm
    
    if diferencia <= 0.15:  # Colchón del 15%
        scores['cm_distance'] = 1.0
    else:
        scores['cm_distance'] = float(pow(1 - diferencia, 0.5))  # Suavizado con raíz cuadrada
    
    # 2. Qué tan dentro del rango está
    min_cm = float(rel["min_cm"])
    max_cm = float(rel["max_cm"])
    
    if adjusted_cm < min_cm or adjusted_cm > max_cm:
        scores['range_fit'] = 0
    else:
        range_center = (min_cm + max_cm) / 2
        range_size = max_cm - min_cm
        distance_to_center = abs(adjusted_cm - range_center)
        scores['range_fit'] = float(1 - pow(distance_to_center / (range_size / 2), 0.7))
    
    # 3. Número de segmentos
    if request.segments is not None:
        segment_ranges = {
            "FS": (35, 45),
            "1C": (25, 35),
            "2C": (10, 20),
            "3C": (3, 10),  # Ajustado para primos terceros
            "4C": (2, 5)
        }
        
        if rel["code"] in segment_ranges:
            min_seg, max_seg = segment_ranges[rel["code"]]
            if request.segments < min_seg:
                scores['segments'] = float(pow(request.segments / min_seg, 0.7))
            elif request.segments > max_seg:
                scores['segments'] = float(pow(max_seg / request.segments, 0.7))
            else:
                scores['segments'] = 1.0
        else:
            scores['segments'] = 0.5
    else:
        scores['segments'] = 0.5
    
    # 4. Tamaño del segmento más grande
    if request.largest_segment is not None:
        largest_segment_ranges = {
            "FS": (150, 250),
            "1C": (80, 150),
            "2C": (50, 100),
            "3C": (15, 60),  # Ajustado para primos terceros
            "4C": (10, 30)
        }
        
        if rel["code"] in largest_segment_ranges:
            min_seg, max_seg = largest_segment_ranges[rel["code"]]
            if request.largest_segment < min_seg:
                scores['largest_segment'] = float(pow(request.largest_segment / min_seg, 0.7))
            elif request.largest_segment > max_seg:
                scores['largest_segment'] = float(pow(max_seg / request.largest_segment, 0.7))
            else:
                scores['largest_segment'] = 1.0
        else:
            scores['largest_segment'] = 0.5
    else:
        scores['largest_segment'] = 0.5
    
    # 5. Coincidencia en cromosoma X
    if request.x_inheritance is not None:
        x_inheritance_patterns = {
            "FS": True,
            "1C": None,
            "2C": None,
            "3C": None,
            "4C": None
        }
        
        expected_x = x_inheritance_patterns.get(rel["code"])
        if expected_x is True and request.x_inheritance:
            scores['x_match'] = 1.0
        elif expected_x is False and not request.x_inheritance:
            scores['x_match'] = 1.0
        elif expected_x is None:
            scores['x_match'] = 0.5
        else:
            scores['x_match'] = 0.0
    else:
        scores['x_match'] = 0.5
    
    # 6. Coincidencia de edad
    scores['age_match'] = float(calculate_age_probability(rel, request))
    
    # Calcular probabilidad final ponderada
    final_score = sum(WEIGHTS[factor] * score for factor, score in scores.items())
    
    # Ajustar por generación si está disponible (nuevo ajuste de ±25%)
    if request.generacion is not None and rel.get("generacion") is not None:
        generation_match = request.generacion == str(rel["generacion"])
        final_score = final_score * (1.25 if generation_match else 0.75)
    
    return float(max(0, min(1, final_score)))

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
    Analiza una relación basada en ADN compartido y otros factores
    """
    try:
        # Validar y convertir los datos de entrada
        cm = float(request.cm)
        segments = int(request.segments) if request.segments is not None else None
        largest_segment = float(request.largest_segment) if request.largest_segment is not None else None
        person1_age = int(request.person1_age) if request.person1_age is not None else None
        person2_age = int(request.person2_age) if request.person2_age is not None else None
        
        # Crear una copia del request con los valores convertidos
        processed_request = AnalysisRequest(
            cm=cm,
            segments=segments,
            largest_segment=largest_segment,
            person1_age=person1_age,
            person2_age=person2_age,
            generacion=request.generacion,
            sexo=request.sexo,
            x_inheritance=request.x_inheritance,
            endogamia=request.endogamia
        )
        
        # Calcular probabilidades para cada relación
        results = []
        for rel in RELS:
            try:
                prob = calculate_probability(rel, processed_request)
                if prob > 0.1:  # Solo incluir relaciones con probabilidad > 10%
                    results.append({
                        "code": rel["code"],
                        "name": rel["nombre"],
                        "description": rel["abreviado"],
                        "probability": float(prob),
                        "avg_cm": float(rel["promedio_cm"]),
                        "min_cm": float(rel["min_cm"]),
                        "max_cm": float(rel["max_cm"])
                    })
            except Exception as e:
                logger.error(f"Error al calcular probabilidad para {rel['code']}: {str(e)}")
                continue
        
        # Ordenar por probabilidad
        results.sort(key=lambda x: x["probability"], reverse=True)
        
        # Preparar el análisis detallado
        most_likely = results[0] if results else None
        second_likely = results[1] if len(results) > 1 else None
        
        # Generar análisis detallado
        analysis = {
            "summary": generate_relationship_summary(processed_request, most_likely, second_likely),
            "suggestions": generate_investigation_suggestions(processed_request, most_likely),
            "relationships": results
        }
        
        return analysis
    except Exception as e:
        logger.error(f"Error en el análisis: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def generate_relationship_summary(request, most_likely, second_likely):
    """
    Genera un resumen detallado de la relación más probable
    """
    if not most_likely:
        return "No se pudo determinar una relación probable con los datos proporcionados."
    
    summary = []
    
    # Información básica
    summary.append(f"Se comparten {request.cm} cM en {request.segments or 'N/A'} segmentos.")
    
    # Diferencia de edad si está disponible
    if request.person1_age and request.person2_age:
        age_diff = abs(request.person1_age - request.person2_age)
        summary.append(f"La diferencia de edad es de {age_diff} años.")
    
    # Relación más probable
    summary.append(f"\nLa relación más probable es {most_likely['name']} ({most_likely['probability']*100:.1f}% de probabilidad).")
    
    # Segunda relación más probable si existe y es significativa
    if second_likely and second_likely["probability"] > 0.15:
        summary.append(f"También es posible que sean {second_likely['name']} ({second_likely['probability']*100:.1f}% de probabilidad).")
        
        # Explicar por qué la segunda opción es menos probable
        if request.person1_age and request.person2_age:
            age_diff = abs(request.person1_age - request.person2_age)
            if "bisabuelo" in second_likely['name'].lower() and age_diff < 40:
                summary.append("Esta relación es menos probable debido a la diferencia de edad relativamente pequeña para ser bisabuelo/a.")
            elif "abuelo" in second_likely['name'].lower() and age_diff < 20:
                summary.append("Esta relación es menos probable debido a la diferencia de edad relativamente pequeña para ser abuelo/a.")
    
    return " ".join(summary)

def generate_investigation_suggestions(request, most_likely):
    """
    Genera sugerencias específicas para investigar la relación
    """
    if not most_likely:
        return []
    
    suggestions = []
    
    # Sugerencias basadas en la relación más probable
    if most_likely["code"] == "2C":  # Primos segundos
        suggestions.extend([
            "Investigar a los bisabuelos y su descendencia",
            "Explorar tíos abuelos y primos del padre/madre",
            "Comparar árboles por líneas colaterales"
        ])
    elif most_likely["code"] == "GGAU":  # Tío/a bisabuelo/a
        suggestions.extend([
            "Investigar la línea de los bisabuelos",
            "Buscar registros de hermanos de los bisabuelos",
            "Explorar registros históricos de la época"
        ])
    elif most_likely["code"] == "1C1R":  # Primo hermano una vez removido
        suggestions.extend([
            "Investigar la línea de los primos hermanos",
            "Explorar registros de hijos de primos hermanos",
            "Comparar árboles por ramas colaterales"
        ])
    
    # Sugerencias basadas en el cromosoma X
    if request.x_inheritance:
        suggestions.append("La coincidencia en el cromosoma X puede ayudar a determinar la línea de parentesco (materna/paterna).")
    
    # Sugerencias basadas en la edad
    if request.person1_age and request.person2_age:
        age_diff = abs(request.person1_age - request.person2_age)
        if age_diff > 40:
            suggestions.append("La gran diferencia de edad sugiere investigar generaciones anteriores.")
    
    return suggestions

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
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))  # Render asigna el puerto en $PORT
    uvicorn.run("main:app", host="0.0.0.0", port=port)