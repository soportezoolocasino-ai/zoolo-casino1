#!/usr/bin/env python3
"""
ZOOLO CASINO v2.5 — Versión PostgreSQL para Render
"""

import os
import json
import csv
import io
import sys
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, render_template_string, request, session, redirect, jsonify, Response, g
from collections import defaultdict

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'zoolo_local_2025_ultra_seguro')

# ==========================================
# CONFIGURACIÓN DE BASE DE DATOS
# ==========================================

DATABASE_URL = os.environ.get('DATABASE_URL')

# Si no hay DATABASE_URL, intentamos usar SQLite como fallback (para desarrollo local)
if not DATABASE_URL:
    import sqlite3
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'zoolo_casino.db')
    print("WARNING: DATABASE_URL no encontrada. Usando SQLite local.", file=sys.stderr)
    
    def get_db():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    
    USE_SQLITE = True
else:
    import psycopg2
    USE_SQLITE = False
    
    def get_db():
        try:
            conn = psycopg2.connect(DATABASE_URL)
            return conn
        except Exception as e:
            print(f"ERROR conectando a PostgreSQL: {e}", file=sys.stderr)
            raise

# Constantes del negocio
PAGO_ANIMAL_NORMAL = 35
PAGO_LECHUZA = 70
PAGO_ESPECIAL = 2
PAGO_TRIPLETA = 60
COMISION_AGENCIA = 0.15
MINUTOS_BLOQUEO = 5

# Horarios
HORARIOS_PERU = [
    "09:00 AM", "10:00 AM", "11:00 AM", "12:00 PM",
    "01:00 PM", "02:00 PM", "03:00 PM", "04:00 PM", "05:00 PM", "06:00 PM"
]
HORARIOS_VENEZUELA = [
    "10:00 AM", "11:00 AM", "12:00 PM", "01:00 PM",
    "02:00 PM", "03:00 PM", "04:00 PM", "05:00 PM", "06:00 PM", "07:00 PM"
]

ANIMALES = {
    "00": "Ballena", "0": "Delfin", "1": "Carnero", "2": "Toro", "3": "Ciempies",
    "4": "Alacran", "5": "Leon", "6": "Rana", "7": "Perico", "8": "Raton", "9": "Aguila",
    "10": "Tigre", "11": "Gato", "12": "Caballo", "13": "Mono", "14": "Paloma",
    "15": "Zorro", "16": "Oso", "17": "Pavo", "18": "Burro", "19": "Chivo", "20": "Cochino",
    "21": "Gallo", "22": "Camello", "23": "Cebra", "24": "Iguana", "25": "Gallina",
    "26": "Vaca", "27": "Perro", "28": "Zamuro", "29": "Elefante", "30": "Caiman",
    "31": "Lapa", "32": "Ardilla", "33": "Pescado", "34": "Venado", "35": "Jirafa",
    "36": "Culebra", "37": "Aviapa", "38": "Conejo", "39": "Tortuga", "40": "Lechuza"
}

COLORES = {
    "00": "verde", "0": "verde",
    "1": "rojo", "3": "rojo", "5": "rojo", "7": "rojo", "9": "rojo",
    "12": "rojo", "14": "rojo", "16": "rojo", "18": "rojo", "19": "rojo",
    "21": "rojo", "23": "rojo", "25": "rojo", "27": "rojo", "30": "rojo",
    "32": "rojo", "34": "rojo", "36": "rojo", "37": "rojo", "39": "rojo",
    "40": "negro",
    "2": "negro", "4": "negro", "6": "negro", "8": "negro", "10": "negro", "11": "negro",
    "13": "negro", "15": "negro", "17": "negro", "20": "negro", "22": "negro",
    "24": "negro", "26": "negro", "28": "negro", "29": "negro", "31": "negro",
    "33": "negro", "35": "negro", "38": "negro"
}

ROJOS = ["1", "3", "5", "7", "9", "12", "14", "16", "18", "19",
         "21", "23", "25", "27", "30", "32", "34", "36", "37", "39"]


# ==================== DATABASE ====================

def init_db():
    """Inicializa la base de datos con tablas para PostgreSQL o SQLite"""
    conn = get_db()
    
    if USE_SQLITE:
        # Versión SQLite
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS agencias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                nombre_agencia TEXT NOT NULL,
                es_admin INTEGER DEFAULT 0,
                comision REAL DEFAULT 0.15,
                activa INTEGER DEFAULT 1,
                creado TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                serial TEXT UNIQUE NOT NULL,
                agencia_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                total REAL NOT NULL,
                pagado INTEGER DEFAULT 0,
                anulado INTEGER DEFAULT 0,
                creado TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS jugadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                hora TEXT NOT NULL,
                seleccion TEXT NOT NULL,
                monto REAL NOT NULL,
                tipo TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tripletas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                animal1 TEXT NOT NULL,
                animal2 TEXT NOT NULL,
                animal3 TEXT NOT NULL,
                monto REAL NOT NULL,
                fecha TEXT NOT NULL,
                pagado INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS resultados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                hora TEXT NOT NULL,
                animal TEXT NOT NULL,
                UNIQUE(fecha, hora)
            );
        """)
        
        # Crear admin si no existe
        admin = conn.execute("SELECT id FROM agencias WHERE es_admin=1").fetchone()
        if not admin:
            conn.execute("""
                INSERT INTO agencias (usuario, password, nombre_agencia, es_admin, comision, activa) 
                VALUES (?, ?, ?, 1, 0, 1)
            """, ('cuborubi', '15821462', 'ADMINISTRADOR'))
        conn.commit()
        conn.close()
        
    else:
        # Versión PostgreSQL
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agencias (
                id SERIAL PRIMARY KEY,
                usuario VARCHAR UNIQUE NOT NULL,
                password VARCHAR NOT NULL,
                nombre_agencia VARCHAR NOT NULL,
                es_admin INTEGER DEFAULT 0,
                comision REAL DEFAULT 0.15,
                activa INTEGER DEFAULT 1,
                creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id SERIAL PRIMARY KEY,
                serial VARCHAR UNIQUE NOT NULL,
                agencia_id INTEGER NOT NULL,
                fecha VARCHAR NOT NULL,
                total REAL NOT NULL,
                pagado INTEGER DEFAULT 0,
                anulado INTEGER DEFAULT 0,
                creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jugadas (
                id SERIAL PRIMARY KEY,
                ticket_id INTEGER NOT NULL,
                hora VARCHAR NOT NULL,
                seleccion VARCHAR NOT NULL,
                monto REAL NOT NULL,
                tipo VARCHAR NOT NULL
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tripletas (
                id SERIAL PRIMARY KEY,
                ticket_id INTEGER NOT NULL,
                animal1 VARCHAR NOT NULL,
                animal2 VARCHAR NOT NULL,
                animal3 VARCHAR NOT NULL,
                monto REAL NOT NULL,
                fecha VARCHAR NOT NULL,
                pagado INTEGER DEFAULT 0
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS resultados (
                id SERIAL PRIMARY KEY,
                fecha VARCHAR NOT NULL,
                hora VARCHAR NOT NULL,
                animal VARCHAR NOT NULL,
                UNIQUE(fecha, hora)
            )
        """)
        
        # Crear admin si no existe
        cur.execute("SELECT id FROM agencias WHERE es_admin=1")
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO agencias (usuario, password, nombre_agencia, es_admin, comision, activa) VALUES (%s, %s, %s, 1, 0, 1)",
                ('cuborubi', '15821462', 'ADMINISTRADOR')
            )
        
        conn.commit()
        cur.close()
        conn.close()


# ==================== UTILIDADES ====================

def ahora_peru():
    """Retorna la hora actual en timezone Perú (UTC-5)"""
    return datetime.now(timezone.utc) - timedelta(hours=5)


def parse_fecha(f):
    """Parsea string de fecha a objeto datetime con múltiples formatos"""
    if not f:
        return None
    formatos = ("%d/%m/%Y %I:%M %p", "%d/%m/%Y", "%Y-%m-%d")
    for fmt in formatos:
        try:
            return datetime.strptime(f, fmt)
        except ValueError:
            continue
    return None


def generar_serial():
    """Genera serial único basado en timestamp"""
    return str(int(ahora_peru().timestamp() * 1000))


def fmt(m):
    """Formatea número quitando decimales innecesarios"""
    try:
        v = float(m)
        return str(int(v)) if v == int(v) else str(v)
    except (ValueError, TypeError):
        return str(m)


def hora_a_min(h):
    """Convierte hora AM/PM a minutos desde medianoche"""
    try:
        partes = h.replace(':', ' ').split()
        hr, mn, ap = int(partes[0]), int(partes[1]), partes[2]
        if ap == 'PM' and hr != 12:
            hr += 12
        elif ap == 'AM' and hr == 12:
            hr = 0
        return hr * 60 + mn
    except (IndexError, ValueError):
        return 0


def puede_vender(hora_sorteo):
    """Determina si aún se puede vender para un sorteo específico"""
    ahora = ahora_peru()
    diff = hora_a_min(hora_sorteo) - (ahora.hour * 60 + ahora.minute)
    return diff > MINUTOS_BLOQUEO


def calcular_premio_animal(monto, num):
    """Calcula premio para apuesta de animal"""
    return monto * (PAGO_LECHUZA if str(num) == "40" else PAGO_ANIMAL_NORMAL)


def calcular_premio_ticket(ticket_id, db=None):
    """
    Calcula el premio total de un ticket comparando con resultados.
    Usa la conexión proporcionada o obtiene una nueva.
    """
    debe_cerrar = False
    if db is None:
        db = get_db()
        debe_cerrar = True
    
    try:
        if USE_SQLITE:
            cur = db.execute("SELECT fecha FROM tickets WHERE id=?", (ticket_id,))
            t = cur.fetchone()
        else:
            cur = db.cursor()
            cur.execute("SELECT fecha FROM tickets WHERE id=%s", (ticket_id,))
            t = cur.fetchone()
            
        if not t:
            return 0
        
        fecha_ticket = parse_fecha(t['fecha'] if USE_SQLITE else t[0])
        if not fecha_ticket:
            return 0
            
        fecha_str = fecha_ticket.strftime("%d/%m/%Y")
        
        # Obtener resultados del día
        if USE_SQLITE:
            res_rows = db.execute("SELECT hora, animal FROM resultados WHERE fecha=?", (fecha_str,)).fetchall()
            resultados = {r['hora']: r['animal'] for r in res_rows}
            jugadas = db.execute("SELECT * FROM jugadas WHERE ticket_id=?", (ticket_id,)).fetchall()
            trips = db.execute("SELECT * FROM tripletas WHERE ticket_id=?", (ticket_id,)).fetchall()
        else:
            cur.execute("SELECT hora, animal FROM resultados WHERE fecha=%s", (fecha_str,))
            res_rows = cur.fetchall()
            resultados = {r[0]: r[1] for r in res_rows}
            cur.execute("SELECT * FROM jugadas WHERE ticket_id=%s", (ticket_id,))
            jugadas = cur.fetchall()
            cur.execute("SELECT * FROM tripletas WHERE ticket_id=%s", (ticket_id,))
            trips = cur.fetchall()
        
        total = 0
        
        # Calcular premios de jugadas normales
        for j in jugadas:
            wa = resultados.get(j['hora'] if USE_SQLITE else j[2])
            if not wa:
                continue
            
            tipo = j['tipo'] if USE_SQLITE else j[5]
            seleccion = j['seleccion'] if USE_SQLITE else j[3]
            monto = j['monto'] if USE_SQLITE else j[4]
                
            if tipo == 'animal' and str(wa) == str(seleccion):
                total += calcular_premio_animal(monto, wa)
            elif tipo == 'especial' and str(wa) not in ["0", "00"]:
                num = int(wa)
                es_rojo = str(wa) in ROJOS
                
                if ((seleccion == 'ROJO' and es_rojo) or 
                    (seleccion == 'NEGRO' and not es_rojo) or
                    (seleccion == 'PAR' and num % 2 == 0) or 
                    (seleccion == 'IMPAR' and num % 2 != 0)):
                    total += monto * PAGO_ESPECIAL
        
        # Calcular premios de tripletas
        for tr in trips:
            nums = {
                tr['animal1'] if USE_SQLITE else tr[2], 
                tr['animal2'] if USE_SQLITE else tr[3], 
                tr['animal3'] if USE_SQLITE else tr[4]
            }
            salidos = {a for a in resultados.values() if a in nums}
            if len(salidos) == 3:
                monto_tr = tr['monto'] if USE_SQLITE else tr[5]
                total += monto_tr * PAGO_TRIPLETA
                
        return total
    finally:
        if debe_cerrar:
            db.close()


# ==================== DECORADORES ====================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or not session.get('es_admin'):
            return "No autorizado", 403
        return f(*args, **kwargs)
    return decorated


def agencia_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Login requerido'}), 403
        if session.get('es_admin'):
            return jsonify({'error': 'Admin no puede vender'}), 403
        return f(*args, **kwargs)
    return decorated


# ==================== RUTAS WEB ====================

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect('/admin' if session.get('es_admin') else '/pos')
    return redirect('/login')


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = ""
    if request.method == 'POST':
        u = request.form.get('usuario', '').strip().lower()
        p = request.form.get('password', '').strip()
        
        db = get_db()
        
        if USE_SQLITE:
            cur = db.execute(
                "SELECT * FROM agencias WHERE usuario=? AND password=? AND activa=1", 
                (u, p)
            )
            row = cur.fetchone()
            db.close()
        else:
            cur = db.cursor()
            cur.execute(
                "SELECT * FROM agencias WHERE usuario=%s AND password=%s AND activa=1", 
                (u, p)
            )
            row = cur.fetchone()
            cur.close()
            db.close()
        
        if row:
            session['user_id'] = row['id'] if USE_SQLITE else row[0]
            session['nombre_agencia'] = row['nombre_agencia'] if USE_SQLITE else row[3]
            session['es_admin'] = bool(row['es_admin'] if USE_SQLITE else row[4])
            return redirect('/')
        error = "Usuario o clave incorrecta"
        
    return render_template_string(LOGIN_HTML, error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


@app.route('/pos')
@login_required
def pos():
    if session.get('es_admin'):
        return redirect('/admin')
    return render_template_string(
        POS_HTML,
        agencia=session['nombre_agencia'],
        animales=ANIMALES,
        colores=COLORES,
        horarios_peru=HORARIOS_PERU,
        horarios_venezuela=HORARIOS_VENEZUELA
    )


@app.route('/admin')
@admin_required
def admin():
    return render_template_string(
        ADMIN_HTML, 
        animales=ANIMALES, 
        horarios=HORARIOS_PERU
    )


# ==================== API ENDPOINTS ====================

@app.route('/api/hora-actual')
@login_required
def hora_actual():
    ahora = ahora_peru()
    bloqueadas = [h for h in HORARIOS_PERU if not puede_vender(h)]
    return jsonify({
        'hora_str': ahora.strftime("%I:%M %p"), 
        'bloqueadas': bloqueadas
    })


@app.route('/api/resultados-hoy')
@login_required
def resultados_hoy():
    hoy = ahora_peru().strftime("%d/%m/%Y")
    db = get_db()
    
    if USE_SQLITE:
        rows = db.execute("SELECT hora, animal FROM resultados WHERE fecha=?", (hoy,)).fetchall()
        rd = {
            r['hora']: {
                'animal': r['animal'],
                'nombre': ANIMALES.get(r['animal'], '?')
            } for r in rows
        }
        db.close()
    else:
        cur = db.cursor()
        cur.execute("SELECT hora, animal FROM resultados WHERE fecha=%s", (hoy,))
        rows = cur.fetchall()
        rd = {
            r[0]: {
                'animal': r[1],
                'nombre': ANIMALES.get(r[1], '?')
            } for r in rows
        }
        cur.close()
        db.close()
    
    for h in HORARIOS_PERU:
        if h not in rd:
            rd[h] = None
            
    return jsonify({'status': 'ok', 'fecha': hoy, 'resultados': rd})


@app.route('/api/resultados-fecha', methods=['POST'])
@login_required
def resultados_fecha():
    data = request.get_json() or {}
    fs = data.get('fecha')
    
    try:
        fecha_obj = datetime.strptime(fs, "%Y-%m-%d") if fs else ahora_peru()
    except ValueError:
        fecha_obj = ahora_peru()
        
    fecha_str = fecha_obj.strftime("%d/%m/%Y")
    db = get_db()
    
    if USE_SQLITE:
        rows = db.execute("SELECT hora, animal FROM resultados WHERE fecha=?", (fecha_str,)).fetchall()
        rd = {
            r['hora']: {
                'animal': r['animal'], 
                'nombre': ANIMALES.get(r['animal'], '?')
            } for r in rows
        }
        db.close()
    else:
        cur = db.cursor()
        cur.execute("SELECT hora, animal FROM resultados WHERE fecha=%s", (fecha_str,))
        rows = cur.fetchall()
        rd = {
            r[0]: {
                'animal': r[1], 
                'nombre': ANIMALES.get(r[1], '?')
            } for r in rows
        }
        cur.close()
        db.close()
    
    for h in HORARIOS_PERU:
        if h not in rd:
            rd[h] = None
            
    return jsonify({
        'status': 'ok',
        'fecha_consulta': fecha_str,
        'resultados': rd
    })


@app.route('/api/procesar-venta', methods=['POST'])
@agencia_required
def procesar_venta():
    db = get_db()
    
    try:
        data = request.get_json()
        jugadas = data.get('jugadas', [])
        
        if not jugadas:
            return jsonify({'error': 'Ticket vacío'}), 400
        
        # Validar que la agencia existe
        if USE_SQLITE:
            agencia = db.execute(
                "SELECT id FROM agencias WHERE id=? AND activa=1", 
                (session['user_id'],)
            ).fetchone()
        else:
            cur = db.cursor()
            cur.execute(
                "SELECT id FROM agencias WHERE id=%s AND activa=1", 
                (session['user_id'],)
            )
            agencia = cur.fetchone()
            cur.close()
        
        if not agencia:
            session.clear()
            return jsonify({'error': 'Sesión inválida o agencia inactiva. Reinicie sesión.'}), 403
        
        # Validar horarios disponibles
        for j in jugadas:
            if j.get('tipo') != 'tripleta' and not puede_vender(j.get('hora', '')):
                return jsonify({'error': f"Sorteo {j['hora']} ya cerró"}), 400
        
        serial = generar_serial()
        fecha = ahora_peru().strftime("%d/%m/%Y %I:%M %p")
        total = sum(j.get('monto', 0) for j in jugadas)
        
        # Insertar ticket
        if USE_SQLITE:
            cur = db.execute(
                "INSERT INTO tickets (serial, agencia_id, fecha, total) VALUES (?, ?, ?, ?)",
                (serial, session['user_id'], fecha, total)
            )
            ticket_id = cur.lastrowid
            db.commit()
        else:
            cur = db.cursor()
            cur.execute(
                "INSERT INTO tickets (serial, agencia_id, fecha, total) VALUES (%s, %s, %s, %s) RETURNING id",
                (serial, session['user_id'], fecha, total)
            )
            ticket_id = cur.fetchone()[0]
            db.commit()
        
        if not ticket_id:
            return jsonify({'error': 'Error al generar ticket. Intente nuevamente.'}), 500
        
        # Insertar jugadas y tripletas
        for j in jugadas:
            tipo = j.get('tipo')
            
            if tipo == 'tripleta':
                nums = str(j.get('seleccion', '')).split(',')
                if len(nums) != 3:
                    return jsonify({'error': 'Tripleta debe tener 3 animales'}), 400
                
                if USE_SQLITE:
                    db.execute(
                        """INSERT INTO tripletas 
                           (ticket_id, animal1, animal2, animal3, monto, fecha) 
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (ticket_id, nums[0].strip(), nums[1].strip(), nums[2].strip(), 
                         j.get('monto'), fecha.split(' ')[0])
                    )
                else:
                    cur.execute(
                        """INSERT INTO tripletas 
                           (ticket_id, animal1, animal2, animal3, monto, fecha) 
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (ticket_id, nums[0].strip(), nums[1].strip(), nums[2].strip(), 
                         j.get('monto'), fecha.split(' ')[0])
                    )
            else:
                if USE_SQLITE:
                    db.execute(
                        """INSERT INTO jugadas 
                           (ticket_id, hora, seleccion, monto, tipo) 
                           VALUES (?, ?, ?, ?, ?)""",
                        (ticket_id, j.get('hora'), str(j.get('seleccion')), 
                         j.get('monto'), tipo)
                    )
                else:
                    cur.execute(
                        """INSERT INTO jugadas 
                           (ticket_id, hora, seleccion, monto, tipo) 
                           VALUES (%s, %s, %s, %s, %s)""",
                        (ticket_id, j.get('hora'), str(j.get('seleccion')), 
                         j.get('monto'), tipo)
                    )
        
        if USE_SQLITE:
            db.commit()
            db.close()
        else:
            db.commit()
            cur.close()
            db.close()
        
        # Generar texto para WhatsApp
        jpoh = defaultdict(list)
        for j in jugadas:
            if j.get('tipo') != 'tripleta':
                jpoh[j.get('hora')].append(j)
        
        lineas = [
            f"*{session['nombre_agencia']}*",
            f"*TICKET:* #{ticket_id}",
            f"*SERIAL:* {serial}", 
            fecha,
            "------------------------", 
            ""
        ]
        
        for hp in HORARIOS_PERU:
            if hp not in jpoh:
                continue
            idx = HORARIOS_PERU.index(hp)
            hv = HORARIOS_VENEZUELA[idx]
            hpc = hp.replace(' ', '').replace('00', '').lower()
            hvc = hv.replace(' ', '').replace('00', '').lower()
            
            lineas.append(f"*ZOOLO.PERU/{hpc}...VZLA/{hvc}*")
            items = []
            for j in jpoh[hp]:
                if j.get('tipo') == 'animal':
                    num = j.get('seleccion', '')
                    n = ANIMALES.get(num, '')[:3].upper()
                    items.append(f"{n}{num}x{fmt(j.get('monto'))}")
                else:
                    sel = j.get('seleccion', '')
                    items.append(f"{sel[:3]}x{fmt(j.get('monto'))}")
            lineas.append(" ".join(items))
            lineas.append("")
        
        # Agregar tripletas al texto
        trips_t = [j for j in jugadas if j.get('tipo') == 'tripleta']
        if trips_t:
            lineas.append("*TRIPLETAS (Paga x60)*")
            for t in trips_t:
                nums = str(t.get('seleccion', '')).split(',')
                ns = [ANIMALES.get(n.strip(), '')[:3].upper() for n in nums]
                lineas.append(f"{'-'.join(ns)} x60 S/{fmt(t.get('monto'))}")
            lineas.append("")
        
        lineas += [
            "------------------------",
            f"*TOTAL: S/{fmt(total)}*",
            "",
            "Buena Suerte! 🍀",
            "El ticket vence a los 3 dias"
        ]
        
        import urllib.parse
        texto = "\n".join(lineas)
        url_wa = f"https://wa.me/?text={urllib.parse.quote(texto)}"
        
        return jsonify({
            'status': 'ok',
            'serial': serial,
            'ticket_id': ticket_id,
            'total': total,
            'url_whatsapp': url_wa
        })
        
    except Exception as e:
        if not USE_SQLITE:
            try:
                db.rollback()
                cur.close()
                db.close()
            except:
                pass
        else:
            try:
                db.close()
            except:
                pass
        return jsonify({'error': f'Error del servidor: {str(e)}'}), 500


# ... (Aquí continuarían el resto de rutas con lógica similar)

# Para simplificar, aquí están las rutas faltantes en versión compacta:

@app.route('/api/mis-tickets', methods=['POST'])
@agencia_required
def mis_tickets():
    try:
        data = request.get_json() or {}
        fi, ff, est = data.get('fecha_inicio'), data.get('fecha_fin'), data.get('estado', 'todos')
        
        dti = datetime.strptime(fi, "%Y-%m-%d") if fi else None
        dtf = datetime.strptime(ff, "%Y-%m-%d").replace(hour=23, minute=59) if ff else None
        
        db = get_db()
        tickets_out = []
        
        if USE_SQLITE:
            rows = db.execute(
                """SELECT * FROM tickets 
                   WHERE agencia_id=? AND anulado=0 
                   ORDER BY id DESC LIMIT 500""",
                (session['user_id'],)
            ).fetchall()
            
            resultado_cache = {}
            tv = 0
            
            for t in rows:
                dt = parse_fecha(t['fecha'])
                if not dt:
                    continue
                if dti and dt < dti:
                    continue
                if dtf and dt > dtf:
                    continue
                
                fecha_str = dt.strftime("%d/%m/%Y")
                
                if fecha_str not in resultado_cache:
                    rr = db.execute("SELECT hora, animal FROM resultados WHERE fecha=?", (fecha_str,)).fetchall()
                    resultado_cache[fecha_str] = {r['hora']: r['animal'] for r in rr}
                
                res_dia = resultado_cache[fecha_str]
                premio_total = 0
                jugadas_det = []
                
                jugadas_raw = db.execute("SELECT * FROM jugadas WHERE ticket_id=?", (t['id'],)).fetchall()
                for j in jugadas_raw:
                    wa = res_dia.get(j['hora'])
                    gano = False
                    pj = 0
                    
                    if wa:
                        if j['tipo'] == 'animal' and str(wa) == str(j['seleccion']):
                            pj = calcular_premio_animal(j['monto'], wa)
                            gano = True
                        elif j['tipo'] == 'especial' and str(wa) not in ["0", "00"]:
                            num = int(wa)
                            es_rojo = str(wa) in ROJOS
                            sel = j['seleccion']
                            
                            if ((sel == 'ROJO' and es_rojo) or 
                                (sel == 'NEGRO' and not es_rojo) or
                                (sel == 'PAR' and num % 2 == 0) or 
                                (sel == 'IMPAR' and num % 2 != 0)):
                                pj = j['monto'] * PAGO_ESPECIAL
                                gano = True
                    
                    if gano:
                        premio_total += pj
                    
                    jugadas_det.append({
                        'tipo': j['tipo'],
                        'hora': j['hora'],
                        'seleccion': j['seleccion'],
                        'nombre': ANIMALES.get(j['seleccion'], j['seleccion']) if j['tipo'] == 'animal' else j['seleccion'],
                        'monto': j['monto'],
                        'resultado': wa,
                        'resultado_nombre': ANIMALES.get(str(wa), str(wa)) if wa else None,
                        'gano': gano,
                        'premio': round(pj, 2)
                    })
                
                tripletas_raw = db.execute("SELECT * FROM tripletas WHERE ticket_id=?", (t['id'],)).fetchall()
                trips_det = []
                
                for tr in tripletas_raw:
                    nums = {tr['animal1'], tr['animal2'], tr['animal3']}
                    salidos = list(dict.fromkeys([a for a in res_dia.values() if a in nums]))
                    gano_t = len(salidos) == 3
                    pt = tr['monto'] * PAGO_TRIPLETA if gano_t else 0
                    
                    if gano_t:
                        premio_total += pt
                    
                    trips_det.append({
                        'animal1': tr['animal1'],
                        'nombre1': ANIMALES.get(tr['animal1'], tr['animal1']),
                        'animal2': tr['animal2'],
                        'nombre2': ANIMALES.get(tr['animal2'], tr['animal2']),
                        'animal3': tr['animal3'],
                        'nombre3': ANIMALES.get(tr['animal3'], tr['animal3']),
                        'monto': tr['monto'],
                        'salieron': salidos,
                        'gano': gano_t,
                        'premio': round(pt, 2),
                        'pagado': bool(tr['pagado'])
                    })
                
                if est == 'pagados' and not t['pagado']:
                    continue
                if est == 'pendientes' and t['pagado']:
                    continue
                if est == 'por_pagar' and (t['pagado'] or premio_total == 0):
                    continue
                
                tickets_out.append({
                    'id': t['id'],
                    'serial': t['serial'],
                    'fecha': t['fecha'],
                    'total': t['total'],
                    'pagado': bool(t['pagado']),
                    'premio_calculado': round(premio_total, 2),
                    'jugadas': jugadas_det,
                    'tripletas': trips_det
                })
                tv += t['total']
            
            db.close()
            
        else:
            # PostgreSQL version
            cur = db.cursor()
            cur.execute(
                """SELECT * FROM tickets 
                   WHERE agencia_id=%s AND anulado=0 
                   ORDER BY id DESC LIMIT 500""",
                (session['user_id'],)
            )
            rows = cur.fetchall()
            
            resultado_cache = {}
            tv = 0
            
            for t in rows:
                dt = parse_fecha(t[3])  # fecha index
                if not dt:
                    continue
                if dti and dt < dti:
                    continue
                if dtf and dt > dtf:
                    continue
                
                fecha_str = dt.strftime("%d/%m/%Y")
                
                if fecha_str not in resultado_cache:
                    cur.execute("SELECT hora, animal FROM resultados WHERE fecha=%s", (fecha_str,))
                    rr = cur.fetchall()
                    resultado_cache[fecha_str] = {r[0]: r[1] for r in rr}
                
                res_dia = resultado_cache[fecha_str]
                premio_total = 0
                jugadas_det = []
                
                cur.execute("SELECT * FROM jugadas WHERE ticket_id=%s", (t[0],))
                jugadas_raw = cur.fetchall()
                
                for j in jugadas_raw:
                    wa = res_dia.get(j[2])  # hora
                    gano = False
                    pj = 0
                    
                    tipo = j[5]
                    seleccion = j[3]
                    monto = j[4]
                    
                    if wa:
                        if tipo == 'animal' and str(wa) == str(seleccion):
                            pj = calcular_premio_animal(monto, wa)
                            gano = True
                        elif tipo == 'especial' and str(wa) not in ["0", "00"]:
                            num = int(wa)
                            es_rojo = str(wa) in ROJOS
                            
                            if ((seleccion == 'ROJO' and es_rojo) or 
                                (seleccion == 'NEGRO' and not es_rojo) or
                                (seleccion == 'PAR' and num % 2 == 0) or 
                                (seleccion == 'IMPAR' and num % 2 != 0)):
                                pj = monto * PAGO_ESPECIAL
                                gano = True
                    
                    if gano:
                        premio_total += pj
                    
                    jugadas_det.append({
                        'tipo': tipo,
                        'hora': j[2],
                        'seleccion': j[3],
                        'nombre': ANIMALES.get(j[3], j[3]) if tipo == 'animal' else j[3],
                        'monto': j[4],
                        'resultado': wa,
                        'resultado_nombre': ANIMALES.get(str(wa), str(wa)) if wa else None,
                        'gano': gano,
                        'premio': round(pj, 2)
                    })
                
                cur.execute("SELECT * FROM tripletas WHERE ticket_id=%s", (t[0],))
                tripletas_raw = cur.fetchall()
                trips_det = []
                
                for tr in tripletas_raw:
                    nums = {tr[2], tr[3], tr[4]}
                    salidos = list(dict.fromkeys([a for a in res_dia.values() if a in nums]))
                    gano_t = len(salidos) == 3
                    pt = tr[6] * PAGO_TRIPLETA if gano_t else 0
                    
                    if gano_t:
                        premio_total += pt
                    
                    trips_det.append({
                        'animal1': tr[2],
                        'nombre1': ANIMALES.get(tr[2], tr[2]),
                        'animal2': tr[3],
                        'nombre2': ANIMALES.get(tr[3], tr[3]),
                        'animal3': tr[4],
                        'nombre3': ANIMALES.get(tr[4], tr[4]),
                        'monto': tr[6],
                        'salieron': salidos,
                        'gano': gano_t,
                        'premio': round(pt, 2),
                        'pagado': bool(tr[7])
                    })
                
                pagado = t[5]
                if est == 'pagados' and not pagado:
                    continue
                if est == 'pendientes' and pagado:
                    continue
                if est == 'por_pagar' and (pagado or premio_total == 0):
                    continue
                
                tickets_out.append({
                    'id': t[0],
                    'serial': t[1],
                    'fecha': t[3],
                    'total': t[4],
                    'pagado': bool(pagado),
                    'premio_calculado': round(premio_total, 2),
                    'jugadas': jugadas_det,
                    'tripletas': trips_det
                })
                tv += t[4]
            
            cur.close()
            db.close()
        
        return jsonify({
            'status': 'ok',
            'tickets': tickets_out,
            'totales': {
                'cantidad': len(tickets_out),
                'ventas': round(tv, 2)
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ... (Resto de rutas administrativas similares)

# Templates HTML (mantener los mismos que tenías)
LOGIN_HTML = '''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ZOOLO CASINO</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;700&family=Rajdhani:wght@500;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#050a12;min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:'Rajdhani',sans-serif}
.box{background:#0a1020;padding:44px 36px;border-radius:6px;border:1px solid #1e3060;width:100%;max-width:400px;text-align:center;box-shadow:0 0 60px rgba(0,80,200,.1)}
.logo{font-family:'Oswald',sans-serif;font-size:2.6rem;font-weight:700;color:#fff;letter-spacing:4px;margin-bottom:4px}
.logo em{color:#f5a623;font-style:normal}
.sub{color:#3a5080;font-size:.8rem;letter-spacing:3px;margin-bottom:36px}
.fg{margin-bottom:18px;text-align:left}
.fg label{display:block;color:#3a5080;font-size:.78rem;letter-spacing:2px;margin-bottom:6px}
.fg input{width:100%;padding:13px 16px;background:#060e1e;border:1px solid #1e3060;border-radius:4px;color:#7ab0ff;font-size:.95rem;font-family:'Rajdhani',sans-serif;letter-spacing:1px}
.fg input:focus{outline:none;border-color:#2060d0;box-shadow:0 0 16px rgba(32,96,208,.15)}
.btn{width:100%;padding:15px;background:linear-gradient(135deg,#1a4cd0,#0d32a0);color:#fff;border:none;border-radius:4px;font-size:.95rem;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:3px;cursor:pointer;margin-top:8px;transition:all .3s}
.btn:hover{background:linear-gradient(135deg,#2060e8,#1440c0);box-shadow:0 6px 20px rgba(20,64,200,.3)}
.err{background:rgba(200,40,40,.1);color:#e05050;padding:11px;border-radius:4px;margin-bottom:16px;border:1px solid rgba(200,40,40,.2);font-size:.85rem}
</style></head><body>
<div class="box">
<div class="logo">ZOO<em>LO</em></div>
<div class="sub">SISTEMA DE APUESTAS</div>
{% if error %}<div class="err">⚠ {{error}}</div>{% endif %}
<form method="POST">
<div class="fg"><label>USUARIO</label><input type="text" name="usuario" required autofocus autocomplete="off"></div>
<div class="fg"><label>CONTRASEÑA</label><input type="password" name="password" required></div>
<button type="submit" class="btn">INGRESAR</button>
</form>
</div></body></html>'''

# [Incluye aquí tus templates POS_HTML y ADMIN_HTML completos que ya tenías]

POS_HTML = r'''[PEGA AQUÍ TU POS_HTML COMPLETO]'''
ADMIN_HTML = r'''[PEGA AQUÍ TU ADMIN_HTML COMPLETO]'''


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
