import os
import sys
import random
from datetime import datetime, timedelta

# Agregar la raíz del proyecto al PATH para permitir imports relativos
raiz_proyecto = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if raiz_proyecto not in sys.path:
    sys.path.append(raiz_proyecto)

from database.db import inicializar_db, guardar_operacion

AEROLINEAS_ICAO = ["AMX", "SLI", "VOI", "VIV", "AAL", "DAL", "UAL", "CMP", "IBE", "AFR", "DLH"]
AERONAVES = ["B738", "A320", "A20N", "A321", "B789", "E190", "MCS", "B772"]
AEROPUERTOS = ["KLAX", "KMIA", "KDFW", "KIAH", "KJFK", "MMUN", "MMGL", "MMMY", "MMPB", "MPTO"]

def generar_datos_mock():
    print("="*60)
    print(" GENERANDO DATOS SIMULADOS PARA PRUEBAS (OFFLINE MOCK DATA)")
    print("="*60)
    
    inicializar_db()
    
    # Fechas a simular
    fechas = ["2026-07-11", "2026-07-12", "2026-07-13"]
    total_generado = 0
    
    for fecha_str in fechas:
        print(f"Generando vuelos para la fecha: {fecha_str}...")
        
        # Simular entre 180 y 250 vuelos por día
        num_vuelos = random.randint(180, 250)
        vuelos_fecha = 0
        
        for i in range(num_vuelos):
            # Generar hora (distribución realista: menos vuelos de 2 AM a 5 AM)
            hora = random.choices(
                population=list(range(24)),
                weights=[
                    5, 3, 1, 1, 2, 5,       # 00:00 - 05:00
                    12, 18, 25, 28, 22, 20, # 06:00 - 11:00 (Picos matutinos)
                    18, 15, 16, 20, 24, 26, # 12:00 - 17:00
                    25, 22, 18, 15, 10, 8   # 18:00 - 23:00
                ],
                k=1
            )[0]
            
            minuto = random.randint(0, 59)
            segundo = random.randint(0, 59)
            
            # Hora local
            fecha_hora_local = f"{fecha_str} {hora:02d}:{minuto:02d}:{segundo:02d}"
            
            # Calcular UTC (Local + 6 horas)
            dt_local = datetime.strptime(fecha_hora_local, "%Y-%m-%d %H:%M:%S")
            dt_utc = dt_local + timedelta(hours=6)
            fecha_hora_utc = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            # Aerolínea
            aero = random.choice(AEROLINEAS_ICAO)
            flight_num = f"{aero}{random.randint(100, 1999)}"
            
            # Operación
            tipo = random.choice(["ARR", "DEP"])
            
            # Origen y Destino
            if tipo == "ARR":
                origen = random.choice([ap for ap in AEROPUERTOS if ap != "MMMX"])
                destino = "MMMX"
            else:
                origen = "MMMX"
                destino = random.choice([ap for ap in AEROPUERTOS if ap != "MMMX"])
                
            # Aeronave
            aeronave = random.choice(AERONAVES)
            
            # ID único de FlightAware mock
            fa_flight_id = f"{flight_num}-{int(dt_utc.timestamp())}-0-0"
            
            op = {
                "fa_flight_id": fa_flight_id,
                "flight_number": flight_num,
                "tipo_operacion": tipo,
                "fecha_hora_utc": fecha_hora_utc,
                "fecha_hora_local": fecha_hora_local,
                "fecha_local_str": fecha_str,
                "hora_local": hora,
                "aerolinea": aero,
                "origen": origen,
                "destino": destino,
                "tipo_aeronave": aeronave
            }
            
            guardado = guardar_operacion(op)
            if guardado:
                vuelos_fecha += 1
                
        total_generado += vuelos_fecha
        print(f"  [OK] Guardados {vuelos_fecha} vuelos simulados para el {fecha_str}.")
        
    print("="*60)
    print(f"PROCESO TERMINADO. Total de operaciones simuladas insertadas: {total_generado}.")
    print("="*60 + "\n")

if __name__ == "__main__":
    generar_datos_mock()
