// Variables Globales
let chartInstance = null;
let airlineChartInstance = null;
let routesChartInstance = null;
let fleetChartInstance = null;
let selectedDate = "";
let rawFlightsList = []; // Almacena la lista de vuelos individuales del día

// Elementos del DOM
const dateSelector = document.getElementById("date-selector");
const btnRefresh = document.getElementById("btn-refresh");
const btnSyncEmpty = document.getElementById("btn-sync-empty");
const kpiTotal = document.getElementById("kpi-total");
const kpiPeak = document.getElementById("kpi-peak");
const kpiAverage = document.getElementById("kpi-average");
const kpiSaturated = document.getElementById("kpi-saturated");
const warningBannerContainer = document.getElementById("warning-banner-container");
const tableBody = document.getElementById("table-body");
const airlineTableBody = document.getElementById("airline-table-body");
const flightsLogTableBody = document.getElementById("flights-log-table-body");
const flightSearchInput = document.getElementById("flight-search");
const sourceIndicator = document.getElementById("source-indicator");
const dashboardContent = document.getElementById("dashboard-content");
const loadingState = document.getElementById("loading-state");
const errorState = document.getElementById("error-state");
const emptyState = document.getElementById("empty-state");

// Obtener la fecha local de CDMX en formato YYYY-MM-DD
function getCdmxDateString() {
  const d = new Date();
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Mexico_City',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  });
  return formatter.format(d);
}

// Inicialización de la Página
document.addEventListener("DOMContentLoaded", () => {
  // Establecer fecha por defecto a "hoy" en CDMX
  selectedDate = getCdmxDateString();
  dateSelector.value = selectedDate;
  
  cargarDatos(selectedDate);
  
  // Event Listeners
  dateSelector.addEventListener("change", (e) => {
    selectedDate = e.target.value;
    cargarDatos(selectedDate);
  });
  
  // El botón refresh gatilla sincronización con la API y recarga
  btnRefresh.addEventListener("click", () => {
    sincronizarYRecargar();
  });
  
  // El botón en el estado vacío gatilla sincronización
  btnSyncEmpty.addEventListener("click", () => {
    sincronizarYRecargar();
  });

  // Buscador interactivo en tiempo real para la Bitácora de Vuelos
  flightSearchInput.addEventListener("input", (e) => {
    const term = e.target.value.toLowerCase().trim();
    if (!term) {
      renderFlightsLog(rawFlightsList);
      return;
    }
    
    // Filtrar la lista local en base a cualquier columna coincendente
    const filtered = rawFlightsList.filter(v => {
      const tipoText = v.tipo === "ARR" ? "llegada" : "salida";
      return v.vuelo.toLowerCase().includes(term) ||
             v.origen.toLowerCase().includes(term) ||
             v.destino.toLowerCase().includes(term) ||
             v.aeronave.toLowerCase().includes(term) ||
             v.aerolinea_nombre.toLowerCase().includes(term) ||
             tipoText.includes(term) ||
             v.hora.includes(term);
    });
    
    renderFlightsLog(filtered);
  // Obtener estado inicial de la autosincronización
  const autosyncToggle = document.getElementById("autosync-toggle");
  
  async function cargarEstadoAutosync() {
    try {
      const res = await fetch("/api/config/autosync");
      if (res.ok) {
        const data = await res.json();
        autosyncToggle.checked = data.enabled;
      }
    } catch (err) {
      console.error("Error al obtener estado de autosync:", err);
    }
  }
  
  cargarEstadoAutosync();
  
  // Event listener para el cambio de autosincronización
  autosyncToggle.addEventListener("change", async (e) => {
    const isChecked = e.target.checked;
    const actionText = isChecked ? "ACTIVAR" : "DESACTIVAR";
    const pin = prompt(`Ingrese la contraseña de seguridad para ${actionText} la sincronización automática (PIN):`);
    
    if (pin === null) {
      e.target.checked = !isChecked; // Revertir
      return;
    }
    
    try {
      const res = await fetch("/api/config/autosync", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          pin: pin,
          enabled: isChecked
        })
      });
      
      const result = await res.json();
      
      if (!res.ok || !result.success) {
        alert(result.error || "Error al configurar la sincronización automática.");
        e.target.checked = !isChecked; // Revertir
      } else {
        alert(result.message);
      }
    } catch (err) {
      console.error("Error al guardar autosync config:", err);
      alert("Error de red al guardar la configuración.");
      e.target.checked = !isChecked; // Revertir
    }
  });

  // Cargar versión de la app
  async function cargarVersion() {
    try {
      const res = await fetch("/version.json");
      if (res.ok) {
        const data = await res.json();
        document.getElementById("app-version").textContent = `v${data.version}`;
      }
    } catch (e) {
      console.error("Error al cargar versión:", e);
    }
  }
  
  cargarVersion();
});

// Cargar Datos desde la API local del servidor Flask
async function cargarDatos(fecha) {
  mostrarCarga("Cargando información local...");
  
  try {
    const response = await fetch(`/api/data?date=${fecha}`);
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.error || `HTTP error! status: ${response.status}`);
    }
    
    const data = await response.json();
    
    if (data.empty) {
      mostrarVacio();
      return;
    }
    
    procesarYRenderizar(
      data.horas, 
      data.aerolineas || [], 
      data.vuelos || [], 
      data.rutas || [], 
      data.flota || [], 
      data.detalle_pico || [], 
      data.insights || [], 
      fecha
    );
    
  } catch (error) {
    console.error("Error al cargar datos:", error);
    mostrarError(`Error al consultar la base de datos local: ${error.message}. Asegúrate de que el servidor Flask esté corriendo.`);
  }
}

// Enviar petición para ejecutar sincronización (Worker) desde el servidor local
async function sincronizarYRecargar() {
  const pin = prompt("Ingrese la contraseña de seguridad para iniciar sincronización (PIN):");
  if (pin === null) return; // Cancelado
  
  mostrarCarga("Sincronizando con FlightAware AeroAPI (Outbound HTTPS)...");
  
  try {
    const response = await fetch(`/api/sync?date=${selectedDate}&pin=${pin}`, {
      method: "POST"
    });
    
    const result = await response.json();
    
    if (!response.ok || !result.success) {
      throw new Error(result.error || "Error en la sincronización.");
    }
    
    // Recargar los datos una vez finalizada la sincronización
    mostrarCarga("Actualizando interfaz...");
    await cargarDatos(selectedDate);
    
  } catch (error) {
    console.error("Error en sincronización:", error);
    mostrarError(`Error de Sincronización: ${error.message}. Verifica tu conexión a internet, tu API Key de FlightAware y que el servidor backend esté encendido.`);
  }
}

// Procesar datos y actualizar la interfaz gráfica
function procesarYRenderizar(horas, aerolineas, vuelos, rutas, flota, detallePico, insights, fecha) {
  // Calcular métricas
  let totalOps = 0;
  let peakOps = 0;
  let peakHour = "N/A";
  let saturatedCount = 0;
  
  horas.forEach(h => {
    totalOps += h.total;
    
    if (h.total > peakOps) {
      peakOps = h.total;
      peakHour = h.bloque_horario;
    }
    
    if (h.total > 44) {
      saturatedCount++;
    }
  });
  
  const avgOps = (totalOps / 24).toFixed(1);
  
  // Renderizar KPIs
  kpiTotal.textContent = totalOps;
  kpiPeak.textContent = `${peakHour} (${peakOps} ops)`;
  kpiAverage.textContent = `${avgOps} / h`;
  kpiSaturated.textContent = `${saturatedCount} hr${saturatedCount !== 1 ? 's' : ''}`;
  
  // Cambiar color de tarjeta de saturación si hay horas con sobrecarga
  const kpiSaturatedCard = kpiSaturated.closest(".kpi-card");
  if (saturatedCount > 0) {
    kpiSaturatedCard.style.setProperty("--card-accent", "var(--accent-rose)");
  } else {
    kpiSaturatedCard.style.setProperty("--card-accent", "var(--accent-emerald)");
  }
  
  // Actualizar Banner de Advertencia de Capacidad
  warningBannerContainer.innerHTML = "";
  if (saturatedCount > 0) {
    const banner = document.createElement("div");
    banner.className = "capacity-warning-banner";
    banner.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <div>
        <strong>Capacidad Máxima Superada:</strong> Se registraron <strong>${saturatedCount} horas</strong> que excedieron la línea de referencia de 44 operaciones por hora. El pico máximo fue de <strong>${peakOps} operaciones</strong> a las ${peakHour}.
      </div>
    `;
    warningBannerContainer.appendChild(banner);
  }
  
  // Renderizar Insights Operacionales
  const insightsList = document.getElementById("insights-list");
  insightsList.innerHTML = "";
  insights.forEach(ins => {
    const li = document.createElement("li");
    li.style.display = "flex";
    li.style.alignItems = "flex-start";
    li.style.gap = "0.75rem";
    li.style.lineHeight = "1.6";
    li.innerHTML = `
      <span style="color: var(--accent-cyan); font-weight: bold; font-size: 1.25rem; line-height: 1;">✦</span>
      <div>${ins}</div>
    `;
    insightsList.appendChild(li);
  });
  
  // Renderizar Desglose de Hora Pico
  const peakHourDetailsContainer = document.getElementById("peak-hour-details");
  peakHourDetailsContainer.innerHTML = "";
  if (detallePico && detallePico.length > 0) {
    const totalPico = detallePico.reduce((acc, curr) => acc + curr.total, 0);
    
    detallePico.forEach(p => {
      const pct = totalPico > 0 ? ((p.total / totalPico) * 100).toFixed(0) : 0;
      const item = document.createElement("div");
      item.style.marginBottom = "0.5rem";
      
      const badgeClass = p.tipo === "ARR" ? "badge-normal" : "badge-source";
      const badgeText = p.tipo === "ARR" ? "ARR" : "DEP";
      
      item.innerHTML = `
        <div style="display: flex; justify-content: space-between; font-size: 0.875rem; margin-bottom: 0.35rem;">
          <div>
            <span class="badge ${badgeClass}" style="padding: 0.15rem 0.4rem; font-size: 0.65rem; margin-right: 0.5rem; border-radius: 4px; font-weight:700;">${badgeText}</span>
            <strong style="color: var(--text-primary); font-family: monospace; font-size: 0.95rem;">${p.aeropuerto}</strong>
          </div>
          <span style="color: var(--text-secondary); font-size: 0.85rem;"><strong>${p.total} ops</strong> (${pct}%)</span>
        </div>
        <div style="background: rgba(255,255,255,0.03); border-radius: 4px; height: 8px; overflow: hidden; position: relative; border: 1px solid rgba(255,255,255,0.01);">
          <div style="background: ${p.tipo === 'ARR' ? 'var(--accent-emerald)' : 'var(--accent-purple)'}; height: 100%; width: ${pct}%; border-radius: 4px; transition: width 0.8s ease-out;"></div>
        </div>
      `;
      peakHourDetailsContainer.appendChild(item);
    });
  } else {
    peakHourDetailsContainer.innerHTML = `
      <div style="text-align:center; color:var(--text-muted); padding: 3rem 0; font-size: 0.875rem; display:flex; flex-direction:column; align-items:center; gap:0.5rem;">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" style="width:32px; height:32px; color:var(--text-muted);">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span>Sin datos operacionales en esta fecha para desglosar la hora pico.</span>
      </div>`;
  }
  
  // Renderizar Tabla Horaria
  tableBody.innerHTML = "";
  horas.forEach(h => {
    const tr = document.createElement("tr");
    
    // Determinar Badge de Estado
    let badgeClass = "badge-normal";
    let badgeText = "Fluido";
    if (h.total > 44) {
      badgeClass = "badge-saturated";
      badgeText = "Saturado";
    } else if (h.total >= 35) {
      badgeClass = "badge-warning";
      badgeText = "Alta Densidad";
    }
    
    tr.innerHTML = `
      <td>${h.bloque_horario}</td>
      <td>${h.arr}</td>
      <td>${h.dep}</td>
      <td><strong>${h.total}</strong></td>
      <td><span class="badge ${badgeClass}">${badgeText}</span></td>
    `;
    tableBody.appendChild(tr);
  });
  
  // Renderizar Tabla de Aerolíneas
  airlineTableBody.innerHTML = "";
  if (aerolineas && aerolineas.length > 0) {
    aerolineas.forEach(a => {
      const tr = document.createElement("tr");
      const pct = totalOps > 0 ? ((a.total / totalOps) * 100).toFixed(1) : "0.0";
      
      tr.innerHTML = `
        <td><strong>${a.nombre}</strong></td>
        <td><span class="badge badge-source">${a.codigo}</span></td>
        <td>${a.arr}</td>
        <td>${a.dep}</td>
        <td><strong>${a.total}</strong></td>
        <td>${pct}%</td>
      `;
      airlineTableBody.appendChild(tr);
    });
    
    // Renderizar gráfico de dona por aerolínea
    renderAirlineChart(aerolineas, totalOps);
  } else {
    airlineTableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding: 2rem;">No hay operaciones de aerolíneas registradas en esta fecha.</td></tr>`;
    if (airlineChartInstance) {
      airlineChartInstance.destroy();
      airlineChartInstance = null;
    }
  }
  
  // Guardar y renderizar la Bitácora Detallada de Vuelos
  rawFlightsList = vuelos;
  renderFlightsLog(rawFlightsList);
  flightSearchInput.value = ""; // Reiniciar filtro
  
  // Renderizar Gráficas Nuevas
  renderChart(horas);
  renderRoutesChart(rutas);
  renderFleetChart(flota);
  
  mostrarResultados();
}

// Renderizar Gráfico de Líneas Temporal (Chart.js)
function renderChart(horas) {
  const ctx = document.getElementById("operationsChart").getContext("2d");
  
  const labels = horas.map(d => d.bloque_horario);
  const totalData = horas.map(d => d.total);
  const arrData = horas.map(d => d.arr);
  const depData = horas.map(d => d.dep);
  const capacityData = Array(24).fill(44);
  
  if (chartInstance) {
    chartInstance.destroy();
  }
  
  const gradientFill = ctx.createLinearGradient(0, 0, 0, 400);
  gradientFill.addColorStop(0, 'rgba(6, 182, 212, 0.25)');
  gradientFill.addColorStop(1, 'rgba(6, 182, 212, 0.0)');
  
  chartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Total Operaciones',
          data: totalData,
          borderColor: '#06b6d4',
          borderWidth: 3,
          pointBackgroundColor: '#06b6d4',
          pointHoverRadius: 6,
          tension: 0.4,
          fill: true,
          backgroundColor: gradientFill,
          z: 10
        },
        {
          label: 'Aterrizajes (ARR)',
          data: arrData,
          borderColor: '#10b981',
          borderWidth: 1.5,
          borderDash: [4, 4],
          pointBackgroundColor: '#10b981',
          pointRadius: 2,
          tension: 0.4,
          fill: false
        },
        {
          label: 'Despegues (DEP)',
          data: depData,
          borderColor: '#8b5cf6',
          borderWidth: 1.5,
          borderDash: [4, 4],
          pointBackgroundColor: '#8b5cf6',
          pointRadius: 2,
          tension: 0.4,
          fill: false
        },
        {
          label: 'Capacidad Declarada (44)',
          data: capacityData,
          borderColor: '#f43f5e',
          borderWidth: 2,
          borderDash: [6, 3],
          pointRadius: 0,
          fill: false,
          tension: 0,
          z: 5
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top',
          labels: {
            color: '#9ca3af',
            font: { family: "'Outfit', sans-serif", size: 12 },
            padding: 20
          }
        },
        tooltip: {
          backgroundColor: '#111425',
          titleColor: '#f3f4f6',
          bodyColor: '#9ca3af',
          borderColor: 'rgba(255, 255, 255, 0.08)',
          borderWidth: 1,
          titleFont: { family: "'Outfit', sans-serif", weight: 'bold' },
          bodyFont: { family: "'Outfit', sans-serif" },
          padding: 12,
          callbacks: {
            label: function(context) {
              let label = context.dataset.label || '';
              if (label) label += ': ';
              if (context.parsed.y !== null) label += context.parsed.y;
              if (context.dataset.label === 'Total Operaciones' && context.parsed.y > 44) {
                label += ' ⚠️ (SOBRE CAPACIDAD)';
              }
              return label;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.03)', borderColor: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#9ca3af', font: { family: "'Outfit', sans-serif" } }
        },
        y: {
          grid: { color: 'rgba(255, 255, 255, 0.05)', borderColor: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#9ca3af', font: { family: "'Outfit', sans-serif" }, stepSize: 5 },
          min: 0,
          suggestedMax: 50
        }
      }
    }
  });
}

// Renderizar Gráfico de Dona para Aerolíneas (Chart.js)
function renderAirlineChart(aerolineas, totalOps) {
  const ctx = document.getElementById("airlineChart").getContext("2d");
  
  if (airlineChartInstance) {
    airlineChartInstance.destroy();
  }
  
  const topAerolineas = [];
  let otrasTotal = 0;
  
  aerolineas.forEach((a, idx) => {
    if (idx < 5) {
      topAerolineas.push(a);
    } else {
      otrasTotal += a.total;
    }
  });
  
  if (otrasTotal > 0) {
    topAerolineas.push({
      codigo: "Otras",
      nombre: "Otras Aerolíneas",
      total: otrasTotal
    });
  }
  
  const labels = topAerolineas.map(a => a.nombre);
  const data = topAerolineas.map(a => a.total);
  
  const colors = [
    '#06b6d4', // Cyan
    '#8b5cf6', // Morado
    '#10b981', // Verde esmeralda
    '#f59e0b', // Amarillo
    '#3b82f6', // Azul
    '#4b5563'  // Gris (Otras)
  ];
  
  airlineChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: colors.slice(0, topAerolineas.length),
        borderColor: 'rgba(16, 20, 38, 0.8)',
        borderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'right',
          labels: {
            color: '#9ca3af',
            font: { family: "'Outfit', sans-serif", size: 12 },
            boxWidth: 12,
            padding: 15
          }
        },
        tooltip: {
          backgroundColor: '#111425',
          titleColor: '#f3f4f6',
          bodyColor: '#9ca3af',
          borderColor: 'rgba(255, 255, 255, 0.08)',
          borderWidth: 1,
          titleFont: { family: "'Outfit', sans-serif", weight: 'bold' },
          bodyFont: { family: "'Outfit', sans-serif" },
          padding: 10,
          callbacks: {
            label: function(context) {
              const val = context.parsed;
              const pct = totalOps > 0 ? ((val / totalOps) * 100).toFixed(1) : "0.0";
              return ` ${context.label}: ${val} ops (${pct}%)`;
            }
          }
        }
      },
      cutout: '65%'
    }
  });
}

// Renderizar Gráfico de Barras Horizontales para Rutas Top
function renderRoutesChart(rutas) {
  const ctx = document.getElementById("routesChart").getContext("2d");
  
  if (routesChartInstance) {
    routesChartInstance.destroy();
  }
  
  if (!rutas || rutas.length === 0) {
    ctx.clearRect(0, 0, 300, 300);
    return;
  }
  
  const labels = rutas.map(r => `${r.origen} ➔ ${r.destino}`);
  const totals = rutas.map(r => r.total);
  
  const gradient = ctx.createLinearGradient(0, 0, 400, 0);
  gradient.addColorStop(0, 'rgba(6, 182, 212, 0.3)');
  gradient.addColorStop(1, '#06b6d4');
  
  routesChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Operaciones',
        data: totals,
        backgroundColor: gradient,
        borderRadius: 6,
        borderWidth: 0,
        barThickness: 16
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#111425',
          titleColor: '#f3f4f6',
          bodyColor: '#9ca3af',
          borderColor: 'rgba(255, 255, 255, 0.08)',
          borderWidth: 1,
          titleFont: { family: "'Outfit', sans-serif", weight: 'bold' },
          bodyFont: { family: "'Outfit', sans-serif" }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.03)', borderColor: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#9ca3af', font: { family: "'Outfit', sans-serif" }, stepSize: 2 }
        },
        y: {
          grid: { display: false },
          ticks: { 
            color: '#f3f4f6', 
            font: { family: "monospace", size: 12, weight: 'bold' } 
          }
        }
      }
    }
  });
}

// Renderizar Gráfico de Dona para Mix de Flota (Aeronaves)
function renderFleetChart(flota) {
  const ctx = document.getElementById("fleetChart").getContext("2d");
  
  if (fleetChartInstance) {
    fleetChartInstance.destroy();
  }
  
  if (!flota || flota.length === 0) {
    ctx.clearRect(0, 0, 300, 300);
    return;
  }
  
  const labels = flota.map(f => f.aeronave);
  const totals = flota.map(f => f.total);
  
  const colors = [
    '#8b5cf6', // Morado
    '#06b6d4', // Cyan
    '#10b981', // Verde
    '#f59e0b', // Amarillo
    '#f43f5e'  // Rosa
  ];
  
  fleetChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: totals,
        backgroundColor: colors.slice(0, flota.length),
        borderColor: 'rgba(16, 20, 38, 0.8)',
        borderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'right',
          labels: {
            color: '#9ca3af',
            font: { family: "'Outfit', sans-serif", size: 12 },
            boxWidth: 12,
            padding: 15
          }
        },
        tooltip: {
          backgroundColor: '#111425',
          titleColor: '#f3f4f6',
          bodyColor: '#9ca3af',
          borderColor: 'rgba(255, 255, 255, 0.08)',
          borderWidth: 1,
          titleFont: { family: "'Outfit', sans-serif", weight: 'bold' },
          bodyFont: { family: "'Outfit', sans-serif" }
        }
      },
      cutout: '65%'
    }
  });
}

// Renderizar la Bitácora Detallada de Vuelos
function renderFlightsLog(list) {
  flightsLogTableBody.innerHTML = "";
  
  if (list && list.length > 0) {
    list.forEach(v => {
      const tr = document.createElement("tr");
      
      const opClass = v.tipo === "ARR" ? "badge-normal" : "badge-source";
      const opText = v.tipo === "ARR" ? "Llegada" : "Salida";
      
      tr.innerHTML = `
        <td>${v.hora}</td>
        <td><strong>${v.vuelo}</strong></td>
        <td><span class="badge ${opClass}">${opText}</span></td>
        <td>${v.aerolinea_nombre}</td>
        <td><span style="font-family: monospace; font-size: 0.95rem; font-weight: 500; color: var(--text-secondary);">${v.origen}</span></td>
        <td><span style="font-family: monospace; font-size: 0.95rem; font-weight: 500; color: var(--text-secondary);">${v.destino}</span></td>
        <td><span class="badge" style="background: rgba(255,255,255,0.05); color: var(--text-secondary); border: 1px solid rgba(255,255,255,0.03);">${v.aeronave}</span></td>
      `;
      flightsLogTableBody.appendChild(tr);
    });
  } else {
    flightsLogTableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:var(--text-muted); padding: 3rem;">No se encontraron vuelos que coincidan con la búsqueda.</td></tr>`;
  }
}

// Funciones Auxiliares de Interfaz
function mostrarCarga(mensaje) {
  dashboardContent.style.opacity = "0.3";
  dashboardContent.style.pointerEvents = "none";
  loadingState.style.display = "flex";
  loadingState.querySelector("p").textContent = mensaje || "Cargando...";
  errorState.style.display = "none";
  emptyState.style.display = "none";
}

// Mostrar Resultados
function mostrarResultados() {
  dashboardContent.style.opacity = "1";
  dashboardContent.style.pointerEvents = "all";
  loadingState.style.display = "none";
  errorState.style.display = "none";
  emptyState.style.display = "none";
}

// Mostrar Error
function mostrarError(mensaje) {
  dashboardContent.style.opacity = "0.1";
  dashboardContent.style.pointerEvents = "none";
  loadingState.style.display = "none";
  errorState.style.display = "flex";
  emptyState.style.display = "none";
  
  errorState.querySelector("p").textContent = mensaje;
}

// Mostrar Estado Vacío
function mostrarVacio() {
  dashboardContent.style.opacity = "0.1";
  dashboardContent.style.pointerEvents = "none";
  loadingState.style.display = "none";
  errorState.style.display = "none";
  emptyState.style.display = "flex";
}
