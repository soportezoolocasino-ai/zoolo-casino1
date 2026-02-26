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
    conn = get_db()
    
    if USE_SQLITE:
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
        
        admin = conn.execute("SELECT id FROM agencias WHERE es_admin=1").fetchone()
        if not admin:
            conn.execute("""
                INSERT INTO agencias (usuario, password, nombre_agencia, es_admin, comision, activa) 
                VALUES (?, ?, ?, 1, 0, 1)
            """, ('cuborubi', '15821462', 'ADMINISTRADOR'))
        conn.commit()
        conn.close()
        
    else:
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
    return datetime.now(timezone.utc) - timedelta(hours=5)

def parse_fecha(f):
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
    return str(int(ahora_peru().timestamp() * 1000))

def fmt(m):
    try:
        v = float(m)
        return str(int(v)) if v == int(v) else str(v)
    except (ValueError, TypeError):
        return str(m)

def hora_a_min(h):
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
    ahora = ahora_peru()
    diff = hora_a_min(hora_sorteo) - (ahora.hour * 60 + ahora.minute)
    return diff > MINUTOS_BLOQUEO

def calcular_premio_animal(monto, num):
    return monto * (PAGO_LECHUZA if str(num) == "40" else PAGO_ANIMAL_NORMAL)

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
        
        for j in jugadas:
            if j.get('tipo') != 'tripleta' and not puede_vender(j.get('hora', '')):
                return jsonify({'error': f"Sorteo {j['hora']} ya cerró"}), 400
        
        serial = generar_serial()
        fecha = ahora_peru().strftime("%d/%m/%Y %I:%M %p")
        total = sum(j.get('monto', 0) for j in jugadas)
        
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
                dt = parse_fecha(t[3])
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
                    wa = res_dia.get(j[2])
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

@app.route('/api/guardar-resultado', methods=['POST'])
@admin_required
def guardar_resultado():
    try:
        data = request.get_json()
        fecha = data.get('fecha')
        hora = data.get('hora')
        animal = data.get('animal')
        
        if not all([fecha, hora, animal]):
            return jsonify({'error': 'Faltan datos'}), 400
        
        db = get_db()
        
        if USE_SQLITE:
            db.execute(
                "INSERT OR REPLACE INTO resultados (fecha, hora, animal) VALUES (?, ?, ?)",
                (fecha, hora, animal)
            )
            db.commit()
            db.close()
        else:
            cur = db.cursor()
            cur.execute(
                """INSERT INTO resultados (fecha, hora, animal) VALUES (%s, %s, %s)
                   ON CONFLICT (fecha, hora) DO UPDATE SET animal = EXCLUDED.animal""",
                (fecha, hora, animal)
            )
            db.commit()
            cur.close()
            db.close()
        
        return jsonify({'status': 'ok', 'message': 'Resultado guardado'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/agencias', methods=['GET', 'POST'])
@admin_required
def manage_agencias():
    db = get_db()
    
    if request.method == 'GET':
        if USE_SQLITE:
            rows = db.execute("SELECT id, usuario, nombre_agencia, comision, activa FROM agencias WHERE es_admin=0").fetchall()
            agencias = [{'id': r['id'], 'usuario': r['usuario'], 'nombre': r['nombre_agencia'], 'comision': r['comision'], 'activa': bool(r['activa'])} for r in rows]
            db.close()
        else:
            cur = db.cursor()
            cur.execute("SELECT id, usuario, nombre_agencia, comision, activa FROM agencias WHERE es_admin=0")
            rows = cur.fetchall()
            agencias = [{'id': r[0], 'usuario': r[1], 'nombre': r[2], 'comision': r[3], 'activa': bool(r[4])} for r in rows]
            cur.close()
            db.close()
        return jsonify({'status': 'ok', 'agencias': agencias})
    
    else:
        try:
            data = request.get_json()
            usuario = data.get('usuario')
            password = data.get('password')
            nombre = data.get('nombre_agencia')
            comision = data.get('comision', 0.15)
            
            if USE_SQLITE:
                db.execute(
                    "INSERT INTO agencias (usuario, password, nombre_agencia, comision) VALUES (?, ?, ?, ?)",
                    (usuario, password, nombre, comision)
                )
                db.commit()
                db.close()
            else:
                cur = db.cursor()
                cur.execute(
                    "INSERT INTO agencias (usuario, password, nombre_agencia, comision) VALUES (%s, %s, %s, %s)",
                    (usuario, password, nombre, comision)
                )
                db.commit()
                cur.close()
                db.close()
            
            return jsonify({'status': 'ok', 'message': 'Agencia creada'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/api/reporte-ventas', methods=['POST'])
@admin_required
def reporte_ventas():
    try:
        data = request.get_json() or {}
        fi, ff = data.get('fecha_inicio'), data.get('fecha_fin')
        
        dti = datetime.strptime(fi, "%Y-%m-%d") if fi else ahora_peru().replace(hour=0, minute=0)
        dtf = datetime.strptime(ff, "%Y-%m-%d").replace(hour=23, minute=59) if ff else ahora_peru()
        
        db = get_db()
        
        if USE_SQLITE:
            query = """
                SELECT t.*, a.nombre_agencia 
                FROM tickets t 
                JOIN agencias a ON t.agencia_id = a.id 
                WHERE t.anulado = 0 
                ORDER BY t.id DESC
            """
            rows = db.execute(query).fetchall()
        else:
            cur = db.cursor()
            cur.execute("""
                SELECT t.*, a.nombre_agencia 
                FROM tickets t 
                JOIN agencias a ON t.agencia_id = a.id 
                WHERE t.anulado = 0 
                ORDER BY t.id DESC
            """)
            rows = cur.fetchall()
        
        resultados = []
        total_ventas = 0
        total_premios = 0
        
        for row in rows:
            if USE_SQLITE:
                dt = parse_fecha(row['fecha'])
                if dt and dti <= dt <= dtf:
                    premio = 0
                    resultados.append({
                        'ticket_id': row['id'],
                        'agencia': row['nombre_agencia'],
                        'fecha': row['fecha'],
                        'total': row['total'],
                        'premio': premio
                    })
                    total_ventas += row['total']
            else:
                dt = parse_fecha(row[3])
                if dt and dti <= dt <= dtf:
                    resultados.append({
                        'ticket_id': row[0],
                        'agencia': row[8],
                        'fecha': row[3],
                        'total': row[4],
                        'premio': 0
                    })
                    total_ventas += row[4]
        
        if USE_SQLITE:
            db.close()
        else:
            cur.close()
            db.close()
        
        return jsonify({
            'status': 'ok',
            'ventas': resultados,
            'resumen': {
                'total_ventas': round(total_ventas, 2),
                'total_premios': round(total_premios, 2),
                'balance': round(total_ventas - total_premios, 2)
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== TEMPLATES HTML ====================

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

POS_HTML = '''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>POS - ZOOLO CASINO</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;700&family=Rajdhani:wght@500;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#050a12;color:#fff;font-family:'Rajdhani',sans-serif;overflow-x:hidden}
.header{background:#0a1020;border-bottom:1px solid #1e3060;padding:12px 20px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}
.logo{font-family:'Oswald',sans-serif;font-size:1.8rem;font-weight:700;letter-spacing:2px}
.logo em{color:#f5a623;font-style:normal}
.agencia{color:#7ab0ff;font-size:.9rem}
.logout{color:#e05050;text-decoration:none;font-size:.85rem;cursor:pointer}
.main{display:flex;min-height:calc(100vh - 60px)}
.sidebar{width:320px;background:#0d1424;border-right:1px solid #1e3060;padding:20px;overflow-y:auto}
.content{flex:1;padding:20px;overflow-y:auto}
.section{margin-bottom:24px}
.section-title{color:#3a5080;font-size:.75rem;letter-spacing:2px;margin-bottom:12px;text-transform:uppercase}
.horas-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
.hora-btn{padding:10px;background:#060e1e;border:1px solid #1e3060;border-radius:4px;color:#7ab0ff;cursor:pointer;text-align:center;font-size:.85rem;transition:all .2s}
.hora-btn:hover{background:#1a2744}
.hora-btn.active{background:#2060d0;color:#fff;border-color:#2060d0}
.hora-btn.bloqueada{opacity:.4;cursor:not-allowed;background:#1a0f0f;border-color:#402020;color:#604040}
.animales-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(90px,1fr));gap:8px}
.animal-btn{padding:12px 8px;background:#060e1e;border:1px solid #1e3060;border-radius:4px;color:#fff;cursor:pointer;text-align:center;transition:all .2s;font-size:.8rem}
.animal-btn:hover{background:#1a2744;transform:translateY(-2px)}
.animal-btn.rojo{border-color:#802020;background:rgba(128,32,32,.2)}
.animal-btn.negro{border-color:#404040;background:rgba(64,64,64,.2)}
.animal-btn.verde{border-color:#208020;background:rgba(32,128,32,.2)}
.animal-btn.selected{border-color:#f5a623;box-shadow:0 0 0 2px rgba(245,166,35,.3)}
.animal-num{font-size:1.2rem;font-weight:700;display:block;margin-bottom:2px}
.especiales-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
.esp-btn{padding:15px;background:#060e1e;border:1px solid #1e3060;border-radius:4px;color:#fff;cursor:pointer;text-align:center;font-weight:600;transition:all .2s}
.esp-btn:hover{background:#1a2744}
.esp-btn.rojo{background:rgba(180,40,40,.2);border-color:#802020}
.esp-btn.negro{background:rgba(40,40,40,.5);border-color:#404040}
.ticket{background:#0a1020;border:1px solid #1e3060;border-radius:6px;padding:16px;margin-top:20px}
.ticket-title{font-size:1.1rem;margin-bottom:12px;color:#f5a623}
.ticket-item{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #1e3060;font-size:.9rem}
.ticket-item:last-child{border-bottom:none}
.ticket-total{display:flex;justify-content:space-between;padding:12px 0;margin-top:8px;border-top:2px solid #f5a623;font-size:1.2rem;font-weight:700}
.input-monto{width:100%;padding:12px;background:#060e1e;border:1px solid #1e3060;border-radius:4px;color:#fff;font-size:1.1rem;text-align:center;margin-bottom:12px;font-family:'Rajdhani',sans-serif}
.input-monto:focus{outline:none;border-color:#2060d0}
.btn-primario{width:100%;padding:14px;background:linear-gradient(135deg,#1a4cd0,#0d32a0);color:#fff;border:none;border-radius:4px;font-size:1rem;font-weight:700;cursor:pointer;margin-top:8px;transition:all .3s}
.btn-primario:hover{background:linear-gradient(135deg,#2060e8,#1440c0)}
.btn-secundario{width:100%;padding:12px;background:transparent;color:#7ab0ff;border:1px solid #1e3060;border-radius:4px;font-size:.9rem;cursor:pointer;margin-top:8px}
.btn-whatsapp{background:#25d366!important;margin-top:8px}
.tabs{display:flex;gap:8px;margin-bottom:16px;border-bottom:1px solid #1e3060;padding-bottom:12px}
.tab-btn{padding:8px 16px;background:transparent;border:none;color:#3a5080;cursor:pointer;font-family:'Rajdhani',sans-serif;font-size:.9rem;transition:all .2s}
.tab-btn.active{color:#f5a623;border-bottom:2px solid #f5a623}
.tab-content{display:none}
.tab-content.active{display:block}
.tripleta-input{display:flex;gap:8px;margin-bottom:12px}
.tripleta-input select{flex:1;padding:10px;background:#060e1e;border:1px solid #1e3060;border-radius:4px;color:#fff}
.eliminar-btn{color:#e05050;cursor:pointer;font-size:1.2rem;padding:0 8px}
.modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.8);z-index:1000;justify-content:center;align-items:center}
.modal-content{background:#0a1020;border:1px solid #1e3060;border-radius:8px;padding:24px;max-width:500px;width:90%;max-height:80vh;overflow-y:auto}
.modal-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.modal-close{color:#e05050;cursor:pointer;font-size:1.5rem}
.success-message{background:rgba(32,128,32,.2);border:1px solid #208020;color:#60ff60;padding:12px;border-radius:4px;margin-bottom:12px;text-align:center}
@media(max-width:768px){.main{flex-direction:column}.sidebar{width:100%;border-right:none;border-bottom:1px solid #1e3060}}
</style>
</head>
<body>
<div class="header">
<div>
<div class="logo">ZOO<em>LO</em></div>
<div class="agencia">{{agencia}}</div>
</div>
<a href="/logout" class="logout">Cerrar Sesión</a>
</div>

<div class="main">
<div class="sidebar">
<div class="section">
<div class="section-title">Sorteo</div>
<div class="horas-grid" id="horasContainer">
{% for hora in horarios_peru %}
<button class="hora-btn" data-hora="{{hora}}">{{hora}}</button>
{% endfor %}
</div>
</div>

<div class="section">
<div class="tabs">
<button class="tab-btn active" onclick="switchTab('animales')">Animales</button>
<button class="tab-btn" onclick="switchTab('especiales')">Especiales</button>
<button class="tab-btn" onclick="switchTab('tripletas')">Tripletas</button>
</div>

<div id="tab-animales" class="tab-content active">
<div class="section-title">Selecciona Animal</div>
<div class="animales-grid" id="animalesContainer">
{% for num, nombre in animales.items() %}
{% if num != '0' and num != '00' %}
<button class="animal-btn {% if num in ['1','3','5','7','9','12','14','16','18','19','21','23','25','27','30','32','34','36','37','39'] %}rojo{% elif num == '40' %}verde{% else %}negro{% endif %}" 
        data-num="{{num}}" data-nombre="{{nombre}}" onclick="selectAnimal('{{num}}', '{{nombre}}')">
<span class="animal-num">{{num}}</span>
<small>{{nombre[:6]}}</small>
</button>
{% endif %}
{% endfor %}
</div>
</div>

<div id="tab-especiales" class="tab-content">
<div class="section-title">Apuestas Especiales</div>
<div class="especiales-grid">
<button class="esp-btn rojo" onclick="selectEspecial('ROJO')">ROJO<br><small>Paga x2</small></button>
<button class="esp-btn negro" onclick="selectEspecial('NEGRO')">NEGRO<br><small>Paga x2</small></button>
<button class="esp-btn" onclick="selectEspecial('PAR')">PAR<br><small>Paga x2</small></button>
<button class="esp-btn" onclick="selectEspecial('IMPAR')">IMPAR<br><small>Paga x2</small></button>
</div>
</div>

<div id="tab-tripletas" class="tab-content">
<div class="section-title">Crear Tripleta</div>
<div class="tripleta-input">
<select id="trip1"><option value="">Animal 1</option>{% for num, nombre in animales.items() %}<option value="{{num}}">{{num}} - {{nombre}}</option>{% endfor %}</select>
</div>
<div class="tripleta-input">
<select id="trip2"><option value="">Animal 2</option>{% for num, nombre in animales.items() %}<option value="{{num}}">{{num}} - {{nombre}}</option>{% endfor %}</select>
</div>
<div class="tripleta-input">
<select id="trip3"><option value="">Animal 3</option>{% for num, nombre in animales.items() %}<option value="{{num}}">{{num}} - {{nombre}}</option>{% endfor %}</select>
</div>
<button class="btn-primario" onclick="agregarTripleta()">Agregar Tripleta (Paga x60)</button>
</div>
</div>
</div>

<div class="content">
<div class="section-title">Monto a Apostar</div>
<input type="number" class="input-monto" id="montoInput" placeholder="0.00" min="1" step="0.1">

<div class="ticket">
<div class="ticket-title">🎫 TICKET ACTUAL</div>
<div id="ticketItems">
<div style="color:#3a5080;text-align:center;padding:20px;">No hay jugadas agregadas</div>
</div>
<div class="ticket-total">
<span>TOTAL:</span>
<span id="ticketTotal">S/ 0.00</span>
</div>
<button class="btn-primario" onclick="procesarVenta()">PROCESAR VENTA</button>
<button class="btn-secundario" onclick="limpiarTicket()">Limpiar Todo</button>
</div>

<button class="btn-secundario" onclick="verMisTickets()" style="margin-top:20px;">📋 Ver Mis Tickets</button>
</div>
</div>

<div id="successModal" class="modal">
<div class="modal-content">
<div class="modal-header">
<h3>✅ Venta Exitosa</h3>
<span class="modal-close" onclick="closeModal()">&times;</span>
</div>
<div id="successContent"></div>
</div>
</div>

<div id="ticketsModal" class="modal">
<div class="modal-content" style="max-width:800px;">
<div class="modal-header">
<h3>📋 Mis Tickets</h3>
<span class="modal-close" onclick="closeTicketsModal()">&times;</span>
</div>
<div id="ticketsContent"></div>
</div>
</div>

<script>
let ticket = [];
let horaSeleccionada = null;
let seleccionActual = null;
let tipoActual = null;

function switchTab(tab) {
document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
document.getElementById('tab-' + tab).classList.add('active');
event.target.classList.add('active');
}

document.querySelectorAll('.hora-btn').forEach(btn => {
btn.addEventListener('click', function() {
if(this.classList.contains('bloqueada')) return;
document.querySelectorAll('.hora-btn').forEach(b => b.classList.remove('active'));
this.classList.add('active');
horaSeleccionada = this.dataset.hora;
});
});

function selectAnimal(num, nombre) {
if(!horaSeleccionada) {
alert('Selecciona una hora de sorteo primero');
return;
}
seleccionActual = num;
tipoActual = 'animal';
document.querySelectorAll('.animal-btn').forEach(b => b.classList.remove('selected'));
event.currentTarget.classList.add('selected');
}

function selectEspecial(tipo) {
if(!horaSeleccionada) {
alert('Selecciona una hora de sorteo primero');
return;
}
seleccionActual = tipo;
tipoActual = 'especial';
}

function agregarTripleta() {
const t1 = document.getElementById('trip1').value;
const t2 = document.getElementById('trip2').value;
const t3 = document.getElementById('trip3').value;
const monto = parseFloat(document.getElementById('montoInput').value);

if(!t1 || !t2 || !t3) {
alert('Selecciona los 3 animales');
return;
}
if(!monto || monto <= 0) {
alert('Ingresa un monto válido');
return;
}
if(t1 === t2 || t2 === t3 || t1 === t3) {
alert('Los 3 animales deben ser diferentes');
return;
}

ticket.push({
tipo: 'tripleta',
seleccion: t1 + ',' + t2 + ',' + t3,
monto: monto,
hora: '-'
});

actualizarTicket();
document.getElementById('trip1').value = '';
document.getElementById('trip2').value = '';
document.getElementById('trip3').value = '';
}

document.getElementById('montoInput').addEventListener('keypress', function(e) {
if(e.key === 'Enter') {
if(tipoActual === 'animal' && seleccionActual) {
agregarJugada('animal', seleccionActual);
} else if(tipoActual === 'especial' && seleccionActual) {
agregarJugada('especial', seleccionActual);
}
}
});

function agregarJugada(tipo, seleccion) {
const monto = parseFloat(document.getElementById('montoInput').value);
if(!monto || monto <= 0) {
alert('Ingresa un monto válido');
return;
}

ticket.push({
tipo: tipo,
seleccion: seleccion,
monto: monto,
hora: horaSeleccionada
});

actualizarTicket();
document.getElementById('montoInput').value = '';
document.getElementById('montoInput').focus();
}

function actualizarTicket() {
const container = document.getElementById('ticketItems');
if(ticket.length === 0) {
container.innerHTML = '<div style="color:#3a5080;text-align:center;padding:20px;">No hay jugadas agregadas</div>';
document.getElementById('ticketTotal').textContent = 'S/ 0.00';
return;
}

let html = '';
let total = 0;
ticket.forEach((item, idx) => {
total += item.monto;
let desc = '';
if(item.tipo === 'animal') {
const nombre = document.querySelector(`[data-num="${item.seleccion}"]`)?.dataset.nombre || '';
desc = `Animal ${item.seleccion} - ${nombre} (${item.hora})`;
} else if(item.tipo === 'especial') {
desc = `${item.seleccion} (${item.hora})`;
} else if(item.tipo === 'tripleta') {
desc = `Tripleta: ${item.seleccion}`;
}
html += `
<div class="ticket-item">
<span>${desc}</span>
<span style="display:flex;align-items:center;">
S/ ${item.monto.toFixed(2)}
<span class="eliminar-btn" onclick="eliminarJugada(${idx})">&times;</span>
</span>
</div>
`;
});
container.innerHTML = html;
document.getElementById('ticketTotal').textContent = 'S/ ' + total.toFixed(2);
}

function eliminarJugada(idx) {
ticket.splice(idx, 1);
actualizarTicket();
}

function limpiarTicket() {
if(confirm('¿Limpiar todo el ticket?')) {
ticket = [];
actualizarTicket();
}
}

function procesarVenta() {
if(ticket.length === 0) {
alert('Agrega jugadas al ticket primero');
return;
}

fetch('/api/procesar-venta', {
method: 'POST',
headers: {'Content-Type': 'application/json'},
body: JSON.stringify({jugadas: ticket})
})
.then(r => r.json())
.then(data => {
if(data.error) {
alert('Error: ' + data.error);
} else {
document.getElementById('successContent').innerHTML = `
<div class="success-message">
<h3>Ticket #${data.ticket_id}</h3>
<p>Serial: ${data.serial}</p>
<p>Total: S/ ${data.total.toFixed(2)}</p>
</div>
<a href="${data.url_whatsapp}" target="_blank" class="btn-primario btn-whatsapp">📱 Compartir por WhatsApp</a>
<button class="btn-secundario" onclick="closeModal();ticket=[];actualizarTicket();" style="margin-top:8px;">Nueva Venta</button>
`;
document.getElementById('successModal').style.display = 'flex';
}
})
.catch(e => alert('Error de conexión: ' + e));
}

function closeModal() {
document.getElementById('successModal').style.display = 'none';
}

function verMisTickets() {
fetch('/api/mis-tickets', {
method: 'POST',
headers: {'Content-Type': 'application/json'},
body: JSON.stringify({})
})
.then(r => r.json())
.then(data => {
if(data.error) {
alert('Error: ' + data.error);
return;
}
let html = '<div style="max-height:60vh;overflow-y:auto;">';
if(data.tickets.length === 0) {
html += '<p style="text-align:center;color:#3a5080;">No hay tickets recientes</p>';
} else {
html += `<p style="margin-bottom:12px;color:#7ab0ff;">Total ventas: S/ ${data.totales.ventas.toFixed(2)} (${data.totales.cantidad} tickets)</p>`;
data.tickets.forEach(t => {
html += `
<div style="border:1px solid #1e3060;border-radius:4px;padding:12px;margin-bottom:8px;background:#060e1e;">
<div style="display:flex;justify-content:space-between;margin-bottom:8px;">
<strong>Ticket #${t.id}</strong>
<span style="color:${t.pagado ? '#60ff60' : '#f5a623'}">${t.pagado ? 'Pagado' : 'Pendiente'}</span>
</div>
<div style="font-size:.85rem;color:#7ab0ff;margin-bottom:4px;">${t.fecha}</div>
<div style="display:flex;justify-content:space-between;font-size:.9rem;">
<span>Apostado: S/ ${t.total.toFixed(2)}</span>
<span style="color:#f5a623;">Premio: S/ ${t.premio_calculado.toFixed(2)}</span>
</div>
</div>
`;
});
}
html += '</div>';
document.getElementById('ticketsContent').innerHTML = html;
document.getElementById('ticketsModal').style.display = 'flex';
});
}

function closeTicketsModal() {
document.getElementById('ticketsModal').style.display = 'none';
}

function actualizarHorasBloqueadas() {
fetch('/api/hora-actual')
.then(r => r.json())
.then(data => {
data.bloqueadas.forEach(hora => {
const btn = document.querySelector(`[data-hora="${hora}"]`);
if(btn) {
btn.classList.add('bloqueada');
btn.title = 'Sorteo cerrado';
}
});
});
}

actualizarHorasBloqueadas();
setInterval(actualizarHorasBloqueadas, 60000);
</script>
</body>
</html>'''

ADMIN_HTML = '''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin - ZOOLO CASINO</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;700&family=Rajdhani:wght@500;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#050a12;color:#fff;font-family:'Rajdhani',sans-serif}
.header{background:#0a1020;border-bottom:1px solid #1e3060;padding:12px 20px;display:flex;justify-content:space-between;align-items:center}
.logo{font-family:'Oswald',sans-serif;font-size:1.8rem;font-weight:700;letter-spacing:2px}
.logo em{color:#f5a623;font-style:normal}
.nav{display:flex;gap:20px}
.nav a{color:#7ab0ff;text-decoration:none;font-size:.9rem;cursor:pointer;padding:8px 16px;border-radius:4px;transition:all .2s}
.nav a:hover{background:#1a2744}
.nav a.active{background:#2060d0;color:#fff}
.container{padding:20px;max-width:1200px;margin:0 auto}
.section{display:none;background:#0a1020;border:1px solid #1e3060;border-radius:8px;padding:24px;margin-bottom:20px}
.section.active{display:block}
.section-title{font-size:1.3rem;margin-bottom:20px;color:#f5a623;border-bottom:1px solid #1e3060;padding-bottom:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:12px}
.card{background:#060e1e;border:1px solid #1e3060;border-radius:6px;padding:16px;text-align:center;cursor:pointer;transition:all .2s}
.card:hover{background:#1a2744;transform:translateY(-2px)}
.card.selected{border-color:#f5a623;box-shadow:0 0 0 3px rgba(245,166,35,.2)}
.card-num{font-size:1.5rem;font-weight:700;margin-bottom:4px}
.card-name{font-size:.85rem;color:#7ab0ff}
.form-group{margin-bottom:16px}
.form-group label{display:block;margin-bottom:6px;color:#3a5080;font-size:.85rem;text-transform:uppercase;letter-spacing:1px}
.form-group input,.form-group select{width:100%;padding:10px;background:#060e1e;border:1px solid #1e3060;border-radius:4px;color:#fff;font-family:'Rajdhani',sans-serif}
.btn{padding:12px 24px;background:linear-gradient(135deg,#1a4cd0,#0d32a0);color:#fff;border:none;border-radius:4px;font-size:.9rem;font-weight:600;cursor:pointer;transition:all .2s}
.btn:hover{background:linear-gradient(135deg,#2060e8,#1440c0)}
.btn-success{background:linear-gradient(135deg,#20a040,#106020)}
.btn-danger{background:linear-gradient(135deg,#d02020,#801010)}
table{width:100%;border-collapse:collapse;margin-top:12px}
th,td{padding:12px;text-align:left;border-bottom:1px solid #1e3060}
th{color:#3a5080;font-size:.8rem;text-transform:uppercase;letter-spacing:1px}
td{font-size:.9rem}
tr:hover{background:#060e1e}
.status{ padding:4px 8px;border-radius:4px;font-size:.8rem;font-weight:600}
.status-activa{background:rgba(32,128,32,.2);color:#60ff60}
.status-inactiva{background:rgba(128,32,32,.2);color:#e05050}
.tabs{display:flex;gap:8px;margin-bottom:16px}
.tab-btn{padding:8px 16px;background:#060e1e;border:1px solid #1e3060;color:#7ab0ff;cursor:pointer;border-radius:4px}
.tab-btn.active{background:#2060d0;color:#fff}
.resultado-box{font-size:2rem;font-weight:700;text-align:center;padding:20px;background:#060e1e;border-radius:8px;margin:12px 0}
</style>
</head>
<body>
<div class="header">
<div class="logo">ZOO<em>LO</em> ADMIN</div>
<div class="nav">
<a onclick="showSection('resultados')" class="active" id="nav-resultados">Resultados</a>
<a onclick="showSection('agencias')" id="nav-agencias">Agencias</a>
<a onclick="showSection('reportes')" id="nav-reportes">Reportes</a>
<a href="/logout">Salir</a>
</div>
</div>

<div class="container">

<div id="resultados" class="section active">
<div class="section-title">📊 Cargar Resultados</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;">
<div>
<div class="form-group">
<label>Fecha</label>
<input type="date" id="fechaResultado">
</div>
<div class="form-group">
<label>Hora del Sorteo</label>
<select id="horaResultado">
{% for hora in horarios %}
<option value="{{hora}}">{{hora}}</option>
{% endfor %}
</select>
</div>
<div class="form-group">
<label>Animal Ganador</label>
<div class="resultado-box" id="animalSeleccionado">-</div>
<input type="hidden" id="animalResultado">
</div>
<button class="btn btn-success" onclick="guardarResultado()" style="width:100%">💾 Guardar Resultado</button>
</div>
<div>
<div class="form-group">
<label>Selecciona el Animal Ganador</label>
<div class="grid" style="max-height:60vh;overflow-y:auto;" id="gridAnimales">
{% for num, nombre in animales.items() %}
<div class="card" onclick="selectAnimalResultado('{{num}}', '{{nombre}}')">
<div class="card-num">{{num}}</div>
<div class="card-name">{{nombre}}</div>
</div>
{% endfor %}
</div>
</div>
</div>
</div>
</div>

<div id="agencias" class="section">
<div class="section-title">🏢 Gestión de Agencias</div>
<div style="display:grid;grid-template-columns:1fr 2fr;gap:20px;">
<div style="background:#060e1e;padding:20px;border-radius:8px;">
<h3 style="margin-bottom:16px;color:#f5a623">Nueva Agencia</h3>
<div class="form-group">
<label>Usuario</label>
<input type="text" id="newUsuario" placeholder="usuario123">
</div>
<div class="form-group">
<label>Contraseña</label>
<input type="password" id="newPassword" placeholder="****">
</div>
<div class="form-group">
<label>Nombre Agencia</label>
<input type="text" id="newNombre" placeholder="Mi Agencia">
</div>
<div class="form-group">
<label>Comisión (%)</label>
<input type="number" id="newComision" value="15" min="0" max="100" step="0.1">
</div>
<button class="btn" onclick="crearAgencia()" style="width:100%">➕ Crear Agencia</button>
</div>
<div>
<h3 style="margin-bottom:16px;color:#f5a623">Lista de Agencias</h3>
<div id="listaAgencias"></div>
</div>
</div>
</div>

<div id="reportes" class="section">
<div class="section-title">📈 Reporte de Ventas</div>
<div style="display:flex;gap:12px;margin-bottom:20px;">
<div class="form-group" style="flex:1">
<label>Desde</label>
<input type="date" id="reporteDesde">
</div>
<div class="form-group" style="flex:1">
<label>Hasta</label>
<input type="date" id="reporteHasta">
</div>
<div class="form-group">
<label style="visibility:hidden">Consultar</label>
<button class="btn" onclick="generarReporte()">📊 Generar</button>
</div>
</div>
<div id="resultadoReporte"></div>
</div>

</div>

<script>
let animalSeleccionado = null;

function showSection(section) {
document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
document.querySelectorAll('.nav a').forEach(a => a.classList.remove('active'));
document.getElementById(section).classList.add('active');
document.getElementById('nav-' + section).classList.add('active');
if(section === 'agencias') cargarAgencias();
}

function selectAnimalResultado(num, nombre) {
animalSeleccionado = num;
document.getElementById('animalResultado').value = num;
document.getElementById('animalSeleccionado').textContent = num + ' - ' + nombre;
document.querySelectorAll('.card').forEach(c => c.classList.remove('selected'));
event.currentTarget.classList.add('selected');
}

function guardarResultado() {
const fecha = document.getElementById('fechaResultado').value;
const hora = document.getElementById('horaResultado').value;
const animal = document.getElementById('animalResultado').value;

if(!fecha || !animal) {
alert('Completa todos los campos');
return;
}

fetch('/api/guardar-resultado', {
method: 'POST',
headers: {'Content-Type': 'application/json'},
body: JSON.stringify({fecha: fecha.split('-').reverse().join('/'), hora, animal})
})
.then(r => r.json())
.then(data => {
if(data.error) alert('Error: ' + data.error);
else {
alert('Resultado guardado correctamente');
document.getElementById('animalSeleccionado').textContent = '-';
document.querySelectorAll('.card').forEach(c => c.classList.remove('selected'));
animalSeleccionado = null;
}
});
}

function crearAgencia() {
const usuario = document.getElementById('newUsuario').value;
const password = document.getElementById('newPassword').value;
const nombre = document.getElementById('newNombre').value;
const comision = document.getElementById('newComision').value;

if(!usuario || !password || !nombre) {
alert('Completa todos los campos');
return;
}

fetch('/api/agencias', {
method: 'POST',
headers: {'Content-Type': 'application/json'},
body: JSON.stringify({usuario, password, nombre_agencia: nombre, comision: comision/100})
})
.then(r => r.json())
.then(data => {
if(data.error) alert('Error: ' + data.error);
else {
alert('Agencia creada correctamente');
cargarAgencias();
document.getElementById('newUsuario').value = '';
document.getElementById('newPassword').value = '';
document.getElementById('newNombre').value = '';
}
});
}

function cargarAgencias() {
fetch('/api/agencias')
.then(r => r.json())
.then(data => {
if(data.error) return;
let html = '<table><thead><tr><th>ID</th><th>Usuario</th><th>Nombre</th><th>Comisión</th><th>Estado</th></tr></thead><tbody>';
data.agencias.forEach(a => {
html += `<tr>
<td>${a.id}</td>
<td>${a.usuario}</td>
<td>${a.nombre}</td>
<td>${(a.comision*100).toFixed(0)}%</td>
<td><span class="status ${a.activa ? 'status-activa' : 'status-inactiva'}">${a.activa ? 'Activa' : 'Inactiva'}</span></td>
</tr>`;
});
html += '</tbody></table>';
document.getElementById('listaAgencias').innerHTML = html;
});
}

function generarReporte() {
const desde = document.getElementById('reporteDesde').value;
const hasta = document.getElementById('reporteHasta').value;

fetch('/api/reporte-ventas', {
method: 'POST',
headers: {'Content-Type': 'application/json'},
body: JSON.stringify({fecha_inicio: desde, fecha_fin: hasta})
})
.then(r => r.json())
.then(data => {
if(data.error) {
alert('Error: ' + data.error);
return;
}
let html = `
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px;">
<div style="background:#060e1e;padding:16px;border-radius:8px;text-align:center;">
<div style="color:#3a5080;font-size:.8rem;margin-bottom:4px">TOTAL VENTAS</div>
<div style="font-size:1.5rem;font-weight:700;color:#fff;">S/ ${data.resumen.total_ventas.toFixed(2)}</div>
</div>
<div style="background:#060e1e;padding:16px;border-radius:8px;text-align:center;">
<div style="color:#3a5080;font-size:.8rem;margin-bottom:4px">TOTAL PREMIOS</div>
<div style="font-size:1.5rem;font-weight:700;color:#f5a623;">S/ ${data.resumen.total_premios.toFixed(2)}</div>
</div>
<div style="background:#060e1e;padding:16px;border-radius:8px;text-align:center;">
<div style="color:#3a5080;font-size:.8rem;margin-bottom:4px">BALANCE</div>
<div style="font-size:1.5rem;font-weight:700;color:${data.resumen.balance >= 0 ? '#60ff60' : '#e05050'};">S/ ${data.resumen.balance.toFixed(2)}</div>
</div>
</div>
<table>
<thead><tr><th>Ticket</th><th>Agencia</th><th>Fecha</th><th>Monto</th><th>Premio</th></tr></thead>
<tbody>`;
data.ventas.forEach(v => {
html += `<tr>
<td>#${v.ticket_id}</td>
<td>${v.agencia}</td>
<td>${v.fecha}</td>
<td>S/ ${v.total.toFixed(2)}</td>
<td>S/ ${v.premio.toFixed(2)}</td>
</tr>`;
});
html += '</tbody></table>';
document.getElementById('resultadoReporte').innerHTML = html;
});
}

document.getElementById('fechaResultado').valueAsDate = new Date();
document.getElementById('reporteDesde').valueAsDate = new Date();
document.getElementById('reporteHasta').valueAsDate = new Date();
</script>
</body>
</html>'''

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
