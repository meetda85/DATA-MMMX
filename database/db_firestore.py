import os
import json
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

# Map of common airlines for names
AEROLINEAS_MAP = {
    "AMX": "Aeroméxico",
    "SLI": "Aeroméxico Connect",
    "VOI": "Volaris",
    "VIV": "VivaAerobus",
    "AAL": "American Airlines",
    "DAL": "Delta Air Lines",
    "UAL": "United Airlines",
    "CMP": "Copa Airlines",
    "IBE": "Iberia",
    "AFR": "Air France",
    "DLH": "Lufthansa",
    "KLM": "KLM Royal Dutch Airlines",
    "BAW": "British Airways",
    "AVA": "Avianca",
    "TAI": "TACA Airlines",
    "LRC": "LACSA",
    "LAN": "LATAM Airlines (Chile)",
    "TAM": "LATAM Airlines (Brasil)",
    "LPE": "LATAM Airlines (Perú)",
    "FDX": "FedEx Express (Carga)",
    "UPS": "UPS Airlines (Carga)",
    "MAA": "Mas Air (Carga)",
    "ESF": "Estafeta (Carga)",
    "MCS": "AeroUnion (Carga)",
    "Otros": "Otros / Aviación General"
}

db_client = None
USE_FIRESTORE = False

# Path to service account file in the project root
cred_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "firebase-service-account.json")

# 1. Attempt credentials loading from Environment variable (secure, ideal for Vercel)
cred_env = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
if cred_env:
    try:
        cred_dict = json.loads(cred_env)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db_client = firestore.client()
        USE_FIRESTORE = True
        print("[FIREBASE] Conectado exitosamente a Firestore vía variable de entorno (Vercel).")
    except Exception as e:
        print(f"[FIREBASE] Error al inicializar Firestore vía env: {e}")
# 2. Fallback to local JSON credentials
elif os.path.exists(cred_path):
    try:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        db_client = firestore.client()
        USE_FIRESTORE = True
        print("[FIREBASE] Conectado exitosamente a Firestore vía archivo local 'firebase-service-account.json'.")
    except Exception as e:
        print(f"[FIREBASE] Error al inicializar Firestore vía JSON local: {e}")
else:
    print("[FIREBASE] Modo local activo: No se detectaron credenciales de Firebase. Usando SQLite.")

_cache_datos_diarios = {}

def limpiar_cache_fecha(fecha_str):
    global _cache_datos_diarios
    if fecha_str in _cache_datos_diarios:
        del _cache_datos_diarios[fecha_str]
        print(f"[FIREBASE] Cache de estadísticas limpiado para la fecha: {fecha_str}")

def guardar_operacion_firestore(op):
    """Guarda un vuelo en Firestore. Document ID único para evitar duplicados."""
    if not USE_FIRESTORE:
        return False
    try:
        doc_id = f"{op['fa_flight_id']}_{op['tipo_operacion']}"
        doc_ref = db_client.collection("registro_operaciones_mmmx").document(doc_id)
        
        doc_snap = doc_ref.get()
        if not doc_snap.exists:
            doc_ref.set(op)
            # Limpiar caché local
            limpiar_cache_fecha(op["fecha_local_str"])
            return True
        return False
    except Exception as e:
        print(f"[FIREBASE] Error al escribir en Firestore: {e}")
        return False

def obtener_vuelos_dia_raw_firestore(fecha_str):
    """Obtiene la lista cruda de documentos de Firestore para una fecha."""
    if not USE_FIRESTORE:
        return []
    try:
        print(f"[FIREBASE] Consultando Firestore para obtener vuelos del día: {fecha_str}")
        docs = db_client.collection("registro_operaciones_mmmx")\
            .where("fecha_local_str", "==", fecha_str)\
            .stream()
            
        vuelos = []
        for doc in docs:
            vuelos.append(doc.to_dict())
            
        print(f"[FIREBASE] Recuperados {len(vuelos)} vuelos de Firestore para el día {fecha_str}.")
        return vuelos
    except Exception as e:
        print(f"[FIREBASE] Error al leer vuelos de Firestore: {e}")
        return []

def procesar_estadisticas_diarias(vuelos_del_dia, fecha_str):
    """Calcula todas las métricas en memoria a partir de los vuelos crudos."""
    # 1. Estadística horaria
    horas_dict = {f"{h:02d}:00": {"arr": 0, "dep": 0, "total": 0} for h in range(24)}
    
    # 2. Aerolíneas
    aerolineas_count = {}
    
    # 3. Rutas
    rutas_count = {}
    
    # 4. Flotas
    flotas_count = {}
    
    # 5. Vuelos para bitácora
    vuelos_log = []
    
    for v in vuelos_del_dia:
        tipo = v.get("tipo_operacion")
        # Asegurar tipo de hora_local es entero
        hora_num = v.get("hora_local", 0)
        try:
            hora_num = int(hora_num)
        except ValueError:
            hora_num = 0
            
        hora_key = f"{hora_num:02d}:00"
        
        # Agrupar por hora
        if hora_key in horas_dict:
            if tipo == "ARR":
                horas_dict[hora_key]["arr"] += 1
            elif tipo == "DEP":
                horas_dict[hora_key]["dep"] += 1
            horas_dict[hora_key]["total"] += 1
            
        # Agrupar por aerolínea
        aero_code = v.get("aerolinea", "Otros") or "Otros"
        if aero_code not in aerolineas_count:
            aerolineas_count[aero_code] = {"arr": 0, "dep": 0, "total": 0}
        if tipo == "ARR":
            aerolineas_count[aero_code]["arr"] += 1
        elif tipo == "DEP":
            aerolineas_count[aero_code]["dep"] += 1
        aerolineas_count[aero_code]["total"] += 1
        
        # Agrupar por ruta
        origen = v.get("origen", "---") or "---"
        destino = v.get("destino", "---") or "---"
        if origen != "---" and destino != "---":
            ruta_key = (origen, destino)
            rutas_count[ruta_key] = rutas_count.get(ruta_key, 0) + 1
            
        # Agrupar por aeronave
        aeronave = v.get("tipo_aeronave", "---") or "---"
        if aeronave != "---":
            flotas_count[aeronave] = flotas_count.get(aeronave, 0) + 1
            
        # Vuelo formateado para el log
        hora_local_str = v.get("fecha_hora_local", "")
        if " " in hora_local_str:
            hora_local_str = hora_local_str.split(" ")[1]
            
        aero_name = AEROLINEAS_MAP.get(aero_code, f"Línea Aérea ({aero_code})")
        vuelos_log.append({
            "vuelo": v.get("flight_number"),
            "tipo": tipo,
            "hora": hora_local_str,
            "aerolinea_nombre": aero_name,
            "aerolinea_codigo": aero_code,
            "origen": origen,
            "destino": destino,
            "aeronave": aeronave
        })
        
    # Ordenar vuelos log por hora
    vuelos_log.sort(key=lambda x: x["hora"])
    
    # Formatear horas list
    horas_list = []
    for hora_bloque in sorted(horas_dict.keys()):
        data = horas_dict[hora_bloque]
        horas_list.append({
            "bloque_horario": hora_bloque,
            "arr": data["arr"],
            "dep": data["dep"],
            "total": data["total"]
        })
        
    # Formatear aerolíneas list
    aerolineas_list = []
    for code, data in aerolineas_count.items():
        name = AEROLINEAS_MAP.get(code, f"Línea Aérea ({code})")
        aerolineas_list.append({
            "codigo": code,
            "nombre": name,
            "arr": data["arr"],
            "dep": data["dep"],
            "total": data["total"]
        })
    aerolineas_list.sort(key=lambda x: x["total"], reverse=True)
    
    # Formatear rutas list (Top 5)
    rutas_list = []
    for (orig, dest), total in sorted(rutas_count.items(), key=lambda x: x[1], reverse=True)[:5]:
        rutas_list.append({
            "origen": orig,
            "destino": dest,
            "total": total
        })
        
    # Formatear flota list (Top 5)
    flota_list = []
    for plane, total in sorted(flotas_count.items(), key=lambda x: x[1], reverse=True)[:5]:
        flota_list.append({
            "aeronave": plane,
            "total": total
        })
        
    # Calcular detalle hora pico
    max_ops = -1
    max_hour_num = None
    for h_bloque, data in horas_dict.items():
        if data["total"] > max_ops:
            max_ops = data["total"]
            max_hour_num = int(h_bloque.split(":")[0])
            
    detalle_pico = []
    if max_hour_num is not None and max_ops > 0:
        vuelos_pico = [v for v in vuelos_del_dia if int(v.get("hora_local", -1)) == max_hour_num]
        
        conectados = {}
        for v in vuelos_pico:
            tipo = v.get("tipo_operacion")
            conectado = v.get("origen") if tipo == "ARR" else v.get("destino")
            if conectado and conectado != "---" and conectado != "MMMX":
                key = (conectado, tipo)
                conectados[key] = conectados.get(key, 0) + 1
                
        for (cone, tipo), total in sorted(conectados.items(), key=lambda x: x[1], reverse=True)[:3]:
            detalle_pico.append({
                "aeropuerto": cone,
                "tipo": tipo,
                "total": total
            })
            
    return {
        "horas": horas_list,
        "aerolineas": aerolineas_list,
        "vuelos": vuelos_log,
        "rutas": rutas_list,
        "flota": flota_list,
        "detalle_pico": detalle_pico
    }

def obtener_datos_dia_firestore(fecha_str):
    """Retorna los datos completos procesados para el dashboard."""
    global _cache_datos_diarios
    if fecha_str in _cache_datos_diarios:
        return _cache_datos_diarios[fecha_str]
        
    vuelos_del_dia = obtener_vuelos_dia_raw_firestore(fecha_str)
    
    # Si no hay vuelos del día, retornar estructura vacía (pero no cachear para reintentar si se sincroniza)
    if not vuelos_del_dia:
        return {
            "horas": [{ "bloque_horario": f"{h:02d}:00", "arr": 0, "dep": 0, "total": 0 } for h in range(24)],
            "aerolineas": [],
            "vuelos": [],
            "rutas": [],
            "flota": [],
            "detalle_pico": []
        }
        
    stats = procesar_estadisticas_diarias(vuelos_del_dia, fecha_str)
    _cache_datos_diarios[fecha_str] = stats
    return stats
