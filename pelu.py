import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from babel.dates import format_date

# --- Conexión a Google Sheets usando Streamlit Secrets ---
def conectar_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["google_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("snturnos")

# --- Obtener feriados ---
def obtener_feriados(sheet):
    return set(sheet.col_values(1)[1:])  # Salta encabezado

# --- Generar fechas válidas (15 días futuros, solo martes a sábados y sin feriados) ---
def fechas_disponibles(feriados, max_dias=15):
    hoy = datetime.today().date()
    fechas_validas = []
    dia = hoy + timedelta(days=1)
    while len(fechas_validas) < max_dias:
        if dia.weekday() in [1, 2, 3, 4, 5] and dia.strftime("%Y-%m-%d") not in feriados:
            fechas_validas.append(dia)
        dia += timedelta(days=1)
    return fechas_validas

# --- Obtener duración total de servicios ---
def obtener_duracion(servicios_seleccionados, servicios_sheet):
    servicios = servicios_sheet.get_all_records()
    duracion_total = 0
    for servicio in servicios:
        if servicio['Servicio'] in servicios_seleccionados:
            duracion_total += int(servicio['Duración'])
    return duracion_total

# --- Buscar próximo horario disponible ---
def buscar_turno_disponible(sheet, fecha, duracion, empleado):
    turnos = sheet.get_all_records()
    hora_inicio = datetime.combine(fecha, datetime.strptime("07:00", "%H:%M").time())
    hora_fin = datetime.combine(fecha, datetime.strptime("21:00", "%H:%M").time())

    while hora_inicio + timedelta(minutes=duracion) <= hora_fin:
        disponible = True
        for t in turnos:
            if t["Fecha"] == fecha.strftime("%d/%m/%Y") and t["Empleado"] == empleado:
                inicio = datetime.strptime(t["Hora inicio"], "%H:%M")
                fin = inicio + timedelta(minutes=int(t["Duración"]))
                rango_ini = hora_inicio.time()
                rango_fin = (hora_inicio + timedelta(minutes=duracion)).time()
                if rango_ini < fin.time() and rango_fin > inicio.time():
                    disponible = False
                    break
        if disponible:
            return hora_inicio.strftime("%H:%M")
        hora_inicio += timedelta(minutes=5)
    return None

# --- Guardar turno ---
def guardar_turno(bd_sheet, cliente_sheet, datos):
    bd_sheet.append_row([
        datos['fecha'],
        datos['empleado'],
        datos['hora'],
        datos['duracion'],
        ", ".join(datos['servicios'])
    ])
    cliente_sheet.append_row([
        datos['fecha'],
        datos['nombre'],
        datos['dni'],
        datos['telefono'],
        datos['empleado'],
        ", ".join(datos['servicios']),
        datos['hora'],
        f"{datos['duracion']} min"
    ])

# --- App Streamlit ---
st.title("💈 Sistema de Turnos Peluquería")

try:
    archivo = conectar_gsheets()
    hoja_pelubd = archivo.worksheet("pelubd")
    hoja_feriados = archivo.worksheet("feriados")
    hoja_empleados = archivo.worksheet("empleados")
    hoja_servicios = archivo.worksheet("servicios")
    hoja_clientes = archivo.worksheet("turnos_clientes")

    feriados = obtener_feriados(hoja_feriados)
    fechas = fechas_disponibles(feriados)

    # ✅ Mostrar fechas en formato completo en español
    opciones_fechas = [format_date(f, format='full', locale='es') for f in fechas]
    opcion_seleccionada = st.selectbox("📅 Seleccioná una fecha", opciones_fechas)
    fecha_real = fechas[opciones_fechas.index(opcion_seleccionada)]
    fecha_seleccionada = fecha_real.strftime("%d/%m/%Y")

    servicios = hoja_servicios.col_values(1)[1:]
    servicios_elegidos = st.multiselect("✂️ Seleccioná hasta 4 servicios", servicios)

if len(servicios_elegidos) > 4:
    st.error("⚠️ Solo podés seleccionar hasta 4 servicios.")
    servicios_elegidos = servicios_elegidos[:4]

        empleados = hoja_empleados.col_values(1)[1:]
        empleado = st.selectbox("👤 Seleccioná al empleado", empleados)

    if servicios_elegidos and empleado:
        duracion_total = obtener_duracion(servicios_elegidos, hoja_servicios)
        hora_disponible = buscar_turno_disponible(
            hoja_pelubd,
            fecha_real,
            duracion_total,
            empleado
        )
        if hora_disponible:
            st.success(f"🕐 Turno disponible a las {hora_disponible}")
            with st.form("form_turno"):
                nombre = st.text_input("Nombre completo")
                dni = st.text_input("DNI")
                telefono = st.text_input("Teléfono")
                enviar = st.form_submit_button("📌 Confirmar Turno")

                if enviar:
                    if nombre and dni and telefono:
                        guardar_turno(hoja_pelubd, hoja_clientes, {
                            "fecha": fecha_seleccionada,
                            "empleado": empleado,
                            "hora": hora_disponible,
                            "duracion": duracion_total,
                            "servicios": servicios_elegidos,
                            "nombre": nombre,
                            "dni": dni,
                            "telefono": telefono
                        })
                        st.success("✅ Turno registrado correctamente.")
                    else:
                        st.error("⚠️ Completá todos los datos del formulario.")
        else:
            st.warning("❌ No hay horarios disponibles para ese día y servicios.")
    else:
        st.info("⏳ Seleccioná servicios y un empleado para ver la disponibilidad.")

except Exception as e:
    st.error(f"⚠️ Error al conectar con Google Sheets: {e}")
