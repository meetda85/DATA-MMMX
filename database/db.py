import os
import sqlite3

# Ruta al archivo de base de datos local
# Redirigir a /tmp en entornos de Vercel ya que el sistema de archivos principal es de solo lectura
if os.environ.get("VERCEL"):
    DB_DIR = "/tmp"
    DB_PATH = os.path.join(DB_DIR, "operaciones_mmmx.db")
else:
    DB_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(DB_DIR, "operaciones_mmmx.db")

# Diccionario de Aerolíneas comunes en el AICM (MMMX) para mapear código ICAO a Nombre Comercial
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

def obtener_conexion():
    """Retorna una conexión a la base de datos SQLite."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_db():
    """Crea la estructura de la base de datos y ejecuta migraciones si es necesario."""
    conn = obtener_conexion()
    cursor = conn.cursor()
    
    # 1. Crear tabla con la estructura completa por defecto para bases de datos nuevas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registro_operaciones_mmmx (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fa_flight_id TEXT NOT NULL,
            flight_number TEXT NOT NULL,
            tipo_operacion TEXT NOT NULL CHECK (tipo_operacion IN ('ARR', 'DEP')),
            fecha_hora_utc TEXT NOT NULL,
            fecha_hora_local TEXT NOT NULL,
            fecha_local_str TEXT NOT NULL,
            hora_local INTEGER NOT NULL,
            aerolinea TEXT,
            origen TEXT,          -- Columna añadida para el aeropuerto de origen
            destino TEXT,         -- Columna añadida para el aeropuerto de destino
            tipo_aeronave TEXT,   -- Columna añadida para el tipo de aeronave
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            UNIQUE(fa_flight_id, tipo_operacion)
        )
    """)
    
    # 2. Migraciones: Añadir columnas si la tabla ya existía sin ellas
    cursor.execute("PRAGMA table_info(registro_operaciones_mmmx)")
    columnas = [row[1] for row in cursor.fetchall()]
    
    migraciones_hechas = False
    
    if "aerolinea" not in columnas:
        print("Migrando: Añadiendo columna 'aerolinea'...")
        cursor.execute("ALTER TABLE registro_operaciones_mmmx ADD COLUMN aerolinea TEXT")
        migraciones_hechas = True
        
    if "origen" not in columnas:
        print("Migrando: Añadiendo columna 'origen'...")
        cursor.execute("ALTER TABLE registro_operaciones_mmmx ADD COLUMN origen TEXT")
        migraciones_hechas = True
        
    if "destino" not in columnas:
        print("Migrando: Añadiendo columna 'destino'...")
        cursor.execute("ALTER TABLE registro_operaciones_mmmx ADD COLUMN destino TEXT")
        migraciones_hechas = True
        
    if "tipo_aeronave" not in columnas:
        print("Migrando: Añadiendo columna 'tipo_aeronave'...")
        cursor.execute("ALTER TABLE registro_operaciones_mmmx ADD COLUMN tipo_aeronave TEXT")
        migraciones_hechas = True
        
    if migraciones_hechas:
        conn.commit()
    
    # 3. Crear índice para acelerar búsquedas
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_fecha_local 
        ON registro_operaciones_mmmx (fecha_local_str)
    """)
    
    conn.commit()
    conn.close()
    print(f"Base de datos inicializada en: {DB_PATH}")

def guardar_operacion(op):
    """Inserta una operación de vuelo. Si ya existe, la ignora."""
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        aerolinea_code = op.get("aerolinea", "Otros")
        origen_code = op.get("origen", "---")
        destino_code = op.get("destino", "---")
        tipo_aeronave = op.get("tipo_aeronave", "---")
        
        cursor.execute("""
            INSERT OR IGNORE INTO registro_operaciones_mmmx (
                fa_flight_id, flight_number, tipo_operacion, 
                fecha_hora_utc, fecha_hora_local, fecha_local_str, hora_local, 
                aerolinea, origen, destino, tipo_aeronave
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            op["fa_flight_id"], op["flight_number"], op["tipo_operacion"],
            op["fecha_hora_utc"], op["fecha_hora_local"], op["fecha_local_str"], op["hora_local"],
            aerolinea_code, origen_code, destino_code, tipo_aeronave
        ))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Error al insertar en SQLite: {e}")
        return False
    finally:
        conn.close()

def obtener_estadistica_horaria(fecha_str):
    """
    Agrupa y calcula las operaciones por hora para una fecha dada.
    Retorna siempre 24 registros (de 00:00 a 23:00) rellenos con 0 si no hay vuelos.
    """
    estadisticas = {f"{h:02d}:00": {"arr": 0, "dep": 0, "total": 0} for h in range(24)}
    
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            hora_local,
            SUM(CASE WHEN tipo_operacion = 'ARR' THEN 1 ELSE 0 END) as arr,
            SUM(CASE WHEN tipo_operacion = 'DEP' THEN 1 ELSE 0 END) as dep,
            COUNT(*) as total
        FROM 
            registro_operaciones_mmmx
        WHERE 
            fecha_local_str = ?
        GROUP BY 
            hora_local
    """, (fecha_str,))
    
    for row in cursor.fetchall():
        hora_num = row["hora_local"]
        hora_key = f"{hora_num:02d}:00"
        
        if hora_key in estadisticas:
            estadisticas[hora_key] = {
                "arr": int(row["arr"]),
                "dep": int(row["dep"]),
                "total": int(row["total"])
            }
            
    conn.close()
    
    resultado = []
    for hora_bloque in sorted(estadisticas.keys()):
        data = estadisticas[hora_bloque]
        resultado.append({
            "bloque_horario": hora_bloque,
            "arr": data["arr"],
            "dep": data["dep"],
            "total": data["total"]
        })
        
    return resultado

def obtener_estadistica_aerolineas(fecha_str):
    """
    Agrupa y cuenta las operaciones por aerolínea para una fecha dada.
    Retorna desgloses de llegadas, salidas y totales.
    """
    conn = obtener_conexion()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            COALESCE(aerolinea, 'Otros') as aero_code,
            SUM(CASE WHEN tipo_operacion = 'ARR' THEN 1 ELSE 0 END) as arr,
            SUM(CASE WHEN tipo_operacion = 'DEP' THEN 1 ELSE 0 END) as dep,
            COUNT(*) as total
        FROM 
            registro_operaciones_mmmx
        WHERE 
            fecha_local_str = ?
        GROUP BY 
            aero_code
        ORDER BY 
            total DESC
    """, (fecha_str,))
    
    resultado = []
    for row in cursor.fetchall():
        code = row["aero_code"]
        name = AEROLINEAS_MAP.get(code, f"Línea Aérea ({code})")
        resultado.append({
            "codigo": code,
            "nombre": name,
            "arr": int(row["arr"]),
            "dep": int(row["dep"]),
            "total": int(row["total"])
        })
        
    conn.close()
    return resultado

def obtener_vuelos_dia(fecha_str):
    """
    Retorna la lista detallada y ordenada cronológicamente de todas las
    operaciones que ocurrieron en un día específico.
    """
    conn = obtener_conexion()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            flight_number, tipo_operacion, fecha_hora_local, aerolinea, 
            origen, destino, tipo_aeronave
        FROM 
            registro_operaciones_mmmx
        WHERE 
            fecha_local_str = ?
        ORDER BY 
            fecha_hora_local ASC
    """, (fecha_str,))
    
    vuelos = []
    for row in cursor.fetchall():
        aero_code = row["aerolinea"] or "Otros"
        aero_name = AEROLINEAS_MAP.get(aero_code, f"Línea Aérea ({aero_code})")
        
        # Extraer solo la hora local HH:MM:SS del timestamp YYYY-MM-DD HH:MM:SS
        hora_local = row["fecha_hora_local"].split(" ")[1] if " " in row["fecha_hora_local"] else row["fecha_hora_local"]
        
        vuelos.append({
            "vuelo": row["flight_number"],
            "tipo": row["tipo_operacion"],
            "hora": hora_local,
            "aerolinea_nombre": aero_name,
            "aerolinea_codigo": aero_code,
            "origen": row["origen"] or "---",
            "destino": row["destino"] or "---",
            "aeronave": row["tipo_aeronave"] or "---"
        })
        
    conn.close()
    return vuelos

def obtener_rutas_top(fecha_str):
    """Retorna las 5 rutas con mayor volumen de operaciones para una fecha."""
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            origen, destino, COUNT(*) as total
        FROM 
            registro_operaciones_mmmx
        WHERE 
            fecha_local_str = ? AND origen != '---' AND destino != '---'
        GROUP BY 
            origen, destino
        ORDER BY 
            total DESC
        LIMIT 5
    """, (fecha_str,))
    
    rutas = []
    for row in cursor.fetchall():
        rutas.append({
            "origen": row["origen"],
            "destino": row["destino"],
            "total": int(row["total"])
        })
    conn.close()
    return rutas

def obtener_flota_top(fecha_str):
    """Retorna los 5 modelos de avión más comunes en las operaciones de una fecha."""
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            tipo_aeronave, COUNT(*) as total
        FROM 
            registro_operaciones_mmmx
        WHERE 
            fecha_local_str = ? AND tipo_aeronave != '---'
        GROUP BY 
            tipo_aeronave
        ORDER BY 
            total DESC
        LIMIT 5
    """, (fecha_str,))
    
    flota = []
    for row in cursor.fetchall():
        flota.append({
            "aeronave": row["tipo_aeronave"],
            "total": int(row["total"])
        })
    conn.close()
    return flota

def obtener_detalle_hora_pico(fecha_str, hora_local):
    """Retorna los aeropuertos más conectados durante la hora pico."""
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            CASE WHEN tipo_operacion = 'ARR' THEN origen ELSE destino END as conectado,
            tipo_operacion,
            COUNT(*) as total
        FROM 
            registro_operaciones_mmmx
        WHERE 
            fecha_local_str = ? AND hora_local = ? AND conectado != '---' AND conectado != 'MMMX'
        GROUP BY 
            conectado, tipo_operacion
        ORDER BY 
            total DESC
        LIMIT 3
    """, (fecha_str, hora_local))
    
    detalle = []
    for row in cursor.fetchall():
        detalle.append({
            "aeropuerto": row["conectado"],
            "tipo": row["tipo_operacion"],
            "total": int(row["total"])
        })
    conn.close()
    return detalle
