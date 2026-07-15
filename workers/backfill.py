import os
import sys
import requests
import re
import json
import time
import traceback
import argparse
from datetime import datetime

# Agregar la raíz del proyecto al PATH para permitir imports relativos
raiz_proyecto = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if raiz_proyecto not in sys.path:
    sys.path.append(raiz_proyecto)

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from pytz import timezone as ZoneInfo

from database.db import inicializar_db, guardar_operacion

# === CONFIGURACIÓN ===
FLIGHTAWARE_API_KEY = os.environ.get("FLIGHTAWARE_API_KEY", "uLGT9UtrCFw7OszjcZjN3zn4dQugAhuK")
# =====================

def guardar_raw_json(data, prefijo):
    """Guarda el JSON crudo en la carpeta raw_data/ para auditoría y análisis externo."""
    raw_dir = os.path.join(raiz_proyecto, "raw_data")
    os.makedirs(raw_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(raw_dir, f"{prefijo}_{timestamp}.json")
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"     [RAW JSON] Payload original guardado en: {filename}")
    except Exception as e:
        print(f"     [ADVERTENCIA] No se pudo guardar el JSON crudo: {e}")

def obtener_vuelos_rango(api_key, start_utc_str, end_utc_str, fecha_str):
    """
    Consulta la API de FlightAware en un rango de tiempo específico.
    Sigue los enlaces de paginación ('next') para recuperar todos los vuelos en el rango.
    Introduce pausas largas (12s) para evitar el error 429 de la API básica.
    """
    url = "https://aeroapi.flightaware.com/aeroapi/airports/MMMX/flights"
    headers = {"x-apikey": api_key}
    
    # Parámetros para la primera petición
    params = {
        "start": start_utc_str,
        "end": end_utc_str,
        "max_pages": 15 # Límite de seguridad
    }
    
    todas_operaciones = []
    pagina = 1
    
    while url:
        print(f"  -> Consultando página {pagina} de AeroAPI: {url if 'cursor' not in url else '(URL con Cursor)'}...")
        
        if "cursor" in url:
            response = requests.get(url, headers=headers)
        else:
            response = requests.get(url, headers=headers, params=params)
            
        if response.status_code != 200:
            print(f"  [ERROR] AeroAPI retornó {response.status_code}: {response.text}")
            break
            
        data = response.json()
        
        # Guardar respuesta cruda original de FlightAware de inmediato
        guardar_raw_json(data, f"backfill_{fecha_str}_pag{pagina}")
        
        # Procesar arribos de esta página
        arrivals = data.get("arrivals", [])
        for flight in arrivals:
            if flight.get("actual_on"):
                op = formatear_vuelo(flight, "ARR", flight["actual_on"])
                todas_operaciones.append(op)
                
        # Procesar salidas de esta página
        departures = data.get("departures", [])
        for flight in departures:
            if flight.get("actual_off"):
                op = formatear_vuelo(flight, "DEP", flight["actual_off"])
                todas_operaciones.append(op)
                
        print(f"     Encontradas {len(arrivals)} llegadas y {len(departures)} salidas en esta página.")
        
        # Revisar si hay una siguiente página
        links = data.get("links")
        next_link = links.get("next") if links else None
        
        if next_link:
            if next_link.startswith("http"):
                url = next_link
            else:
                if not next_link.startswith("/aeroapi"):
                    next_link = "/aeroapi" + next_link
                url = "https://aeroapi.flightaware.com" + next_link
            pagina += 1
            
            # PAUSA DE SEGURIDAD (Rate Limiting):
            # La API básica tiene límites de consultas por minuto muy restrictivos.
            # Pausamos 12 segundos para estar completamente seguros de no levantar alarmas de spam en su API.
            print("     Pausando 12.0 segundos para respetar de forma segura el límite de peticiones por minuto...")
            time.sleep(12.0)
        else:
            url = None
            
    return todas_operaciones

def formatear_vuelo(flight, tipo, timestamp_utc_str):
    """Convierte los timestamps a la hora local de CDMX y extrae la aerolínea."""
    dt_str = timestamp_utc_str.replace("Z", "+00:00")
    dt_utc = datetime.fromisoformat(dt_str)
    
    cdmx_tz = ZoneInfo("America/Mexico_City")
    dt_local = dt_utc.astimezone(cdmx_tz)
    
    fecha_hora_local = dt_local.strftime("%Y-%m-%d %H:%M:%S")
    fecha_local_str = dt_local.strftime("%Y-%m-%d")
    hora_local = dt_local.hour
    
    ident = flight["ident"]
    match = re.match(r'^([A-Z]{2,4})\d+', ident)
    aerolinea = match.group(1) if match else "Otros"
    
    # Extraer origen, destino y tipo de aeronave con protección frente a nulos
    origin_obj = flight.get("origin")
    origen = origin_obj.get("code", "---") if origin_obj else "---"
    
    dest_obj = flight.get("destination")
    destino = dest_obj.get("code", "---") if dest_obj else "---"
    
    tipo_aeronave = flight.get("aircraft_type", "---") or "---"
    
    return {
        "fa_flight_id": flight["fa_flight_id"],
        "flight_number": ident,
        "tipo_operacion": tipo,
        "fecha_hora_utc": dt_utc.isoformat(),
        "fecha_hora_local": fecha_hora_local,
        "fecha_local_str": fecha_local_str,
        "hora_local": hora_local,
        "aerolinea": aerolinea,
        "origen": origen,
        "destino": destino,
        "tipo_aeronave": tipo_aeronave
    }

def ejecutar_backfill(fecha_str):
    print("="*60)
    print(f" INICIANDO HISTORIAL DE IMPORTACIÓN (PAGINACIÓN CON 12S PAUSA) PARA: {fecha_str}")
    print("="*60)
    
    inicializar_db()
    
    if FLIGHTAWARE_API_KEY == "TU_FLIGHTAWARE_API_KEY" or not FLIGHTAWARE_API_KEY:
        print("ERROR: La API Key de FlightAware no está configurada.")
        return
        
    cdmx_tz = ZoneInfo("America/Mexico_City")
    try:
        dt_start_local = datetime.strptime(f"{fecha_str} 00:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=cdmx_tz)
        hoy_str = datetime.now(cdmx_tz).strftime("%Y-%m-%d")
        if fecha_str == hoy_str:
            dt_end_local = datetime.now(cdmx_tz)
            print("Importando desde las 00:00 hasta la hora actual (fecha de hoy).")
        else:
            dt_end_local = datetime.strptime(f"{fecha_str} 23:59:59", "%Y-%m-%d %H:%M:%S").replace(tzinfo=cdmx_tz)
            print("Importando el día completo (fecha pasada).")
    except ValueError:
        print("ERROR: Formato de fecha inválido. Debe ser YYYY-MM-DD.")
        return
        
    # Convertir rangos locales a UTC
    dt_start_utc = dt_start_local.astimezone(ZoneInfo("UTC"))
    dt_end_utc = dt_end_local.astimezone(ZoneInfo("UTC"))
    
    start_utc_str = dt_start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc_str = dt_end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    print(f"Rango local (CDMX): {dt_start_local}  -->  {dt_end_local}")
    print(f"Rango UTC (AeroAPI): {start_utc_str}  -->  {end_utc_str}")
    
    # Consultar API
    try:
        operaciones = obtener_vuelos_rango(FLIGHTAWARE_API_KEY, start_utc_str, end_utc_str, fecha_str)
    except Exception as e:
        print(f"Error al llamar a AeroAPI: {e}")
        traceback.print_exc()
        return
        
    print(f"\nFinalizada consulta de API. Encontradas {len(operaciones)} operaciones en pista en total.")
    
    # Guardar en SQLite
    nuevos = 0
    for op in operaciones:
        if op["fecha_local_str"] == fecha_str:
            guardado = guardar_operacion(op)
            if guardado:
                nuevos += 1
                
    print(f"Registros guardados en SQLite: {nuevos} operaciones nuevas.")
    print("="*60 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recupera e importa el historial completo de operaciones de un día.")
    parser.add_argument("date", nargs="?", help="Fecha a importar en formato YYYY-MM-DD (por defecto hoy)")
    args = parser.parse_args()
    
    cdmx_tz = ZoneInfo("America/Mexico_City")
    fecha_default = datetime.now(cdmx_tz).strftime("%Y-%m-%d")
    fecha_a_importar = args.date if args.date else fecha_default
    
    ejecutar_backfill(fecha_a_importar)
