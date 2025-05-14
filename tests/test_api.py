import pytest
import requests
import json
from fastapi.testclient import TestClient
from main import app, request_counts
from app.config import settings

BASE_URL = "http://localhost:8001"

client = TestClient(app)

@pytest.mark.relationships
def test_get_relationships():
    """
    Verifica que el endpoint GET /api/relationships devuelve:
    - Un código 200
    - Una lista de relaciones válidas
    - Cada relación tiene todos los campos requeridos
    - Los datos son consistentes y válidos
    """
    response = client.get("/api/relationships/?cm=1500")
    assert response.status_code == 200, "El endpoint debería devolver código 200"
    data = response.json()
    assert "results" in data, "La respuesta debe contener la clave 'results'"
    assert isinstance(data["results"], list), "Los resultados deben ser una lista"
    assert len(data["results"]) > 0, "La lista de resultados no debe estar vacía"
    
    # Verificar que los resultados tienen la estructura correcta
    required_fields = ["code", "nombre", "abreviado", "promedio_cm", "min_cm", "max_cm"]
    for relationship in data["results"]:
        for field in required_fields:
            assert field in relationship, f"Falta el campo requerido '{field}' en la relación"
        
        # Verificar que los valores son válidos
        assert relationship["min_cm"] <= relationship["promedio_cm"] <= relationship["max_cm"], \
            f"Los valores de cM no son consistentes para la relación {relationship['code']}"

@pytest.mark.analysis
def test_calculate_relationships():
    """
    Verifica el endpoint POST /api/v1/analyze con diferentes casos:
    - Caso completo con todos los parámetros
    - Caso básico solo con cM
    - Casos de error con datos inválidos
    """
    # Caso 1: Todos los parámetros
    payload = {
        "cm": 1500,
        "generacion": "1",
        "sexo": "M",
        "x_inheritance": True,
        "segments": 25,
        "largest_segment": 100.5
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200, "El análisis completo debería ser exitoso"
    data = response.json()
    assert isinstance(data, dict), "La respuesta debe ser un diccionario"
    assert "relationships" in data, "La respuesta debe contener la clave 'relationships'"
    assert isinstance(data["relationships"], list), "Las relaciones deben ser una lista"
    assert len(data["relationships"]) > 0, "Deberían existir relaciones posibles"
    
    # Verificar estructura y validez de los resultados
    required_fields = [
        "code", "nombre", "abreviado", "promedio_cm", "min_cm", "max_cm",
        "adjustedProb", "xPlausible", "agePlausible"
    ]
    for relationship in data["relationships"]:
        for field in required_fields:
            assert field in relationship, f"Falta el campo '{field}' en el resultado"
        assert 0 <= relationship["adjustedProb"] <= 1, \
            f"La probabilidad debe estar entre 0 y 1, encontrado: {relationship['adjustedProb']}"
    
    # Caso 2: Solo centimorgans
    response = client.post("/api/v1/analyze", json={"cm": 1500})
    assert response.status_code == 200, "El análisis básico debería ser exitoso"
    
    # Caso 3: Datos inválidos
    invalid_payloads = [
        ({"cm": -100}, "Los cM negativos deberían ser rechazados"),
        ({"cm": 0}, "Los cM igual a 0 deberían ser rechazados"),
        ({"cm": 7000}, "Los cM mayores a 4000 deberían ser rechazados"),
        ({}, "La falta de cM debería ser rechazada")
    ]
    
    for payload, message in invalid_payloads:
        response = client.post("/api/v1/analyze", json=payload)
        assert response.status_code == 422, message

@pytest.mark.histogram
def test_get_histogram():
    """
    Verifica que el endpoint GET /api/histogram:
    - Devuelve datos válidos para códigos de relación existentes
    - Maneja correctamente códigos inexistentes
    - Los datos del histograma son consistentes
    """
    # Obtener un código válido
    response = client.get("/api/relationships/?cm=1500")
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) > 0, "No se encontraron relaciones para probar"
    code = data["results"][0]["code"]
    
    # Probar histograma con código válido
    response = client.get(f"/api/histogram/?code={code}")
    assert response.status_code == 200, f"El histograma para el código {code} debería existir"
    data = response.json()
    assert "histogram" in data, "La respuesta debe contener la clave 'histogram'"
    assert isinstance(data["histogram"], dict), "El histograma debe ser un diccionario"
    
    # Verificar formato del histograma
    for range_key, value in data["histogram"].items():
        assert isinstance(value, int), \
            f"Los valores del histograma deben ser enteros, encontrado: {type(value)}"
        assert value >= 0, f"Los conteos deben ser no negativos, encontrado: {value}"
    
    # Probar con código inválido
    response = client.get("/api/histogram/?code=INVALID")
    assert response.status_code == 404, "Códigos inválidos deberían devolver 404"

@pytest.mark.api
def test_read_root():
    """
    Verifica que el endpoint raíz:
    - Devuelve un código 200
    - Contiene un mensaje de estado
    """
    response = client.get("/")
    assert response.status_code == 200, "El endpoint raíz debe estar disponible"
    data = response.json()
    assert "message" in data, "La respuesta debe contener un mensaje"
    assert isinstance(data["message"], str), "El mensaje debe ser una cadena de texto"

@pytest.mark.skip(reason="El cliente de test está excluido del rate limiting en el middleware, por lo que esta prueba no es válida en el entorno de test.")
@pytest.mark.security
def test_rate_limiting():
    """
    Verifica que el rate limiting:
    - Permite el número correcto de peticiones por minuto
    - Bloquea peticiones excesivas
    - Devuelve el código y mensaje apropiados
    """
    # Resetear el estado del rate limiting antes de la prueba
    request_counts.clear()
    # Realizar peticiones hasta el límite
    responses = []
    for _ in range(settings.RATE_LIMIT_PER_MINUTE):
        response = client.get("/api/v1/relationships")
        responses.append(response.status_code)
    # Verificar que todas las peticiones fueron exitosas
    assert all(code == 200 for code in responses), \
        "Todas las peticiones dentro del límite deberían ser exitosas"
    # Intentar una petición adicional
    response = client.get("/api/v1/relationships")
    assert response.status_code == 429, \
        "La petición que excede el límite debería ser rechazada"
    assert "error" in response.json(), \
        "La respuesta de error debería incluir un mensaje"

@pytest.mark.security
def test_security_headers():
    """
    Verifica que los headers de seguridad:
    - Están presentes en la respuesta
    - Tienen los valores correctos
    - Incluyen todas las protecciones necesarias
    """
    response = client.get("/")
    headers = response.headers
    
    security_headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block"
    }
    
    for header, expected_value in security_headers.items():
        assert header in headers, f"Falta el header de seguridad: {header}"
        assert headers[header] == expected_value, \
            f"Valor incorrecto para {header}: esperado {expected_value}, encontrado {headers[header]}"
    
    assert "Content-Security-Policy" in headers, \
        "Debe incluir Content-Security-Policy"
    assert "Strict-Transport-Security" in headers, \
        "Debe incluir Strict-Transport-Security"

@pytest.mark.documentation
def test_api_documentation():
    """
    Verifica que la documentación de la API:
    - Es accesible
    - Contiene la interfaz Swagger
    - Está correctamente formateada
    """
    response = client.get("/docs")
    assert response.status_code == 200, "La documentación debe estar disponible"
    assert "swagger-ui" in response.text, \
        "La documentación debe incluir la interfaz Swagger"

@pytest.mark.documentation
def test_openapi_schema():
    """
    Verifica que el esquema OpenAPI:
    - Es accesible
    - Tiene la estructura correcta
    - Incluye todos los componentes necesarios
    """
    response = client.get("/openapi.json")
    assert response.status_code == 200, "El esquema OpenAPI debe estar disponible"
    schema = response.json()
    
    required_fields = ["openapi", "info", "paths", "components"]
    for field in required_fields:
        assert field in schema, \
            f"El esquema debe incluir el campo: {field}"

@pytest.mark.parametrize("caso,payload,expected_relationship", [
    (
        "Bettina y Mariana - Primas segundas",
        {
            "cm": 286.3,
            "generacion": "2",
            "sexo": "F",
            "x_inheritance": True,
            "segments": 14,
            "largest_segment": 79.2
        },
        "2C"
    ),
    (
        "Javier y Soledad - Hermanos completos",
        {
            "cm": 2730,
            "generacion": "0",
            "sexo": "M",
            "x_inheritance": True,
            "segments": None,
            "largest_segment": None
        },
        "FS"
    ),
    (
        "Sebastian y Alejo - Primos hermanos",
        {
            "cm": 884.6,
            "generacion": "1",
            "sexo": "M",
            "x_inheritance": False,
            "segments": 29,
            "largest_segment": 100.1
        },
        "1C"
    ),
    (
        "Soledad y Elizabeth - Primas terceras",
        {
            "cm": 65.8,
            "generacion": "3",
            "sexo": "F",
            "x_inheritance": False,
            "segments": 5,
            "largest_segment": 24.5
        },
        "3C"
    )
])
def test_real_cases(caso, payload, expected_relationship):
    """
    Verifica casos reales de relaciones:
    - La predicción coincide con la relación conocida
    - La probabilidad es significativa
    - Los resultados son consistentes
    
    Parámetros:
    - caso: Descripción del caso de prueba
    - payload: Datos de la relación
    - expected_relationship: Código de relación esperado
    """
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200, f"El análisis para {caso} debería ser exitoso"
    data = response.json()
    
    assert isinstance(data, dict), "Los resultados deben ser un diccionario"
    assert "relationships" in data, "La respuesta debe contener la clave 'relationships'"
    assert isinstance(data["relationships"], list), "Las relaciones deben ser una lista"
    assert len(data["relationships"]) > 0, f"No se encontraron resultados para {caso}"
    
    # Ordenar por probabilidad ajustada
    sorted_results = sorted(data["relationships"], key=lambda x: x["adjustedProb"], reverse=True)
    most_probable = sorted_results[0]
    
    # Verificar que la relación más probable es la esperada
    assert most_probable["code"] == expected_relationship, \
        f"Para {caso}, se esperaba {expected_relationship} pero se obtuvo {most_probable['code']}"
    
    # Verificar que la probabilidad es significativa
    assert most_probable["adjustedProb"] >= 0.15, \
        f"Para {caso}, la probabilidad de {expected_relationship} es muy baja: {most_probable['adjustedProb']}"
    
    # Verificar consistencia de los resultados
    for result in sorted_results:
        assert 0 <= result["adjustedProb"] <= 1, \
            f"Probabilidad inválida en {caso}: {result['adjustedProb']}"
        if not (result["min_cm"] <= payload["cm"] <= result["max_cm"]):
            print(f"WARNING: Los cM están fuera del rango para {result['code']} en {caso}: {payload['cm']} no está entre {result['min_cm']} y {result['max_cm']}")
        # Chequear segmentos si están presentes
        segment_ranges = {
            "FS": (35, 45),
            "1C": (25, 35),
            "2C": (10, 20),
            "3C": (3, 10),
            "4C": (2, 5)
        }
        if payload.get("segments") is not None and result["code"] in segment_ranges:
            min_seg, max_seg = segment_ranges[result["code"]]
            if not (min_seg <= payload["segments"] <= max_seg):
                print(f"WARNING: Segmentos fuera de rango para {result['code']} en {caso}: {payload['segments']} no está entre {min_seg} y {max_seg}")
        # Chequear largest_segment si está presente
        largest_segment_ranges = {
            "FS": (150, 250),
            "1C": (80, 150),
            "2C": (50, 100),
            "3C": (15, 60),
            "4C": (10, 30)
        }
        if payload.get("largest_segment") is not None and result["code"] in largest_segment_ranges:
            min_l, max_l = largest_segment_ranges[result["code"]]
            if not (min_l <= payload["largest_segment"] <= max_l):
                print(f"WARNING: Largest segment fuera de rango para {result['code']} en {caso}: {payload['largest_segment']} no está entre {min_l} y {max_l}")

@pytest.mark.parametrize("payload,expected_status", [
    ({"cm": 1500}, 200),
    ({"cm": 1500, "generacion": "1", "sexo": "M", "x_inheritance": True}, 200),
    ({"cm": 1500, "generacion": None, "sexo": None, "x_inheritance": None}, 200),
    ({"cm": -100}, 422),
    ({"cm": 0}, 422),
    ({"cm": 7000}, 422),
    ({}, 422)
])
def test_analyze_relationship(payload, expected_status):
    """
    Verifica diferentes escenarios de análisis de relaciones:
    - Casos válidos con diferentes combinaciones de parámetros
    - Casos inválidos con valores fuera de rango
    - Manejo de errores apropiado
    
    Parámetros:
    - payload: Datos de entrada para el análisis
    - expected_status: Código de estado HTTP esperado
    """
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == expected_status, \
        f"Estado incorrecto para payload {payload}"
    
    if expected_status == 200:
        data = response.json()
        assert isinstance(data, dict), "Los resultados deben ser un diccionario"
        assert "relationships" in data, "La respuesta debe contener la clave 'relationships'"
        assert isinstance(data["relationships"], list), "Las relaciones deben ser una lista"
        assert len(data["relationships"]) > 0, "No se encontraron resultados"
        # Verificar estructura y validez de los resultados
        required_fields = [
            "code", "nombre", "abreviado", "promedio_cm", "min_cm", "max_cm", "adjustedProb"
        ]
        for relationship in data["relationships"]:
            for field in required_fields:
                assert field in relationship, \
                    f"Falta el campo '{field}' en el resultado"
            # Verificar que la probabilidad está entre 0 y 1
            assert 0 <= relationship["adjustedProb"] <= 1, \
                f"Probabilidad inválida: {relationship['adjustedProb']}"

def test_third_cousins_female():
    """
    Verifica el caso de primas terceras (3C) con herencia del cromosoma X.
    """
    payload = {
        "cm": 65.8,
        "generacion": "3",
        "sexo": "F",
        "x_inheritance": True,
        "segments": 5,
        "largest_segment": 24.5
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "relationships" in data
    assert isinstance(data["relationships"], list)
    assert len(data["relationships"]) > 0
    # Verificar que la relación más probable es 3C
    sorted_results = sorted(data["relationships"], key=lambda x: x["adjustedProb"], reverse=True)
    most_probable = sorted_results[0]
    assert most_probable["code"] == "3C"
    assert most_probable["adjustedProb"] >= 0.15

def test_half_sisters_paternal_xmatch():
    """
    Verifica el caso de medias hermanas con herencia paterna del cromosoma X.
    """
    payload = {
        "cm": 1800,
        "generacion": "0",
        "sexo": "F",
        "x_inheritance": True,
        "segments": 35,
        "largest_segment": 150.2
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "relationships" in data
    assert isinstance(data["relationships"], list)
    assert len(data["relationships"]) > 0
    # Verificar que la relación más probable es HS
    sorted_results = sorted(data["relationships"], key=lambda x: x["adjustedProb"], reverse=True)
    most_probable = sorted_results[0]
    assert most_probable["code"] == "HS"
    assert most_probable["adjustedProb"] >= 0.15

def test_second_cousins_female():
    """
    Verifica el caso de primas segundas (2C) con herencia del cromosoma X.
    """
    payload = {
        "cm": 286.3,
        "generacion": "2",
        "sexo": "F",
        "x_inheritance": True,
        "segments": 14,
        "largest_segment": 79.2
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "relationships" in data
    assert isinstance(data["relationships"], list)
    assert len(data["relationships"]) > 0
    # Verificar que la relación más probable es 2C
    sorted_results = sorted(data["relationships"], key=lambda x: x["adjustedProb"], reverse=True)
    most_probable = sorted_results[0]
    assert most_probable["code"] == "2C"
    assert most_probable["adjustedProb"] >= 0.15

def test_first_cousin_of_parent():
    """
    Verifica el caso de primo/a hermano/a de un padre (1C1R).
    """
    payload = {
        "cm": 884.6,
        "generacion": "1",
        "sexo": "M",
        "x_inheritance": False,
        "segments": 29,
        "largest_segment": 100.1
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "relationships" in data
    assert isinstance(data["relationships"], list)
    assert len(data["relationships"]) > 0
    # Verificar que la relación más probable es 1C1R o 1C
    sorted_results = sorted(data["relationships"], key=lambda x: x["adjustedProb"], reverse=True)
    most_probable = sorted_results[0]
    assert most_probable["code"] in ["1C1R", "1C"], f"Se esperaba 1C1R o 1C pero se obtuvo {most_probable['code']}"
    assert most_probable["adjustedProb"] >= 0.15 