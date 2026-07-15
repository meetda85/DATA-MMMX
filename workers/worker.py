import os
import sys
import requests
import re
import time
from datetime import datetime

# Agregar la raíz del proyecto al PATH para permitir imports relativos
raiz_proyecto = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if raiz_proyecto not in sys.path:
    sys.path.append(raiz_proyecto)

try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback para versiones de Python anteriores a 3.9
    from pytz import timezone as ZoneInfo

from database.db import inicializar_db, guardar_operacion

# === CONFIGURACIÓN ===
# Clave de la API de FlightAware (AeroAPI v3.0)
FLIGHTAWARE_API_KEY = os.environ.get("FLIGHTAWARE_API_KEY", "uLGT9UtrCFw7OszjcZjN3zn4dQugAhuK")
# =====================

def hacer_peticion_aeroapi(api_key, url, params=None):
    """Realiza una petición a la AeroAPI con reintentos para manejar límites de velocidad (429)."""
    headers = {"x-apikey": api_key}
    max_reintentos = 3
    espera_base = 15
    
    for intento in range(max_reintentos):
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                segundos_espera = int(retry_after) if retry_after else espera_base * (intento + 1)
            except ValueError:
                segundos_espera = espera_base * (intento + 1)
                
            print(f"  [429] Límite de tasa alcanzado. Esperando {segundos_espera} segundos (intento {intento+1}/{max_reintentos})...")
            time.sleep(segundos_espera)
        else:
            raise Exception(f"AeroAPI retornó {response.status_code}: {response.text}")
            
    raise Exception("Se superó el límite de reintentos tras recibir errores 429 consecutivamente.")

def formatear_vuelo(flight, tipo, timestamp_utc_str):
    """Formatea los datos del vuelo y calcula los valores de hora local (CDMX)."""
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

def procesar_vuelos(data):
    """Filtra y formatea operaciones en pista reales."""
    operaciones = []
    
    # Aterrizajes (ARR)
    for flight in data.get("arrivals", []):
        if flight.get("actual_on"):
            op = formatear_vuelo(flight, "ARR", flight["actual_on"])
            operaciones.append(op)
            
    # Despegues (DEP)
    for flight in data.get("departures", []):
        if flight.get("actual_off"):
            op = formatear_vuelo(flight, "DEP", flight["actual_off"])
            operaciones.append(op)
            
    return operaciones

def ejecutar_sincronizacion(fecha_sync_str=None):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Iniciando sincronización local...")
    
    inicializar_db()
    
    if FLIGHTAWARE_API_KEY == "TU_FLIGHTAWARE_API_KEY" or not FLIGHTAWARE_API_KEY:
        print("ERROR: La API Key de FlightAware no está configurada.")
        return
        
    start_utc = None
    end_utc = None
    
    if fecha_sync_str:
        try:
            cdmx_tz = ZoneInfo("America/Mexico_City")
            if hasattr(cdmx_tz, "localize"):
                dt_start = cdmx_tz.localize(datetime.strptime(f"{fecha_sync_str} 00:00:00", "%Y-%m-%d %H:%M:%S"))
                dt_end = cdmx_tz.localize(datetime.strptime(f"{fecha_sync_str} 23:59:59", "%Y-%m-%d %H:%M:%S"))
            else:
                dt_start = datetime.strptime(f"{fecha_sync_str} 00:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=cdmx_tz)
                dt_end = datetime.strptime(f"{fecha_sync_str} 23:59:59", "%Y-%m-%d %H:%M:%S").replace(tzinfo=cdmx_tz)
                
            start_utc = dt_start.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
            end_utc = dt_end.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"Sincronizando rango específico para fecha {fecha_sync_str} local (CDMX).")
            print(f"UTC Start: {start_utc} | UTC End: {end_utc}")
        except Exception as e:
            print(f"Error al procesar la fecha de sincronización: {e}")
            return
            
    url = "https://aeroapi.flightaware.com/aeroapi/airports/MMMX/flights"
    params = {"max_pages": 1}
    if start_utc:
        params["start"] = start_utc
    if end_utc:
        params["end"] = end_utc
        
    next_url = url
    current_params = params
    pagina = 1
    insertados_totales = 0
    paginas_procesadas = 0
    
    while next_url:
        print(f"Consultando página {pagina}...")
        try:
            if next_url == url:
                data = hacer_peticion_aeroapi(FLIGHTAWARE_API_KEY, next_url, current_params)
            else:
                full_url = f"https://aeroapi.flightaware.com/aeroapi{next_url}"
                data = hacer_peticion_aeroapi(FLIGHTAWARE_API_KEY, full_url)
        except Exception as e:
            print(f"Error al obtener datos en página {pagina}: {e}")
            break
            
        operaciones = procesar_vuelos(data)
        print(f"  Página {pagina}: Se encontraron {len(operaciones)} operaciones en pista.")
        
        insertados_pagina = 0
        for op in operaciones:
            nuevo = guardar_operacion(op)
            if nuevo:
                insertados_pagina += 1
                print(f"  [NUEVO] Vuelo {op['flight_number']} ({op['origen']}->{op['destino']} en {op['tipo_aeronave']}) registrado a las {op['fecha_hora_local']} local.")
                
        insertados_totales += insertados_pagina
        print(f"  Página {pagina}: {insertados_pagina} nuevos registros guardados.")
        
        paginas_procesadas += 1
        
        # Siguiente página
        links = data.get("links") or {}
        next_url = links.get("next")
        pagina += 1
        
        # Límite de seguridad
        if pagina > 50:
            print("Alcanzado el límite máximo de seguridad de 50 páginas.")
            break
            
        # Espera preventiva para respetar la tasa de peticiones (Rate Limit)
        if next_url:
            time.sleep(1.5)
            
    print(f"Sincronización finalizada. Páginas procesadas: {paginas_procesadas}. Total registros nuevos guardados localmente: {insertados_totales}.")

if __name__ == "__main__":
    ejecutar_sincronizacion()
