import os
import sys
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

from database.db import obtener_estadistica_horaria, obtener_estadistica_aerolineas

def obtener_fecha_local_cdmx():
    """Retorna la fecha de hoy en CDMX (CST, UTC-6) en formato YYYY-MM-DD."""
    cdmx_tz = ZoneInfo("America/Mexico_City")
    return datetime.now(cdmx_tz).strftime("%Y-%m-%d")

def generar_reporte_diario(fecha_str):
    """Genera un reporte en texto con las estadísticas de operaciones para la fecha."""
    try:
        # Validar formato
        datetime.strptime(fecha_str, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: Formato de fecha '{fecha_str}' inválido. Debe ser YYYY-MM-DD.")
        sys.exit(1)
        
    print(f"Generando reporte diario de operaciones para la fecha: {fecha_str}...")
    
    # 1. Obtener datos
    horas_data = obtener_estadistica_horaria(fecha_str)
    aerolineas_data = obtener_estadistica_aerolineas(fecha_str)
    
    total_ops = sum(h["total"] for h in horas_data)
    if total_ops == 0:
        print(f"ADVERTENCIA: No se encontraron operaciones registradas en SQLite para la fecha {fecha_str}.")
        # Continuar para generar un reporte de "Sin operaciones", o salir. Generaremos el reporte igual.
        
    # 2. Calcular KPIs
    total_llegadas = sum(h["arr"] for h in horas_data)
    total_salidas = sum(h["dep"] for h in horas_data)
    
    max_ops = 0
    max_hora = "N/A"
    horas_saturadas = []
    
    for h in horas_data:
        if h["total"] > max_ops:
            max_ops = h["total"]
            max_hora = h["bloque_horario"]
        if h["total"] > 44:
            horas_saturadas.append(f"{h['bloque_horario']} ({h['total']} ops)")
            
    # 3. Formatear el Reporte de Texto (ASCII Art)
    reporte = []
    reporte.append("=" * 80)
    reporte.append(f"REPORTE CONSOLIDADO DE OPERACIONES DIARIAS - AEROPUERTO MMMX")
    reporte.append(f"Fecha Reportada: {fecha_str}")
    reporte.append(f"Generado el:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Hora Local)")
    reporte.append("=" * 80)
    reporte.append("")
    
    reporte.append("--- RESUMEN GENERAL ---")
    reporte.append(f"  * Total de Operaciones: {total_ops}")
    reporte.append(f"  * Total de Aterrizajes (ARR): {total_llegadas}")
    reporte.append(f"  * Total de Despegues (DEP):   {total_salidas}")
    reporte.append(f"  * Promedio de Operaciones/Hora: {(total_ops / 24):.1f}")
    reporte.append(f"  * Hora Pico de Operaciones:     {max_hora} ({max_ops} operaciones)")
    reporte.append(f"  * Capacidad Declarada AICM:     44 operaciones / hora")
    
    if horas_saturadas:
        reporte.append(f"  * [ALERTA] Horas Excedidas (>44 ops): {len(horas_saturadas)} bloque(s) de hora")
        for hs in horas_saturadas:
            reporte.append(f"    - Bloque: {hs} ⚠️")
    else:
        reporte.append("  * Estado de Saturación: Ningún bloque horario excedió el límite de 44 ops.")
    reporte.append("")
    
    reporte.append("--- PARTICIPACIÓN POR AEROLÍNEA ---")
    if aerolineas_data:
        reporte.append(f" {'Aerolínea':<35} | {'ICAO':<5} | {'ARR':<5} | {'DEP':<5} | {'Total':<6} | {'% Part.':<7}")
        reporte.append(" " + "-" * 75)
        for a in aerolineas_data:
            pct = (a["total"] / total_ops * 100) if total_ops > 0 else 0
            reporte.append(f" {a['nombre']:<35} | {a['codigo']:<5} | {a['arr']:<5} | {a['dep']:<5} | {a['total']:<6} | {pct:.1f}%")
    else:
        reporte.append("  No hay operaciones registradas para agrupar por aerolínea.")
    reporte.append("")
    
    reporte.append("--- DISTRIBUCIÓN HORARIA ---")
    reporte.append(f" {'Bloque':<8} | {'ARR (Llegadas)':<14} | {'DEP (Salidas)':<13} | {'Total Ops':<9} | {'Estado':<12}")
    reporte.append(" " + "-" * 62)
    for h in horas_data:
        estado = "Fluido"
        if h["total"] > 44:
            estado = "SATURADO ⚠️"
        elif h["total"] >= 35:
            estado = "Alta Densidad"
            
        reporte.append(f" {h['bloque_horario']:<8} | {h['arr']:<14} | {h['dep']:<13} | {h['total']:<9} | {estado:<12}")
    reporte.append("")
    reporte.append("=" * 80)
    reporte.append("Fin del reporte. Guardado de forma local y privada.")
    reporte.append("=" * 80)
    
    reporte_texto = "\n".join(reporte)
    
    # 4. Guardar en Carpeta 'reports'
    reports_dir = os.path.join(raiz_proyecto, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    report_filename = os.path.join(reports_dir, f"reporte_{fecha_str}.txt")
    
    with open(report_filename, "w", encoding="utf-8") as f:
        f.write(reporte_texto)
        
    try:
        print(reporte_texto)
    except UnicodeEncodeError:
        # Reemplazar caracteres que no se pueden codificar en la consola de Windows (como CP1252)
        print(reporte_texto.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8'))
    print(f"\n[OK] Reporte escrito exitosamente en: {report_filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera un reporte diario de operaciones de MMMX en texto.")
    parser.add_argument("date", nargs="?", help="Fecha del reporte en formato YYYY-MM-DD (por defecto hoy)")
    args = parser.parse_args()
    
    # Si no se provee fecha, tomar la fecha actual en CDMX
    fecha_reporte = args.date if args.date else obtener_fecha_local_cdmx()
    
    generar_reporte_diario(fecha_reporte)
