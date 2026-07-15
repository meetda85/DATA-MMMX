import os
import sys
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory

# Variables globales para control de sincronización automática
AUTO_SYNC_ENABLED = False

def background_sync_loop():
    global AUTO_SYNC_ENABLED
    print("[PROGRAMADOR] Iniciando hilo del programador automático (Desactivado por defecto).")
    while True:
        # Esperar 1 hora en bloques de 60 segundos
        for _ in range(60):
            time.sleep(60)
            if not AUTO_SYNC_ENABLED:
                break
        
        if AUTO_SYNC_ENABLED:
            try:
                print("[PROGRAMADOR] Iniciando sincronización automática programada...")
                from workers.worker import ejecutar_sincronizacion
                
                # Obtener la fecha local de CDMX en formato YYYY-MM-DD
                try:
                    from zoneinfo import ZoneInfo
                    cdmx_tz = ZoneInfo("America/Mexico_City")
                except ImportError:
                    from pytz import timezone
                    cdmx_tz = timezone("America/Mexico_City")
                    
                fecha_hoy = datetime.now(cdmx_tz).strftime("%Y-%m-%d")
                ejecutar_sincronizacion(fecha_hoy)
                print(f"[PROGRAMADOR] Sincronización automática de {fecha_hoy} completada.")
            except Exception as e:
                print(f"[PROGRAMADOR] Error en la sincronización programada: {e}")

# Agregar el directorio raíz del proyecto al PATH para permitir imports relativos
raiz_proyecto = os.path.dirname(os.path.abspath(__file__))
if raiz_proyecto not in sys.path:
    sys.path.append(raiz_proyecto)

from database.db import (
    inicializar_db, obtener_estadistica_horaria, obtener_estadistica_aerolineas, 
    obtener_vuelos_dia, obtener_rutas_top, obtener_flota_top, obtener_detalle_hora_pico
)

# Inicializar Flask y configurar el directorio de archivos estáticos (Dashboard)
app = Flask(__name__, static_folder="dashboard", static_url_path="")

# Asegurar que la base de datos SQLite esté inicializada al arrancar el servidor
inicializar_db()

@app.route("/")
def index():
    """Sirve el archivo HTML principal del dashboard."""
    return send_from_directory(app.static_folder, "index.html")

@app.route("/api/data", methods=["GET"])
def get_data():
    """
    Retorna la estadística horaria de operaciones para una fecha dada.
    Formato: /api/data?date=YYYY-MM-DD
    """
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "El parámetro 'date' es requerido. Ejemplo: ?date=2026-07-13"}), 400
        
    try:
        # Validar que la fecha venga en formato YYYY-MM-DD
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido. Utilice el formato YYYY-MM-DD"}), 400
        
    try:
        data = obtener_estadistica_horaria(date_str)
        aerolineas = obtener_estadistica_aerolineas(date_str)
        vuelos = obtener_vuelos_dia(date_str)
        
        # Calcular si hay alguna operación en el día para saber si está vacío
        has_data = any(h["total"] > 0 for h in data)
        
        rutas = []
        flota = []
        detalle_pico = []
        insights = []
        
        if has_data:
            rutas = obtener_rutas_top(date_str)
            flota = obtener_flota_top(date_str)
            
            # Calcular hora pico en número entero para pasar a la consulta
            max_ops = -1
            max_hour_num = None
            for h in data:
                if h["total"] > max_ops:
                    max_ops = h["total"]
                    max_hour_num = int(h["bloque_horario"].split(":")[0])
            
            if max_hour_num is not None and max_ops > 0:
                detalle_pico = obtener_detalle_hora_pico(date_str, max_hour_num)
                
            # Generar Insights Operativos Dinámicos
            # 1. Aerolínea Líder
            if aerolineas:
                leader = aerolineas[0]
                insights.append(f"<strong>Aerolínea Líder:</strong> <span>{leader['nombre']} ({leader['codigo']})</span> concentró la mayor actividad con <strong>{leader['total']}</strong> operaciones (ARR: {leader['arr']} / DEP: {leader['dep']}).")
            
            # 2. Ruta Más Transitada
            if rutas:
                top_route = rutas[0]
                insights.append(f"<strong>Corredor Crítico:</strong> La ruta de mayor conectividad del día fue <strong>{top_route['origen']} ➔ {top_route['destino']}</strong> con <strong>{top_route['total']}</strong> operaciones en pista.")
            
            # 3. Flota Dominante
            if flota:
                top_plane = flota[0]
                insights.append(f"<strong>Flota Mayoritaria:</strong> El modelo de aeronave con más actividad registrada fue el <strong>{top_plane['aeronave']}</strong>, realizando un total de <strong>{top_plane['total']}</strong> operaciones.")
            
            # 4. Balance Arribos vs Salidas
            total_arr = sum(h["arr"] for h in data)
            total_dep = sum(h["dep"] for h in data)
            total_total = total_arr + total_dep
            if total_total > 0:
                pct_arr = (total_arr / total_total) * 100
                pct_dep = (total_dep / total_total) * 100
                insights.append(f"<strong>Balance Operativo:</strong> El AICM registró <strong>{total_arr}</strong> aterrizajes ({pct_arr:.1f}%) y <strong>{total_dep}</strong> despegues ({pct_dep:.1f}%), mostrando un balance operacional estable.")
        else:
            insights.append("No se encontraron operaciones registradas en esta fecha para generar hallazgos.")
        
        return jsonify({
            "fecha": date_str,
            "horas": data,
            "aerolineas": aerolineas,
            "vuelos": vuelos,
            "rutas": rutas,
            "flota": flota,
            "detalle_pico": detalle_pico,
            "insights": insights,
            "empty": not has_data
        })
    except Exception as e:
        return jsonify({"error": f"Error al consultar la base de datos: {str(e)}"}), 500

@app.route("/api/sync", methods=["POST"])
def run_sync():
    """
    Endpoint para ejecutar el worker de recolección en tiempo real.
    Permite refrescar los datos desde el dashboard web con un clic.
    """
    pin = request.args.get("pin") or request.form.get("pin")
    if request.is_json:
        data = request.get_json() or {}
        pin = pin or data.get("pin")
        
    if pin != "0348":
        return jsonify({"success": False, "error": "Contraseña de seguridad incorrecta."}), 401
        
    date_str = request.args.get("date")
    if date_str:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return jsonify({"success": False, "error": "Formato de fecha inválido. Debe ser YYYY-MM-DD"}), 400
            
    try:
        from workers.worker import ejecutar_sincronizacion
        ejecutar_sincronizacion(date_str)
        return jsonify({
            "success": True, 
            "message": f"Sincronización con FlightAware AeroAPI completada con éxito para la fecha: {date_str if date_str else 'reciente'}."
        })
    except Exception as e:
        return jsonify({
            "success": False, 
            "error": f"Fallo al ejecutar la sincronización: {str(e)}"
        }), 500

@app.route("/api/config/autosync", methods=["GET"])
def get_autosync_status():
    global AUTO_SYNC_ENABLED
    return jsonify({
        "success": True,
        "enabled": AUTO_SYNC_ENABLED
    })

@app.route("/api/config/autosync", methods=["POST"])
def config_autosync():
    global AUTO_SYNC_ENABLED
    pin = request.args.get("pin") or request.form.get("pin")
    enabled = request.args.get("enabled") or request.form.get("enabled")
    
    if request.is_json:
        data = request.get_json() or {}
        pin = pin or data.get("pin")
        enabled = enabled if enabled is not None else data.get("enabled")
        
    if pin != "0348":
        return jsonify({"success": False, "error": "Contraseña de seguridad incorrecta."}), 401
        
    if enabled is None:
        return jsonify({"success": False, "error": "El parámetro 'enabled' es requerido."}), 400
        
    if isinstance(enabled, str):
        AUTO_SYNC_ENABLED = enabled.lower() in ("true", "1", "yes")
    else:
        AUTO_SYNC_ENABLED = bool(enabled)
        
    print(f"[CONFIG] Sincronización automática {'activada' if AUTO_SYNC_ENABLED else 'desactivada'} por el usuario.")
    return jsonify({
        "success": True, 
        "enabled": AUTO_SYNC_ENABLED,
        "message": f"Sincronización automática {'activada' if AUTO_SYNC_ENABLED else 'desactivada'} con éxito."
    })

if __name__ == "__main__":
    # Configurar puerto y host por defecto (0.0.0.0 para acceso en red local)
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    
    import socket
    local_ip = "127.0.0.1"
    try:
        # Conectar a una IP pública (no realiza tráfico real) para obtener la interfaz activa
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass
    
    print("\n" + "="*50)
    print(f" Servidor de Operaciones MMMX Iniciado")
    print(f" Acceso en esta PC: http://localhost:{port}")
    if local_ip != "127.0.0.1":
        print(f" Acceso en tu Tablet/Red Local: http://{local_ip}:{port}")
    print("="*50 + "\n")
    
    # Iniciar hilo de sincronización automática en segundo plano
    threading.Thread(target=background_sync_loop, daemon=True).start()
    
    app.run(host=host, port=port, debug=True)
