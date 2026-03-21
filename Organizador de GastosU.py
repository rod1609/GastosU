import json
import os
import smtplib
import threading
import time
from datetime import date, datetime
from email.message import EmailMessage

from flask import Flask, redirect, render_template_string, request, url_for

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GASTOS_FILE = os.path.join(BASE_DIR, "gastos_pasajes.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

gastos = []
proximo_id = 1
email_destino = os.environ.get("TASKS_EMAIL_TO", "")
ultimo_recordatorio = ""

EMAIL_FROM = os.environ.get("TASKS_EMAIL_FROM", "romartelo08@gmail.com")
EMAIL_PASSWORD = os.environ.get("TASKS_EMAIL_PASSWORD", "nescrksscowvhbei")
REMINDER_HOUR = int(os.environ.get("TASKS_REMINDER_HOUR", "12"))
recordatorio_iniciado = False


def cargar_gastos():
    global gastos, proximo_id
    gastos[:] = []
    if os.path.exists(GASTOS_FILE):
        try:
            with open(GASTOS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                gastos[:] = data
        except (json.JSONDecodeError, OSError):
            pass
    proximo_id = max((g["id"] for g in gastos), default=0) + 1


def guardar_gastos():
    try:
        with open(GASTOS_FILE, "w", encoding="utf-8") as f:
            json.dump(gastos, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def cargar_config():
    global email_destino, ultimo_recordatorio
    if not os.path.exists(CONFIG_FILE):
        return
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            email_destino = data.get("email_destino", email_destino)
            ultimo_recordatorio = data.get("ultimo_recordatorio", ultimo_recordatorio)
    except (json.JSONDecodeError, OSError):
        pass


def guardar_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "email_destino": email_destino,
                    "ultimo_recordatorio": ultimo_recordatorio,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
    except OSError:
        pass


def gasto_por_id(gasto_id):
    return next((g for g in gastos if g["id"] == gasto_id), None)


def a_float(valor):
    try:
        return round(float(valor), 2)
    except (TypeError, ValueError):
        return None


def validar_fecha(fecha_texto):
    try:
        datetime.strptime(fecha_texto, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


def resumen():
    hoy = date.today()
    iso_hoy = hoy.isocalendar()
    total_ida = sum(g["pasaje_ida"] for g in gastos)
    total_vuelta = sum(g["pasaje_vuelta"] for g in gastos)
    total_general = total_ida + total_vuelta
    total_semanal = 0.0
    total_mensual = 0.0

    for g in gastos:
        try:
            fecha_gasto = datetime.strptime(g["fecha"], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue

        if fecha_gasto.isocalendar()[:2] == iso_hoy[:2]:
            total_semanal += g.get("total_dia", 0)
        if fecha_gasto.year == hoy.year and fecha_gasto.month == hoy.month:
            total_mensual += g.get("total_dia", 0)

    return {
        "dias_registrados": len(gastos),
        "total_ida": round(total_ida, 2),
        "total_vuelta": round(total_vuelta, 2),
        "total_general": round(total_general, 2),
        "total_semanal": round(total_semanal, 2),
        "total_mensual": round(total_mensual, 2),
    }


def gastos_ordenados():
    return sorted(gastos, key=lambda g: g["fecha"], reverse=True)


def enviar_recordatorio_diario():
    if not (EMAIL_FROM and EMAIL_PASSWORD and email_destino):
        return False

    msg = EmailMessage()
    msg["Subject"] = "Recordatorio: registra tu gasto de pasaje universitario"
    msg["From"] = EMAIL_FROM
    msg["To"] = email_destino
    msg.set_content(
        """Hola,

Este es tu recordatorio de lunes a viernes para registrar tu gasto diario
de pasaje de ida y vuelta en Organizador de GastosU.

Que tengas un buen dia de clases.
"""
    )

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception:
        return False


def iniciar_recordatorio_semanal():
    def loop_recordatorio():
        global ultimo_recordatorio
        while True:
            ahora = datetime.now()
            hoy = ahora.date().isoformat()
            es_laboral = ahora.weekday() < 5
            hora_objetivo = ahora.hour >= REMINDER_HOUR

            if es_laboral and hora_objetivo and ultimo_recordatorio != hoy:
                enviado = enviar_recordatorio_diario()
                if enviado:
                    ultimo_recordatorio = hoy
                    guardar_config()
            time.sleep(60)

    hilo = threading.Thread(target=loop_recordatorio, daemon=True)
    hilo.start()


@app.before_request
def asegurar_recordatorio():
    global recordatorio_iniciado
    if not recordatorio_iniciado:
        iniciar_recordatorio_semanal()
        recordatorio_iniciado = True


PLANTILLA_INDEX = """
<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Organizador de GastosU</title>
    <style>
      body { font-family: system-ui, sans-serif; margin: 0; padding: 0; background: #f3f4f6; }
      .container { max-width: 960px; margin: 32px auto; background: #fff; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.06); padding: 24px 28px 32px; }
      h1 { margin: 0 0 14px; font-size: 1.8rem; }
      .intro { margin: 0 0 20px; color: #4b5563; }
      .resumen { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; margin-bottom: 22px; }
      .card { background: #eef2ff; border: 1px solid #e0e7ff; border-radius: 8px; padding: 10px 12px; }
      .card h3 { margin: 0 0 4px; font-size: 0.84rem; color: #4338ca; font-weight: 600; }
      .card p { margin: 0; font-size: 1.05rem; font-weight: 700; color: #1f2937; }
      form { display: grid; grid-template-columns: 1.2fr 1fr 1fr 1.6fr auto; gap: 8px; margin-bottom: 18px; }
      input, button { padding: 9px 10px; border-radius: 6px; border: 1px solid #d1d5db; font-size: 0.94rem; }
      button { background: #2563eb; color: #fff; border: none; cursor: pointer; }
      button:hover { background: #1d4ed8; }
      .tabla-wrap { width: 100%; overflow-x: auto; }
      table { width: 100%; border-collapse: collapse; min-width: 680px; }
      th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid #e5e7eb; font-size: 0.93rem; }
      th { color: #374151; background: #f9fafb; }
      .total-dia { font-weight: 700; color: #111827; }
      .acciones a { margin-right: 8px; font-size: 0.85rem; text-decoration: none; }
      .editar { color: #2563eb; }
      .eliminar { color: #dc2626; }
      .acciones a:hover { text-decoration: underline; }
      .vacio { color: #9ca3af; margin: 8px 0 0; }
      .error { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; padding: 9px 10px; border-radius: 8px; margin: 0 0 14px; }
      .correo-box { margin: 0 0 14px; background: #eff6ff; border: 1px solid #dbeafe; border-radius: 8px; padding: 10px; }
      .correo-box h3 { margin: 0 0 8px; font-size: 0.95rem; color: #1d4ed8; }
      .correo-box p { margin: 6px 0 0; color: #6b7280; font-size: 0.85rem; }
      .correo-form { display: grid; grid-template-columns: 1fr auto; gap: 8px; margin: 0; }
      @media (max-width: 850px) {
        .container { margin: 12px; padding: 18px 14px 20px; border-radius: 10px; }
        h1 { font-size: 1.35rem; margin-bottom: 10px; }
        .intro { font-size: 0.93rem; margin-bottom: 14px; }
        .resumen { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        form { grid-template-columns: 1fr; }
        input, button { font-size: 1rem; }
        .correo-form { grid-template-columns: 1fr; }
      }
      @media (max-width: 600px) {
        .resumen { grid-template-columns: 1fr; }
        .tabla-wrap { overflow: visible; }
        table { min-width: 0; border-collapse: separate; border-spacing: 0 10px; }
        thead { display: none; }
        tbody tr { display: block; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 10px; padding: 8px 10px; }
        tbody td { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; border: none; padding: 6px 0; text-align: right; }
        tbody td::before { content: attr(data-label); color: #4b5563; font-weight: 600; text-align: left; }
        .acciones { justify-content: flex-end; }
        .acciones a { margin-right: 0; margin-left: 12px; }
      }
    </style>
  </head>
  <body>
    <div class="container">
      <h1>Organizador de Gastos de Pasajes (Universidad)</h1>
      <p class="intro">Registra cada dia de clases con pasaje de ida y vuelta para controlar tu presupuesto.</p>

      {% if error %}
      <p class="error">{{ error }}</p>
      {% endif %}

      <section class="correo-box">
        <h3>Recordatorio por correo (lunes a viernes)</h3>
        <form class="correo-form" action="{{ url_for('config_correo') }}" method="post">
          <input type="email" name="email" value="{{ email_destino or '' }}" placeholder="tu_correo@ejemplo.com" required>
          <button type="submit">Guardar correo</button>
        </form>
        <p>Se enviara 1 recordatorio diario de lunes a viernes despues de las {{ reminder_hour }}:00.</p>
      </section>

      <section class="resumen">
        <div class="card"><h3>Dias registrados</h3><p>{{ resumen.dias_registrados }}</p></div>
        <div class="card"><h3>Total ida</h3><p>S/. {{ "%.2f"|format(resumen.total_ida) }}</p></div>
        <div class="card"><h3>Total vuelta</h3><p>S/. {{ "%.2f"|format(resumen.total_vuelta) }}</p></div>
        <div class="card"><h3>Total general</h3><p>S/. {{ "%.2f"|format(resumen.total_general) }}</p></div>
        <div class="card"><h3>Gasto semanal</h3><p>S/. {{ "%.2f"|format(resumen.total_semanal) }}</p></div>
        <div class="card"><h3>Gasto mensual</h3><p>S/. {{ "%.2f"|format(resumen.total_mensual) }}</p></div>
      </section>

      <form action="{{ url_for('agregar_gasto') }}" method="post">
        <input type="date" name="fecha" value="{{ hoy }}" required>
        <input type="number" name="pasaje_ida" step="0.01" min="0" placeholder="Pasaje ida" required>
        <input type="number" name="pasaje_vuelta" step="0.01" min="0" placeholder="Pasaje vuelta" required>
        <input type="text" name="nota" placeholder="Nota opcional (ej: hubo trafico)">
        <button type="submit">Guardar dia</button>
      </form>

      {% if gastos %}
      <div class="tabla-wrap">
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Ida</th>
              <th>Vuelta</th>
              <th>Total del dia</th>
              <th>Nota</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {% for g in gastos %}
            <tr>
              <td data-label="Fecha">{{ g.fecha }}</td>
              <td data-label="Ida">S/. {{ "%.2f"|format(g.pasaje_ida) }}</td>
              <td data-label="Vuelta">S/. {{ "%.2f"|format(g.pasaje_vuelta) }}</td>
              <td class="total-dia" data-label="Total del dia">S/. {{ "%.2f"|format(g.total_dia) }}</td>
              <td data-label="Nota">{{ g.nota or "-" }}</td>
              <td class="acciones" data-label="Acciones">
                <a class="editar" href="{{ url_for('editar_gasto', gasto_id=g.id) }}">Editar</a>
                <a class="eliminar" href="{{ url_for('eliminar_gasto', gasto_id=g.id) }}">Eliminar</a>
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% else %}
      <p class="vacio">Aun no registras gastos de pasaje.</p>
      {% endif %}
    </div>
  </body>
</html>
"""

PLANTILLA_EDITAR = """
<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Editar gasto</title>
    <style>
      body { font-family: system-ui, sans-serif; margin: 0; padding: 0; background: #f3f4f6; }
      .container { max-width: 620px; margin: 36px auto; background: #fff; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.06); padding: 24px 28px 30px; }
      h1 { margin: 0 0 14px; font-size: 1.5rem; }
      form { display: grid; gap: 10px; }
      input, button { padding: 9px 10px; border-radius: 6px; border: 1px solid #d1d5db; font-size: 0.94rem; }
      button { background: #2563eb; color: #fff; border: none; cursor: pointer; }
      button:hover { background: #1d4ed8; }
      .volver { display: inline-block; margin-top: 12px; color: #6b7280; font-size: 0.9rem; text-decoration: none; }
      .volver:hover { text-decoration: underline; }
      .error { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; padding: 9px 10px; border-radius: 8px; margin: 0 0 14px; }
      @media (max-width: 700px) {
        .container { margin: 12px; padding: 18px 14px 20px; border-radius: 10px; }
        h1 { font-size: 1.25rem; margin-bottom: 10px; }
        input, button { font-size: 1rem; }
      }
    </style>
  </head>
  <body>
    <div class="container">
      <h1>Editar gasto diario</h1>
      {% if error %}
      <p class="error">{{ error }}</p>
      {% endif %}
      <form method="post">
        <input type="date" name="fecha" value="{{ gasto.fecha }}" required>
        <input type="number" name="pasaje_ida" step="0.01" min="0" value="{{ gasto.pasaje_ida }}" required>
        <input type="number" name="pasaje_vuelta" step="0.01" min="0" value="{{ gasto.pasaje_vuelta }}" required>
        <input type="text" name="nota" value="{{ gasto.nota }}" placeholder="Nota opcional">
        <button type="submit">Guardar cambios</button>
      </form>
      <a class="volver" href="{{ url_for('index') }}">Volver al inicio</a>
    </div>
  </body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(
        PLANTILLA_INDEX,
        gastos=gastos_ordenados(),
        resumen=resumen(),
        hoy=date.today().isoformat(),
        error=request.args.get("error", ""),
        email_destino=email_destino,
        reminder_hour=REMINDER_HOUR,
    )


@app.route("/config-correo", methods=["POST"])
def config_correo():
    global email_destino
    email = request.form.get("email", "").strip()
    if email:
        email_destino = email
        guardar_config()
    return redirect(url_for("index"))


@app.route("/agregar", methods=["POST"])
def agregar_gasto():
    global proximo_id
    fecha = request.form.get("fecha", "").strip()
    ida = a_float(request.form.get("pasaje_ida", "").strip())
    vuelta = a_float(request.form.get("pasaje_vuelta", "").strip())
    nota = request.form.get("nota", "").strip()

    if not validar_fecha(fecha):
        return redirect(url_for("index", error="La fecha no es valida."))
    if ida is None or ida < 0 or vuelta is None or vuelta < 0:
        return redirect(url_for("index", error="Ingresa montos validos para ida y vuelta."))

    gastos.append(
        {
            "id": proximo_id,
            "fecha": fecha,
            "pasaje_ida": ida,
            "pasaje_vuelta": vuelta,
            "total_dia": round(ida + vuelta, 2),
            "nota": nota,
        }
    )
    proximo_id += 1
    guardar_gastos()
    return redirect(url_for("index"))


@app.route("/editar/<int:gasto_id>", methods=["GET", "POST"])
def editar_gasto(gasto_id):
    gasto = gasto_por_id(gasto_id)
    if not gasto:
        return redirect(url_for("index", error="Registro no encontrado."))

    if request.method == "POST":
        fecha = request.form.get("fecha", "").strip()
        ida = a_float(request.form.get("pasaje_ida", "").strip())
        vuelta = a_float(request.form.get("pasaje_vuelta", "").strip())
        nota = request.form.get("nota", "").strip()

        if not validar_fecha(fecha):
            return render_template_string(PLANTILLA_EDITAR, gasto=gasto, error="La fecha no es valida.")
        if ida is None or ida < 0 or vuelta is None or vuelta < 0:
            return render_template_string(
                PLANTILLA_EDITAR,
                gasto=gasto,
                error="Ingresa montos validos para ida y vuelta.",
            )

        gasto["fecha"] = fecha
        gasto["pasaje_ida"] = ida
        gasto["pasaje_vuelta"] = vuelta
        gasto["total_dia"] = round(ida + vuelta, 2)
        gasto["nota"] = nota
        guardar_gastos()
        return redirect(url_for("index"))

    return render_template_string(PLANTILLA_EDITAR, gasto=gasto, error="")


@app.route("/eliminar/<int:gasto_id>")
def eliminar_gasto(gasto_id):
    global gastos
    gastos = [g for g in gastos if g["id"] != gasto_id]
    guardar_gastos()
    return redirect(url_for("index"))


cargar_config()
cargar_gastos()


if __name__ == "__main__":
    app.run(debug=True)
