import os
import sys
import glob
import json
import re
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

def restaurar_datos():
    print("="*60)
    print(" RESTAURANDO DATOS REALES DESDE PAYLOADS JSON GUARDADOS")
    print("="*60)
    
    inicializar_db()
    
    raw_dir = os.path.join(raiz_proyecto, "raw_data")
    if not os.path.exists(raw_dir):
        print(f"No existe la carpeta raw_data/ en: {raw_dir}")
        return
        
    # Buscar todos los archivos JSON en raw_data/
    archivos_json = glob.glob(os.path.join(raw_dir, "*.json"))
    if not archivos_json:
        print("No se encontraron archivos JSON en raw_data/")
        return
        
    print(f"Encontrados {len(archivos_json)} archivos de payload en raw_data/.")
    
    cdmx_tz = ZoneInfo("America/Mexico_City")
    total_nuevos = 0
    
    for arch in sorted(archivos_json):
        nombre_arch = os.path.basename(arch)
        print(f"\nProcesando archivo: {nombre_arch}...")
        
        try:
            with open(arch, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  [ERROR] No se pudo leer {nombre_arch}: {e}")
            continue
            
        operaciones = []
        
        # Procesar arribos
        arrivals = data.get("arrivals", [])
        for flight in arrivals:
            if flight.get("actual_on"):
                op = formatear_vuelo(flight, "ARR", flight["actual_on"])
                operaciones.append(op)
                
        # Procesar salidas
        departures = data.get("departures", [])
        for flight in departures:
            if flight.get("actual_off"):
                op = formatear_vuelo(flight, "DEP", flight["actual_off"])
                operaciones.append(op)
                
        print(f"  Encontrados {len(operaciones)} vuelos en el JSON crudo.")
        
        nuevos_archivo = 0
        for op in operaciones:
            guardado = guardar_operacion(op)
            if guardado:
                nuevos_archivo += 1
                total_nuevos += 1
                
        print(f"  -> {nuevos_archivo} operaciones nuevas agregadas a SQLite desde este archivo.")
        
    print("\n" + "="*60)
    print(f"RESTAURACIÓN FINALIZADA. Insertadas {total_nuevos} operaciones reales en SQLite.")
    print("="*60 + "\n")

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

if __name__ == "__main__":
    restaurar_datos()
