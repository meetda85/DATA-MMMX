# Sistema de Monitoreo de Operaciones MMMX (100% Local y Privado)

Este sistema permite recopilar, almacenar y visualizar la estadística horaria de las operaciones reales (aterrizajes y despegues en pista) del Aeropuerto Internacional de la Ciudad de México (MMMX), contrastándolas con la capacidad declarada de 44 operaciones por hora.

**Esta versión está diseñada para funcionar de manera 100% local y offline**, sin dependencias en la nube (como Firebase o Supabase). Toda la base de datos se guarda en un archivo SQLite local (`database/operaciones_mmmx.db`), garantizando la absoluta privacidad de tus datos y evitando cualquier riesgo de fuga de información.

---

## Estructura del Proyecto

El código está organizado de la siguiente manera:

```text
/
├── database/
│   ├── db.py                    # Módulo Python para la base de datos SQLite y consultas SQL
│   └── operaciones_mmmx.db      # Archivo de base de datos local (Se genera automáticamente)
├── workers/
│   └── worker.py                # Script Python para consultar AeroAPI y guardar en SQLite
├── dashboard/
│   ├── index.html               # Interfaz del Panel de Control (HTML5)
│   ├── style.css                # Estilo visual premium (Tema oscuro y Glassmorphism)
│   └── app.js                   # Lógica JavaScript (Peticiones REST a localhost y Chart.js)
├── app.py                       # Servidor local Flask que sirve el dashboard y provee la API
└── requirements.txt             # Dependencias necesarias para ejecutar el proyecto en Python
```

---

## Guía de Instalación y Ejecución Local

### Paso 1: Instalar dependencias
Asegúrate de tener Python 3 instalado en tu máquina. Abre una terminal en la carpeta raíz del proyecto e instala las librerías necesarias ejecutando:

```bash
pip install -r requirements.txt
```

### Paso 2: Configurar tu API Key de FlightAware
Para poder realizar consultas a FlightAware, debes configurar tu API Key. Puedes hacerlo de dos formas:

1. **Recomendado (Seguro)**: Define la variable de entorno en tu sistema:
   * **En Windows (PowerShell)**: `$env:FLIGHTAWARE_API_KEY="tu_clave_aqui"`
   * **En Linux/macOS**: `export FLIGHTAWARE_API_KEY="tu_clave_aqui"`
2. **Alternativo**: Abre el archivo `workers/worker.py` y reemplaza `"TU_FLIGHTAWARE_API_KEY"` en la línea 17 por tu clave real:
   ```python
   FLIGHTAWARE_API_KEY = os.environ.get("FLIGHTAWARE_API_KEY", "tu_clave_real_aqui")
   ```

---

### Paso 3: Arrancar el Servidor Local y Dashboard
Desde tu terminal en la carpeta raíz del proyecto, ejecuta:

```bash
python app.py
```

El servidor web Flask arrancará localmente. Verás una pantalla indicando que el servidor está en ejecución:
```text
==================================================
 Servidor de Operaciones MMMX Iniciado
 Abre en tu navegador: http://localhost:5000
==================================================
```
Abre tu navegador e ingresa a `http://localhost:5000` para ver la aplicación web interna.

---

### Paso 4: Automatizar la Carga de Datos (Worker/Cron)
Para que la base de datos local se actualice de forma continua una vez por hora, puedes programar la ejecución del script del worker:

* **En Windows (Programador de Tareas)**:
  1. Crea una tarea básica que se ejecute cada 1 hora.
  2. Acción: **Iniciar un programa**.
  3. Programa o script: `python` (o la ruta absoluta a tu ejecutable de Python).
  4. Agregar argumentos: `workers/worker.py` (o la ruta absoluta a tu archivo).
  5. Iniciar en: La ruta de la carpeta raíz del proyecto.
* **En Linux/macOS (Cron)**:
  Agrega la siguiente línea a tu archivo `crontab` (`crontab -e`) para ejecutar el worker al minuto 0 de cada hora:
  ```text
  0 * * * * cd /ruta/al/proyecto && python workers/worker.py >> /var/log/mmmx_sync.log 2>&1
  ```

#### Sincronización Manual:
Si no deseas programar tareas del sistema operativo, **¡no hay problema!** El Dashboard incluye una integración en tiempo real: al dar clic en el botón de **Recargar (Flechas circulares)** en la esquina superior derecha del dashboard, el frontend enviará una petición al servidor Flask para que ejecute el worker en el acto, consulte AeroAPI y actualice el dashboard inmediatamente con los datos más recientes.

---

## Privacidad y Seguridad

1. **Base de Datos Privada**: La base de datos es un archivo SQLite (`database/operaciones_mmmx.db`). Nunca se subirá a internet ni se compartirá con ningún servidor web. Puedes copiar este archivo para respaldar la información.
2. **Aislamiento de Red**: La única llamada a internet que realiza el sistema es la consulta saliente a la API de FlightAware (`https://aeroapi.flightaware.com`) para descargar los datos operativos de los vuelos. Ningún dato local tuyo se envía de vuelta.
3. **Chart.js CDN**: La librería de gráficos se carga vía CDN (`cdn.jsdelivr.net`). Si deseas un aislamiento 100% offline (sin internet), puedes descargar el archivo de Chart.js y guardarlo en la carpeta `/dashboard` cambiando la etiqueta `<script>` en `index.html`.
