/**
 * WORKER DE AUTOMATIZACIÓN - GOOGLE APPS SCRIPT (RECOMENDADO)
 * 
 * Este script consulta la API de FlightAware (AeroAPI v3.0) para obtener los vuelos
 * reales de llegada (ARR) y salida (DEP) del aeropuerto MMMX, calcula su hora local
 * de Ciudad de México (UTC-6) y actualiza de forma incremental la base de datos de
 * Firestore, optimizando lecturas/escrituras.
 * 
 * Instrucciones de configuración en Apps Script:
 * 1. Ve a https://script.google.com
 * 2. Crea un nuevo proyecto.
 * 3. Copia y pega este código en el editor (código 'Codigo.gs').
 * 4. Configura las credenciales en las constantes de abajo.
 * 5. Configura un activador (Trigger) del tipo 'Basado en tiempo' para ejecutarse cada 1 hora.
 */

// === CONFIGURACIÓN ===
const FLIGHTAWARE_API_KEY = "TU_FLIGHTAWARE_API_KEY"; // Se reemplazará con tu llave real
const FIREBASE_PROJECT_ID = "TU_FIREBASE_PROJECT_ID";  // ID de tu proyecto de Firebase

// Credenciales de Service Account de Firebase/GCP para la escritura segura en Firestore
const FIREBASE_SERVICE_ACCOUNT = {
  "client_email": "TU_SERVICE_ACCOUNT_EMAIL",
  "private_key": "-----BEGIN PRIVATE KEY-----\nTU_PRIVATE_KEY\n-----END PRIVATE KEY-----\n"
};
// =====================

/**
 * Función principal que ejecuta la sincronización.
 * Programa esta función para ejecutarse cada hora.
 */
function ejecutarSincronizacionMMMX() {
  Logger.log("Iniciando sincronización de operaciones de MMMX...");
  
  // 1. Obtener Token de Acceso para Firestore
  var accessToken;
  try {
    accessToken = obtenerAccessTokenFirestore(FIREBASE_SERVICE_ACCOUNT);
    Logger.log("Token de acceso de Firestore generado correctamente.");
  } catch (e) {
    Logger.log("Error al autenticar con Firebase: " + e.toString());
    return;
  }
  
  // 2. Consultar FlightAware AeroAPI
  var flightsData;
  try {
    flightsData = obtenerVuelosDesdeAeroAPI(FLIGHTAWARE_API_KEY);
    Logger.log("Vuelos obtenidos exitosamente desde AeroAPI.");
  } catch (e) {
    Logger.log("Error al consultar AeroAPI: " + e.toString());
    return;
  }
  
  // 3. Procesar y filtrar operaciones reales
  var operacionesCandidatas = procesarVuelosAeroAPI(flightsData);
  Logger.log("Se encontraron " + operacionesCandidatas.length + " operaciones candidatas en pista.");
  
  if (operacionesCandidatas.length === 0) {
    Logger.log("No hay operaciones reales nuevas para procesar.");
    return;
  }
  
  // 4. Identificar las fechas locales involucradas en este lote
  var fechasInvolucradas = {};
  operacionesCandidatas.forEach(function(op) {
    fechasInvolucradas[op.fecha_local_str] = true;
  });
  
  // 5. Para cada fecha, obtener los registros ya existentes en Firestore para evitar duplicados
  var registrosExistentes = {};
  var estadisticasDiarias = {};
  
  Object.keys(fechasInvolucradas).forEach(function(fecha) {
    registrosExistentes[fecha] = obtenerRegistrosExistentesEnFirestore(accessToken, fecha);
    Logger.log("Fecha " + fecha + ": " + registrosExistentes[fecha].size + " vuelos ya registrados.");
    
    estadisticasDiarias[fecha] = obtenerODiseniarEstadisticaDiaria(accessToken, fecha);
  });
  
  // 6. Filtrar solo los registros que realmente son nuevos y acumular los cambios
  var nuevosVuelosAAgregar = [];
  var fechasModificadas = {};
  
  operacionesCandidatas.forEach(function(op) {
    var idUnico = op.fa_flight_id + "_" + op.tipo_operacion;
    
    // Si no está registrado aún para esa fecha
    if (!registrosExistentes[op.fecha_local_str].has(idUnico)) {
      nuevosVuelosAAgregar.push(op);
      registrosExistentes[op.fecha_local_str].add(idUnico); // Evitar duplicar en el mismo lote
      
      // Incrementar estadísticas en memoria
      var horaKey = String(op.hora_local).padStart(2, '0');
      var tipoMin = op.tipo_operacion.toLowerCase(); // 'arr' o 'dep'
      
      var stats = estadisticasDiarias[op.fecha_local_str];
      if (stats.horas && stats.horas[horaKey]) {
        stats.horas[horaKey][tipoMin] = (stats.horas[horaKey][tipoMin] || 0) + 1;
        stats.horas[horaKey]["total"] = (stats.horas[horaKey]["total"] || 0) + 1;
        fechasModificadas[op.fecha_local_str] = true;
      }
    }
  });
  
  Logger.log("Total de operaciones nuevas a registrar: " + nuevosVuelosAAgregar.length);
  
  if (nuevosVuelosAAgregar.length === 0) {
    Logger.log("Ninguna operación nueva que insertar.");
    return;
  }
  
  // 7. Enviar escrituras a Firestore mediante un commit por lote (Batch Write)
  try {
    guardarEnFirestoreLote(accessToken, nuevosVuelosAAgregar, estadisticasDiarias, fechasModificadas);
    Logger.log("Sincronización finalizada con éxito.");
  } catch (e) {
    Logger.log("Error al escribir lote en Firestore: " + e.toString());
  }
}

/**
 * Consulta la API de FlightAware.
 */
function obtenerVuelosDesdeAeroAPI(apiKey) {
  var url = "https://aeroapi.flightaware.com/aeroapi/airports/MMMX/flights?max_pages=1";
  var options = {
    "method": "get",
    "headers": {
      "x-apikey": apiKey
    },
    "muteHttpExceptions": true
  };
  
  var response = UrlFetchApp.fetch(url, options);
  var code = response.getResponseCode();
  
  if (code !== 200) {
    throw new Error("AeroAPI retornó código " + code + ": " + response.getContentText());
  }
  
  return JSON.parse(response.getContentText());
}

/**
 * Extrae los campos de pista reales y los formatea convirtiendo a hora de CDMX (UTC-6).
 */
function procesarVuelosAeroAPI(data) {
  var operaciones = [];
  
  // Procesar Aterrizajes (ARR)
  if (data.arrivals && Array.isArray(data.arrivals)) {
    data.arrivals.forEach(function(flight) {
      // actual_on representa el tiempo real en pista (touchdown)
      if (flight.actual_on) {
        var op = formatearDatosVuelo(flight, 'ARR', flight.actual_on);
        operaciones.push(op);
      }
    });
  }
  
  // Procesar Despegues (DEP)
  if (data.departures && Array.isArray(data.departures)) {
    data.departures.forEach(function(flight) {
      // actual_off representa el tiempo real de despegue (wheels up)
      if (flight.actual_off) {
        var op = formatearDatosVuelo(flight, 'DEP', flight.actual_off);
        operaciones.push(op);
      }
    });
  }
  
  return operaciones;
}

/**
 * Formatea la información del vuelo y calcula los campos temporales locales en CDMX.
 */
function formatearDatosVuelo(flight, tipo, timestampUtc) {
  // Parsear el timestamp UTC (puede venir como string ISO8601 o unix epoch numérico)
  var dateUtc;
  if (typeof timestampUtc === 'number') {
    dateUtc = new Date(timestampUtc * 1000);
  } else {
    dateUtc = new Date(timestampUtc);
  }
  
  // CDMX está en CST (UTC-6 fijo sin horario de verano desde 2022)
  var timeZone = "America/Mexico_City";
  var fechaHoraLocalStr = Utilities.formatDate(dateUtc, timeZone, "yyyy-MM-dd HH:mm:ss");
  var fechaLocalStr = Utilities.formatDate(dateUtc, timeZone, "yyyy-MM-dd");
  var horaLocalStr = Utilities.formatDate(dateUtc, timeZone, "HH");
  var horaLocalNum = parseInt(horaLocalStr, 10);
  
  return {
    "fa_flight_id": flight.fa_flight_id,
    "flight_number": flight.ident,
    "tipo_operacion": tipo,
    "fecha_hora_utc": dateUtc.toISOString(),
    "fecha_hora_local": fechaHoraLocalStr,
    "fecha_local_str": fechaLocalStr,
    "hora_local": horaLocalNum
  };
}

/**
 * Realiza una consulta (runQuery) en Firestore para saber qué ID de vuelos ya existen
 * en la fecha dada para evitar procesarlos doble.
 */
function obtenerRegistrosExistentesEnFirestore(accessToken, fecha) {
  var url = "https://firestore.googleapis.com/v1/projects/" + FIREBASE_PROJECT_ID + "/databases/(default)/documents:runQuery";
  
  var queryPayload = {
    "structuredQuery": {
      "from": [{ "collectionId": "registro_operaciones_mmmx" }],
      "where": {
        "fieldFilter": {
          "field": { "fieldPath": "fecha_local_str" },
          "op": "EQUAL",
          "value": { "stringValue": fecha }
        }
      },
      "select": {
        "fields": [{ "fieldPath": "fa_flight_id" }, { "fieldPath": "tipo_operacion" }]
      }
    }
  };
  
  var options = {
    "method": "post",
    "headers": {
      "Authorization": "Bearer " + accessToken,
      "Content-Type": "application/json"
    },
    "payload": JSON.stringify(queryPayload),
    "muteHttpExceptions": true
  };
  
  var response = UrlFetchApp.fetch(url, options);
  var text = response.getContentText();
  
  var resultsSet = new Set();
  
  try {
    var responseJson = JSON.parse(text);
    if (Array.isArray(responseJson)) {
      responseJson.forEach(function(item) {
        if (item.document && item.document.name) {
          // El ID del documento está al final del name
          var parts = item.document.name.split("/");
          var docId = parts[parts.length - 1];
          resultsSet.add(docId);
        }
      });
    }
  } catch (e) {
    Logger.log("Error al procesar query de duplicados para " + fecha + ": " + e.toString());
  }
  
  return resultsSet;
}

/**
 * Obtiene el documento de estadísticas diarias para una fecha de Firestore.
 * Si no existe, inicializa un objeto con todas las horas en 0.
 */
function obtenerODiseniarEstadisticaDiaria(accessToken, fecha) {
  var url = "https://firestore.googleapis.com/v1/projects/" + FIREBASE_PROJECT_ID + "/databases/(default)/documents/estadistica_diaria_mmmx/" + fecha;
  
  var options = {
    "method": "get",
    "headers": {
      "Authorization": "Bearer " + accessToken
    },
    "muteHttpExceptions": true
  };
  
  var response = UrlFetchApp.fetch(url, options);
  var code = response.getResponseCode();
  
  if (code === 200) {
    var doc = JSON.parse(response.getContentText());
    return firestoreToJs(doc.fields);
  } else if (code === 404) {
    // Inicializar estadísticas vacías de las 24 horas
    var stats = {
      "fecha": fecha,
      "horas": {}
    };
    for (var i = 0; i < 24; i++) {
      var horaKey = String(i).padStart(2, '0');
      stats.horas[horaKey] = { "arr": 0, "dep": 0, "total": 0 };
    }
    return stats;
  } else {
    throw new Error("Error al consultar estadísticas diarias (" + code + "): " + response.getContentText());
  }
}

/**
 * Guarda en Firestore por lote (usando el endpoint :commit para escrituras atómicas).
 */
function guardarEnFirestoreLote(accessToken, nuevosVuelos, estadisticasDiarias, fechasModificadas) {
  var url = "https://firestore.googleapis.com/v1/projects/" + FIREBASE_PROJECT_ID + "/databases/(default)/documents:commit";
  
  var writes = [];
  
  // A. Agregar escrituras de los nuevos vuelos en la colección detallada
  nuevosVuelos.forEach(function(op) {
    var docId = op.fa_flight_id + "_" + op.tipo_operacion;
    var name = "projects/" + FIREBASE_PROJECT_ID + "/databases/(default)/documents/registro_operaciones_mmmx/" + docId;
    
    writes.push({
      "update": {
        "name": name,
        "fields": jsToFirestore(op)
      }
    });
  });
  
  // B. Agregar escrituras para actualizar las estadísticas de las fechas modificadas
  Object.keys(fechasModificadas).forEach(function(fecha) {
    var name = "projects/" + FIREBASE_PROJECT_ID + "/databases/(default)/documents/estadistica_diaria_mmmx/" + fecha;
    var statsData = estadisticasDiarias[fecha];
    
    writes.push({
      "update": {
        "name": name,
        "fields": jsToFirestore(statsData)
      }
    });
  });
  
  // Firestore REST API limita a 500 escrituras por commit
  // Si superamos las 400 operaciones por lote, las dividimos para seguridad
  var batchSize = 400;
  for (var i = 0; i < writes.length; i += batchSize) {
    var batch = writes.slice(i, i + batchSize);
    
    var payload = {
      "writes": batch
    };
    
    var options = {
      "method": "post",
      "headers": {
        "Authorization": "Bearer " + accessToken,
        "Content-Type": "application/json"
      },
      "payload": JSON.stringify(payload),
      "muteHttpExceptions": true
    };
    
    var response = UrlFetchApp.fetch(url, options);
    var code = response.getResponseCode();
    if (code !== 200) {
      throw new Error("Error en commit de Firestore (" + code + "): " + response.getContentText());
    }
    
    Logger.log("Lote de escrituras de Firestore insertado (" + batch.length + " escrituras).");
  }
}

/**
 * Autenticación mediante Service Account JWT (RS256) autogenerado
 * para obtener un access_token sin depender de librerías externas.
 */
function obtenerAccessTokenFirestore(serviceAccount) {
  var header = JSON.stringify({
    "alg": "RS256",
    "typ": "JWT"
  });
  
  var now = Math.floor(new Date().getTime() / 1000);
  var claimSet = JSON.stringify({
    "iss": serviceAccount.client_email,
    "scope": "https://www.googleapis.com/auth/datastore",
    "aud": "https://oauth2.googleapis.com/token",
    "exp": now + 3600,
    "iat": now
  });
  
  var toSign = Utilities.base64EncodeWebSafe(header) + "." + Utilities.base64EncodeWebSafe(claimSet);
  var privateKey = serviceAccount.private_key;
  
  var signatureBytes = Utilities.computeRsaSha256Signature(toSign, privateKey);
  var signature = Utilities.base64EncodeWebSafe(signatureBytes);
  var jwt = toSign + "." + signature;
  
  var options = {
    "method": "post",
    "payload": {
      "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
      "assertion": jwt
    },
    "muteHttpExceptions": true
  };
  
  var response = UrlFetchApp.fetch("https://oauth2.googleapis.com/token", options);
  var code = response.getResponseCode();
  var text = response.getContentText();
  
  if (code !== 200) {
    throw new Error("Fallo al obtener OAuth token de Google: " + text);
  }
  
  var result = JSON.parse(text);
  return result.access_token;
}

// === UTILERÍAS DE CONVERSIÓN FIRESTORE REST ===

function firestoreToJs(fields) {
  var obj = {};
  if (!fields) return obj;
  for (var key in fields) {
    var valObj = fields[key];
    if (valObj.stringValue !== undefined) {
      obj[key] = valObj.stringValue;
    } else if (valObj.integerValue !== undefined) {
      obj[key] = parseInt(valObj.integerValue, 10);
    } else if (valObj.doubleValue !== undefined) {
      obj[key] = parseFloat(valObj.doubleValue);
    } else if (valObj.booleanValue !== undefined) {
      obj[key] = valObj.booleanValue;
    } else if (valObj.timestampValue !== undefined) {
      obj[key] = valObj.timestampValue;
    } else if (valObj.mapValue !== undefined) {
      obj[key] = firestoreToJs(valObj.mapValue.fields || {});
    } else if (valObj.arrayValue !== undefined) {
      var arr = [];
      var values = valObj.arrayValue.values || [];
      for (var i = 0; i < values.length; i++) {
        var item = values[i];
        if (item.stringValue !== undefined) arr.push(item.stringValue);
        else if (item.integerValue !== undefined) arr.push(parseInt(item.integerValue, 10));
        else if (item.mapValue !== undefined) arr.push(firestoreToJs(item.mapValue.fields || {}));
      }
      obj[key] = arr;
    }
  }
  return obj;
}

function jsToFirestore(obj) {
  var fields = {};
  for (var key in obj) {
    var val = obj[key];
    if (typeof val === 'string') {
      if (val.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/)) {
        fields[key] = { "timestampValue": val };
      } else {
        fields[key] = { "stringValue": val };
      }
    } else if (typeof val === 'number') {
      if (Number.isInteger(val)) {
        fields[key] = { "integerValue": String(val) };
      } else {
        fields[key] = { "doubleValue": val };
      }
    } else if (typeof val === 'boolean') {
      fields[key] = { "booleanValue": val };
    } else if (val instanceof Date) {
      fields[key] = { "timestampValue": val.toISOString() };
    } else if (Array.isArray(val)) {
      var values = [];
      for (var i = 0; i < val.length; i++) {
        var item = val[i];
        if (typeof item === 'string') values.push({ "stringValue": item });
        else if (typeof item === 'number') values.push({ "integerValue": String(item) });
        else if (typeof item === 'object') values.push({ "mapValue": { "fields": jsToFirestore(item) } });
      }
      fields[key] = { "arrayValue": { "values": values } };
    } else if (typeof val === 'object' && val !== null) {
      fields[key] = { "mapValue": { "fields": jsToFirestore(val) } };
    }
  }
  return fields;
}
