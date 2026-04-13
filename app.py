#!/usr/bin/env python3
"""
ZOOLO CASINO LOCAL v3.0 — Código Optimizado
- Tripleta válida solo día actual (9am-6pm)
- Cierre a 2 minutos del sorteo
- Jugada manual por texto (pegar números)
- Repetir ticket por serial editable
"""

import os, json, csv, io, re
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, render_template_string, request, session, redirect, jsonify, Response
from collections import defaultdict

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'zoolo_local_2025_seguro')
DATABASE_URL = os.environ.get('DATABASE_URL', '')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

PAGO_ANIMAL_NORMAL = 35
PAGO_LECHUZA       = 70
PAGO_ESPECIAL      = 2
PAGO_TRIPLETA      = 60
COMISION_AGENCIA   = 0.15
MINUTOS_BLOQUEO    = 3  # Cierre 3 minutos antes del sorteo (a los :57)

# Horarios: 8AM a 6PM (11 sorteos) — hora Peru
HORARIOS_PERU = [
    "08:00 AM","09:00 AM","10:00 AM","11:00 AM","12:00 PM",
    "01:00 PM","02:00 PM","03:00 PM","04:00 PM","05:00 PM","06:00 PM"
]

# Horarios Plus: 8AM a 7PM (12 sorteos) — hora Venezuela (UTC-4)
HORARIOS_PLUS = [
    "08:00 AM","09:00 AM","10:00 AM","11:00 AM","12:00 PM",
    "01:00 PM","02:00 PM","03:00 PM","04:00 PM","05:00 PM","06:00 PM","07:00 PM"
]

ANIMALES = {
    "00":"Ballena","0":"Delfin","1":"Carnero","2":"Toro","3":"Ciempies",
    "4":"Alacran","5":"Leon","6":"Rana","7":"Perico","8":"Raton","9":"Aguila",
    "10":"Tigre","11":"Gato","12":"Caballo","13":"Mono","14":"Paloma",
    "15":"Zorro","16":"Oso","17":"Pavo","18":"Burro","19":"Chivo","20":"Cochino",
    "21":"Gallo","22":"Camello","23":"Cebra","24":"Iguana","25":"Gallina",
    "26":"Vaca","27":"Perro","28":"Zamuro","29":"Elefante","30":"Caiman",
    "31":"Lapa","32":"Ardilla","33":"Pescado","34":"Venado","35":"Jirafa",
    "36":"Culebra","37":"Aviapa","38":"Conejo","39":"Tortuga","40":"Lechuza"
}

COLORES = {
    "00":"verde","0":"verde",
    "1":"rojo","3":"rojo","5":"rojo","7":"rojo","9":"rojo",
    "12":"rojo","14":"rojo","16":"rojo","18":"rojo","19":"rojo",
    "21":"rojo","23":"rojo","25":"rojo","27":"rojo","30":"rojo",
    "32":"rojo","34":"rojo","36":"rojo","37":"rojo","39":"rojo",
    "40":"negro",
    "2":"negro","4":"negro","6":"negro","8":"negro","10":"negro","11":"negro",
    "13":"negro","15":"negro","17":"negro","20":"negro","22":"negro",
    "24":"negro","26":"negro","28":"negro","29":"negro","31":"negro",
    "33":"negro","35":"negro","38":"negro"
}

ROJOS = ["1","3","5","7","9","12","14","16","18","19",
         "21","23","25","27","30","32","34","36","37","39"]

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return _DBWrap(conn)

class _DBWrap:
    """Hace que psycopg2 sea compatible con el patron with get_db() as db: de SQLite"""
    def __init__(self, conn):
        self._c = conn
        self._cur = conn.cursor()

    # --- context manager ---
    def __enter__(self):
        return self
    def __exit__(self, exc, val, tb):
        if exc:
            self._c.rollback()
        else:
            self._c.commit()
        self._cur.close()
        self._c.close()
        return False

    # --- ejecutar queries ---
    def execute(self, sql, params=None):
        self._cur.execute(sql, params or ())
        return self  # devuelve self para poder encadenar .fetchone()/.fetchall()

    def executemany(self, sql, seq):
        self._cur.executemany(sql, seq)
        return self

    def executescript(self, script):
        # PostgreSQL no tiene executescript - ejecutar sentencia por sentencia
        for stmt in script.split(';'):
            s = stmt.strip()
            if s:
                try:
                    self._cur.execute(s)
                except Exception:
                    self._c.rollback()
        return self

    # --- resultados como dict (compatible con sqlite3.Row) ---
    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in self._cur.description]
        return _Row(dict(zip(cols, row)))

    def fetchall(self):
        rows = self._cur.fetchall()
        if not rows:
            return []
        cols = [d[0] for d in self._cur.description]
        return [_Row(dict(zip(cols, r))) for r in rows]

    # --- lastrowid usando lastval() de PostgreSQL ---
    @property
    def lastrowid(self):
        self._cur.execute("SELECT lastval()")
        return self._cur.fetchone()[0]

    def commit(self):
        self._c.commit()

    def close(self):
        self._cur.close()
        self._c.close()

    # Iteracion directa sobre resultados
    def __iter__(self):
        cols = [d[0] for d in self._cur.description]
        for row in self._cur:
            yield _Row(dict(zip(cols, row)))


class _Row(dict):
    """Fila compatible con sqlite3.Row: acceso por nombre y por indice"""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)
    def keys(self):
        return super().keys()

def init_db():
    with get_db() as db:
        # Tablas principales (SERIAL en lugar de AUTOINCREMENT, sin FOREIGN KEY inline)
        db.execute("""CREATE TABLE IF NOT EXISTS agencias (
            id SERIAL PRIMARY KEY, usuario TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
            nombre_agencia TEXT NOT NULL, nombre_banco TEXT DEFAULT '',
            es_admin INTEGER DEFAULT 0, comision REAL DEFAULT 0.15,
            activa INTEGER DEFAULT 1, tope_taquilla REAL DEFAULT 0,
            creado TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')))""")
        db.execute("""CREATE TABLE IF NOT EXISTS tickets (
            id SERIAL PRIMARY KEY, serial TEXT UNIQUE NOT NULL,
            agencia_id INTEGER NOT NULL, fecha TEXT NOT NULL, total REAL NOT NULL,
            pagado INTEGER DEFAULT 0, anulado INTEGER DEFAULT 0,
            creado TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')))""")
        db.execute("""CREATE TABLE IF NOT EXISTS jugadas (
            id SERIAL PRIMARY KEY, ticket_id INTEGER NOT NULL, hora TEXT NOT NULL,
            seleccion TEXT NOT NULL, monto REAL NOT NULL, tipo TEXT NOT NULL,
            loteria TEXT NOT NULL DEFAULT 'peru')""")
        db.execute("""CREATE TABLE IF NOT EXISTS tripletas (
            id SERIAL PRIMARY KEY, ticket_id INTEGER NOT NULL, animal1 TEXT NOT NULL,
            animal2 TEXT NOT NULL, animal3 TEXT NOT NULL, monto REAL NOT NULL,
            fecha TEXT NOT NULL, pagado INTEGER DEFAULT 0,
            loteria TEXT NOT NULL DEFAULT 'peru')""")
        db.execute("""CREATE TABLE IF NOT EXISTS resultados (
            id SERIAL PRIMARY KEY, fecha TEXT NOT NULL, hora TEXT NOT NULL,
            animal TEXT NOT NULL, loteria TEXT NOT NULL DEFAULT 'peru',
            UNIQUE(fecha, hora, loteria))""")
        db.execute("""CREATE TABLE IF NOT EXISTS topes (
            id SERIAL PRIMARY KEY, hora TEXT NOT NULL, numero TEXT NOT NULL,
            monto_tope REAL NOT NULL, loteria TEXT NOT NULL DEFAULT 'peru',
            UNIQUE(hora, numero, loteria))""")
        db.execute("""CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY, agencia_id INTEGER, usuario TEXT,
            accion TEXT NOT NULL, detalle TEXT, ip TEXT,
            creado TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')))""")
        # Indices
        for idx in [
            "CREATE INDEX IF NOT EXISTS idx_tickets_agencia ON tickets(agencia_id)",
            "CREATE INDEX IF NOT EXISTS idx_tickets_fecha ON tickets(fecha)",
            "CREATE INDEX IF NOT EXISTS idx_jugadas_ticket ON jugadas(ticket_id)",
            "CREATE INDEX IF NOT EXISTS idx_tripletas_ticket ON tripletas(ticket_id)",
            "CREATE INDEX IF NOT EXISTS idx_resultados_fecha ON resultados(fecha)",
            "CREATE INDEX IF NOT EXISTS idx_audit_logs_fecha ON audit_logs(creado)",
        ]:
            db.execute(idx)
        # Tablas opcionales
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS zoolo_acumulado (
                id SERIAL PRIMARY KEY, fecha TEXT NOT NULL, hora TEXT NOT NULL,
                venta_total REAL DEFAULT 0, presupuesto_premios REAL DEFAULT 0,
                premio_pagado REAL DEFAULT 0, ganancia_casa REAL DEFAULT 0,
                saldo_acumulado REAL DEFAULT 0, animal_ganador TEXT, UNIQUE(fecha, hora))""")
            db.execute("""CREATE TABLE IF NOT EXISTS zoolo_frecuencia_semanal (
                id SERIAL PRIMARY KEY, semana TEXT NOT NULL, animal TEXT NOT NULL,
                veces INTEGER DEFAULT 0, UNIQUE(semana, animal))""")
            db.commit()
        except: pass
        # Migraciones (ignorar si ya existen)
        for sql in [
            "ALTER TABLE agencias ADD COLUMN tope_taquilla REAL DEFAULT 0",
            "ALTER TABLE agencias ADD COLUMN nombre_banco TEXT DEFAULT ''",
            "ALTER TABLE resultados ADD COLUMN loteria TEXT NOT NULL DEFAULT 'peru'",
            "ALTER TABLE topes ADD COLUMN loteria TEXT NOT NULL DEFAULT 'peru'",
            "ALTER TABLE jugadas ADD COLUMN loteria TEXT NOT NULL DEFAULT 'peru'",
            "ALTER TABLE tripletas ADD COLUMN loteria TEXT NOT NULL DEFAULT 'peru'",
        ]:
            try:
                db.execute(sql)
                db.commit()
            except: pass
        admin = db.execute("SELECT id FROM agencias WHERE es_admin=1").fetchone()
        if not admin:
            db.execute("INSERT INTO agencias (usuario,password,nombre_agencia,es_admin,comision,activa) VALUES (%s,%s,%s,1,0,1)",
                       ('cuborubi','15821462','ADMINISTRADOR'))
            db.commit()

def ahora_peru():
    return datetime.now(timezone.utc) - timedelta(hours=5)

def ahora_venezuela():
    return datetime.now(timezone.utc) - timedelta(hours=4)

def parse_fecha(f):
    if not f: return None
    for fmt in ("%d/%m/%Y %I:%M %p", "%d/%m/%Y", "%Y-%m-%d"):
        try: return datetime.strptime(f, fmt)
        except: pass
    return None

def generar_serial():
    return str(int(ahora_peru().timestamp() * 1000))

def fmt(m):
    try:
        v = float(m)
        return str(int(v)) if v == int(v) else str(v)
    except: return str(m)

def hora_a_min(h):
    try:
        p = h.replace(':',' ').split()
        hr, mn, ap = int(p[0]), int(p[1]), p[2]
        if ap=='PM' and hr!=12: hr+=12
        elif ap=='AM' and hr==12: hr=0
        return hr*60+mn
    except: return 0

def puede_vender(hora_sorteo):
    ahora = ahora_peru()
    diff = hora_a_min(hora_sorteo) - (ahora.hour*60+ahora.minute)
    return diff > MINUTOS_BLOQUEO

def puede_vender_plus(hora_sorteo):
    ahora = ahora_venezuela()
    diff = hora_a_min(hora_sorteo) - (ahora.hour*60+ahora.minute)
    return diff > MINUTOS_BLOQUEO

def calcular_premio_animal(monto, num):
    return monto * (PAGO_LECHUZA if str(num)=="40" else PAGO_ANIMAL_NORMAL)

def resultados_validos_para_tripleta(resultados_dia, hora_compra_ticket):
    """
    Filtra resultados_dia {hora: animal} devolviendo solo los sorteos
    POSTERIORES O IGUALES a la hora de compra del ticket.
    Los sorteos que ya habian ocurrido cuando se compro la tripleta
    NO cuentan para completarla.
    hora_compra_ticket: objeto datetime con la hora de compra.
    """
    if hora_compra_ticket is None:
        return resultados_dia
    min_compra = hora_compra_ticket.hour * 60 + hora_compra_ticket.minute
    return {h: a for h, a in resultados_dia.items() if hora_a_min(h) >= min_compra}

def calcular_premio_ticket(ticket_id, db=None):
    """
    Calcula el premio de un ticket respetando la separación de loterías.
    Cada jugada/tripleta solo se compara contra los resultados de SU lotería.
    Zoolo Casino PERÚ y Zoolo Casino PLUS son 100% independientes.
    """
    close = False
    if db is None:
        db = get_db(); close = True
    try:
        t = db.execute("SELECT fecha FROM tickets WHERE id=%s", (ticket_id,)).fetchone()
        if not t: return 0
        fecha_ticket = parse_fecha(t['fecha'])
        if not fecha_ticket: return 0
        fecha_str = fecha_ticket.strftime("%d/%m/%Y")

        # Cargar resultados de cada lotería POR SEPARADO — nunca mezclar
        res_rows_peru = db.execute(
            "SELECT hora, animal FROM resultados WHERE fecha=%s AND loteria='peru'", (fecha_str,)
        ).fetchall()
        res_rows_plus = db.execute(
            "SELECT hora, animal FROM resultados WHERE fecha=%s AND loteria='plus'", (fecha_str,)
        ).fetchall()
        resultados_peru = {r['hora']: r['animal'] for r in res_rows_peru}
        resultados_plus = {r['hora']: r['animal'] for r in res_rows_plus}

        total = 0

        # Jugadas — cada una usa SOLO los resultados de su propia lotería
        jugadas = db.execute("SELECT * FROM jugadas WHERE ticket_id=%s", (ticket_id,)).fetchall()
        for j in jugadas:
            lot_j = j['loteria'] if 'loteria' in j.keys() else 'peru'
            res_dia = resultados_plus if lot_j == 'plus' else resultados_peru
            wa = res_dia.get(j['hora'])
            if not wa: continue
            if j['tipo']=='animal' and str(wa)==str(j['seleccion']):
                total += calcular_premio_animal(j['monto'], wa)
            elif j['tipo']=='especial' and str(wa) not in ["0","00"]:
                sel, num = j['seleccion'], int(wa)
                if (sel=='ROJO' and str(wa) in ROJOS) or \
                   (sel=='NEGRO' and str(wa) not in ROJOS) or \
                   (sel=='PAR' and num%2==0) or \
                   (sel=='IMPAR' and num%2!=0):
                    total += j['monto'] * PAGO_ESPECIAL

        # Tripletas — cada una usa SOLO los resultados de su propia lotería
        # Solo cuentan sorteos POSTERIORES a la hora de compra del ticket
        res_validos_peru = resultados_validos_para_tripleta(resultados_peru, fecha_ticket)
        res_validos_plus = resultados_validos_para_tripleta(resultados_plus, fecha_ticket)
        trips = db.execute("SELECT * FROM tripletas WHERE ticket_id=%s", (ticket_id,)).fetchall()
        for tr in trips:
            lot_tr = tr['loteria'] if 'loteria' in tr.keys() else 'peru'
            res_validos = res_validos_plus if lot_tr == 'plus' else res_validos_peru
            nums = {tr['animal1'], tr['animal2'], tr['animal3']}
            salidos = {a for a in res_validos.values() if a in nums}
            if len(salidos)==3:
                total += tr['monto'] * PAGO_TRIPLETA
        return total
    finally:
        if close: db.close()

def login_required(f):
    @wraps(f)
    def d(*a,**k):
        if 'user_id' not in session: return redirect('/login')
        return f(*a,**k)
    return d

def admin_required(f):
    @wraps(f)
    def d(*a,**k):
        if 'user_id' not in session or not session.get('es_admin'):
            return "No autorizado", 403
        return f(*a,**k)
    return d

def agencia_required(f):
    @wraps(f)
    def d(*a,**k):
        if 'user_id' not in session: return jsonify({'error':'Login requerido'}),403
        if session.get('es_admin'): return jsonify({'error':'Admin no puede vender'}),403
        return f(*a,**k)
    return d

def log_audit(accion, detalle=None):
    try:
        ip = request.remote_addr
        with get_db() as db:
            db.execute(
                "INSERT INTO audit_logs (agencia_id, usuario, accion, detalle, ip) VALUES (%s,%s,%s,%s,%s)",
                (session.get('user_id'), session.get('nombre_agencia','?'), accion, detalle, ip)
            )
            db.commit()
    except: pass

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect('/admin' if session.get('es_admin') else '/pos')
    return redirect('/login')

@app.route('/login', methods=['GET','POST'])
def login():
    error=""
    if request.method=='POST':
        u = request.form.get('usuario','').strip().lower()
        p = request.form.get('password','').strip()
        with get_db() as db:
            row = db.execute("SELECT * FROM agencias WHERE usuario=%s AND password=%s AND activa=1",(u,p)).fetchone()
        if row:
            session['user_id'] = row['id']
            session['nombre_agencia'] = row['nombre_agencia']
            session['nombre_banco'] = row['nombre_banco'] if row['nombre_banco'] else ''
            session['es_admin'] = bool(row['es_admin'])
            log_audit('LOGIN', f"Ingreso exitoso desde {request.remote_addr}")
            return redirect('/')
        error="Usuario o clave incorrecta"
    return render_template_string(LOGIN_HTML, error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/pos')
@login_required
def pos():
    if session.get('es_admin'): return redirect('/admin')
    return render_template_string(POS_HTML,
        agencia=session['nombre_agencia'],
        animales=ANIMALES,
        colores=COLORES,
        horarios_peru=HORARIOS_PERU,
        horarios_plus=HORARIOS_PLUS)

@app.route('/admin')
@admin_required
def admin():
    return render_template_string(ADMIN_HTML, animales=ANIMALES, horarios=HORARIOS_PERU, horarios_plus=HORARIOS_PLUS)

# ========== API ==========
@app.route('/api/hora-actual')
@login_required
def hora_actual():
    ahora_p = ahora_peru()
    ahora_v = ahora_venezuela()
    bloqueadas_peru = [h for h in HORARIOS_PERU if not puede_vender(h)]
    bloqueadas_plus = [h for h in HORARIOS_PLUS if not puede_vender_plus(h)]
    return jsonify({
        'hora_str': ahora_p.strftime("%I:%M %p"),
        'hora_str_plus': ahora_v.strftime("%I:%M %p"),
        'bloqueadas': bloqueadas_peru,
        'bloqueadas_plus': bloqueadas_plus
    })

@app.route('/api/resultados-hoy')
@login_required
def resultados_hoy():
    hoy = ahora_peru().strftime("%d/%m/%Y")
    loteria = request.args.get('loteria', 'peru')
    horarios = HORARIOS_PLUS if loteria == 'plus' else HORARIOS_PERU
    with get_db() as db:
        rows = db.execute("SELECT hora,animal FROM resultados WHERE fecha=%s AND loteria=%s",(hoy, loteria)).fetchall()
    rd = {r['hora']:{'animal':r['animal'],'nombre':ANIMALES.get(r['animal'],'?')} for r in rows}
    for h in horarios:
        if h not in rd: rd[h]=None
    return jsonify({'status':'ok','fecha':hoy,'resultados':rd})

@app.route('/api/resultados-fecha', methods=['POST'])
@login_required
def resultados_fecha():
    data = request.get_json() or {}
    fs = data.get('fecha')
    loteria = data.get('loteria', 'peru')
    horarios = HORARIOS_PLUS if loteria == 'plus' else HORARIOS_PERU
    try: fecha_obj = datetime.strptime(fs, "%Y-%m-%d") if fs else ahora_peru()
    except: fecha_obj = ahora_peru()
    fecha_str = fecha_obj.strftime("%d/%m/%Y")
    with get_db() as db:
        rows = db.execute("SELECT hora,animal FROM resultados WHERE fecha=%s AND loteria=%s",(fecha_str, loteria)).fetchall()
    rd = {r['hora']:{'animal':r['animal'],'nombre':ANIMALES.get(r['animal'],'?')} for r in rows}
    for h in horarios:
        if h not in rd: rd[h]=None
    return jsonify({'status':'ok','fecha_consulta':fecha_str,'resultados':rd})

@app.route('/api/procesar-venta', methods=['POST'])
@agencia_required
def procesar_venta():
    try:
        data = request.get_json()
        jugadas = data.get('jugadas', [])
        if not jugadas: return jsonify({'error':'Ticket vacío'}),400

        # Separar jugadas por lotería
        jugadas_peru = [j for j in jugadas if j.get('loteria','peru') == 'peru']
        jugadas_plus = [j for j in jugadas if j.get('loteria','peru') == 'plus']

        # Validar horarios bloqueados — cada lotería con su zona horaria
        for j in jugadas_peru:
            if j['tipo']!='tripleta' and not puede_vender(j['hora']):
                return jsonify({'error':f"PERU — Sorteo {j['hora']} ya cerró (5 min antes)"}),400
        for j in jugadas_plus:
            if j['tipo']!='tripleta' and not puede_vender_plus(j['hora']):
                return jsonify({'error':f"PLUS — Sorteo {j['hora']} ya cerró (5 min antes)"}),400

        hoy = ahora_peru().strftime("%d/%m/%Y")
        agencia_id = session['user_id']
        total = sum(j['monto'] for j in jugadas)

        with get_db() as db:
            # Verificar tope de taquilla
            ag = db.execute("SELECT tope_taquilla, comision FROM agencias WHERE id=%s", (agencia_id,)).fetchone()
            tope_taq = ag['tope_taquilla'] if ag else 0
            if tope_taq and tope_taq > 0:
                ventas_hoy = db.execute(
                    "SELECT COALESCE(SUM(total),0) as tot FROM tickets WHERE agencia_id=%s AND anulado=0 AND fecha LIKE %s",
                    (agencia_id, hoy+'%')
                ).fetchone()['tot']
                if ventas_hoy + total > tope_taq:
                    return jsonify({'error':f'Tope de taquilla alcanzado. Límite: S/{tope_taq}, vendido hoy: S/{ventas_hoy:.2f}'}),400

            # Verificar topes por número — considerando lotería
            for j in jugadas:
                if j['tipo'] == 'animal':
                    lot = j.get('loteria','peru')
                    tope_row = db.execute(
                        "SELECT monto_tope FROM topes WHERE hora=%s AND numero=%s AND loteria=%s",
                        (j['hora'], j['seleccion'], lot)
                    ).fetchone()
                    if tope_row:
                        ya_apostado = db.execute("""
                            SELECT COALESCE(SUM(jg.monto),0) as tot
                            FROM jugadas jg
                            JOIN tickets tk ON jg.ticket_id=tk.id
                            WHERE jg.hora=%s AND jg.seleccion=%s AND jg.tipo='animal' AND jg.loteria=%s
                            AND tk.anulado=0 AND tk.fecha LIKE %s
                        """, (j['hora'], j['seleccion'], lot, hoy+'%')).fetchone()['tot']
                        if ya_apostado + j['monto'] > tope_row['monto_tope']:
                            nombre = ANIMALES.get(j['seleccion'], j['seleccion'])
                            lot_label = 'PLUS' if lot=='plus' else 'PERU'
                            return jsonify({'error':f'Tope alcanzado para {j["seleccion"]}-{nombre} en {j["hora"]} ({lot_label}). Disponible: S/{tope_row["monto_tope"]-ya_apostado:.2f}'}),400

        serial = generar_serial()
        fecha  = ahora_peru().strftime("%d/%m/%Y %I:%M %p")

        with get_db() as db:
            cur = db.execute("INSERT INTO tickets (serial,agencia_id,fecha,total) VALUES (%s,%s,%s,%s) RETURNING id",
                (serial, agencia_id, fecha, total))
            ticket_id = db.fetchone()[0]

            for j in jugadas:
                lot = j.get('loteria','peru')
                if j['tipo']=='tripleta':
                    nums = j['seleccion'].split(',')
                    db.execute("INSERT INTO tripletas (ticket_id,animal1,animal2,animal3,monto,fecha,loteria) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (ticket_id, nums[0], nums[1], nums[2], j['monto'], fecha.split(' ')[0], lot))
                else:
                    db.execute("INSERT INTO jugadas (ticket_id,hora,seleccion,monto,tipo,loteria) VALUES (%s,%s,%s,%s,%s,%s)",
                        (ticket_id, j['hora'], j['seleccion'], j['monto'], j['tipo'], lot))
            db.commit()

        log_audit('VENTA', f"Ticket #{ticket_id} serial:{serial} total:S/{total}")

        def fmt_h_ticket(h):
            m2 = re.match(r'(\d+):(\d+) (AM|PM)', h.strip())
            if m2:
                hh, mm, ap = m2.group(1), m2.group(2), m2.group(3)
                return f"{int(hh)}{ap}" if mm=='00' else f"{int(hh)}:{mm}{ap}"
            return h.replace(' ','')

        def fmt_h_plus_ticket(h):
            """Returns 'Xam VEN - Yam PERU' where Y = X-1h (Venezuela is UTC-4, Peru UTC-5)."""
            m2 = re.match(r'(\d+):(\d+) (AM|PM)', h.strip())
            if not m2: return h.replace(' ','')
            hh, mm, ap = int(m2.group(1)), m2.group(2), m2.group(3)
            ven_label = f"{hh}{ap}" if mm=='00' else f"{hh}:{mm}{ap}"
            # Convert to 24h, subtract 1 hour, back to 12h for Peru label
            h24 = hh % 12 + (12 if ap=='PM' else 0)
            peru_h24 = (h24 - 1) % 24
            peru_ap = 'PM' if peru_h24 >= 12 else 'AM'
            peru_hh = peru_h24 % 12 or 12
            peru_label = f"{peru_hh}{peru_ap}" if mm=='00' else f"{peru_hh}:{mm}{peru_ap}"
            return f"{ven_label} VEN - {peru_label} PERU"


        nombre_banco = session.get('nombre_banco', '').strip()
        sep_banco = f"-----------{nombre_banco}-----------" if nombre_banco else "------------------------"

        lineas = [f"*{session['nombre_agencia']}*",
                  f"*TICKET:* #{ticket_id}",
                  f"*SERIAL:* {serial}",
                  fecha,
                  sep_banco,
                  ""]

        # Jugadas PERU
        jpoh_peru = defaultdict(list)
        for j in jugadas_peru:
            if j['tipo']!='tripleta': jpoh_peru[j['hora']].append(j)

        for hp in HORARIOS_PERU:
            if hp not in jpoh_peru: continue
            hpc = fmt_h_ticket(hp)
            lineas.append(f"*ZOOLO.PERU / {hpc}*")
            items=[]
            for j in jpoh_peru[hp]:
                if j['tipo']=='animal':
                    n = ANIMALES.get(j['seleccion'],'')[0:3].upper()
                    items.append(f"{n}{j['seleccion']}x{fmt(j['monto'])}")
                else:
                    items.append(f"{j['seleccion'][0:3]}x{fmt(j['monto'])}")
            lineas.append(" ".join(items))
            lineas.append("")

        # Jugadas PLUS
        jpoh_plus = defaultdict(list)
        for j in jugadas_plus:
            if j['tipo']!='tripleta': jpoh_plus[j['hora']].append(j)

        for hp in HORARIOS_PLUS:
            if hp not in jpoh_plus: continue
            hpc = fmt_h_plus_ticket(hp)
            lineas.append(f"*ZOOLO.PLUS / {hpc}*")
            items=[]
            for j in jpoh_plus[hp]:
                if j['tipo']=='animal':
                    n = ANIMALES.get(j['seleccion'],'')[0:3].upper()
                    items.append(f"{n}{j['seleccion']}x{fmt(j['monto'])}")
                else:
                    items.append(f"{j['seleccion'][0:3]}x{fmt(j['monto'])}")
            lineas.append(" ".join(items))
            lineas.append("")

        # Tripletas
        ahora_dt = ahora_peru()
        trips_peru = [j for j in jugadas_peru if j['tipo']=='tripleta']
        trips_plus = [j for j in jugadas_plus if j['tipo']=='tripleta']

        if trips_peru or trips_plus:
            lineas.append("-------------------------------")
            fecha_hoy_fmt = ahora_dt.strftime("%d/%m/%Y")
            for t in trips_peru:
                nums = t['seleccion'].split(',')
                hora_ini = HORARIOS_PERU[0]; hora_fin = HORARIOS_PERU[-1]
                lineas.append(f"-------TRPLZOOL----------")
                lineas.append(f"DESDE {fecha_hoy_fmt} Sorteo {fmt_h_ticket(hora_ini)} PERU")
                lineas.append(f"HASTA {fecha_hoy_fmt} Sorteo {fmt_h_ticket(hora_fin)} PERU")
                lineas.append(f"(11 sorteos fijos del dia: 8AM a 6PM)")
                partes = [f"{n}({ANIMALES.get(n,'')[0:3].upper()})" for n in nums]
                lineas.append(f"  TRIPLETA: " + " - ".join(partes) + f" x {fmt(t['monto'])} SL")
            for t in trips_plus:
                nums = t['seleccion'].split(',')
                hora_ini = HORARIOS_PLUS[0]; hora_fin = HORARIOS_PLUS[-1]
                lineas.append("-------TRPLZOOL+----------")
                lineas.append(f"DESDE {fecha_hoy_fmt} Sorteo {fmt_h_plus_ticket(hora_ini)} PLUS")
                lineas.append(f"HASTA {fecha_hoy_fmt} Sorteo {fmt_h_plus_ticket(hora_fin)} PLUS")
                lineas.append("(12 sorteos fijos del dia: 8AM a 7PM VEN / 7AM a 6PM PERU)")
                partes = [f"{n}({ANIMALES.get(n,'')[0:3].upper()})" for n in nums]
                lineas.append("  TRIPLETA: " + " - ".join(partes) + f" x {fmt(t['monto'])} SL")
            lineas.append("-------------------------------")

        lineas += ["------------------------",
                   f"*TOTAL: S/{fmt(total)}*",
                   "",
                   "Buena Suerte! 🍀",
                   "El ticket vence a los 3 dias"]
        lineas = [l for l in lineas if l != ""]

        import urllib.parse
        texto = "\n".join(lineas)
        url_wa = f"https://wa.me/?text={urllib.parse.quote(texto)}"

        return jsonify({
            'status':'ok',
            'serial':serial,
            'ticket_id':ticket_id,
            'total':total,
            'url_whatsapp':url_wa
        })
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/repetir-ticket', methods=['POST'])
@agencia_required
def repetir_ticket():
    """Obtiene datos de un ticket por serial para repetirlo"""
    try:
        serial = request.json.get('serial')
        if not serial:
            return jsonify({'error':'Serial requerido'}),400
        
        with get_db() as db:
            t = db.execute("SELECT * FROM tickets WHERE serial=%s AND agencia_id=%s", 
                          (serial, session['user_id'])).fetchone()
            if not t:
                return jsonify({'error':'Ticket no encontrado'}),404
            
            # Obtener jugadas
            jugadas = db.execute("SELECT * FROM jugadas WHERE ticket_id=%s", (t['id'],)).fetchall()
            tripletas = db.execute("SELECT * FROM tripletas WHERE ticket_id=%s", (t['id'],)).fetchall()
            
            jugadas_list = []
            for j in jugadas:
                jugadas_list.append({
                    'tipo': j['tipo'],
                    'hora': j['hora'],
                    'seleccion': j['seleccion'],
                    'monto': j['monto'],
                    'nombre': ANIMALES.get(j['seleccion'], j['seleccion']) if j['tipo']=='animal' else j['seleccion']
                })
            
            trips_list = []
            for tr in tripletas:
                lot_tr = tr['loteria'] if 'loteria' in tr.keys() else 'peru'
                trips_list.append({
                    'tipo': 'tripleta',
                    'animal1': tr['animal1'],
                    'animal2': tr['animal2'],
                    'animal3': tr['animal3'],
                    'monto': tr['monto'],
                    'seleccion': f"{tr['animal1']},{tr['animal2']},{tr['animal3']}",
                    'loteria': lot_tr
                })
            
            return jsonify({
                'status': 'ok',
                'ticket_original': {
                    'serial': t['serial'],
                    'fecha': t['fecha'],
                    'total': t['total']
                },
                'jugadas': jugadas_list + trips_list
            })
            
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/mis-tickets', methods=['POST'])
@agencia_required
def mis_tickets():
    try:
        data = request.get_json() or {}
        fi = data.get('fecha_inicio'); ff = data.get('fecha_fin'); est = data.get('estado','todos')
        dti = datetime.strptime(fi,"%Y-%m-%d") if fi else None
        dtf = datetime.strptime(ff,"%Y-%m-%d").replace(hour=23,minute=59) if ff else None
        
        with get_db() as db:
            rows = db.execute("SELECT * FROM tickets WHERE agencia_id=%s AND anulado=0 ORDER BY id DESC LIMIT 500",
                            (session['user_id'],)).fetchall()
            resultado_cache = {}
            tickets_out = []
            
            for t in rows:
                dt = parse_fecha(t['fecha'])
                if not dt: continue
                if dti and dt<dti: continue
                if dtf and dt>dtf: continue
                if est=='pagados' and not t['pagado']: continue
                if est=='pendientes' and t['pagado']: continue
                
                fecha_str = dt.strftime("%d/%m/%Y")
                cache_key_peru = fecha_str + '_peru'
                cache_key_plus = fecha_str + '_plus'
                if cache_key_peru not in resultado_cache:
                    rr = db.execute("SELECT hora,animal FROM resultados WHERE fecha=%s AND loteria='peru'",(fecha_str,)).fetchall()
                    resultado_cache[cache_key_peru] = {r['hora']:r['animal'] for r in rr}
                if cache_key_plus not in resultado_cache:
                    rr = db.execute("SELECT hora,animal FROM resultados WHERE fecha=%s AND loteria='plus'",(fecha_str,)).fetchall()
                    resultado_cache[cache_key_plus] = {r['hora']:r['animal'] for r in rr}

                res_dia_peru = resultado_cache[cache_key_peru]
                res_dia_plus = resultado_cache[cache_key_plus]
                jugadas_raw = db.execute("SELECT * FROM jugadas WHERE ticket_id=%s",(t['id'],)).fetchall()
                tripletas_raw = db.execute("SELECT * FROM tripletas WHERE ticket_id=%s",(t['id'],)).fetchall()
                
                premio_total = 0
                jugadas_det = []
                
                for j in jugadas_raw:
                    lot_j = j['loteria'] if 'loteria' in j.keys() else 'peru'
                    res_dia = res_dia_plus if lot_j == 'plus' else res_dia_peru
                    wa = res_dia.get(j['hora']); gano=False; pj=0
                    if wa:
                        if j['tipo']=='animal' and str(wa)==str(j['seleccion']):
                            pj=calcular_premio_animal(j['monto'],wa); gano=True
                        elif j['tipo']=='especial' and str(wa) not in ["0","00"]:
                            sel,num=j['seleccion'],int(wa)
                            if (sel=='ROJO' and str(wa) in ROJOS) or \
                               (sel=='NEGRO' and str(wa) not in ROJOS) or \
                               (sel=='PAR' and num%2==0) or \
                               (sel=='IMPAR' and num%2!=0):
                                pj=j['monto']*PAGO_ESPECIAL; gano=True
                    if gano: premio_total+=pj
                    jugadas_det.append({
                        'tipo':j['tipo'],'hora':j['hora'],'seleccion':j['seleccion'],
                        'nombre':ANIMALES.get(j['seleccion'],j['seleccion']) if j['tipo']=='animal' else j['seleccion'],
                        'monto':j['monto'],'resultado':wa,
                        'resultado_nombre':ANIMALES.get(str(wa),str(wa)) if wa else None,
                        'gano':gano,'premio':round(pj,2),
                        'loteria': lot_j
                    })
                
                trips_det = []
                res_validos_trip_peru = resultados_validos_para_tripleta(res_dia_peru, dt)
                res_validos_trip_plus = resultados_validos_para_tripleta(res_dia_plus, dt)
                for tr in tripletas_raw:
                    lot_tr = tr['loteria'] if 'loteria' in tr.keys() else 'peru'
                    res_validos_trip = res_validos_trip_plus if lot_tr == 'plus' else res_validos_trip_peru
                    nums={tr['animal1'],tr['animal2'],tr['animal3']}
                    salidos=list(dict.fromkeys([a for a in res_validos_trip.values() if a in nums]))
                    gano_t=len(salidos)==3; pt=tr['monto']*PAGO_TRIPLETA if gano_t else 0
                    if gano_t: premio_total+=pt
                    trips_det.append({
                        'animal1':tr['animal1'],'nombre1':ANIMALES.get(tr['animal1'],tr['animal1']),
                        'animal2':tr['animal2'],'nombre2':ANIMALES.get(tr['animal2'],tr['animal2']),
                        'animal3':tr['animal3'],'nombre3':ANIMALES.get(tr['animal3'],tr['animal3']),
                        'monto':tr['monto'],'salieron':salidos,'gano':gano_t,'premio':round(pt,2),
                        'pagado':bool(tr['pagado']),'loteria':lot_tr
                    })
                
                if est=='por_pagar' and (t['pagado'] or premio_total==0): continue
                
                tickets_out.append({
                    'id':t['id'],'serial':t['serial'],'fecha':t['fecha'],
                    'total':t['total'],'pagado':bool(t['pagado']),
                    'premio_calculado':round(premio_total,2),
                    'jugadas':jugadas_det,'tripletas':trips_det
                })
        
        tv = sum(t['total'] for t in tickets_out)
        return jsonify({
            'status':'ok',
            'tickets':tickets_out,
            'totales':{'cantidad':len(tickets_out),'ventas':round(tv,2)}
        })
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/consultar-ticket-detalle', methods=['POST'])
@login_required
def consultar_ticket_detalle():
    try:
        serial = (request.get_json() or {}).get('serial')
        if not serial: return jsonify({'error':'Serial requerido'}),400
        
        with get_db() as db:
            if session.get('es_admin'):
                t = db.execute("SELECT * FROM tickets WHERE serial=%s",(serial,)).fetchone()
            else:
                t = db.execute("SELECT * FROM tickets WHERE serial=%s AND agencia_id=%s",
                              (serial,session['user_id'])).fetchone()
            
            if not t: return jsonify({'error':'Ticket no encontrado'})
            t = dict(t)
            fecha_str = parse_fecha(t['fecha']).strftime("%d/%m/%Y")
            res_rows_peru = db.execute("SELECT hora,animal FROM resultados WHERE fecha=%s AND loteria='peru'",(fecha_str,)).fetchall()
            res_rows_plus = db.execute("SELECT hora,animal FROM resultados WHERE fecha=%s AND loteria='plus'",(fecha_str,)).fetchall()
            res_dia_peru = {r['hora']:r['animal'] for r in res_rows_peru}
            res_dia_plus = {r['hora']:r['animal'] for r in res_rows_plus}
            jugadas_raw = db.execute("SELECT * FROM jugadas WHERE ticket_id=%s",(t['id'],)).fetchall()
            tripletas_raw = db.execute("SELECT * FROM tripletas WHERE ticket_id=%s",(t['id'],)).fetchall()
        
        premio_total=0; jdet=[]
        for j in jugadas_raw:
            lot_j = j['loteria'] if 'loteria' in j.keys() else 'peru'
            res_dia = res_dia_plus if lot_j == 'plus' else res_dia_peru
            wa=res_dia.get(j['hora']); gano=False; pj=0
            if wa:
                if j['tipo']=='animal' and str(wa)==str(j['seleccion']):
                    pj=calcular_premio_animal(j['monto'],wa); gano=True
                elif j['tipo']=='especial' and str(wa) not in ["0","00"]:
                    sel,num=j['seleccion'],int(wa)
                    if (sel=='ROJO' and str(wa) in ROJOS) or \
                       (sel=='NEGRO' and str(wa) not in ROJOS) or \
                       (sel=='PAR' and num%2==0) or \
                       (sel=='IMPAR' and num%2!=0):
                        pj=j['monto']*PAGO_ESPECIAL; gano=True
            if gano: premio_total+=pj
            jdet.append({
                'tipo':j['tipo'],'hora':j['hora'],'seleccion':j['seleccion'],
                'nombre_seleccion':ANIMALES.get(j['seleccion'],j['seleccion']) if j['tipo']=='animal' else j['seleccion'],
                'monto':j['monto'],'resultado':wa,
                'resultado_nombre':ANIMALES.get(str(wa),str(wa)) if wa else None,
                'gano':gano,'premio':round(pj,2),
                'loteria': lot_j
            })
        
        tdet=[]
        fecha_ticket_dt = parse_fecha(t['fecha'])
        res_validos_trip_peru = resultados_validos_para_tripleta(res_dia_peru, fecha_ticket_dt)
        res_validos_trip_plus = resultados_validos_para_tripleta(res_dia_plus, fecha_ticket_dt)
        for tr in tripletas_raw:
            lot_tr = tr['loteria'] if 'loteria' in tr.keys() else 'peru'
            res_validos_trip = res_validos_trip_plus if lot_tr == 'plus' else res_validos_trip_peru
            nums={tr['animal1'],tr['animal2'],tr['animal3']}
            salidos=list(dict.fromkeys([a for a in res_validos_trip.values() if a in nums]))
            gano_t=len(salidos)==3; pt=tr['monto']*PAGO_TRIPLETA if gano_t else 0
            if gano_t: premio_total+=pt
            tdet.append({
                'tipo':'tripleta',
                'animal1':tr['animal1'],'nombre1':ANIMALES.get(tr['animal1'],''),
                'animal2':tr['animal2'],'nombre2':ANIMALES.get(tr['animal2'],''),
                'animal3':tr['animal3'],'nombre3':ANIMALES.get(tr['animal3'],''),
                'monto':tr['monto'],'salieron':salidos,'gano':gano_t,
                'premio':round(pt,2),'pagado':bool(tr['pagado']),'loteria':lot_tr
            })
        
        return jsonify({
            'status':'ok',
            'ticket':{
                'id':t['id'],'serial':t['serial'],'fecha':t['fecha'],
                'total_apostado':t['total'],'pagado':bool(t['pagado']),
                'anulado':bool(t['anulado']),'premio_total':round(premio_total,2)
            },
            'jugadas':jdet,'tripletas':tdet
        })
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/verificar-ticket', methods=['POST'])
@login_required
def verificar_ticket():
    try:
        serial = request.json.get('serial')
        with get_db() as db:
            t = db.execute("SELECT * FROM tickets WHERE serial=%s",(serial,)).fetchone()
            if not t: return jsonify({'error':'Ticket no existe'})
            if not session.get('es_admin') and t['agencia_id']!=session['user_id']:
                return jsonify({'error':'No autorizado'})
            if t['anulado']: return jsonify({'error':'TICKET ANULADO'})
            if t['pagado']:  return jsonify({'error':'YA FUE PAGADO'})
            premio = calcular_premio_ticket(t['id'], db)
        return jsonify({'status':'ok','ticket_id':t['id'],'total_ganado':round(premio,2)})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/pagar-ticket', methods=['POST'])
@login_required
def pagar_ticket():
    try:
        tid = request.json.get('ticket_id')
        with get_db() as db:
            t = db.execute("SELECT * FROM tickets WHERE id=%s",(tid,)).fetchone()
            if not t: return jsonify({'error':'Ticket no existe'})
            if not session.get('es_admin') and t['agencia_id']!=session['user_id']:
                return jsonify({'error':'No autorizado'})
            db.execute("UPDATE tickets SET pagado=1 WHERE id=%s",(tid,))
            db.execute("UPDATE tripletas SET pagado=1 WHERE ticket_id=%s",(tid,))
            db.commit()
        log_audit('PAGO', f"Ticket id:{tid} pagado")
        return jsonify({'status':'ok','mensaje':'Ticket pagado'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/anular-ticket', methods=['POST'])
@login_required
def anular_ticket():
    try:
        serial = request.json.get('serial')
        with get_db() as db:
            t = db.execute("SELECT * FROM tickets WHERE serial=%s",(serial,)).fetchone()
            if not t: return jsonify({'error':'Ticket no existe'})
            
            # Verificar permisos
            if not session.get('es_admin') and t['agencia_id']!=session['user_id']:
                return jsonify({'error':'No autorizado'})
            
            if t['pagado']: 
                return jsonify({'error':'Ya pagado, no se puede anular'})
            
            if t['anulado']:
                return jsonify({'error':'Ticket ya estaba anulado'})
            
            # Agencias pueden anular si todos los sorteos del ticket aún no cerraron
            if not session.get('es_admin'):
                jugs = db.execute("SELECT hora, loteria FROM jugadas WHERE ticket_id=%s",(t['id'],)).fetchall()
                for j in jugs:
                    lot_j = j['loteria'] if 'loteria' in j.keys() else 'peru'
                    cerrado = not puede_vender_plus(j['hora']) if lot_j == 'plus' else not puede_vender(j['hora'])
                    if cerrado:
                        lot_label = 'PLUS' if lot_j == 'plus' else 'PERÚ'
                        return jsonify({'error':f"No se puede anular: el sorteo {j['hora']} ({lot_label}) ya cerró"})
            
            # Anular ticket
            db.execute("UPDATE tickets SET anulado=1 WHERE id=%s",(t['id'],))
            db.commit()
            
        log_audit('ANULACION', f"Ticket serial:{serial} anulado")
        return jsonify({'status':'ok','mensaje':'Ticket anulado correctamente'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/caja')
@agencia_required
def caja_agencia():
    try:
        hoy = ahora_peru().strftime("%d/%m/%Y")
        with get_db() as db:
            tickets = db.execute("SELECT * FROM tickets WHERE agencia_id=%s AND anulado=0 AND fecha LIKE %s",
                                (session['user_id'], hoy+'%')).fetchall()
            ag = db.execute("SELECT comision FROM agencias WHERE id=%s",(session['user_id'],)).fetchone()
            com_pct = ag['comision'] if ag else COMISION_AGENCIA
            
            ventas=0; premios_pagados=0; pendientes=0
            for t in tickets:
                ventas += t['total']
                p = calcular_premio_ticket(t['id'],db)
                if t['pagado']: 
                    premios_pagados+=p
                elif p>0: 
                    pendientes+=1
        
        return jsonify({
            'ventas':round(ventas,2),
            'premios':round(premios_pagados,2),
            'comision':round(ventas*com_pct,2),
            'balance':round(ventas-premios_pagados-ventas*com_pct,2),
            'tickets_pendientes':pendientes,
            'total_tickets':len(tickets)
        })
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/caja-historico', methods=['POST'])
@agencia_required
def caja_historico():
    try:
        data = request.get_json()
        fi,ff = data.get('fecha_inicio'), data.get('fecha_fin')
        if not fi or not ff: return jsonify({'error':'Fechas requeridas'}),400
        
        dti = datetime.strptime(fi,"%Y-%m-%d")
        dtf = datetime.strptime(ff,"%Y-%m-%d").replace(hour=23,minute=59)
        
        with get_db() as db:
            ag = db.execute("SELECT comision FROM agencias WHERE id=%s",(session['user_id'],)).fetchone()
            com_pct = ag['comision'] if ag else COMISION_AGENCIA
            tickets = db.execute("SELECT * FROM tickets WHERE agencia_id=%s AND anulado=0 ORDER BY id DESC LIMIT 2000",
                                (session['user_id'],)).fetchall()
        
        dias={}; tv=0; tp=0
        for t in tickets:
            dt=parse_fecha(t['fecha'])
            if not dt or dt<dti or dt>dtf: continue
            dk=dt.strftime("%d/%m/%Y")
            if dk not in dias: 
                dias[dk]={'ventas':0,'tickets':0,'premios':0}
            dias[dk]['ventas']+=t['total']
            dias[dk]['tickets']+=1
            tv+=t['total']
            with get_db() as db2: 
                p=calcular_premio_ticket(t['id'],db2)
            if t['pagado']: 
                dias[dk]['premios']+=p
                tp+=p
        
        resumen=[]
        for dk in sorted(dias.keys()):
            d=dias[dk]
            cd=d['ventas']*com_pct
            resumen.append({
                'fecha':dk,
                'tickets':d['tickets'],
                'ventas':round(d['ventas'],2),
                'premios':round(d['premios'],2),
                'comision':round(cd,2),
                'balance':round(d['ventas']-d['premios']-cd,2)
            })
        
        tc=tv*com_pct
        return jsonify({
            'resumen_por_dia':resumen,
            'totales':{
                'ventas':round(tv,2),
                'premios':round(tp,2),
                'comision':round(tc,2),
                'balance':round(tv-tp-tc,2)
            }
        })
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ========== ADMIN ROUTES ==========
@app.route('/admin/guardar-resultado', methods=['POST'])
@admin_required
def guardar_resultado():
    try:
        hora = request.form.get('hora','').strip()
        animal = request.form.get('animal','').strip()
        fi = request.form.get('fecha','').strip()
        loteria = request.form.get('loteria','peru').strip()

        if animal not in ANIMALES:
            return jsonify({'error':'Animal inválido'}),400

        horarios_validos = HORARIOS_PLUS if loteria == 'plus' else HORARIOS_PERU
        if hora not in horarios_validos:
            return jsonify({'error':'Hora inválida para esta lotería'}),400

        if fi:
            try:
                fecha = datetime.strptime(fi,"%Y-%m-%d").strftime("%d/%m/%Y")
            except:
                fecha = ahora_peru().strftime("%d/%m/%Y")
        else:
            fecha = ahora_peru().strftime("%d/%m/%Y")

        with get_db() as db:
            ya_salio = db.execute(
                "SELECT hora FROM resultados WHERE fecha=%s AND animal=%s AND hora!=%s AND loteria=%s",
                (fecha, animal, hora, loteria)
            ).fetchone()
            if ya_salio:
                nombre_animal = ANIMALES[animal]
                lot_label = 'PLUS' if loteria=='plus' else 'PERU'
                return jsonify({
                    'error': f'⚠️ El animal {animal}-{nombre_animal} ya salió hoy en {lot_label} en el sorteo de {ya_salio["hora"]}. '
                             f'Un animal no puede repetirse el mismo día.'
                }), 400

            db.execute("""
                INSERT INTO resultados (fecha,hora,animal,loteria) VALUES (%s,%s,%s,%s)
                ON CONFLICT(fecha,hora,loteria) DO UPDATE SET animal=EXCLUDED.animal
            """,(fecha, hora, animal, loteria))
            db.commit()

        lot_label = 'PLUS' if loteria=='plus' else 'PERU'
        log_audit('RESULTADO', f"Loteria:{lot_label} Fecha:{fecha} Hora:{hora} Animal:{animal} ({ANIMALES[animal]})")
        return jsonify({
            'status':'ok',
            'mensaje':f'[{lot_label}] {hora} = {animal} ({ANIMALES[animal]})',
            'fecha':fecha
        })
    except Exception as e:
        return jsonify({'error':str(e)}),500





@app.route('/api/resultados-fecha-admin', methods=['POST'])
@admin_required
def resultados_fecha_admin():
    data = request.get_json() or {}
    fs = data.get('fecha')
    loteria = data.get('loteria', 'peru')
    horarios = HORARIOS_PLUS if loteria == 'plus' else HORARIOS_PERU
    try:
        fecha_str = datetime.strptime(fs,"%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        fecha_str = ahora_peru().strftime("%d/%m/%Y")

    with get_db() as db:
        rows = db.execute("SELECT hora,animal FROM resultados WHERE fecha=%s AND loteria=%s",(fecha_str, loteria)).fetchall()

    rd={r['hora']:{'animal':r['animal'],'nombre':ANIMALES.get(r['animal'],'?')} for r in rows}
    for h in horarios:
        if h not in rd: rd[h]=None

    return jsonify({'status':'ok','fecha_consulta':fecha_str,'resultados':rd})

@app.route('/admin/lista-agencias')
@admin_required
def lista_agencias():
    with get_db() as db:
        rows = db.execute("SELECT id,usuario,nombre_agencia,nombre_banco,comision,activa,tope_taquilla FROM agencias WHERE es_admin=0").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/admin/crear-agencia', methods=['POST'])
@admin_required
def crear_agencia():
    try:
        u = request.form.get('usuario','').strip().lower()
        p = request.form.get('password','').strip()
        n = request.form.get('nombre','').strip()
        nb = request.form.get('nombre_banco','').strip()
        
        if not u or not p or not n: 
            return jsonify({'error':'Complete todos los campos'}),400
        
        with get_db() as db:
            ex = db.execute("SELECT id FROM agencias WHERE usuario=%s",(u,)).fetchone()
            if ex: 
                return jsonify({'error':'Usuario ya existe'}),400
            db.execute("""
                INSERT INTO agencias (usuario,password,nombre_agencia,nombre_banco,es_admin,comision,activa) 
                VALUES (%s,%s,%s,%s,0,%s,1)
            """,(u,p,n,nb,COMISION_AGENCIA))
            db.commit()
        
        return jsonify({'status':'ok','mensaje':f'Agencia {n} creada'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/editar-agencia', methods=['POST'])
@admin_required
def editar_agencia():
    try:
        data = request.get_json() or {}
        aid = data.get('id')
        
        with get_db() as db:
            if 'nombre_banco' in data:
                db.execute("UPDATE agencias SET nombre_banco=%s WHERE id=%s AND es_admin=0",(data['nombre_banco'],aid))
            if 'password' in data and data['password']:
                db.execute("UPDATE agencias SET password=%s WHERE id=%s AND es_admin=0",(data['password'],aid))
            if 'comision' in data:
                db.execute("UPDATE agencias SET comision=%s WHERE id=%s AND es_admin=0",(float(data['comision'])/100,aid))
            if 'activa' in data:
                db.execute("UPDATE agencias SET activa=%s WHERE id=%s AND es_admin=0",(1 if data['activa'] else 0,aid))
            if 'tope_taquilla' in data:
                db.execute("UPDATE agencias SET tope_taquilla=%s WHERE id=%s AND es_admin=0",(float(data['tope_taquilla']),aid))
            db.commit()
        
        log_audit('EDITAR_AGENCIA', f"Agencia id:{aid} modificada")
        return jsonify({'status':'ok'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/eliminar-agencia', methods=['POST'])
@admin_required
def eliminar_agencia():
    try:
        data = request.get_json() or {}
        aid = data.get('id')
        if not aid:
            return jsonify({'error': 'ID requerido'}), 400
        with get_db() as db:
            ag = db.execute("SELECT id, nombre_agencia, es_admin FROM agencias WHERE id=%s", (aid,)).fetchone()
            if not ag:
                return jsonify({'error': 'Agencia no encontrada'}), 404
            if ag['es_admin']:
                return jsonify({'error': 'No se puede eliminar al administrador'}), 403
            # Verificar si tiene tickets activos (no anulados)
            tickets_activos = db.execute(
                "SELECT COUNT(*) as cnt FROM tickets WHERE agencia_id=%s AND anulado=0", (aid,)
            ).fetchone()['cnt']
            if tickets_activos > 0:
                return jsonify({'error': f'La agencia tiene {tickets_activos} ticket(s) activo(s). Anúlelos antes de eliminar.'}), 400
            nombre = ag['nombre_agencia']
            db.execute("DELETE FROM agencias WHERE id=%s AND es_admin=0", (aid,))
            db.commit()
        log_audit('ELIMINAR_AGENCIA', f"Agencia id:{aid} '{nombre}' eliminada")
        return jsonify({'status': 'ok', 'mensaje': f'Agencia {nombre} eliminada correctamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---- TOPES ----
@app.route('/admin/topes', methods=['GET'])
@admin_required
def get_topes():
    try:
        loteria = request.args.get('loteria', 'peru')
        horarios = HORARIOS_PLUS if loteria == 'plus' else HORARIOS_PERU
        hora = request.args.get('hora', horarios[0])
        hoy = ahora_peru().strftime("%d/%m/%Y")
        with get_db() as db:
            topes_rows = db.execute(
                "SELECT numero, monto_tope FROM topes WHERE hora=%s AND loteria=%s ORDER BY CAST(numero AS INTEGER) ASC",
                (hora, loteria)
            ).fetchall()
            jugadas_rows = db.execute("""
                SELECT jg.seleccion, COALESCE(SUM(jg.monto),0) as apostado
                FROM jugadas jg
                JOIN tickets tk ON jg.ticket_id=tk.id
                WHERE jg.hora=%s AND jg.tipo='animal' AND jg.loteria=%s AND tk.anulado=0 AND tk.fecha LIKE %s
                GROUP BY jg.seleccion
                ORDER BY CAST(jg.seleccion AS INTEGER) ASC
            """, (hora, loteria, hoy+'%')).fetchall()
        apostado_map = {r['seleccion']: r['apostado'] for r in jugadas_rows}
        topes_map = {r['numero']: r['monto_tope'] for r in topes_rows}
        numeros = sorted(set(list(topes_map.keys()) + list(apostado_map.keys())), key=lambda x: int(x) if x.isdigit() else -1)
        result = []
        for num in numeros:
            result.append({
                'numero': num,
                'nombre': ANIMALES.get(num, '?'),
                'tope': topes_map.get(num, 0),
                'apostado': round(apostado_map.get(num, 0), 2),
                'disponible': round(max(0, topes_map.get(num, 0) - apostado_map.get(num, 0)), 2) if num in topes_map else None,
                'libre': num not in topes_map
            })
        return jsonify({'status':'ok','topes':result,'hora':hora,'loteria':loteria})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/topes/guardar', methods=['POST'])
@admin_required
def guardar_tope():
    try:
        data = request.get_json() or {}
        hora = data.get('hora')
        numero = str(data.get('numero',''))
        monto = float(data.get('monto', 0))
        loteria = data.get('loteria', 'peru')
        horarios_validos = HORARIOS_PLUS if loteria == 'plus' else HORARIOS_PERU
        if hora not in horarios_validos:
            return jsonify({'error':'Hora inválida'}),400
        if numero not in ANIMALES:
            return jsonify({'error':'Número inválido'}),400
        with get_db() as db:
            if monto <= 0:
                db.execute("DELETE FROM topes WHERE hora=%s AND numero=%s AND loteria=%s", (hora, numero, loteria))
                log_audit('TOPE_LIBRE', f"Hora:{hora} Num:{numero} Lot:{loteria} puesto en libre")
            else:
                db.execute("""
                    INSERT INTO topes (hora, numero, monto_tope, loteria) VALUES (%s,%s,%s,%s)
                    ON CONFLICT(hora,numero,loteria) DO UPDATE SET monto_tope=EXCLUDED.monto_tope
                """, (hora, numero, monto, loteria))
                log_audit('TOPE_SET', f"Hora:{hora} Num:{numero}-{ANIMALES[numero]} Lot:{loteria} Tope:S/{monto}")
            db.commit()
        return jsonify({'status':'ok'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/topes/limpiar', methods=['POST'])
@admin_required
def limpiar_topes():
    try:
        data = request.get_json() or {}
        hora = data.get('hora')
        loteria = data.get('loteria', 'peru')
        horarios_validos = HORARIOS_PLUS if loteria == 'plus' else HORARIOS_PERU
        if hora not in horarios_validos:
            return jsonify({'error':'Hora inválida'}),400
        with get_db() as db:
            db.execute("DELETE FROM topes WHERE hora=%s AND loteria=%s", (hora, loteria))
            db.commit()
        log_audit('TOPES_LIMPIAR', f"Todos los topes de {hora} ({loteria}) eliminados")
        return jsonify({'status':'ok','mensaje':f'Topes de {hora} ({loteria}) eliminados'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ---- RIESGO MEJORADO ----
@app.route('/admin/riesgo')
@admin_required
def riesgo():
    try:
        hoy = ahora_peru().strftime("%d/%m/%Y")
        loteria = request.args.get('loteria', 'peru')
        horarios = HORARIOS_PLUS if loteria == 'plus' else HORARIOS_PERU
        now = ahora_venezuela() if loteria == 'plus' else ahora_peru()
        am  = now.hour*60+now.minute

        hora_param = request.args.get('hora', '').strip()
        if hora_param and hora_param in horarios:
            sorteo = hora_param
        else:
            sorteo = None
            for h in horarios:
                m = hora_a_min(h)
                if am >= m-MINUTOS_BLOQUEO and am < m+60:
                    sorteo = h; break
            if not sorteo:
                for h in horarios:
                    if (hora_a_min(h)-am) > MINUTOS_BLOQUEO:
                        sorteo = h; break
            if not sorteo:
                sorteo = horarios[-1]

        with get_db() as db:
            agencias_hora = db.execute("""
                SELECT DISTINCT ag.id, ag.nombre_agencia, ag.usuario
                FROM agencias ag
                JOIN tickets tk ON ag.id=tk.agencia_id
                JOIN jugadas jg ON tk.id=jg.ticket_id
                WHERE jg.hora=%s AND jg.loteria=%s AND tk.anulado=0 AND tk.fecha LIKE %s
                ORDER BY ag.nombre_agencia
            """, (sorteo, loteria, hoy+'%')).fetchall()

            jugadas_rows = db.execute("""
                SELECT jg.seleccion, COALESCE(SUM(jg.monto),0) as apostado
                FROM jugadas jg
                JOIN tickets tk ON jg.ticket_id=tk.id
                WHERE jg.hora=%s AND jg.tipo='animal' AND jg.loteria=%s AND tk.anulado=0 AND tk.fecha LIKE %s
                GROUP BY jg.seleccion
                ORDER BY CAST(jg.seleccion AS INTEGER) ASC
            """, (sorteo, loteria, hoy+'%')).fetchall()

            topes_rows = db.execute("SELECT numero, monto_tope FROM topes WHERE hora=%s AND loteria=%s", (sorteo, loteria)).fetchall()
            topes_map = {r['numero']: r['monto_tope'] for r in topes_rows}

        total = sum(r['apostado'] for r in jugadas_rows)
        riesgo_d = {}
        for r in jugadas_rows:
            sel = r['seleccion']
            monto = r['apostado']
            mult = PAGO_LECHUZA if sel=="40" else PAGO_ANIMAL_NORMAL
            riesgo_d[sel] = {
                'nombre': ANIMALES.get(sel, sel),
                'apostado': round(monto, 2),
                'pagaria': round(monto*mult, 2),
                'es_lechuza': sel=="40",
                'porcentaje': round(monto/total*100, 1) if total>0 else 0,
                'tope': topes_map.get(sel, 0),
                'libre': sel not in topes_map
            }

        return jsonify({
            'riesgo': riesgo_d,
            'sorteo_objetivo': sorteo,
            'total_apostado': round(total, 2),
            'minutos_cierre': MINUTOS_BLOQUEO,
            'agencias_hora': [dict(a) for a in agencias_hora],
            'hora_seleccionada': sorteo,
            'loteria': loteria
        })
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/riesgo-agencia', methods=['POST'])
@admin_required
def riesgo_agencia():
    """Detalle de jugadas de una agencia específica para una hora"""
    try:
        data = request.get_json() or {}
        agencia_id = data.get('agencia_id')
        hora = data.get('hora')
        if not agencia_id or not hora:
            return jsonify({'error':'Parámetros requeridos'}),400
        hoy = ahora_peru().strftime("%d/%m/%Y")
        with get_db() as db:
            jugadas = db.execute("""
                SELECT jg.seleccion, jg.tipo, COALESCE(SUM(jg.monto),0) as apostado, COUNT(*) as cnt
                FROM jugadas jg
                JOIN tickets tk ON jg.ticket_id=tk.id
                WHERE tk.agencia_id=%s AND jg.hora=%s AND tk.anulado=0 AND tk.fecha LIKE %s
                GROUP BY jg.seleccion, jg.tipo
                ORDER BY CAST(jg.seleccion AS INTEGER) ASC
            """, (agencia_id, hora, hoy+'%')).fetchall()
            ag = db.execute("SELECT nombre_agencia FROM agencias WHERE id=%s", (agencia_id,)).fetchone()
        result = []
        for j in jugadas:
            mult = PAGO_LECHUZA if j['seleccion']=="40" else PAGO_ANIMAL_NORMAL
            nombre = ANIMALES.get(j['seleccion'], j['seleccion']) if j['tipo']=='animal' else j['seleccion']
            result.append({
                'seleccion': j['seleccion'],
                'nombre': nombre,
                'tipo': j['tipo'],
                'apostado': round(j['apostado'], 2),
                'pagaria': round(j['apostado']*mult, 2) if j['tipo']=='animal' else 0,
                'tickets': j['cnt']
            })
        return jsonify({'status':'ok','jugadas':result,'agencia':ag['nombre_agencia'] if ag else '?','hora':hora})
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ---- REPORTE AGENCIA POR HORA ----
@app.route('/admin/reporte-agencia-horas', methods=['POST'])
@admin_required
def reporte_agencia_horas():
    """Ventas de una agencia desglosadas por hora de sorteo en un rango de fechas"""
    try:
        data = request.get_json() or {}
        agencia_id = data.get('agencia_id')
        fi = data.get('fecha_inicio')
        ff = data.get('fecha_fin')
        if not agencia_id or not fi or not ff:
            return jsonify({'error':'Parámetros requeridos'}),400
        dti = datetime.strptime(fi, "%Y-%m-%d")
        dtf = datetime.strptime(ff, "%Y-%m-%d").replace(hour=23, minute=59)
        with get_db() as db:
            ag = db.execute("SELECT nombre_agencia, usuario FROM agencias WHERE id=%s", (agencia_id,)).fetchone()
            jugadas_rows = db.execute("""
                SELECT jg.hora, jg.seleccion, jg.tipo, jg.monto,
                       tk.fecha, tk.serial
                FROM jugadas jg
                JOIN tickets tk ON jg.ticket_id=tk.id
                WHERE tk.agencia_id=%s AND tk.anulado=0
                ORDER BY tk.fecha DESC
            """, (agencia_id,)).fetchall()
        # Group by hour
        por_hora = {}
        for j in jugadas_rows:
            dt = parse_fecha(j['fecha'])
            if not dt or dt<dti or dt>dtf: continue
            h = j['hora']
            if h not in por_hora:
                por_hora[h] = {'hora': h, 'total': 0, 'jugadas': [], 'conteo': 0}
            nombre = ANIMALES.get(j['seleccion'], j['seleccion']) if j['tipo']=='animal' else j['seleccion']
            por_hora[h]['total'] = round(por_hora[h]['total'] + j['monto'], 2)
            por_hora[h]['conteo'] += 1
            # Group seleccion within hour
            found = next((x for x in por_hora[h]['jugadas'] if x['seleccion']==j['seleccion'] and x['tipo']==j['tipo']), None)
            if found:
                found['apostado'] = round(found['apostado'] + j['monto'], 2)
                found['cnt'] += 1
            else:
                por_hora[h]['jugadas'].append({'seleccion':j['seleccion'],'nombre':nombre,'tipo':j['tipo'],'apostado':round(j['monto'],2),'cnt':1})
        # Sort hours by schedule order
        resumen = []
        for h in HORARIOS_PERU:
            if h in por_hora:
                entry = por_hora[h]
                entry['jugadas'].sort(key=lambda x: int(x['seleccion']) if x['seleccion'].isdigit() else -1)
                resumen.append(entry)
        return jsonify({
            'status':'ok',
            'agencia': ag['nombre_agencia'] if ag else '?',
            'usuario': ag['usuario'] if ag else '?',
            'resumen': resumen,
            'total_general': round(sum(x['total'] for x in resumen), 2)
        })
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ---- AUDIT LOGS ----
@app.route('/admin/audit-logs', methods=['POST'])
@admin_required
def get_audit_logs():
    try:
        data = request.get_json() or {}
        fi = data.get('fecha_inicio')
        ff = data.get('fecha_fin')
        filtro = data.get('filtro', '')
        limit = int(data.get('limit', 200))
        with get_db() as db:
            rows = db.execute("""
                SELECT al.*, ag.nombre_agencia
                FROM audit_logs al
                LEFT JOIN agencias ag ON al.agencia_id=ag.id
                ORDER BY al.id DESC LIMIT %s
            """, (limit,)).fetchall()
        result = []
        for r in rows:
            dt_str = r['creado']
            if fi and dt_str[:10] < fi: continue
            if ff and dt_str[:10] > ff: continue
            if filtro and filtro.lower() not in (r['accion']+r['usuario']+str(r['detalle'] or '')).lower(): continue
            result.append({
                'id': r['id'],
                'fecha': r['creado'],
                'agencia': r['nombre_agencia'] or r['usuario'] or '?',
                'accion': r['accion'],
                'detalle': r['detalle'] or '',
                'ip': r['ip'] or ''
            })
        return jsonify({'status':'ok','logs':result,'total':len(result)})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/reporte-agencias')
@admin_required
def reporte_agencias():
    try:
        hoy = ahora_peru().strftime("%d/%m/%Y")
        with get_db() as db:
            ags = db.execute("SELECT * FROM agencias WHERE es_admin=0").fetchall()
            tickets = db.execute("SELECT * FROM tickets WHERE anulado=0 AND fecha LIKE %s",(hoy+'%',)).fetchall()
        
        data=[]; tv=tp=tc=0
        for ag in ags:
            mts=[t for t in tickets if t['agencia_id']==ag['id']]
            ventas=sum(t['total'] for t in mts); pp=0
            for t in mts:
                with get_db() as db2: 
                    p=calcular_premio_ticket(t['id'],db2)
                if t['pagado']: 
                    pp+=p
            com=ventas*ag['comision']
            data.append({
                'nombre':ag['nombre_agencia'],
                'usuario':ag['usuario'],
                'ventas':round(ventas,2),
                'premios_pagados':round(pp,2),
                'comision':round(com,2),
                'balance':round(ventas-pp-com,2),
                'tickets':len(mts)
            })
            tv+=ventas; tp+=pp; tc+=com
        
        return jsonify({
            'agencias':data,
            'global':{
                'ventas':round(tv,2),
                'pagos':round(tp,2),
                'comisiones':round(tc,2),
                'balance':round(tv-tp-tc,2)
            }
        })
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/tripletas-hoy')
@admin_required
def tripletas_hoy():
    try:
        hoy=ahora_peru().strftime("%d/%m/%Y")
        with get_db() as db:
            trips=db.execute("""
                SELECT tr.*,tk.serial,tk.agencia_id,tk.fecha as fecha_ticket
                FROM tripletas tr 
                JOIN tickets tk ON tr.ticket_id=tk.id 
                WHERE tr.fecha=%s
            """,(hoy,)).fetchall()
            res_rows_peru=db.execute("SELECT hora,animal FROM resultados WHERE fecha=%s AND loteria='peru'",(hoy,)).fetchall()
            res_rows_plus=db.execute("SELECT hora,animal FROM resultados WHERE fecha=%s AND loteria='plus'",(hoy,)).fetchall()
            res_dia_peru={r['hora']:r['animal'] for r in res_rows_peru}
            res_dia_plus={r['hora']:r['animal'] for r in res_rows_plus}
            ags={ag['id']:ag['nombre_agencia'] for ag in db.execute("SELECT id,nombre_agencia FROM agencias").fetchall()}
        
        out=[]; ganadoras=0
        for tr in trips:
            lot_tr = tr['loteria'] if 'loteria' in tr.keys() else 'peru'
            res_dia = res_dia_plus if lot_tr == 'plus' else res_dia_peru
            nums={tr['animal1'],tr['animal2'],tr['animal3']}
            fecha_compra_dt = parse_fecha(tr['fecha_ticket'])
            # Hora desde la que cuentan los sorteos para esta tripleta
            hora_compra_str = fecha_compra_dt.strftime("%I:%M %p").lstrip('0') if fecha_compra_dt else '?'
            res_validos = resultados_validos_para_tripleta(res_dia, fecha_compra_dt)
            salidos=list(dict.fromkeys([a for a in res_validos.values() if a in nums]))
            # Todos los números que ya salieron en el día para esta lotería (para mostrar contexto)
            todos_salidos = list(dict.fromkeys(res_dia.values()))
            gano=len(salidos)==3
            if gano: 
                ganadoras+=1
            out.append({
                'id':tr['id'],
                'serial':tr['serial'],
                'agencia':ags.get(tr['agencia_id'],'?'),
                'animal1':tr['animal1'],'animal2':tr['animal2'],'animal3':tr['animal3'],
                'nombres':[ANIMALES.get(tr['animal1'],''),ANIMALES.get(tr['animal2'],''),ANIMALES.get(tr['animal3'],'')],
                'monto':tr['monto'],
                'premio':tr['monto']*PAGO_TRIPLETA if gano else 0,
                'gano':gano,
                'salieron':salidos,
                'pagado':bool(tr['pagado']),
                'loteria':lot_tr,
                'hora_compra': hora_compra_str,
                'fecha_compra': tr['fecha_ticket'],
                'sorteos_validos': len(res_validos),
                'sorteos_totales': len(res_dia)
            })
        
        return jsonify({
            'tripletas':out,
            'total':len(out),
            'ganadoras':ganadoras,
            'total_premios':sum(x['premio'] for x in out)
        })
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/exportar-csv', methods=['POST'])
@admin_required
def exportar_csv():
    try:
        data=request.get_json(); 
        fi=data.get('fecha_inicio'); 
        ff=data.get('fecha_fin')
        dti=datetime.strptime(fi,"%Y-%m-%d")
        dtf=datetime.strptime(ff,"%Y-%m-%d").replace(hour=23,minute=59)
        
        with get_db() as db:
            ags=db.execute("SELECT * FROM agencias WHERE es_admin=0").fetchall()
            all_t=db.execute("SELECT * FROM tickets WHERE anulado=0 ORDER BY id DESC LIMIT 50000").fetchall()
        
        stats={ag['id']:{
            'nombre':ag['nombre_agencia'],
            'usuario':ag['usuario'],
            'tickets':0,
            'ventas':0,
            'premios':0,
            'comision_pct':ag['comision']
        } for ag in ags}
        
        for t in all_t:
            dt=parse_fecha(t['fecha'])
            if not dt or dt<dti or dt>dtf: continue
            aid=t['agencia_id']
            if aid not in stats: continue
            stats[aid]['tickets']+=1
            stats[aid]['ventas']+=t['total']
            if t['pagado']:
                with get_db() as db2: 
                    stats[aid]['premios']+=calcular_premio_ticket(t['id'],db2)
        
        out=io.StringIO(); 
        w=csv.writer(out)
        w.writerow(['REPORTE ZOOLO CASINO'])
        w.writerow([f'Periodo: {fi} al {ff}'])
        w.writerow([])
        w.writerow(['Agencia','Usuario','Tickets','Ventas','Premios','Comision','Balance'])
        
        tv=0
        for s in sorted(stats.values(),key=lambda x:x['ventas'],reverse=True):
            if s['tickets']==0: continue
            com=s['ventas']*s['comision_pct']
            w.writerow([
                s['nombre'],
                s['usuario'],
                s['tickets'],
                round(s['ventas'],2),
                round(s['premios'],2),
                round(com,2),
                round(s['ventas']-s['premios']-com,2)
            ])
            tv+=s['ventas']
        
        w.writerow([])
        w.writerow(['TOTAL','',sum(s['tickets'] for s in stats.values()),round(tv,2),'','',''])
        out.seek(0)
        
        return Response(
            out.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition':f'attachment; filename=reporte_{fi}_{ff}.csv'}
        )
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/estadisticas-rango', methods=['POST'])
@admin_required
def estadisticas_rango():
    try:
        data=request.get_json()
        fi=data.get('fecha_inicio')
        ff=data.get('fecha_fin')
        if not fi or not ff: 
            return jsonify({'error':'Fechas requeridas'}),400
        
        dti=datetime.strptime(fi,"%Y-%m-%d")
        dtf=datetime.strptime(ff,"%Y-%m-%d").replace(hour=23,minute=59)
        
        with get_db() as db:
            all_t=db.execute("SELECT * FROM tickets WHERE anulado=0 ORDER BY id DESC LIMIT 10000").fetchall()
        
        dias={}; total_v=total_p=total_t=0
        for t in all_t:
            dt=parse_fecha(t['fecha'])
            if not dt or dt<dti or dt>dtf: continue
            dk=dt.strftime("%d/%m/%Y")
            if dk not in dias: 
                dias[dk]={'ventas':0,'tickets':0,'ids':[]}
            dias[dk]['ventas']+=t['total']
            dias[dk]['tickets']+=1
            dias[dk]['ids'].append(t['id'])
            total_v+=t['total']
            total_t+=1
        
        resumen=[]
        total_p=0
        for dk in sorted(dias.keys()):
            d=dias[dk]
            prem=0
            for tid in d['ids']:
                with get_db() as db2: 
                    prem+=calcular_premio_ticket(tid,db2)
            total_p+=prem
            cd=d['ventas']*COMISION_AGENCIA
            resumen.append({
                'fecha':dk,
                'ventas':round(d['ventas'],2),
                'premios':round(prem,2),
                'comisiones':round(cd,2),
                'balance':round(d['ventas']-prem-cd,2),
                'tickets':d['tickets']
            })
        
        tc=total_v*COMISION_AGENCIA
        return jsonify({
            'resumen_por_dia':resumen,
            'totales':{
                'ventas':round(total_v,2),
                'premios':round(total_p,2),
                'comisiones':round(tc,2),
                'balance':round(total_v-total_p-tc,2),
                'tickets':total_t
            }
        })
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/reporte-agencias-rango', methods=['POST'])
@admin_required
def reporte_agencias_rango():
    try:
        data=request.get_json()
        fi=data.get('fecha_inicio')
        ff=data.get('fecha_fin')
        if not fi or not ff: 
            return jsonify({'error':'Fechas requeridas'}),400
        
        dti=datetime.strptime(fi,"%Y-%m-%d")
        dtf=datetime.strptime(ff,"%Y-%m-%d").replace(hour=23,minute=59)
        
        with get_db() as db:
            ags=db.execute("SELECT * FROM agencias WHERE es_admin=0").fetchall()
            all_t=db.execute("SELECT * FROM tickets WHERE anulado=0 ORDER BY id DESC LIMIT 50000").fetchall()
        
        stats={ag['id']:{
            'nombre':ag['nombre_agencia'],
            'usuario':ag['usuario'],
            'tickets':0,
            'ventas':0,
            'premios_teoricos':0,
            'comision_pct':ag['comision']
        } for ag in ags}
        
        for t in all_t:
            dt=parse_fecha(t['fecha'])
            if not dt or dt<dti or dt>dtf: continue
            aid=t['agencia_id']
            if aid not in stats: continue
            stats[aid]['tickets']+=1
            stats[aid]['ventas']+=t['total']
            with get_db() as db2: 
                p=calcular_premio_ticket(t['id'],db2)
            stats[aid]['premios_teoricos']+=p
        
        out=[]
        for s in stats.values():
            if s['tickets']==0: continue
            com=s['ventas']*s['comision_pct']
            s['comision']=round(com,2)
            s['balance']=round(s['ventas']-s['premios_teoricos']-com,2)
            s['ventas']=round(s['ventas'],2)
            s['premios_teoricos']=round(s['premios_teoricos'],2)
            out.append(s)
        
        out.sort(key=lambda x:x['ventas'],reverse=True)
        tv=sum(x['ventas'] for x in out)
        
        if tv>0:
            for x in out: 
                x['porcentaje_ventas']=round(x['ventas']/tv*100,1)
        
        total={
            'tickets':sum(x['tickets'] for x in out),
            'ventas':round(tv,2),
            'premios':round(sum(x['premios_teoricos'] for x in out),2),
            'comision':round(sum(x['comision'] for x in out),2),
            'balance':round(sum(x['balance'] for x in out),2)
        }
        
        return jsonify({
            'agencias':out,
            'total':total,
            'periodo':{'inicio':fi,'fin':ff}
        })
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ===================== HTML =====================

LOGIN_HTML = '''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ZOOLO CASINO</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;700&family=Rajdhani:wght@500;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#050a12;min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:'Rajdhani',sans-serif}
.box{background:#0a1020;padding:44px 36px;border-radius:8px;border:1px solid #1e3060;width:100%;max-width:400px;text-align:center;box-shadow:0 0 60px rgba(0,80,200,.1)}
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

POS_HTML = r'''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1,user-scalable=no">
<title>{{agencia}} — POS</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;600;700&family=Rajdhani:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#f0f4f8;--panel:#ffffff;--card:#f8fafc;--border:#e2e8f0;
  --gold:#c47b00;--blue:#1d4ed8;--teal:#0284c7;
  --red:#dc2626;--red-bg:#fef2f2;--red-border:#fca5a5;
  --negro:#1e3a5f;--negro-bg:#eff6ff;--negro-border:#bfdbfe;
  --verde:#166534;--verde-bg:#f0fdf4;--verde-border:#bbf7d0;
  --green:#16a34a;--orange:#ea580c;--purple:#7c3aed;
  --text:#1e293b;--text2:#64748b;
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent;user-select:none}
html,body{height:100%;overflow:hidden}
body{background:var(--bg);color:var(--text);font-family:'Rajdhani',sans-serif;font-size:14px;display:flex;flex-direction:column}

/* TOPBAR */
.topbar{background:#1e293b;border-bottom:3px solid #f5a623;padding:0 10px;height:36px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.brand{font-family:'Oswald',sans-serif;font-size:1rem;font-weight:700;letter-spacing:2px;color:#fff}
.brand em{color:var(--gold);font-style:normal}
.agent-name{color:#8ab0e0;font-size:.78rem;letter-spacing:1px;margin-left:10px}
.top-right{display:flex;align-items:center;gap:5px}
.clock{color:#f5a623;font-family:'Oswald',sans-serif;font-size:.8rem;background:#334155;padding:2px 6px;border-radius:3px;border:1px solid #475569;white-space:nowrap}
.tbtn{padding:4px 8px;border:none;background:#334155;color:#e2e8f0;border-radius:3px;cursor:pointer;font-size:.68rem;font-family:'Oswald',sans-serif;font-weight:700;letter-spacing:1px;white-space:nowrap}
.tbtn:hover{background:#475569;color:#fff}
.tbtn.exit{background:#991b1b;color:#fff}
.tbtn.exit:hover{background:#b91c1c}

/* LAYOUT */
.layout{display:flex;flex:1;overflow:hidden;gap:0;min-height:0}

/* PANEL IZQUIERDO — ANIMALES */
.left-panel{display:flex;flex-direction:column;width:55%;border-right:2px solid var(--border);overflow:hidden;background:#ffffff;min-height:0}

/* ESPECIALES */
.especiales-bar{display:flex;gap:4px;padding:5px 6px;background:#f1f5f9;border-bottom:2px solid var(--border);flex-shrink:0}
.esp-btn{flex:1;padding:9px 4px;text-align:center;border-radius:4px;cursor:pointer;font-family:'Oswald',sans-serif;font-size:.82rem;font-weight:700;letter-spacing:1px;border:2px solid transparent;transition:all .15s}
.esp-btn.rojo{background:#cc1a1a;border-color:#ff2a2a;color:#fff}
.esp-btn.rojo.sel{background:#ff1a1a;border-color:#ff6060;box-shadow:0 0 12px rgba(255,40,40,.5)}
.esp-btn.rojo:hover{background:#e02020;border-color:#ff4040}
.esp-btn.negro{background:#1a2a5a;border-color:#2a4090;color:#c0d8ff}
.esp-btn.negro.sel{background:#2a3a80;border-color:#4060d0;box-shadow:0 0 12px rgba(60,100,240,.5)}
.esp-btn.negro:hover{background:#223070;border-color:#3050c0}
.esp-btn.par{background:#0a7a90;border-color:#00c4d8;color:#fff}
.esp-btn.par.sel{background:#00a0c0;border-color:#00e8ff;box-shadow:0 0 12px rgba(0,200,220,.5)}
.esp-btn.par:hover{background:#0a8aa0;border-color:#00d0e8}
.esp-btn.impar{background:#6a20a0;border-color:#9a40d0;color:#fff}
.esp-btn.impar.sel{background:#8030c0;border-color:#c060ff;box-shadow:0 0 12px rgba(160,80,240,.5)}
.esp-btn.impar:hover{background:#7a28b0;border-color:#b050e8}

/* JUGADA MANUAL */
.manual-box{padding:6px;background:#f1f5f9;border-bottom:2px solid #e2e8f0}
.manual-input{width:100%;padding:8px;background:#fff;border:2px solid #0284c7;border-radius:4px;color:#c47b00;font-family:'Oswald',sans-serif;font-size:1rem;letter-spacing:1px;text-transform:uppercase}
.manual-input:focus{outline:none;border-color:#7c3aed}
.manual-label{color:#64748b;font-size:.65rem;font-family:'Oswald',sans-serif;letter-spacing:1px;margin-bottom:4px;display:flex;justify-content:space-between}
.manual-label span{color:#f5a623}

/* GRID ANIMALES */
.animals-scroll{flex:1;overflow-y:auto;padding:4px 5px;min-height:0}
.animals-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px}

/* CELDA ANIMAL */
.acard{border-radius:5px;padding:8px 3px;text-align:center;cursor:pointer;transition:all .12s;border:2px solid transparent;position:relative;min-height:54px;display:flex;flex-direction:column;align-items:center;justify-content:center}
.acard:active{transform:scale(.95)}
.acard.cv{background:#166534;border-color:#166534}
.acard.cv .anum{color:#ffffff}.acard.cv .anom{color:#f0fff0}
.acard.cv:hover{background:#15803d;border-color:#15803d}
.acard.cv.sel{box-shadow:0 0 8px rgba(2,132,199,.4);transform:scale(1.05);border-color:#0284c7!important}
.acard.cr{background:#780606;border-color:#780606}
.acard.cr .anum{color:#ffffff}.acard.cr .anom{color:#fff5f5}
.acard.cr:hover{background:#991b1b;border-color:#991b1b}
.acard.cr.sel{box-shadow:0 0 8px rgba(2,132,199,.4);transform:scale(1.05);border-color:#0284c7!important}
.acard.cn{background:#000000;border-color:#000000}
.acard.cn .anum{color:#ffffff}.acard.cn .anom{color:#f8f8ff}
.acard.cn:hover{background:#1e293b;border-color:#1e293b}
.acard.cn.sel{box-shadow:0 0 8px rgba(2,132,199,.4);transform:scale(1.05);border-color:#0284c7!important}
.acard.cl{background:#fef9c3;border-color:#d97706}
.acard.cl .anum{color:#000000}.acard.cl .anom{color:#92400e}
.acard.cl:hover{background:#fef08a;border-color:#b45309}
.acard.cl.sel{box-shadow:0 0 8px rgba(2,132,199,.4);transform:scale(1.05);border-color:#0284c7!important}
.acard.sel::after{content:'✓';position:absolute;top:0;right:2px;font-size:.6rem;color:#fff;font-weight:700}
.anum{font-size:.9rem;font-weight:700;font-family:'Oswald',sans-serif;line-height:1.1}
.anom{font-size:.72rem;font-weight:600;line-height:1.2;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}

/* PANEL DERECHO */
.right-panel{width:45%;display:flex;flex-direction:column;overflow-y:auto;background:#f8fafc;padding:6px;min-height:0}

.rsec{padding:6px 8px;border-bottom:1px solid var(--border)}
.rlabel{font-family:'Oswald',sans-serif;font-size:.65rem;font-weight:600;color:#64748b;letter-spacing:2px;text-transform:uppercase;margin-bottom:4px}

/* HORARIOS */
.horas-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:3px}
.hbtn{padding:6px 2px;text-align:center;background:#f1f5f9;border:2px solid #cbd5e1;border-radius:3px;cursor:pointer;font-size:.72rem;font-family:'Oswald',sans-serif;color:#475569;transition:all .15s;line-height:1.2}
.hbtn:hover{background:#0284c7;border-color:#0284c7;color:#fff}
.hbtn.sel{background:#0284c7;border-color:#0369a1;color:#fff;font-weight:700}
.hbtn.bloq{background:#fee2e2;border-color:#fca5a5;color:#ef4444;cursor:not-allowed;opacity:.7}
.hbtn .hperu{font-size:.82rem;font-weight:700}
.hbtn .hven{font-size:.68rem;color:#94a3b8}
.hbtn.sel .hven{color:#e0f2fe}
.horas-btns-row{display:flex;gap:3px;margin-top:3px}
.hsel-btn{flex:1;padding:5px;font-size:.65rem;background:#e2e8f0;border:2px solid #cbd5e1;color:#475569;border-radius:3px;cursor:pointer;font-family:'Oswald',sans-serif;font-weight:700;text-align:center;transition:all .15s}
.hsel-btn:hover{background:#0284c7;border-color:#0284c7;color:#fff}

/* MONTO */
.monto-sec{padding:5px 8px;border-bottom:1px solid var(--border)}
.presets{display:flex;flex-wrap:wrap;gap:3px;margin-bottom:4px}
.mpre{padding:7px 10px;background:#e2e8f0;border:2px solid #cbd5e1;border-radius:3px;color:#1e293b;cursor:pointer;font-size:.82rem;font-family:'Oswald',sans-serif;font-weight:700;transition:all .15s}
.mpre:hover,.mpre:active{background:#0284c7;border-color:#0284c7;color:#fff}
.monto-input-wrap{display:flex;align-items:center;gap:4px}
.monto-label{color:#f5a623;font-size:.85rem;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:1px;white-space:nowrap}
.monto-input{flex:1;padding:9px 8px;background:#fff;border:2px solid #d97706;border-radius:3px;color:#c47b00;font-size:1.1rem;font-family:'Oswald',sans-serif;font-weight:700;text-align:center;letter-spacing:1px}
.monto-input:focus{outline:none;border-color:#f59e0b;box-shadow:0 0 8px rgba(245,158,11,.25)}

/* TICKET — ahora en panel izquierdo, abajo */
.ticket-sec{padding:4px 8px;border-top:2px solid #d97706;background:#fffbeb;display:flex;flex-direction:column;flex-shrink:0}
.ticket-list{overflow-y:auto;min-height:60px;max-height:220px;background:#fff;border:1px solid #e2e8f0;border-radius:4px;padding:4px;margin-bottom:4px}
.ti{display:flex;align-items:center;gap:3px;padding:4px;border-bottom:1px solid #f1f5f9;font-size:.7rem}
.ti-desc{flex:1;color:#1e293b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.68rem}
.ti-hora{color:#0284c7;font-size:.65rem;min-width:38px;font-family:'Oswald',sans-serif;font-weight:700}
.ti-monto{color:#16a34a;font-weight:700;font-family:'Oswald',sans-serif;min-width:30px;text-align:right;font-size:.7rem}
.ti-del{background:#dc2626;border:none;color:#fff;cursor:pointer;font-size:.55rem;padding:2px 4px;border-radius:2px}
.ti-del:hover{background:#b91c1c}
.ticket-empty{color:#94a3b8;text-align:center;padding:20px;font-size:.72rem;letter-spacing:2px}
.ticket-total{text-align:right;padding:5px 6px;font-family:'Oswald',sans-serif;color:#c47b00;font-size:.95rem;font-weight:700;border-top:2px solid #d97706;background:#fffbeb}

/* BOTONES ACCION */
.actions-sec{padding:5px 8px;display:flex;flex-direction:column;gap:3px;flex-shrink:0}
.btn-add{width:100%;padding:11px;background:#1a3a90;color:#fff;border:2px solid #4070d0;border-radius:4px;font-family:'Oswald',sans-serif;font-weight:700;font-size:.88rem;letter-spacing:2px;cursor:pointer;transition:all .15s}
.btn-add:hover{background:#2050c0;border-color:#60a0ff}
.btn-wa{width:100%;padding:11px;background:#16a34a;color:#fff;border:2px solid #22c55e;border-radius:4px;font-family:'Oswald',sans-serif;font-weight:700;font-size:.88rem;letter-spacing:2px;cursor:pointer;transition:all .15s}
.btn-wa:hover{background:#15803d}
.btn-wa:disabled{background:#dcfce7;border-color:#bbf7d0;color:#86efac;cursor:not-allowed}
.btns-row{display:grid;grid-template-columns:1fr 1fr;gap:3px}
.btns-row2{display:grid;grid-template-columns:1fr 1fr 1fr;gap:3px}
.abtn{padding:10px 4px;text-align:center;border-radius:4px;cursor:pointer;font-family:'Oswald',sans-serif;font-size:.75rem;font-weight:700;letter-spacing:1px;border:2px solid;transition:all .15s;white-space:nowrap;color:#fff}
.abtn.res{background:#006080;border-color:#00b8d8}
.abtn.res:hover{background:#0080a8;border-color:#00e0ff}
.abtn.caja{background:#166534;border-color:#22c55e}
.abtn.caja:hover{background:#15803d;border-color:#4ade80}
.abtn.pagar{background:#854d0e;border-color:#f59e0b}
.abtn.pagar:hover{background:#a16207;border-color:#fbbf24}
.abtn.trip{background:#6b21a8;border-color:#a855f7}
.abtn.trip:hover{background:#7e22ce;border-color:#c084fc}
.abtn.anular{background:#991b1b;border-color:#ef4444}
.abtn.anular:hover{background:#b91c1c;border-color:#ff6060}
.abtn.borrar{background:#7c2d12;border-color:#f97316}
.abtn.borrar:hover{background:#9a3412;border-color:#fb923c}
.abtn.rep{background:#1e40af;border-color:#3b82f6}
.abtn.rep:hover{background:#2563eb;border-color:#60a5fa}
.abtn.salir{background:#7f1d1d;border-color:#dc2626}
.abtn.salir:hover{background:#991b1b;border-color:#ef4444}

/* MODALES */
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:1000;overflow-y:auto;padding:8px;align-items:flex-start;justify-content:center}
.modal.open{display:flex}
.mc{background:#ffffff;border:2px solid #e2e8f0;border-radius:6px;width:100%;max-width:640px;margin:auto;box-shadow:0 8px 30px rgba(0,0,0,.15)}
.mh{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-bottom:2px solid #0284c7;background:#f0f9ff}
.mh h3{font-family:'Oswald',sans-serif;color:#0284c7;font-size:.85rem;letter-spacing:2px}
.mbody{padding:14px 16px}
.btn-close{background:#7f1d1d;color:#fff;border:2px solid #dc2626;border-radius:3px;padding:5px 12px;cursor:pointer;font-size:.78rem;font-family:'Oswald',sans-serif;font-weight:700;letter-spacing:1px}
.btn-close:hover{background:#991b1b}
.frow{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.frow input,.frow select{flex:1;min-width:110px;padding:8px 10px;background:#f8fafc;border:2px solid #cbd5e1;border-radius:3px;color:#1e293b;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600}
.frow input:focus,.frow select:focus{outline:none;border-color:#0284c7}
.btn-q{width:100%;padding:10px;background:#1d4ed8;color:#fff;border:2px solid #3b82f6;border-radius:3px;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:2px;cursor:pointer;margin-bottom:8px;font-size:.78rem}
.btn-q:hover{background:#2563eb}
.ri{display:flex;justify-content:space-between;align-items:center;padding:7px 10px;margin:3px 0;background:#f8fafc;border-radius:3px;border-left:3px solid #e2e8f0;font-size:.78rem}
.ri.ok{border-left-color:#16a34a;background:#f0fdf4}
.ri-hora{color:#fbbf24;font-weight:700;font-family:'Oswald',sans-serif;font-size:.82rem}
.ri-animal{color:#4ade80;font-weight:700}
.tcard{background:#f8fafc;padding:10px;margin:5px 0;border-radius:4px;border-left:3px solid #e2e8f0;font-size:.75rem;border:1px solid #e2e8f0}
.tcard.gano{border-left-color:#16a34a;background:#f0fdf4}
.tcard.pte{border-left-color:#f59e0b;background:#fffbeb}
.ts{color:#0284c7;font-weight:700;font-family:'Oswald',sans-serif}
.badge{display:inline-block;padding:2px 6px;border-radius:3px;font-size:.62rem;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:1px;color:#fff}
.badge.p{background:#16a34a;border:1px solid #22c55e}
.badge.g{background:#854d0e;border:1px solid #f59e0b}
.badge.n{background:#1e40af;border:1px solid #3b82f6}
.jrow{display:flex;justify-content:space-between;align-items:center;padding:3px 8px;margin:2px 0;border-radius:3px;background:#f1f5f9;border-left:3px solid #e2e8f0;font-size:.73rem}
.jrow.gano{background:#f0fdf4;border-left-color:#16a34a}
.trip-row{display:flex;justify-content:space-between;align-items:center;padding:5px 8px;margin:2px 0;border-radius:3px;background:#faf5ff;border-left:3px solid #7c3aed;font-size:.73rem}
.trip-row.gano{background:#060418;border-left-color:#c084fc}
.sbox{background:#f8fafc;border-radius:3px;padding:10px;margin:6px 0;border:1px solid #e2e8f0}
.srow{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #f1f5f9;font-size:.75rem}
.srow:last-child{border-bottom:none}
.sl{color:#64748b}.sv{color:#c47b00;font-weight:700;font-family:'Oswald',sans-serif}
.caja-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}
.cg{background:#f8fafc;border:2px solid #e2e8f0;border-radius:3px;padding:10px;text-align:center}
.cgl{color:#64748b;font-size:.6rem;letter-spacing:2px;margin-bottom:3px;font-family:'Oswald',sans-serif}
.cgv{color:#c47b00;font-size:1rem;font-weight:700;font-family:'Oswald',sans-serif}
.cgv.g{color:#16a34a}.cgv.r{color:#dc2626}

/* TRIPLETA MODAL */
.trip-slots{display:flex;gap:8px;margin-bottom:12px}
.tslot{flex:1;background:#faf5ff;border:2px solid #c4b5fd;border-radius:4px;padding:8px;text-align:center;cursor:pointer;min-height:46px;display:flex;flex-direction:column;align-items:center;justify-content:center;transition:all .15s}
.tslot.act{border-color:#7c3aed;box-shadow:0 0 12px rgba(124,58,237,.3);background:#ede9fe}
.tslot.fill{border-color:#7c3aed;background:#f5f3ff}
.tslot .snum{font-size:.9rem;font-weight:700;font-family:'Oswald',sans-serif;color:#7c3aed}
.tslot .snom{font-size:.58rem;color:#6d28d9}
.tslot .sph{font-size:.65rem;color:#7c3aed;letter-spacing:1px}
.trip-modal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;margin-top:12px;max-height:300px;overflow-y:auto;padding:4px}
.trip-modal-grid .acard{padding:6px 2px}

/* TOAST */
.toast{position:fixed;bottom:10px;left:50%;transform:translateX(-50%);padding:8px 18px;border-radius:4px;font-family:'Oswald',sans-serif;font-size:.78rem;letter-spacing:1px;font-weight:700;z-index:9999;display:none;max-width:90%;text-align:center}
.toast.ok{background:#16a34a;color:#fff;border:2px solid #22c55e}
.toast.err{background:#dc2626;color:#fff;border:2px solid #ef4444}

/* SCROLL */
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:#f1f5f9}
::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:2px}
::-webkit-scrollbar-thumb:hover{background:#94a3b8}

/* REPETIR MODAL */
.rep-info{background:#0a1a30;border:1px solid #1a4a80;border-radius:4px;padding:10px;margin-bottom:12px;font-size:.8rem;color:#80b0e0}
.rep-item{display:flex;align-items:center;gap:8px;padding:6px;background:#060c1a;border-radius:3px;margin-bottom:6px;border:1px solid #1a2a40}
.rep-item select{flex:1;padding:6px;background:#0a1828;border:1px solid #2a4a80;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem}
.rep-item input[type="number"]{width:80px;padding:6px;background:#0a1828;border:1px solid #d97706;color:#fbbf24;font-family:'Oswald',sans-serif;text-align:center}

/* RESPONSIVE */
@media(max-width:599px){
  html,body{overflow:auto}
  .layout{flex-direction:column}
  .left-panel{width:100%;border-right:none;border-bottom:2px solid var(--border);max-height:60vh}
  .right-panel{width:100%}
  .animals-grid{grid-template-columns:repeat(7,1fr)}
  .trip-modal-grid{grid-template-columns:repeat(7,1fr)}
  .topbar .agent-name{display:none}
}
@media(min-width:600px) and (max-width:900px){
  .animals-grid{grid-template-columns:repeat(7,1fr)}
  .trip-modal-grid{grid-template-columns:repeat(7,1fr)}
}
</style></head><body>

<!-- TOPBAR -->
<div class="topbar">
  <div style="display:flex;align-items:center">
    <div class="brand">ZOO<em>LO</em></div>
    <div class="agent-name">{{agencia}}</div>
  </div>
  <div class="top-right">
    <div class="clock" id="clock">--:--</div>
    <button class="tbtn" onclick="openMod('mod-consultas')">📋 Consultas</button>
    <button class="tbtn" onclick="openMod('mod-archivo')">📁 Archivo</button>
    <button class="tbtn exit" onclick="location.href='/logout'">SALIR</button>
  </div>
</div>

<!-- BANNER SIN CONEXIÓN -->
<div id="offline-banner" style="display:none;background:#fef2f2;border-bottom:2px solid #ef4444;padding:6px 14px;align-items:center;justify-content:center;gap:10px;flex-shrink:0">
  <span style="color:#dc2626;font-family:'Oswald',sans-serif;font-size:.82rem;letter-spacing:2px;font-weight:700">⚠️ SIN CONEXIÓN — VENTA BLOQUEADA PARA EVITAR TICKETS FANTASMA</span>
</div>

<!-- LAYOUT -->
<div class="layout">

  <!-- IZQUIERDA: ESPECIALES + MANUAL + ANIMALES -->
  <div class="left-panel">

    <!-- ESPECIALES -->
    <div class="especiales-bar">
      <div class="esp-btn rojo" id="esp-ROJO" onclick="selEsp('ROJO')">ROJO</div>
      <div class="esp-btn negro" id="esp-NEGRO" onclick="selEsp('NEGRO')">NEGRO</div>
      <div class="esp-btn par" id="esp-PAR" onclick="selEsp('PAR')">PAR</div>
      <div class="esp-btn impar" id="esp-IMPAR" onclick="selEsp('IMPAR')">IMPAR</div>
    </div>

    <!-- JUGADA MANUAL -->
    <div class="manual-box">
      <div class="manual-label">
        <span>📝 JUGADA MANUAL (pegar números)</span>
        <span style="font-size:.6rem;color:#4a6090">Ej: 2.25.36.14.11</span>
      </div>
      <div style="display:flex;gap:4px">
        <input type="text" class="manual-input" id="manual-input" placeholder="1.5.6.12 ó 5,6,8,40" style="flex:1" onpaste="handleManualPaste(event)" onkeyup="handleManualKeyup(event)">
        <button style="padding:6px 10px;background:#1a3a70;border:1px solid #2060c0;color:#80c0ff;font-size:.75rem;font-family:'Oswald',sans-serif;cursor:pointer;border-radius:3px;white-space:nowrap" onclick="confirmarManual()">✓ OK</button>
      </div>
    </div>

    <!-- GRID ANIMALES -->
    <div class="animals-scroll">
      <div class="animals-grid" id="animals-grid"></div>
    </div>

    <!-- TICKET — panel izquierdo inferior, visible siempre -->
    <div class="ticket-sec">
      <div class="rlabel" style="padding:4px 0 2px;color:#854d0e;letter-spacing:2px">🎫 TICKET EN ELABORACIÓN</div>
      <div class="ticket-list" id="ticket-list">
        <div class="ticket-empty">TICKET VACÍO</div>
      </div>
      <div id="ticket-total" style="display:none" class="ticket-total"></div>
    </div>

  </div>

  <!-- DERECHA: CONTROLES -->
  <div class="right-panel">

    <!-- HORARIOS -->
    <div class="rsec">
      <div style="display:flex;gap:4px;margin-bottom:6px">
        <button id="tab-peru" onclick="cambiarLoteria('peru')" style="flex:1;padding:7px 4px;background:#1a3a90;border:2px solid #4070d0;border-radius:4px;color:#fff;font-family:'Oswald',sans-serif;font-size:.72rem;font-weight:700;letter-spacing:1px;cursor:pointer;transition:all .15s" class="active">🇵🇪 ZOOLO PERU</button>
        <button id="tab-plus" onclick="cambiarLoteria('plus')" style="flex:1;padding:7px 4px;background:#3b0764;border:2px solid #a855f7;border-radius:4px;color:#fff;font-family:'Oswald',sans-serif;font-size:.72rem;font-weight:700;letter-spacing:1px;cursor:pointer;transition:all .15s">🎰 ZOOLO PLUS</button>
      </div>
      <div class="rlabel" id="horas-label">⏰ PERÚ — 11 Sorteos (Cierra 3 min antes (al :57))</div>
      <div class="horas-grid" id="horas-grid"></div>
      <div class="horas-btns-row">
        <button class="hsel-btn" onclick="selTodos()">☑ Todos</button>
        <button class="hsel-btn" onclick="limpiarH()">✕ Limpiar</button>
      </div>
    </div>

    <!-- MONTO -->
    <div class="monto-sec">
      <div class="presets">
        <button class="mpre" onclick="setM(.5)">0.5</button>
        <button class="mpre" onclick="setM(1)">1</button>
        <button class="mpre" onclick="setM(2)">2</button>
        <button class="mpre" onclick="setM(5)">5</button>
        <button class="mpre" onclick="setM(10)">10</button>
        <button class="mpre" onclick="setM(20)">20</button>
        <button class="mpre" onclick="setM(50)">50</button>
      </div>
      <div class="monto-input-wrap">
        <span class="monto-label">S/</span>
        <input type="number" class="monto-input" id="monto" value="1" min="0.5" step="0.5">
      </div>
    </div>

    <!-- BOTONES ACCIÓN -->
    <div class="actions-sec">
      <button class="btn-add" onclick="agregar()">➕ AGREGAR AL TICKET</button>
      <button class="btn-wa" onclick="vender()" id="btn-wa" disabled>📤 ENVIAR POR WHATSAPP</button>
      <div class="btns-row">
        <div class="abtn res" onclick="openResultados()">📊 RESULTADOS</div>
        <div class="abtn caja" onclick="openCaja()">💰 CAJA</div>
      </div>
      <div class="btns-row">
        <div class="abtn pagar" onclick="openPagar()">💵 PAGAR</div>
        <div class="abtn anular" onclick="openAnular()">❌ ANULAR</div>
      </div>
      <div class="btns-row2">
        <div class="abtn trip" onclick="openTripletaModal()">🎯 TRIPLETA</div>
        <div class="abtn rep" onclick="openRepetirModal()">🔄 REPETIR</div>
        <div class="abtn borrar" onclick="borrarTodo()">🗑 BORRAR</div>
      </div>
    </div>

  </div>
</div>

<div class="toast" id="toast"></div>

<!-- MODALES -->

<!-- REPETIR TICKET -->
<div class="modal" id="mod-repetir">
<div class="mc">
  <div class="mh">
    <h3>🔄 REPETIR TICKET</h3>
    <button class="btn-close" onclick="closeMod('mod-repetir')">✕</button>
  </div>
  <div class="mbody">
    <div class="frow">
      <input type="text" id="rep-serial" placeholder="Serial del ticket" style="flex:2">
      <button class="btn-q" onclick="cargarTicketRepetir()" style="flex:1;margin:0">CARGAR</button>
    </div>
    <div id="rep-contenido"></div>
  </div>
</div></div>

<!-- TRIPLETA -->
<div class="modal" id="mod-tripleta">
<div class="mc">
  <div class="mh" style="border-color:#7c3aed;background:linear-gradient(135deg,#1a0a30,#0c1a3a)">
    <h3 style="color:#e0d0ff;font-family:'Oswald',sans-serif;letter-spacing:2px">🎯 JUGAR TRIPLETA x60</h3>
    <button class="btn-close" onclick="closeMod('mod-tripleta')">✕</button>
  </div>
  <div class="mbody">

    <!-- SELECTOR DE LOTERÍA dentro del modal -->
    <div style="display:flex;gap:0;border:2px solid #2a3a6a;border-radius:6px;overflow:hidden;margin-bottom:14px">
      <button id="trip-tab-peru"
        onclick="selTripLoteria('peru')"
        style="flex:1;padding:10px 6px;font-family:'Oswald',sans-serif;font-size:.8rem;letter-spacing:1px;cursor:pointer;border:none;transition:all .2s;background:#0c2461;color:#90b8ff">
        🇵🇪 ZOOLO PERÚ<br><span style="font-size:.62rem;opacity:.8">11 sorteos · 8AM–6PM Lima</span>
      </button>
      <button id="trip-tab-plus"
        onclick="selTripLoteria('plus')"
        style="flex:1;padding:10px 6px;font-family:'Oswald',sans-serif;font-size:.8rem;letter-spacing:1px;cursor:pointer;border:none;transition:all .2s;background:#1a0540;color:#c084fc">
        🎰 ZOOLO PLUS<br><span style="font-size:.62rem;opacity:.8">12 sorteos · 8AM–7PM VEN</span>
      </button>
    </div>

    <div class="trip-slots">
      <div class="tslot act" id="tms0" onclick="activarSlotModal(0)"><div class="sph">ANIMAL 1</div></div>
      <div class="tslot" id="tms1" onclick="activarSlotModal(1)"><div class="sph">ANIMAL 2</div></div>
      <div class="tslot" id="tms2" onclick="activarSlotModal(2)"><div class="sph">ANIMAL 3</div></div>
    </div>
    
    <div class="trip-modal-grid" id="trip-modal-grid"></div>
    
    <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border)">
      <div style="color:var(--purple);font-size:.75rem;margin-bottom:6px;font-family:'Oswald',sans-serif;letter-spacing:1px">MONTO PARA TRIPLETA</div>
      <div class="monto-input-wrap">
        <span class="monto-label">S/</span>
        <input type="number" class="monto-input" id="monto-tripleta" value="1" min="0.5" step="0.5">
      </div>
    </div>
    
    <div style="display:flex;gap:8px;margin-top:12px">
      <button class="btn-q" id="trip-btn-agregar" style="flex:1" onclick="agregarTripletaModal()">✅ AGREGAR AL TICKET</button>
      <button class="btn-close" style="flex:1;background:#1e3050;border-color:#4080c0;color:#90c0ff" onclick="closeMod('mod-tripleta')">CANCELAR</button>
    </div>
  </div>
</div></div>

<!-- RESULTADOS -->
<div class="modal" id="mod-resultados">
<div class="mc">
  <div class="mh"><h3>📊 RESULTADOS</h3><button class="btn-close" onclick="closeMod('mod-resultados')">✕</button></div>
  <div class="mbody">
    <div class="frow"><input type="date" id="res-fecha"></div>
    <button class="btn-q" onclick="cargarResultados()">VER RESULTADOS</button>
    <div id="res-titulo" style="color:var(--teal);font-family:'Oswald',sans-serif;letter-spacing:2px;text-align:center;margin-bottom:8px;font-size:.8rem"></div>
    <div id="res-lista" style="max-height:340px;overflow-y:auto"></div>
  </div>
</div></div>

<!-- CONSULTAS -->
<div class="modal" id="mod-consultas">
<div class="mc">
  <div class="mh"><h3>📋 CONSULTAS</h3><button class="btn-close" onclick="closeMod('mod-consultas')">✕</button></div>
  <div class="mbody">
    <div class="frow">
      <input type="date" id="mt-ini">
      <input type="date" id="mt-fin">
      <select id="mt-estado">
        <option value="todos">Todos</option>
        <option value="pagados">Pagados</option>
        <option value="pendientes">Pendientes</option>
        <option value="por_pagar">Con Premio</option>
      </select>
    </div>
    <button class="btn-q" onclick="consultarTickets()">BUSCAR</button>
    <div id="mt-resumen" style="display:none;background:rgba(0,180,216,.06);border:1px solid #0a4050;border-radius:3px;padding:8px;margin-bottom:8px;color:var(--teal);font-size:.78rem;font-family:'Oswald',sans-serif;letter-spacing:1px"></div>
    <div id="mt-lista" style="max-height:400px;overflow-y:auto">
      <p style="color:var(--text2);text-align:center;padding:20px;letter-spacing:2px;font-size:.75rem">USE LOS FILTROS Y BUSQUE</p>
    </div>
  </div>
</div></div>

<!-- ARCHIVO -->
<div class="modal" id="mod-archivo">
<div class="mc">
  <div class="mh"><h3>📁 ARCHIVO — CAJA HISTÓRICO</h3><button class="btn-close" onclick="closeMod('mod-archivo')">✕</button></div>
  <div class="mbody">
    <div class="frow"><input type="date" id="ar-ini"><input type="date" id="ar-fin"></div>
    <button class="btn-q" onclick="cajaHist()">VER HISTÓRICO</button>
    <div id="ar-res"></div>
  </div>
</div></div>

<!-- BUSCAR/PAGAR -->
<div class="modal" id="mod-pagar">
<div class="mc">
  <div class="mh"><h3>💵 VERIFICAR / PAGAR</h3><button class="btn-close" onclick="closeMod('mod-pagar')">✕</button></div>
  <div class="mbody">
    <div class="frow"><input type="text" id="pag-serial" placeholder="Serial del ticket"></div>
    <button class="btn-q" onclick="verificarTicket()">VERIFICAR</button>
    <div id="pag-res"></div>
  </div>
</div></div>

<!-- ANULAR -->
<div class="modal" id="mod-anular">
<div class="mc">
  <div class="mh"><h3>❌ ANULAR TICKET</h3><button class="btn-close" onclick="closeMod('mod-anular')">✕</button></div>
  <div class="mbody">
    <div class="frow"><input type="text" id="an-serial" placeholder="Serial del ticket"></div>
    <button class="btn-q" style="background:linear-gradient(135deg,#3a1010,#280808);border-color:#6b1515;color:#e05050" onclick="anularTicket()">ANULAR</button>
    <div id="an-res"></div>
  </div>
</div></div>

<!-- CAJA HOY -->
<div class="modal" id="mod-caja">
<div class="mc">
  <div class="mh"><h3>💰 CAJA HOY</h3><button class="btn-close" onclick="closeMod('mod-caja')">✕</button></div>
  <div class="mbody" id="caja-body"></div>
</div></div>

<script>
const ANIMALES = {{ animales | tojson }};
const COLORES  = {{ colores | tojson }};
const HPERU = {{ horarios_peru | tojson }};
const HPLUS = {{ horarios_plus | tojson }};
const ROJOS = ["1","3","5","7","9","12","14","16","18","19","21","23","25","27","30","32","34","36","37","39"];
const ORDEN = ['00','0','1','2','3','4','5','6','7','8','9','10','11','12','13','14','15','16','17','18','19','20','21','22','23','24','25','26','27','28','29','30','31','32','33','34','35','36','37','38','39','40'];

let carrito = [];
let horasSel = [];
let horasSelPlus = [];
let animalesSel = [];
let espSel = null;
let horasBloq = [];
let horasBloqPlus = [];
let loteriaActiva = 'peru'; // 'peru' o 'plus'
let tripSlotModal = 0;
let tripAnimModal = [null, null, null];

// INIT
function init(){
  renderAnimales();
  renderHoras();
  renderTripModalGrid();
  actualizarBloq();
  setInterval(actualizarBloq, 30000);
  setInterval(actualizarClock, 1000);
  setInterval(verificarConexion, 10000);
  actualizarClock();
  verificarConexion();
  
  let hoy = new Date().toISOString().split('T')[0];
  ['res-fecha','mt-ini','mt-fin','ar-ini','ar-fin'].forEach(id=>{
    let el=document.getElementById(id); if(el) el.value=hoy;
  });
}

let _sinConexion = false;
function verificarConexion(){
  fetch('/api/hora-actual',{cache:'no-store'})
  .then(r=>{
    if(r.ok && _sinConexion){
      _sinConexion=false;
      document.getElementById('offline-banner').style.display='none';
      document.getElementById('btn-wa').disabled = window._carritoLen===0;
    }
  })
  .catch(()=>{
    _sinConexion=true;
    document.getElementById('offline-banner').style.display='flex';
    document.getElementById('btn-wa').disabled=true;
  });
}

function actualizarClock(){
  // Hora Lima/Peru = UTC-5, siempre fija (Peru no usa horario de verano)
  let now = new Date();
  let utcMs = now.getTime() + now.getTimezoneOffset() * 60000; // normalizar a UTC
  let peruMs = utcMs - 5 * 3600000;                            // restar 5h → UTC-5
  let peru = new Date(peruMs);
  let h = peru.getHours(), m = peru.getMinutes();
  let ap = h >= 12 ? 'PM' : 'AM';
  h = h % 12 || 12;
  document.getElementById('clock').textContent = `${h}:${String(m).padStart(2,'0')} ${ap} · LIMA`;
}

function actualizarBloq(){
  fetch('/api/hora-actual').then(r=>r.json()).then(d=>{
    horasBloq = d.bloqueadas||[];
    horasBloqPlus = d.bloqueadas_plus||[];
    horasSel = horasSel.filter(h=>!horasBloq.includes(h));
    horasSelPlus = horasSelPlus.filter(h=>!horasBloqPlus.includes(h));
    renderHoras();
  }).catch(()=>{});
}

// COLORES
function getCardClass(k){
  if(k==='40') return 'cl';
  let c = COLORES[k];
  if(c==='verde') return 'cv';
  if(c==='rojo')  return 'cr';
  return 'cn';
}

// ANIMALES GRID
function renderAnimales(){
  let g = document.getElementById('animals-grid');
  g.innerHTML = '';
  ORDEN.forEach(k=>{
    if(!ANIMALES[k]) return;
    let d = document.createElement('div');
    d.className = `acard ${getCardClass(k)}`;
    d.dataset.k = k;
    d.innerHTML = `<div class="anum">${k}</div><div class="anom">${ANIMALES[k]}</div>`;
    d.onclick = ()=>toggleAnimal(k,d);
    g.appendChild(d);
  });
}

function toggleAnimal(k, el){
  let i = animalesSel.indexOf(k);
  if(i>=0){ 
    animalesSel.splice(i,1); 
    el.classList.remove('sel'); 
  } else { 
    animalesSel.push(k); 
    el.classList.add('sel'); 
  }
}

// JUGADA MANUAL
function handleManualPaste(e){
  e.preventDefault();
  let texto = (e.clipboardData || window.clipboardData).getData('text');
  document.getElementById('manual-input').value = texto;
  procesarManual(texto);
}

function handleManualKeyup(e){
  // Procesar al presionar Enter o al detectar separadores típicos
  let val = e.target.value;
  if(e.key==='Enter'){
    procesarManual(val);
    e.target.value='';
  }
}

function procesarManual(texto){
  if(!texto || !texto.trim()){ return; }
  // Soporta formatos: 1.5.9.10 / 7,19,25 / 1-5-9 / 1 5 9 / mezcla
  // Los puntos aquí son SEPARADORES no decimales (ej: 1.5.9.10 = números 1,5,9,10)
  let nums = texto.split(/[.,\-;\s\n\/|]+/).map(x=>x.trim()).filter(x=>x!=='');
  let validos = [];
  let invalidos = [];
  
  nums.forEach(n=>{
    // Normalizar: quitar ceros a la izquierda excepto "00"
    let num = n;
    if(n === '00') { num = '00'; }
    else { num = n.replace(/^0+/, '') || '0'; }
    
    if(ANIMALES[num] !== undefined){
      if(!validos.includes(num)) validos.push(num);
    } else {
      invalidos.push(n);
    }
  });
  
  if(validos.length===0){
    toast('No se encontraron números válidos (0-40 ó 00)','err');
    return;
  }
  
  // Seleccionar en el grid visualmente
  validos.forEach(k=>{
    if(!animalesSel.includes(k)){
      animalesSel.push(k);
    }
    let card = document.querySelector(`.acard[data-k="${k}"]`);
    if(card) card.classList.add('sel');
  });
  
  let msg = `✅ Seleccionados: ${validos.map(k=>k+'-'+ANIMALES[k]).join(', ')}`;
  if(invalidos.length) msg += ` | Ignorados: ${invalidos.join(',')}`;
  toast(msg,'ok');
  document.getElementById('manual-input').value='';
}

// Procesar manual al hacer click en botón o al salir del input
function confirmarManual(){
  let val = document.getElementById('manual-input').value;
  if(val.trim()) procesarManual(val);
}

// ESPECIALES
function selEsp(v){
  if(espSel===v){ 
    espSel=null; 
    document.getElementById('esp-'+v).classList.remove('sel'); 
  } else {
    if(espSel) document.getElementById('esp-'+espSel).classList.remove('sel');
    espSel=v;
    animalesSel=[]; 
    document.querySelectorAll('.animals-grid .acard').forEach(c=>c.classList.remove('sel'));
    document.getElementById('esp-'+v).classList.add('sel');
  }
}

// HORARIOS
function renderHoras(){
  let g = document.getElementById('horas-grid'); g.innerHTML='';
  let isPlus = loteriaActiva === 'plus';
  let lista = isPlus ? HPLUS : HPERU;
  let bloq = isPlus ? horasBloqPlus : horasBloq;
  let sel = isPlus ? horasSelPlus : horasSel;
  lista.forEach(h=>{
    let b = document.createElement('div');
    b.className = 'hbtn';
    let isBloq = bloq.includes(h);
    let isSel = sel.includes(h);
    if(isBloq) b.classList.add('bloq');
    if(isSel) b.classList.add('sel');
    let hp = h.replace(':00','');
    b.innerHTML = `<div class="hperu">${hp}</div>`;
    if(!isBloq) b.onclick = ()=>toggleH(h);
    g.appendChild(b);
  });
}
function toggleH(h){
  let isPlus = loteriaActiva === 'plus';
  let arr = isPlus ? horasSelPlus : horasSel;
  let i = arr.indexOf(h);
  if(i>=0) arr.splice(i,1);
  else arr.push(h);
  renderHoras();
}
function selTodos(){
  if(loteriaActiva === 'plus'){
    horasSelPlus = HPLUS.filter(h=>!horasBloqPlus.includes(h));
  } else {
    horasSel = HPERU.filter(h=>!horasBloq.includes(h));
  }
  renderHoras();
}
function limpiarH(){
  if(loteriaActiva === 'plus') horasSelPlus = [];
  else horasSel = [];
  renderHoras();
}

function cambiarLoteria(lot){
  loteriaActiva = lot;
  document.getElementById('tab-peru').classList.toggle('active', lot==='peru');
  document.getElementById('tab-plus').classList.toggle('active', lot==='plus');
  let lbl = lot==='plus'
    ? '⏰ PLUS — 12 Sorteos (Cierra 3 min antes (al :57))'
    : '⏰ PERÚ — 11 Sorteos (Cierra 3 min antes (al :57))';
  document.getElementById('horas-label').textContent = lbl;
  renderHoras();
}

function openTripletaModal(){
  tripAnimModal = [null, null, null];
  tripSlotModal = 0;
  actualizarSlotsModal();
  renderTripModalGrid();
  // Iniciar con la lotería activa en las tabs principales
  selTripLoteria(loteriaActiva || 'peru');
  openMod('mod-tripleta');
}

function selTripLoteria(lot){
  // Guardar la lotería elegida dentro del modal
  window.tripLoteriaModal = lot;

  let tabPeru = document.getElementById('trip-tab-peru');
  let tabPlus = document.getElementById('trip-tab-plus');
  let btn     = document.getElementById('trip-btn-agregar');

  if(lot === 'plus'){
    // Tab PLUS activo
    tabPlus.style.background    = '#6b21a8';
    tabPlus.style.color         = '#f3e8ff';
    tabPlus.style.fontWeight    = '700';
    tabPlus.style.boxShadow     = 'inset 0 -3px 0 #a855f7';
    // Tab PERU inactivo
    tabPeru.style.background    = '#0c1020';
    tabPeru.style.color         = '#4a6090';
    tabPeru.style.fontWeight    = 'normal';
    tabPeru.style.boxShadow     = 'none';
    // Botón agregar
    btn.style.background        = 'linear-gradient(135deg,#6b21a8,#4c1d95)';
    btn.style.borderColor       = '#a855f7';
    btn.style.color             = '#f3e8ff';
    btn.textContent             = '✅ AGREGAR — ZOOLO PLUS';
  } else {
    // Tab PERU activo
    tabPeru.style.background    = '#0c4a9e';
    tabPeru.style.color         = '#e0f0ff';
    tabPeru.style.fontWeight    = '700';
    tabPeru.style.boxShadow     = 'inset 0 -3px 0 #3b9eff';
    // Tab PLUS inactivo
    tabPlus.style.background    = '#0c1020';
    tabPlus.style.color         = '#4a6090';
    tabPlus.style.fontWeight    = 'normal';
    tabPlus.style.boxShadow     = 'none';
    // Botón agregar
    btn.style.background        = 'linear-gradient(135deg,#166534,#14532d)';
    btn.style.borderColor       = '#22c55e';
    btn.style.color             = '#dcfce7';
    btn.textContent             = '✅ AGREGAR — ZOOLO PERÚ';
  }
}

function renderTripModalGrid(){
  let g = document.getElementById('trip-modal-grid');
  if(!g) return;
  g.innerHTML = '';
  ORDEN.forEach(k=>{
    if(!ANIMALES[k]) return;
    let d = document.createElement('div');
    d.className = `acard ${getCardClass(k)}`;
    d.innerHTML = `<div class="anum">${k}</div><div class="anom">${ANIMALES[k]}</div>`;
    d.onclick = ()=>selTripAnimModal(k);
    g.appendChild(d);
  });
}

function activarSlotModal(i){ 
  tripSlotModal = i; 
  actualizarSlotsModal(); 
}

function selTripAnimModal(k){
  let otro = tripAnimModal.findIndex((x,idx)=>x===k && idx!==tripSlotModal);
  if(otro>=0){ 
    toast('Animal ya seleccionado en otro slot','err'); 
    return; 
  }
  tripAnimModal[tripSlotModal] = k;
  actualizarSlotsModal();
  if(tripSlotModal < 2){
    let nextEmpty = tripAnimModal.findIndex(x=>x===null, tripSlotModal+1);
    if(nextEmpty === -1) nextEmpty = tripSlotModal+1;
    if(nextEmpty < 3) tripSlotModal = nextEmpty;
  }
  actualizarSlotsModal();
}

function actualizarSlotsModal(){
  for(let i=0;i<3;i++){
    let s = document.getElementById('tms'+i);
    let k = tripAnimModal[i];
    if(k){
      s.innerHTML = `<div class="snum">${k}</div><div class="snom">${ANIMALES[k].substring(0,6)}</div>`;
      s.className = `tslot fill${i===tripSlotModal?' act':''}`;
      s.onclick = ()=>{ tripAnimModal[i]=null; activarSlotModal(i); };
    } else {
      s.innerHTML = `<div class="sph">ANIMAL ${i+1}</div>`;
      s.className = `tslot${i===tripSlotModal?' act':''}`;
      s.onclick = ()=>activarSlotModal(i);
    }
  }
}

function agregarTripletaModal(){
  if(tripAnimModal.includes(null)){
    toast('Selecciona los 3 animales','err');
    return;
  }
  let monto = parseFloat(document.getElementById('monto-tripleta').value)||0;
  if(monto<=0){ toast('Monto inválido','err'); return; }
  let lot = window.tripLoteriaModal || loteriaActiva || 'peru';
  let lotLabel = lot==='plus' ? 'ZOOLO PLUS (8AM-7PM VEN)' : 'ZOOLO PERÚ (8AM-6PM Lima)';
  let sel = tripAnimModal.join(',');
  let desc = tripAnimModal.map(n=>n+'-'+ANIMALES[n].substring(0,4)).join(' ');
  carrito.push({tipo:'tripleta',hora:'TODO DÍA',seleccion:sel,monto,desc:'🎯 '+desc,loteria:lot});
  
  renderCarrito();
  closeMod('mod-tripleta');
  toast(`Tripleta agregada (${lotLabel})`, 'ok');
}

// REPETIR TICKET
function openRepetirModal(){
  document.getElementById('rep-serial').value='';
  document.getElementById('rep-contenido').innerHTML='';
  openMod('mod-repetir');
}

function cargarTicketRepetir(){
  let serial = document.getElementById('rep-serial').value.trim();
  if(!serial){ toast('Ingrese serial','err'); return; }
  
  fetch('/api/repetir-ticket',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({serial:serial})
  })
  .then(r=>r.json())
  .then(d=>{
    if(d.error){
      toast(d.error,'err');
      return;
    }
    mostrarEditorRepetir(d);
  })
  .catch(()=>toast('Error al cargar ticket','err'));
}

function mostrarEditorRepetir(data){
  let html = `<div class="rep-info">
    <div>📋 Ticket Original: <b>${data.ticket_original.serial}</b></div>
    <div>💰 Total Original: S/${data.ticket_original.total}</div>
    <div style="margin-top:8px;color:#f5a623">Modifique horarios y montos antes de agregar:</div>
  </div>`;
  
  data.jugadas.forEach((j,idx)=>{
    if(j.tipo==='tripleta'){
      let lotLabel = j.loteria==='plus' ? '🟣 PLUS' : '🔵 PERÚ';
      html += `<div class="rep-item">
        <span style="color:#c084fc;font-family:'Oswald',sans-serif;min-width:60px">🎯 TRIP</span>
        <span style="flex:1;color:#e0a0ff">${j.animal1}-${j.animal2}-${j.animal3} <span style="font-size:.65rem;opacity:.8">${lotLabel}</span></span>
        <input type="number" id="rep-m-${idx}" value="${j.monto}" min="0.5" step="0.5">
        <button class="btn-close" style="padding:4px 8px;font-size:.7rem" data-loteria="${j.loteria||'peru'}" onclick="agregarItemRepetir(${idx},'tripleta','${j.animal1},${j.animal2},${j.animal3}','${j.loteria||'peru'}')">➕</button>
      </div>`;
    } else {
      let horaOpts = HPERU.map(h=>{
        let bloq = horasBloq.includes(h);
        return `<option value="${h}" ${bloq?'disabled':''}>${h}${bloq?' (CERRADO)':''}</option>`;
      }).join('');
      
      html += `<div class="rep-item">
        <span style="color:${j.tipo==='animal'?'#4ade80':'#60a5fa'};font-family:'Oswald',sans-serif;min-width:60px">${j.tipo==='animal'?'🐾':'🎲'} ${j.seleccion}</span>
        <select id="rep-h-${idx}">${horaOpts}</select>
        <input type="number" id="rep-m-${idx}" value="${j.monto}" min="0.5" step="0.5">
        <button class="btn-close" style="padding:4px 8px;font-size:.7rem" onclick="agregarItemRepetir(${idx},'${j.tipo}','${j.seleccion}')">➕</button>
      </div>`;
    }
  });
  
  html += `<button class="btn-q" onclick="agregarTodoRepetir()" style="margin-top:12px;background:#166534;border-color:#22c55e">AGREGAR TODO AL TICKET</button>`;
  
  document.getElementById('rep-contenido').innerHTML = html;
  
  // Seleccionar horarios originales donde estén disponibles
  data.jugadas.forEach((j,idx)=>{
    if(j.tipo!=='tripleta'){
      let sel = document.getElementById(`rep-h-${idx}`);
      if(sel){
        for(let opt of sel.options){
          if(opt.value===j.hora && !opt.disabled){
            sel.value = j.hora;
            break;
          }
        }
      }
    }
  });
}

function agregarItemRepetir(idx, tipo, seleccion, loteria){
  let monto = parseFloat(document.getElementById(`rep-m-${idx}`).value)||0;
  if(monto<=0){ toast('Monto inválido','err'); return; }
  
  if(tipo==='tripleta'){
    let nums = seleccion.split(',');
    let desc = nums.map(n=>n+'-'+ANIMALES[n].substring(0,4)).join(' ');
    let lot = loteria || 'peru';
    carrito.push({tipo:'tripleta',hora:'TODO DÍA',seleccion:seleccion,monto,desc:'🎯 '+desc,loteria:lot});
    toast('Tripleta agregada','ok');
  } else {
    let hora = document.getElementById(`rep-h-${idx}`).value;
    if(!hora){ toast('Seleccione horario','err'); return; }
    if(horasBloq.includes(hora)){ toast('Ese horario ya cerró','err'); return; }
    
    let nombre = tipo==='animal' ? ANIMALES[seleccion] : seleccion;
    carrito.push({
      tipo:tipo,
      hora:hora,
      seleccion:seleccion,
      monto:monto,
      desc: tipo==='animal' ? `${seleccion}-${nombre}` : `🎲 ${seleccion}`
    });
    toast('Jugada agregada','ok');
  }
  renderCarrito();
}

function agregarTodoRepetir(){
  // Simular clicks en todos los botones +
  let btns = document.querySelectorAll('#rep-contenido .rep-item button');
  btns.forEach(btn=>btn.click());
}

// MONTO
function setM(v){ document.getElementById('monto').value=v; }

// AGREGAR
function agregar(){
  let monto = parseFloat(document.getElementById('monto').value)||0;
  if(monto<=0){ toast('Monto inválido','err'); return; }
  let lot = loteriaActiva;
  let sel = lot==='plus' ? horasSelPlus : horasSel;

  // Especial
  if(espSel){
    if(sel.length===0){ toast('Seleccione horario','err'); return; }
    sel.forEach(h=>{
      let labels={'ROJO':'🔴 ROJO','NEGRO':'⚫ NEGRO','PAR':'🔵 PAR','IMPAR':'🟡 IMPAR'};
      carrito.push({tipo:'especial',hora:h,seleccion:espSel,monto,desc:labels[espSel]+' x2',loteria:lot});
    });
    renderCarrito(); 
    toast('Especial(es) agregado','ok'); 
    return;
  }

  // Animal
  if(animalesSel.length===0){ toast('Seleccione animal(es)','err'); return; }
  if(sel.length===0){ toast('Seleccione horario(s)','err'); return; }
  
  sel.forEach(h=>{
    animalesSel.forEach(k=>{
      carrito.push({tipo:'animal',hora:h,seleccion:k,monto,desc:`${k}-${ANIMALES[k]}`,loteria:lot});
    });
  });
  
  animalesSel=[];
  document.querySelectorAll('.animals-grid .acard').forEach(c=>c.classList.remove('sel'));
  document.getElementById('manual-input').value='';
  
  renderCarrito(); 
  toast(`Jugadas agregadas (${lot.toUpperCase()})`,'ok');
}

// CARRITO
function renderCarrito(){
  let list=document.getElementById('ticket-list');
  let tot=document.getElementById('ticket-total');
  window._carritoLen = carrito.length;
  document.getElementById('btn-wa').disabled = (carrito.length===0 || _sinConexion);
  
  if(!carrito.length){
    list.innerHTML='<div class="ticket-empty">TICKET VACÍO</div>';
    tot.style.display='none'; 
    return;
  }
  
  let html='', total=0;
  carrito.forEach((it,i)=>{
    total+=it.monto;
    let lot = it.loteria||'peru';
    let isTrip = it.tipo==='tripleta';
    let lotLabel = lot==='plus'
      ? `<span style="background:#4c1d95;border:1px solid #a855f7;color:#e9d5ff;font-size:.58rem;font-family:'Oswald',sans-serif;padding:1px 5px;border-radius:3px;flex-shrink:0">${isTrip?'🎯 ':''} PLUS</span>`
      : `<span style="background:#0c2461;border:1px solid #3b9eff;color:#bae6fd;font-size:.58rem;font-family:'Oswald',sans-serif;padding:1px 5px;border-radius:3px;flex-shrink:0">${isTrip?'🎯 ':''}PERÚ</span>`;
    let horaLabel = it.hora==='TODO DÍA'?'x60':it.hora.replace(':00','').replace(' ','');
    html+=`<div class="ti" style="${isTrip?'border-left:3px solid '+(lot==='plus'?'#a855f7':'#3b9eff')+';background:rgba(100,60,180,.08)':''}">
      <span class="ti-hora">${horaLabel}</span>
      ${lotLabel}
      <span class="ti-desc">${it.desc}</span>
      <span class="ti-monto">${it.monto}</span>
      <button class="ti-del" onclick="quitarItem(${i})">✕</button>
    </div>`;
  });
  
  list.innerHTML=html;
  tot.style.display='block';
  tot.textContent=`TOTAL: S/ ${total.toFixed(2)}`;
}

function quitarItem(i){ carrito.splice(i,1); renderCarrito(); }
function borrarTodo(){ 
  carrito=[]; 
  animalesSel=[];
  espSel=null;
  horasSel=[];
  horasSelPlus=[];
  document.querySelectorAll('.acard').forEach(c=>c.classList.remove('sel'));
  document.querySelectorAll('.esp-btn').forEach(e=>e.classList.remove('sel'));
  renderCarrito(); 
  toast('Ticket borrado','err'); 
}

// VENDER
async function vender(){
  if(!carrito.length){ toast('Ticket vacío','err'); return; }
  
  let btn=document.getElementById('btn-wa');
  btn.disabled=true; 
  btn.textContent='⏳ PROCESANDO...';
  
  try{
    let r=await fetch('/api/procesar-venta',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({jugadas:carrito.map(c=>({hora:c.hora,seleccion:c.seleccion,monto:c.monto,tipo:c.tipo,loteria:c.loteria||'peru'}))})
    });
    let d=await r.json();
    
    if(d.error){ 
      toast(d.error,'err'); 
    } else {
      window.open(d.url_whatsapp,'_blank');
      toast(`✅ Ticket #${d.ticket_id} generado!`,'ok');
      
      // LIMPIAR TODO
      carrito=[];
      animalesSel=[];
      if(espSel){
        document.getElementById('esp-'+espSel).classList.remove('sel');
        espSel=null;
      }
      horasSel=[];
      horasSelPlus=[];
      document.getElementById('manual-input').value='';
      renderCarrito();
      renderAnimales();
      renderHoras();
    }
  } catch(e){ 
    toast('Error de conexión','err'); 
  } finally{ 
    btn.disabled=false; 
    btn.textContent='📤 ENVIAR POR WHATSAPP'; 
  }
}

// RESULTADOS
function openResultados(){
  // Poner fecha de hoy por defecto al abrir
  if(!document.getElementById('res-fecha').value){
    document.getElementById('res-fecha').value = new Date().toISOString().split('T')[0];
  }
  openMod('mod-resultados');
  cargarResultados();
}
function cargarResultados(){
  let f=document.getElementById('res-fecha').value; 
  if(!f)return;
  let c=document.getElementById('res-lista');
  c.innerHTML='<p style="color:var(--text2);text-align:center;padding:10px;font-size:.75rem;letter-spacing:2px">CARGANDO...</p>';
  
  let fd=new Date(f+'T12:00:00');
  document.getElementById('res-titulo').textContent=fd.toLocaleDateString('es-PE',{weekday:'long',day:'numeric',month:'long'}).toUpperCase();

  Promise.all([
    fetch('/api/resultados-fecha',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha:f,loteria:'peru'})}).then(r=>r.json()),
    fetch('/api/resultados-fecha',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha:f,loteria:'plus'})}).then(r=>r.json())
  ]).then(([dp,dpl])=>{
    let html='<div style="color:#0ea5e9;font-family:\'Oswald\',sans-serif;font-size:.72rem;letter-spacing:2px;padding:4px 0 6px;border-bottom:1px solid #e2e8f0;margin-bottom:4px">🇵🇪 ZOOLO CASINO — PERÚ (11 SORTEOS)</div>';
    HPERU.forEach(h=>{
      let res=dp.resultados[h];
      html+=`<div class="ri ${res?'ok':''}">
        <span class="ri-hora">${h.replace(':00 AM',' AM').replace(':00 PM',' PM')}</span>
        ${res?`<span class="ri-animal">${res.animal} — ${res.nombre}</span>`:'<span style="color:#4a6090;font-size:.78rem">PENDIENTE</span>'}
      </div>`;
    });
    html+='<div style="color:#a855f7;font-family:\'Oswald\',sans-serif;font-size:.72rem;letter-spacing:2px;padding:8px 0 6px;border-bottom:1px solid #e2e8f0;margin-top:10px;margin-bottom:4px">🎰 ZOOLO CASINO PLUS (12 SORTEOS)</div>';
    HPLUS.forEach(h=>{
      let res=dpl.resultados[h];
      html+=`<div class="ri ${res?'ok':''}">
        <span class="ri-hora">${h.replace(':00 AM',' AM').replace(':00 PM',' PM')}</span>
        ${res?`<span class="ri-animal">${res.animal} — ${res.nombre}</span>`:'<span style="color:#4a6090;font-size:.78rem">PENDIENTE</span>'}
      </div>`;
    });
    c.innerHTML=html||'<p style="color:#4a6090;text-align:center;padding:20px;font-size:.75rem;letter-spacing:2px">SIN RESULTADOS</p>';
  })
  .catch(()=>{c.innerHTML='<p style="color:var(--red);text-align:center;padding:12px">Error de conexión</p>';});
}

// CONSULTAS
function consultarTickets(){
  let ini=document.getElementById('mt-ini').value;
  let fin=document.getElementById('mt-fin').value;
  let est=document.getElementById('mt-estado').value;
  if(!ini||!fin){ toast('Seleccione fechas','err'); return; }
  
  let lista=document.getElementById('mt-lista');
  lista.innerHTML='<p style="color:#6090c0;text-align:center;padding:15px;font-size:.75rem;letter-spacing:2px">CARGANDO...</p>';
  
  fetch('/api/mis-tickets',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin,estado:est})
  })
  .then(r=>r.json())
  .then(d=>{
    if(d.error){
      lista.innerHTML=`<p style="color:#f87171;text-align:center">${d.error}</p>`;
      return;
    }
    let res=document.getElementById('mt-resumen'); 
    res.style.display='block';
    res.textContent=`${d.totales.cantidad} TICKET(S) — TOTAL: S/ ${d.totales.ventas.toFixed(2)}`;
    
    if(!d.tickets.length){
      lista.innerHTML='<p style="color:#4a6090;text-align:center;padding:20px;font-size:.75rem;letter-spacing:2px">SIN RESULTADOS</p>';
      return;
    }
    
    let html='';
    d.tickets.forEach((t)=>{
      let bc=t.pagado?'p':(t.premio_calculado>0?'g':'n');
      let bt=t.pagado?'✅ PAGADO':(t.premio_calculado>0?'🏆 GANADOR':'⏳ PENDIENTE');
      let tc=t.pagado?'gano':(t.premio_calculado>0?'pte':'');

      let jhtml='';
      if(t.jugadas && t.jugadas.length){
        jhtml+=`<div style="color:#4080c0;font-size:.65rem;font-family:'Oswald',sans-serif;letter-spacing:2px;padding:4px 0 2px">JUGADAS</div>`;
        t.jugadas.forEach(j=>{
          let rn=j.resultado?(j.resultado+' — '+(j.resultado_nombre||'')):'...';
          let tipoIcon=j.tipo==='especial'?'🎲':'🐾';
          let lotBadge=j.loteria==='plus'
            ?`<span style="background:#3b0764;border:1px solid #a855f7;color:#e9d5ff;font-family:'Oswald',sans-serif;font-size:.58rem;padding:1px 4px;border-radius:2px;flex-shrink:0">PLUS</span>`
            :`<span style="background:#0c2461;border:1px solid #0ea5e9;color:#bae6fd;font-family:'Oswald',sans-serif;font-size:.58rem;padding:1px 4px;border-radius:2px;flex-shrink:0">PERÚ</span>`;
          jhtml+=`<div class="jrow ${j.gano?'gano':''}">
            <span style="color:#00c8e8;font-family:'Oswald',sans-serif;font-size:.68rem;min-width:52px;font-weight:700">${j.hora.replace(':00 ','').replace(' ','')}</span>
            ${lotBadge}
            <span style="flex:1;color:#c0d8f0;font-size:.72rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-left:3px">${tipoIcon} ${j.tipo==='animal'?(j.seleccion+' '+j.nombre):j.seleccion}</span>
            <span style="color:#6090c0;font-size:.68rem;margin:0 4px">S/${j.monto}</span>
            <span style="font-size:.68rem;min-width:60px;text-align:right">
              ${j.resultado?`<span style="color:${j.gano?'#4ade80':'#6090c0'}">${j.gano?'✓':'✗'} ${rn}</span>`:'<span style="color:#2a4060">PEND</span>'}
            </span>
            ${j.gano?`<span style="color:#4ade80;font-weight:700;font-family:'Oswald',sans-serif;font-size:.72rem;margin-left:4px">+${j.premio}</span>`:''}
          </div>`;
        });
      }

      let thtml='';
      if(t.tripletas && t.tripletas.length){
        thtml+=`<div style="color:#c084fc;font-size:.65rem;font-family:'Oswald',sans-serif;letter-spacing:2px;padding:4px 0 2px;margin-top:4px">🎯 TRIPLETAS x60</div>`;
        t.tripletas.forEach(tr=>{
          let salStr=tr.salieron&&tr.salieron.length?tr.salieron.join(', '):'Ninguno aún';
          let pend=3-tr.salieron.length;
          let trLotBadge=tr.loteria==='plus'
            ?`<span style="background:#3b0764;border:1px solid #a855f7;color:#e9d5ff;font-family:'Oswald',sans-serif;font-size:.58rem;padding:1px 4px;border-radius:2px">PLUS</span>`
            :`<span style="background:#0c2461;border:1px solid #0ea5e9;color:#bae6fd;font-family:'Oswald',sans-serif;font-size:.58rem;padding:1px 4px;border-radius:2px">PERÚ</span>`;
          thtml+=`<div class="trip-row ${tr.gano?'gano':''}">
            <div style="flex:1">
              <div style="display:flex;gap:4px;flex-wrap:wrap;align-items:center">
                ${trLotBadge}
                <span style="background:#3b0764;border:2px solid #7c3aed;border-radius:3px;padding:2px 5px;font-family:'Oswald',sans-serif;font-size:.72rem;color:#e0a0ff">${tr.animal1} ${tr.nombre1}</span>
                <span style="color:#6040a0;font-size:.7rem">•</span>
                <span style="background:#3b0764;border:2px solid #7c3aed;border-radius:3px;padding:2px 5px;font-family:'Oswald',sans-serif;font-size:.72rem;color:#e0a0ff">${tr.animal2} ${tr.nombre2}</span>
                <span style="color:#6040a0;font-size:.7rem">•</span>
                <span style="background:#3b0764;border:2px solid #7c3aed;border-radius:3px;padding:2px 5px;font-family:'Oswald',sans-serif;font-size:.72rem;color:#e0a0ff">${tr.animal3} ${tr.nombre3}</span>
              </div>
              <div style="margin-top:3px;font-size:.68rem">
                <span style="color:#6090c0">Salieron: </span>
                <span style="color:${tr.gano?'#4ade80':'#a080c0'}">${salStr}</span>
                ${!tr.gano&&pend>0?`<span style="color:#4a3080"> (faltan ${pend})</span>`:''}
                ${tr.gano?'<span style="color:#4ade80;font-weight:700"> ✅ GANÓ</span>':''}
              </div>
            </div>
            <div style="text-align:right;flex-shrink:0;margin-left:8px">
              <div style="color:#fbbf24;font-family:'Oswald',sans-serif;font-weight:700">S/${tr.monto}</div>
              ${tr.gano?`<div style="color:#4ade80;font-weight:700;font-family:'Oswald',sans-serif">+S/${tr.premio.toFixed(2)}</div>`:'<div style="color:#3a2060;font-size:.68rem">x60</div>'}
              ${tr.pagado?'<div style="color:#22c55e;font-size:.65rem;font-family:\'Oswald\',sans-serif">COBRADO</div>':''}
            </div>
          </div>`;
        });
      }

      html+=`<div class="tcard ${tc}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px;margin-bottom:6px">
          <div style="flex:1;min-width:0">
            <div class="ts">🎫 #${t.serial}</div>
            <div style="color:#4a6090;font-size:.7rem">${t.fecha}</div>
          </div>
          <div style="text-align:right;flex-shrink:0">
            <span class="badge ${bc}">${bt}</span>
            <div style="color:#fbbf24;font-family:'Oswald',sans-serif;font-size:.9rem;margin-top:3px;font-weight:700">S/${t.total}</div>
            ${t.premio_calculado>0?`<div style="color:#4ade80;font-size:.82rem;font-weight:700;font-family:'Oswald',sans-serif">PREMIO: S/${t.premio_calculado.toFixed(2)}</div>`:''}
          </div>
        </div>
        ${jhtml}${thtml}
      </div>`;
    });
    lista.innerHTML=html;
  })
  .catch(()=>{lista.innerHTML='<p style="color:#f87171;text-align:center">Error de conexión</p>';});
}

// ARCHIVO/CAJA HISTÓRICO
function cajaHist(){
  let ini=document.getElementById('ar-ini').value;
  let fin=document.getElementById('ar-fin').value;
  if(!ini||!fin){ toast('Seleccione fechas','err'); return; }
  
  let c=document.getElementById('ar-res');
  c.innerHTML='<p style="color:var(--text2);text-align:center;padding:10px;font-size:.75rem;letter-spacing:2px">CARGANDO...</p>';
  
  fetch('/api/caja-historico',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin})
  })
  .then(r=>r.json())
  .then(d=>{
    if(d.error){c.innerHTML=`<p style="color:var(--red)">${d.error}</p>`;return;}
    let html='<div class="sbox">';
    d.resumen_por_dia.forEach(dia=>{
      let col=dia.balance>=0?'var(--green)':'var(--red)';
      html+=`<div class="srow">
        <span class="sl">${dia.fecha}</span>
        <span style="font-size:.72rem;color:var(--text2)">V:${dia.ventas}</span>
        <span class="sv" style="color:${col}">S/${dia.balance.toFixed(2)}</span>
      </div>`;
    });
    html+=`</div><div class="sbox">
      <div class="srow"><span class="sl">Ventas</span><span class="sv">S/${d.totales.ventas.toFixed(2)}</span></div>
      <div class="srow"><span class="sl">Premios</span><span class="sv" style="color:var(--red)">S/${d.totales.premios.toFixed(2)}</span></div>
      <div class="srow"><span class="sl">Comisión</span><span class="sv">S/${d.totales.comision.toFixed(2)}</span></div>
      <div class="srow"><span class="sl">Balance</span><span class="sv" style="color:${d.totales.balance>=0?'var(--green)':'var(--red)'}">S/${d.totales.balance.toFixed(2)}</span></div>
    </div>`;
    c.innerHTML=html;
  });
}

// CAJA HOY
function openCaja(){
  openMod('mod-caja');
  fetch('/api/caja').then(r=>r.json()).then(d=>{
    if(d.error) return;
    let bc=d.balance>=0?'g':'r';
    document.getElementById('caja-body').innerHTML=`
      <div class="caja-grid">
        <div class="cg"><div class="cgl">VENTAS</div><div class="cgv">S/${d.ventas.toFixed(2)}</div></div>
        <div class="cg"><div class="cgl">PREMIOS PAGADOS</div><div class="cgv r">S/${d.premios.toFixed(2)}</div></div>
        <div class="cg"><div class="cgl">COMISIÓN</div><div class="cgv">S/${d.comision.toFixed(2)}</div></div>
        <div class="cg"><div class="cgl">BALANCE</div><div class="cgv ${bc}">S/${d.balance.toFixed(2)}</div></div>
      </div>
      <div class="sbox">
        <div class="srow"><span class="sl">Tickets vendidos</span><span class="sv">${d.total_tickets}</span></div>
        <div class="srow"><span class="sl">Con premio pendiente</span><span class="sv" style="color:#c08020">${d.tickets_pendientes}</span></div>
      </div>`;
  });
}

// PAGAR
function openPagar(){ 
  openMod('mod-pagar'); 
  document.getElementById('pag-serial').value=''; 
  document.getElementById('pag-res').innerHTML=''; 
}

function verificarTicket(){
  let s=document.getElementById('pag-serial').value.trim(); 
  if(!s)return;
  
  let c=document.getElementById('pag-res');
  fetch('/api/verificar-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({serial:s})})
  .then(r=>r.json())
  .then(d=>{
    if(d.error){
      c.innerHTML=`<div style="background:var(--red-bg);color:var(--red);padding:10px;border-radius:3px;text-align:center;margin-top:8px;border:1px solid var(--red-border)">❌ ${d.error}</div>`;
      return;
    }
    let col=d.total_ganado>0?'var(--green)':'var(--text2)';
    c.innerHTML=`<div style="border:1px solid ${col};border-radius:4px;padding:14px;margin-top:10px">
      <div style="color:var(--teal);font-family:'Oswald',sans-serif;letter-spacing:2px;margin-bottom:10px">TICKET #${s}</div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <span style="color:var(--text2);font-size:.8rem">PREMIO</span>
        <span style="color:${col};font-family:'Oswald',sans-serif;font-size:1.2rem;font-weight:700">S/${d.total_ganado.toFixed(2)}</span>
      </div>
      ${d.total_ganado>0?`<button onclick="pagarTicket(${d.ticket_id},${d.total_ganado})" style="width:100%;padding:11px;background:linear-gradient(135deg,#0a3020,#062018);color:var(--green);border:1px solid #0d5a2a;border-radius:3px;font-weight:700;cursor:pointer;font-family:'Oswald',sans-serif;letter-spacing:2px;font-size:.85rem">💰 CONFIRMAR PAGO S/${d.total_ganado.toFixed(2)}</button>`:'<div style="color:var(--text2);text-align:center;font-size:.8rem;padding:6px">SIN PREMIO</div>'}
    </div>`;
  });
}

function pagarTicket(tid,m){
  if(!confirm(`¿Confirmar pago S/${m}?`))return;
  fetch('/api/pagar-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticket_id:tid})})
  .then(r=>r.json())
  .then(d=>{
    if(d.status==='ok'){
      toast('✅ Ticket pagado','ok');
      closeMod('mod-pagar');
    } else {
      toast(d.error||'Error','err');
    }
  });
}

// ANULAR
function openAnular(){ 
  openMod('mod-anular'); 
  document.getElementById('an-serial').value=''; 
  document.getElementById('an-res').innerHTML=''; 
}

function anularTicket(){
  let s=document.getElementById('an-serial').value.trim(); 
  if(!s)return;
  
  fetch('/api/anular-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({serial:s})})
  .then(r=>r.json())
  .then(d=>{
    let c=document.getElementById('an-res');
    if(d.status==='ok') {
      c.innerHTML=`<div style="background:#062012;color:var(--green);padding:10px;border-radius:3px;text-align:center;margin-top:8px;border:1px solid #0d5a2a">✅ ${d.mensaje}</div>`;
    } else {
      c.innerHTML=`<div style="background:var(--red-bg);color:var(--red);padding:10px;border-radius:3px;text-align:center;margin-top:8px;border:1px solid var(--red-border)">❌ ${d.error}</div>`;
    }
  });
}

// MODAL
function openMod(id){ document.getElementById(id).classList.add('open'); }
function closeMod(id){ document.getElementById(id).classList.remove('open'); }
document.querySelectorAll('.modal').forEach(m=>{
  m.addEventListener('click',e=>{ if(e.target===m) m.classList.remove('open'); });
});

// TOAST
function toast(msg,tipo){
  let t=document.getElementById('toast');
  t.textContent=msg; 
  t.className='toast '+tipo; 
  t.style.display='block';
  clearTimeout(window._tt);
  window._tt=setTimeout(()=>t.style.display='none',2800);
}

document.addEventListener('DOMContentLoaded',init);
</script>
</body></html>'''

ADMIN_HTML = r'''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ADMIN — ZOOLO</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;600;700&family=Rajdhani:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#f0f4f8;--panel:#ffffff;--card:#f8fafc;--border:#e2e8f0;--gold:#c47b00;--blue:#1d4ed8;--teal:#0284c7;--red:#dc2626;--green:#16a34a;--purple:#7c3aed;--text:#1e293b;--text2:#64748b}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Rajdhani',sans-serif;min-height:100vh}
.topbar{background:#1e293b;border-bottom:3px solid #f5a623;padding:0 16px;height:40px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.brand{font-family:'Oswald',sans-serif;font-size:1rem;font-weight:700;color:#fff;letter-spacing:2px}
.brand em{color:var(--gold);font-style:normal}
.btn-exit{background:#991b1b;color:#fff;border:2px solid #ef4444;padding:6px 14px;border-radius:3px;cursor:pointer;font-family:'Oswald',sans-serif;font-weight:700;font-size:.78rem;letter-spacing:1px;transition:all .15s}
.btn-exit:hover{background:#b91c1c}
.tabs{display:flex;background:#1e293b;border-bottom:2px solid #334155;overflow-x:auto;position:sticky;top:40px;z-index:99}
.tab{padding:10px 12px;cursor:pointer;color:#94a3b8;font-size:.7rem;font-family:'Oswald',sans-serif;letter-spacing:2px;border-bottom:3px solid transparent;transition:all .2s;white-space:nowrap;font-weight:600}
.tab:hover{color:#e2e8f0;background:#334155}
.tab.active{color:#38bdf8;border-bottom-color:#0284c7;background:#0f172a}
.tc{display:none;padding:14px;max-width:960px;margin:auto}
.tc.active{display:block}
.fbox{background:#ffffff;border:2px solid #e2e8f0;border-radius:6px;padding:15px;margin-bottom:12px;box-shadow:0 1px 4px rgba(0,0,0,.07)}
.fbox h3{font-family:'Oswald',sans-serif;color:#0284c7;margin-bottom:12px;font-size:.82rem;letter-spacing:2px;border-bottom:2px solid #e2e8f0;padding-bottom:8px}
.frow{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.frow input,.frow select{flex:1;min-width:100px;padding:9px 11px;background:#f8fafc;border:2px solid #cbd5e1;border-radius:3px;color:#1e293b;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600}
.frow input:focus,.frow select:focus{outline:none;border-color:#0284c7}
.btn-s{padding:9px 14px;background:#16a34a;color:#fff;border:2px solid #22c55e;border-radius:3px;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:1px;cursor:pointer;font-size:.75rem;white-space:nowrap}
.btn-s:hover{background:#15803d}
.btn-d{padding:9px 14px;background:#dc2626;color:#fff;border:2px solid #ef4444;border-radius:3px;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:1px;cursor:pointer;font-size:.75rem}
.btn-d:hover{background:#b91c1c}
.btn-sec{padding:7px 10px;background:#e2e8f0;color:#475569;border:2px solid #cbd5e1;border-radius:3px;cursor:pointer;font-size:.75rem;font-family:'Oswald',sans-serif;letter-spacing:1px;font-weight:700}
.btn-sec:hover{background:#0284c7;border-color:#0284c7;color:#fff}
.sgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-bottom:16px}
.sc{background:#ffffff;border:2px solid #e2e8f0;border-radius:4px;padding:12px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.sc h3{color:#64748b;font-size:.62rem;letter-spacing:2px;font-family:'Oswald',sans-serif;margin-bottom:5px}
.sc p{color:#c47b00;font-size:1.25rem;font-weight:700;font-family:'Oswald',sans-serif}
.sc p.g{color:#16a34a}.sc p.r{color:#dc2626}
.ri{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;margin:3px 0;background:#f8fafc;border-radius:3px;border-left:3px solid #cbd5e1}
.ri.ok{border-left-color:#16a34a;background:#f0fdf4}
.msg{padding:9px 12px;border-radius:3px;margin:6px 0;font-size:.82rem;font-family:'Oswald',sans-serif;letter-spacing:1px;text-align:center;font-weight:700;border:2px solid}
.msg.ok{background:#16a34a;color:#fff;border-color:#22c55e}
.msg.err{background:#dc2626;color:#fff;border-color:#ef4444}
table{width:100%;border-collapse:collapse;font-size:.8rem}
th{background:#f1f5f9;color:#0284c7;padding:9px;text-align:left;border-bottom:2px solid #e2e8f0;font-family:'Oswald',sans-serif;letter-spacing:1px;font-size:.72rem}
td{padding:7px 9px;border-bottom:1px solid #f1f5f9;color:var(--text)}
tr:hover td{background:#f8fafc}
.rank-item{display:flex;justify-content:space-between;align-items:center;padding:11px 13px;margin:5px 0;background:#fffbeb;border-radius:3px;border-left:3px solid #f59e0b;border:1px solid #fde68a}
.glmsg{position:fixed;top:48px;left:50%;transform:translateX(-50%);z-index:999;min-width:240px;display:none;box-shadow:0 4px 20px rgba(0,0,0,.15)}
.sbox{background:#f8fafc;border-radius:3px;padding:10px;margin:6px 0;border:1px solid #e2e8f0}
.srow{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #f1f5f9;font-size:.8rem}
.srow:last-child{border-bottom:none}
.sl{color:#64748b}.sv{color:#c47b00;font-weight:700;font-family:'Oswald',sans-serif}
.btn-edit{padding:5px 10px;background:#1d4ed8;color:#fff;border:2px solid #3b82f6;border-radius:3px;cursor:pointer;font-size:.72rem;font-family:'Oswald',sans-serif;letter-spacing:1px;font-weight:700}
.btn-edit:hover{background:#2563eb}
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:#f1f5f9}
::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:2px}
::-webkit-scrollbar-thumb:hover{background:#94a3b8}
</style></head><body>
<div class="topbar">
  <div class="brand">ZOO<em>LO</em> — ADMIN</div>
  <button class="btn-exit" onclick="location.href='/logout'">SALIR</button>
</div>
<div id="glmsg" class="glmsg"></div>
<div class="tabs">
  <div class="tab active" onclick="showTab('dashboard')">📊 DASHBOARD</div>
  <div class="tab" onclick="showTab('resultados')">🎯 RESULTADOS</div>
  <div class="tab" onclick="showTab('tripletas')">🔮 TRIPLETAS</div>
  <div class="tab" onclick="showTab('riesgo')">⚠️ RIESGO</div>
  <div class="tab" onclick="showTab('topes')">🛡️ TOPES</div>
  <div class="tab" onclick="showTab('reportes')">📈 REPORTES</div>
  <div class="tab" onclick="showTab('agencias')">🏪 AGENCIAS</div>
  <div class="tab" onclick="showTab('operaciones')">💰 OPERACIONES</div>
  <div class="tab" onclick="showTab('auditoria')">📋 AUDITORÍA</div>
</div>

<div id="tc-dashboard" class="tc active">
  <div class="sgrid">
    <div class="sc"><h3>VENTAS HOY</h3><p id="d-v">--</p></div>
    <div class="sc"><h3>PREMIOS PAGADOS</h3><p id="d-p" class="r">--</p></div>
    <div class="sc"><h3>COMISIONES</h3><p id="d-c">--</p></div>
    <div class="sc"><h3>BALANCE</h3><p id="d-b">--</p></div>
  </div>
  <div class="fbox"><h3>🏪 POR AGENCIA (HOY)</h3><div id="dash-ags"></div></div>
</div>

<div id="tc-resultados" class="tc">
  <div class="fbox">
    <h3>📅 FECHA</h3>
    <div class="frow">
      <input type="date" id="ra-fecha">
      <select id="ra-loteria" style="padding:8px 12px;background:#0a1828;border:2px solid #2a4a80;border-radius:3px;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600">
        <option value="peru">🇵🇪 ZOOLO PERU (11 sorteos)</option>
        <option value="plus">🎰 ZOOLO PLUS (12 sorteos)</option>
      </select>
      <button class="btn-s" onclick="cargarRA()">VER</button>
    </div>
  </div>
  <div class="fbox">
    <h3>📋 RESULTADOS</h3>
    <div id="ra-lista" style="max-height:400px;overflow-y:auto"></div>
  </div>
  <div class="fbox">
    <h3>✏️ CARGAR RESULTADO MANUAL</h3>
    <div style="background:#fffbeb;border:1px solid #f59e0b;border-radius:4px;padding:8px 12px;margin-bottom:10px;font-size:.75rem;color:#92400e;font-family:'Rajdhani',sans-serif;font-weight:600">⚠️ El auto-sorteo elige al azar entre los animales 00–39 (Lechuza #40 nunca sale automáticamente). Para que salga el 40, cargarlo aquí manualmente.</div>
    <div class="frow">
      <select id="ra-lot-manual" onchange="actualizarHorasAdmin()" style="padding:8px 12px;background:#0a1828;border:2px solid #a855f7;border-radius:3px;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600">
        <option value="peru">🇵🇪 PERU</option>
        <option value="plus">🎰 PLUS</option>
      </select>
      <select id="ra-hora">{% for h in horarios %}<option value="{{h}}">{{h}}</option>{% endfor %}</select>
      <select id="ra-animal">{% for k,v in animales.items() %}<option value="{{k}}">{{k}} — {{v}}</option>{% endfor %}</select>
      <input type="date" id="ra-fi" style="max-width:160px">
      <button class="btn-s" onclick="guardarRA()">💾 GUARDAR</button>
    </div>
    <div id="ra-msg"></div>
  </div>
</div>

<div id="tc-tripletas" class="tc">
  <div class="fbox">
    <h3>🔮 TRIPLETAS HOY</h3>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center">
      <!-- Selector de lotería para el reporte de tripletas -->
      <div style="display:flex;gap:0;border:2px solid #2a3a6a;border-radius:5px;overflow:hidden">
        <button id="trip-adm-tab-peru" onclick="selTripAdmLot('peru')"
          style="padding:8px 16px;font-family:'Oswald',sans-serif;font-size:.78rem;letter-spacing:1px;cursor:pointer;border:none;background:#0c4a9e;color:#e0f0ff;font-weight:700">
          🇵🇪 ZOOLO PERÚ<br><span style="font-size:.6rem;opacity:.8">11 sorteos · 8AM–6PM</span>
        </button>
        <button id="trip-adm-tab-plus" onclick="selTripAdmLot('plus')"
          style="padding:8px 16px;font-family:'Oswald',sans-serif;font-size:.78rem;letter-spacing:1px;cursor:pointer;border:none;background:#0c1020;color:#4a6090">
          🎰 ZOOLO PLUS<br><span style="font-size:.6rem;opacity:.8">12 sorteos · 8AM–7PM VEN</span>
        </button>
        <button id="trip-adm-tab-todas" onclick="selTripAdmLot('todas')"
          style="padding:8px 16px;font-family:'Oswald',sans-serif;font-size:.78rem;letter-spacing:1px;cursor:pointer;border:none;background:#0c1020;color:#4a6090">
          📋 TODAS
        </button>
      </div>
      <button class="btn-s" onclick="cargarTrip()" style="margin-left:4px">🔄 ACTUALIZAR</button>
    </div>
    <div id="tri-stats" style="margin-bottom:10px"></div>
    <div id="tri-lista" style="max-height:600px;overflow-y:auto"></div>
  </div>
</div>

<div id="tc-riesgo" class="tc">
  <div class="fbox">
    <h3>⚠️ RIESGO EN TIEMPO REAL (cierra 5 min antes)</h3>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center">
      <select id="riesgo-loteria-sel" onchange="cargarRiesgo()" style="padding:8px 12px;background:#0a1828;border:2px solid #a855f7;border-radius:3px;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600">
        <option value="peru">🇵🇪 PERU</option>
        <option value="plus">🎰 PLUS</option>
      </select>
      <select id="riesgo-hora-sel" style="padding:8px 12px;background:#0a1828;border:2px solid #2a4a80;border-radius:3px;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600">
        {% for h in horarios %}<option value="{{h}}">{{h}}</option>{% endfor %}
      </select>
      <button class="btn-s" onclick="cargarRiesgo()">🔄 ACTUALIZAR</button>
      <div id="riesgo-info" style="color:var(--gold);font-family:'Oswald',sans-serif;font-size:.8rem;letter-spacing:1px"></div>
    </div>
    <div id="riesgo-lista" style="max-height:420px;overflow-y:auto;margin-bottom:10px"></div>
    <div id="riesgo-agencias-btns" style="display:flex;flex-wrap:wrap;gap:6px;padding-top:10px;border-top:1px solid #1a2a50"></div>
    <div id="riesgo-agencia-detalle" style="margin-top:10px"></div>
  </div>
</div>

<div id="tc-topes" class="tc">
  <div class="fbox">
    <h3>🛡️ GESTIÓN DE TOPES POR NÚMERO</h3>
    <div style="color:var(--text2);font-size:.78rem;margin-bottom:12px">Si no hay tope configurado = JUGADA LIBRE (cualquier monto). Tope 0 = elimina tope.</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center">
      <select id="tope-loteria-sel" onchange="cargarTopes()" style="padding:8px 12px;background:#0a1828;border:2px solid #a855f7;border-radius:3px;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600">
        <option value="peru">🇵🇪 PERU</option>
        <option value="plus">🎰 PLUS</option>
      </select>
      <select id="tope-hora-sel" style="padding:8px 12px;background:#0a1828;border:2px solid #2a4a80;border-radius:3px;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600">
        {% for h in horarios %}<option value="{{h}}">{{h}}</option>{% endfor %}
      </select>
      <button class="btn-s" onclick="cargarTopes()">🔄 VER TOPES</button>
      <button class="btn-d" onclick="limpiarTopesHora()">🗑 LIMPIAR HORA</button>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center">
      <select id="tope-num" style="padding:8px 12px;background:#0a1828;border:2px solid #2a4a80;border-radius:3px;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600;flex:1;min-width:160px">
        {% for k,v in animales.items() %}<option value="{{k}}">{{k}} — {{v}}</option>{% endfor %}
      </select>
      <input type="number" id="tope-monto" placeholder="Monto tope (0=libre)" min="0" step="1" style="width:160px;padding:8px 10px;background:#0a1828;border:2px solid #d97706;border-radius:3px;color:#fbbf24;font-family:'Oswald',sans-serif;font-size:.9rem;text-align:center">
      <button class="btn-s" onclick="guardarTope()">💾 GUARDAR TOPE</button>
    </div>
    <div id="tope-msg" style="margin-bottom:8px"></div>
    <div id="topes-lista" style="max-height:500px;overflow-y:auto"></div>
  </div>
</div>

<div id="tc-reportes" class="tc">
  <div class="fbox">
    <h3>📈 REPORTE GLOBAL POR RANGO</h3>
    <div class="frow">
      <input type="date" id="rep-ini"><input type="date" id="rep-fin">
      <button class="btn-s" onclick="generarReporte()">GENERAR</button>
      <button class="btn-sec" onclick="exportarCSV()">📥 CSV</button>
    </div>
    <div id="rep-out" style="display:none">
      <div class="sgrid" style="margin-top:12px">
        <div class="sc"><h3>VENTAS</h3><p id="rv">--</p></div>
        <div class="sc"><h3>PREMIOS</h3><p id="rp" class="r">--</p></div>
        <div class="sc"><h3>COMISIÓN</h3><p id="rc">--</p></div>
        <div class="sc"><h3>BALANCE</h3><p id="rb">--</p></div>
      </div>
      <div style="overflow-x:auto;margin-top:10px"><table>
        <thead><tr><th>Fecha</th><th>Tickets</th><th>Ventas</th><th>Premios</th><th>Comisión</th><th>Balance</th></tr></thead>
        <tbody id="rep-tbody"></tbody>
      </table></div>
      <h4 style="color:var(--gold);margin:14px 0 8px;font-family:'Oswald',sans-serif;letter-spacing:2px;font-size:.8rem">POR AGENCIA</h4>
      <div id="rep-ags"></div>
    </div>
  </div>
  <div class="fbox">
    <h3>📊 REPORTE DETALLADO POR AGENCIA</h3>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center">
      <select id="rep-ag-sel" style="flex:1;min-width:180px;padding:9px 11px;background:#0a1828;border:2px solid #2a4a80;border-radius:3px;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600">
        <option value="">— Seleccione agencia —</option>
      </select>
      <input type="date" id="rep-ag-ini">
      <input type="date" id="rep-ag-fin">
      <button class="btn-s" onclick="reporteAgenciaHoras()">VER DETALLE</button>
    </div>
    <div id="rep-ag-out"></div>
  </div>
</div>

<div id="tc-agencias" class="tc">
  <div class="fbox">
    <h3>➕ NUEVA AGENCIA</h3>
    <div class="frow">
      <input type="text" id="ag-u" placeholder="Usuario">
      <input type="password" id="ag-p" placeholder="Contraseña">
      <input type="text" id="ag-n" placeholder="Nombre agencia">
      <input type="text" id="ag-nb" placeholder="Nombre banquero/grupo (ticket)">
      <button class="btn-s" onclick="crearAg()">CREAR</button>
    </div>
    <div id="ag-msg"></div>
  </div>
  <div class="fbox">
    <h3>🏪 AGENCIAS</h3>
    <button class="btn-sec" onclick="cargarAgs()" style="margin-bottom:8px">🔄 Actualizar</button>
    <div style="overflow-x:auto"><table>
      <thead><tr><th>ID</th><th>Usuario</th><th>Nombre</th><th>Comisión %</th><th>Tope Taquilla S/</th><th>Estado</th><th>Acción</th></tr></thead>
      <tbody id="tabla-ags"></tbody>
    </table></div>
  </div>
  <div class="fbox" id="edit-ag-box" style="display:none">
    <h3>✏️ EDITAR AGENCIA</h3>
    <div class="frow">
      <input type="text" id="edit-ag-nombre" placeholder="Nombre agencia" readonly style="color:var(--gold)">
      <input type="text" id="edit-ag-banco" placeholder="Nombre banquero/grupo (ticket)">
      <input type="password" id="edit-ag-pass" placeholder="Nueva contraseña (vacío=no cambiar)">
      <input type="number" id="edit-ag-com" placeholder="Comisión %" min="0" max="100" step="1">
      <input type="number" id="edit-ag-tope" placeholder="Tope taquilla S/ (0=sin límite)" min="0" step="10">
    </div>
    <div style="display:flex;gap:6px;flex-wrap:wrap">
      <button class="btn-s" onclick="guardarEditAg()">💾 GUARDAR CAMBIOS</button>
      <button class="btn-sec" onclick="document.getElementById('edit-ag-box').style.display='none'">CANCELAR</button>
      <button class="btn-sec" onclick="eliminarAgDesdeEdit()" style="background:#7f1d1d;border-color:#ef4444;color:#fca5a5;margin-left:auto">🗑️ ELIMINAR AGENCIA</button>
    </div>
    <input type="hidden" id="edit-ag-id">
    <div id="edit-ag-msg" style="margin-top:6px"></div>
  </div>
</div>

<div id="tc-operaciones" class="tc">
  <div class="fbox">
    <h3>💰 VERIFICAR / PAGAR</h3>
    <div class="frow"><input type="text" id="op-ser" placeholder="Serial"><button class="btn-s" onclick="verificarAdm()">VERIFICAR</button></div>
    <div id="op-res"></div>
  </div>
  <div class="fbox">
    <h3>❌ ANULAR (ADMIN)</h3>
    <div class="frow"><input type="text" id="an-ser" placeholder="Serial"><button class="btn-d" onclick="anularAdm()">ANULAR</button></div>
    <div id="an-res"></div>
  </div>
</div>

<div id="tc-auditoria" class="tc">
  <div class="fbox">
    <h3>📋 REGISTRO DE AUDITORÍA</h3>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center">
      <input type="date" id="aud-ini">
      <input type="date" id="aud-fin">
      <input type="text" id="aud-filtro" placeholder="Filtrar (usuario, acción...)" style="flex:1;min-width:140px;padding:9px 11px;background:#0a1828;border:2px solid #2a4a80;border-radius:3px;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600">
      <button class="btn-s" onclick="cargarAudit()">🔍 BUSCAR</button>
    </div>
    <div id="aud-res" style="color:var(--text2);font-size:.75rem;margin-bottom:8px"></div>
    <div style="overflow-x:auto;max-height:600px;overflow-y:auto">
      <table>
        <thead><tr><th>#</th><th>Fecha/Hora</th><th>Agencia/Usuario</th><th>Acción</th><th>Detalle</th><th>IP</th></tr></thead>
        <tbody id="aud-tbody"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
const ANIMALES = {{ animales | tojson }};
const ANIMALES_ADM = ANIMALES;  // alias para uso en panel de tripletas
const HORARIOS = {{ horarios | tojson }};
const HORARIOS_PLUS = {{ horarios_plus | tojson }};
const TABS=['dashboard','resultados','tripletas','riesgo','topes','reportes','agencias','operaciones','auditoria'];

function showTab(id){
  TABS.forEach(t=>{
    document.getElementById('tc-'+t).classList.toggle('active',t===id);
    document.querySelectorAll('.tab')[TABS.indexOf(t)].classList.toggle('active',t===id);
  });
  if(id==='dashboard') cargarDash();
  if(id==='resultados'){setHoy('ra-fecha');setHoy('ra-fi');cargarRA();}
  if(id==='tripletas'){ selTripAdmLot(tripAdmLotActiva||'peru'); }
  if(id==='riesgo') cargarRiesgo();
  if(id==='topes') cargarTopes();
  if(id==='agencias'){cargarAgs();cargarAgsSel();}
  if(id==='auditoria'){setHoy('aud-ini');setHoy('aud-fin');cargarAudit();}
}
function setHoy(id){let e=document.getElementById(id);if(e)e.value=new Date().toISOString().split('T')[0];}
function showMsg(id,msg,t){let e=document.getElementById(id);e.innerHTML=`<div class="msg ${t}">${msg}</div>`;setTimeout(()=>e.innerHTML='',4000);}
function glMsg(msg,t){let e=document.getElementById('glmsg');e.innerHTML=`<div class="msg ${t}" style="box-shadow:0 4px 20px rgba(0,0,0,.8)">${msg}</div>`;e.style.display='block';setTimeout(()=>e.style.display='none',4000);}

function cargarDash(){
  fetch('/admin/reporte-agencias').then(r=>r.json()).then(d=>{
    if(d.error)return;
    document.getElementById('d-v').textContent='S/'+d.global.ventas.toFixed(2);
    document.getElementById('d-p').textContent='S/'+d.global.pagos.toFixed(2);
    document.getElementById('d-c').textContent='S/'+d.global.comisiones.toFixed(2);
    let bp=document.getElementById('d-b'); bp.textContent='S/'+d.global.balance.toFixed(2);
    bp.className=d.global.balance>=0?'g':'r';
    let html=d.agencias.length?'':'<p style="color:var(--text2);text-align:center;padding:20px;font-size:.78rem;letter-spacing:2px">SIN ACTIVIDAD HOY</p>';
    d.agencias.forEach(ag=>{
      html+=`<div class="rank-item">
        <div><b style="color:var(--gold);font-family:'Oswald',sans-serif">${ag.nombre}</b>
          <span style="color:var(--text2);font-size:.72rem;margin-left:6px">${ag.usuario} — ${ag.tickets} tickets</span></div>
        <div style="text-align:right">
          <div style="color:var(--green);font-family:'Oswald',sans-serif">S/${ag.ventas.toFixed(2)}</div>
          <div style="color:${ag.balance>=0?'var(--green)':'var(--red)'};font-size:.82rem">Bal: S/${ag.balance.toFixed(2)}</div>
        </div>
      </div>`;
    });
    document.getElementById('dash-ags').innerHTML=html;
  });
}

function cargarRA(){
  let f=document.getElementById('ra-fecha').value; if(!f)return;
  let loteria=document.getElementById('ra-loteria').value||'peru';
  let c=document.getElementById('ra-lista');
  c.innerHTML='<p style="color:var(--text2);text-align:center;padding:12px;font-size:.75rem;letter-spacing:2px">CARGANDO...</p>';
  fetch('/api/resultados-fecha-admin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha:f,loteria:loteria})})
  .then(r=>r.json()).then(d=>{
    if(d.error){c.innerHTML=`<p style="color:var(--red);text-align:center;padding:12px">${d.error}</p>`;return;}
    let horarios = loteria==='plus' ? HORARIOS_PLUS : HORARIOS;
    let lot_label = loteria==='plus' ? '🎰 PLUS' : '🇵🇪 PERU';
    let html=`<div style="color:${loteria==='plus'?'#a855f7':'#0ea5e9'};font-family:'Oswald',sans-serif;font-size:.72rem;letter-spacing:2px;padding:4px 0 8px;margin-bottom:4px">${lot_label}</div>`;
    horarios.forEach(h=>{
      let res=d.resultados[h];
      html+=`<div class="ri ${res?'ok':''}">
        <span style="color:var(--gold);font-weight:700;font-family:'Oswald',sans-serif;font-size:.82rem">${h}</span>
        <div style="display:flex;align-items:center;gap:8px">
          ${res?`<span style="color:var(--green);font-weight:600">${res.animal} — ${res.nombre}</span>`:'<span style="color:#4a6090;font-size:.78rem">PENDIENTE</span>'}
          <button class="btn-edit" onclick="preRA('${h}','${f}','${res?res.animal:''}','${loteria}')">${res?'✏️ Editar':'➕ Cargar'}</button>
        </div>
      </div>`;
    });
    c.innerHTML=html;
  }).catch(()=>{c.innerHTML='<p style="color:var(--red);text-align:center;padding:12px">Error de conexión</p>';});
}
function actualizarHorasAdmin(){
  let lot=document.getElementById('ra-lot-manual').value||'peru';
  let sel=document.getElementById('ra-hora');
  let horarios = lot==='plus' ? HORARIOS_PLUS : HORARIOS;
  sel.innerHTML = horarios.map(h=>`<option value="${h}">${h}</option>`).join('');
}
function preRA(h, f, a, lot){
  let lotEl=document.getElementById('ra-lot-manual');
  if(lotEl && lot) { lotEl.value=lot; actualizarHorasAdmin(); }
  document.getElementById('ra-hora').value = h;
  document.getElementById('ra-fi').value = f;
  if(a && a !== '') document.getElementById('ra-animal').value = a;
  document.querySelector('#tc-resultados .fbox:last-child').scrollIntoView({behavior:'smooth'});
  showMsg('ra-msg', `✏️ Editando ${h} (${lot||'peru'}) — selecciona el animal y guarda`, 'ok');
}
function guardarRA(){
  let hora=document.getElementById('ra-hora').value;
  let animal=document.getElementById('ra-animal').value;
  let fecha=document.getElementById('ra-fi').value;
  let loteria=document.getElementById('ra-lot-manual').value||'peru';
  let form=new FormData();
  form.append('hora',hora); form.append('animal',animal); form.append('loteria',loteria);
  if(fecha) form.append('fecha',fecha);
  fetch('/admin/guardar-resultado',{method:'POST',body:form}).then(r=>r.json()).then(d=>{
    if(d.status==='ok'){showMsg('ra-msg','✅ '+d.mensaje,'ok');cargarRA();}
    else showMsg('ra-msg','❌ '+d.error,'err');
  });
}

let tripAdmLotActiva = 'peru';

function selTripAdmLot(lot){
  tripAdmLotActiva = lot;
  // Estilos de tabs
  ['peru','plus','todas'].forEach(l=>{
    let btn = document.getElementById('trip-adm-tab-'+l);
    if(!btn) return;
    if(l===lot){
      if(l==='peru'){ btn.style.background='#0c4a9e'; btn.style.color='#e0f0ff'; btn.style.fontWeight='700'; }
      else if(l==='plus'){ btn.style.background='#6b21a8'; btn.style.color='#f3e8ff'; btn.style.fontWeight='700'; }
      else { btn.style.background='#1a3060'; btn.style.color='#a0c0ff'; btn.style.fontWeight='700'; }
    } else {
      btn.style.background='#0c1020'; btn.style.color='#4a6090'; btn.style.fontWeight='normal';
    }
  });
  cargarTrip();
}

function cargarTrip(){
  let l=document.getElementById('tri-lista');
  l.innerHTML='<p style="color:#4a6090;text-align:center;padding:12px;font-size:.75rem;letter-spacing:2px">CARGANDO...</p>';
  fetch('/admin/tripletas-hoy').then(r=>r.json()).then(d=>{
    // Filtrar por lotería activa
    let trips = d.tripletas;
    if(tripAdmLotActiva !== 'todas'){
      trips = trips.filter(tr=>( tr.loteria||'peru' ) === tripAdmLotActiva);
    }
    let ganadoras = trips.filter(t=>t.gano).length;
    let premiosFilt = trips.reduce((s,t)=>s+t.premio,0);

    let lotTitulo = tripAdmLotActiva==='plus'
      ? '🎰 ZOOLO PLUS — 12 SORTEOS (8AM–7PM VEN)'
      : tripAdmLotActiva==='todas'
        ? '📋 TODAS LAS LOTERÍAS'
        : '🇵🇪 ZOOLO PERÚ — 11 SORTEOS (8AM–6PM)';

    document.getElementById('tri-stats').innerHTML=`
      <div style="color:#6090c0;font-family:'Oswald',sans-serif;font-size:.72rem;letter-spacing:2px;margin-bottom:8px;padding:6px 10px;background:#060c1a;border-radius:3px;border-left:3px solid #2a4a8a">${lotTitulo}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <div class="sc" style="flex:1"><h3>TOTAL</h3><p>${trips.length}</p></div>
        <div class="sc" style="flex:1"><h3>GANADORAS</h3><p class="g">${ganadoras}</p></div>
        <div class="sc" style="flex:1"><h3>PREMIOS</h3><p class="r">S/${premiosFilt.toFixed(2)}</p></div>
      </div>`;

    if(!trips.length){
      l.innerHTML='<p style="color:#2a4060;text-align:center;padding:20px;font-size:.75rem;letter-spacing:2px">NO HAY TRIPLETAS PARA ESTA LOTERÍA HOY</p>';
      return;
    }

    let html='';
    trips.forEach(tr=>{
      let lot = tr.loteria||'peru';
      let isPlus = lot==='plus';
      let lotBadge = isPlus
        ? `<span style="background:#4c1d95;border:1px solid #a855f7;color:#f3e8ff;font-family:'Oswald',sans-serif;font-size:.62rem;padding:2px 7px;border-radius:3px;letter-spacing:1px">🎰 ZOOLO PLUS</span>`
        : `<span style="background:#0c2461;border:1px solid #3b9eff;color:#bae6fd;font-family:'Oswald',sans-serif;font-size:.62rem;padding:2px 7px;border-radius:3px;letter-spacing:1px">🇵🇪 ZOOLO PERÚ</span>`;
      let accentColor = isPlus ? '#a855f7' : '#3b9eff';
      let bgColor = tr.gano ? '#030e05' : (isPlus ? '#0d0620' : '#030d1a');
      let borderColor = tr.gano ? '#22c55e' : accentColor;
      let salStr = tr.salieron && tr.salieron.length
        ? tr.salieron.map(a=>`<span style="background:#1a3020;border:1px solid #22c55e;color:#4ade80;padding:1px 5px;border-radius:2px;font-family:'Oswald',sans-serif;font-size:.7rem">${a}(${ANIMALES_ADM[a]||a})</span>`).join(' ')
        : '<span style="color:#4a6090;font-style:italic">Ninguno aún</span>';

      // Sorteos que ya contaban al momento de compra (info de validez)
      let infoConteo = `<span style="color:#4a6090;font-size:.68rem">Contando desde: </span><span style="color:#fbbf24;font-family:'Oswald',sans-serif;font-size:.7rem">${tr.hora_compra}</span>`;
      let infoSorteos = `<span style="color:#4a6090;font-size:.68rem"> · Sorteos válidos: </span><span style="color:#a0c0ff;font-family:'Oswald',sans-serif;font-size:.7rem">${tr.sorteos_validos}/${tr.sorteos_totales}</span>`;

      html+=`
      <div style="padding:14px;margin:7px 0;background:${bgColor};border-left:4px solid ${borderColor};border-radius:5px;border:1px solid ${tr.gano?'#166534':(isPlus?'#3b0764':'#0c2461')}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:10px;flex-wrap:wrap">
          <div style="display:flex;flex-direction:column;gap:4px">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              ${lotBadge}
              <span style="color:#c0d8f0;font-family:'Oswald',sans-serif;font-size:.78rem;letter-spacing:1px">TRIPLETA #${tr.id} — Serial: ${tr.serial}</span>
            </div>
            <div style="color:#6090c0;font-size:.7rem">Agencia: <span style="color:#a0c0e0;font-weight:700">${tr.agencia}</span>
              <span style="color:#3a5070;margin:0 4px">·</span>
              <span style="color:#4a6090;font-size:.68rem">Comprado: </span><span style="color:#90b0d0;font-size:.7rem">${tr.fecha_compra||'?'}</span>
            </div>
          </div>
          <div style="text-align:right;flex-shrink:0">
            <div style="color:#fbbf24;font-family:'Oswald',sans-serif;font-size:.95rem;font-weight:700">S/${tr.monto} <span style="color:#6090c0;font-size:.68rem">x60</span></div>
            ${tr.gano?`<div style="color:#4ade80;font-family:'Oswald',sans-serif;font-weight:700;font-size:1.05rem">+S/${tr.premio.toFixed(2)}</div>`:''}
            ${tr.pagado?'<div style="background:#166534;color:#fff;padding:2px 6px;border-radius:3px;font-size:.62rem;font-family:\'Oswald\',sans-serif;border:1px solid #22c55e;margin-top:3px">✅ COBRADO</div>':''}
          </div>
        </div>

        <!-- Animales de la tripleta -->
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;align-items:center">
          ${[0,1,2].map(i=>`
            <div style="background:#0a0020;border:2px solid ${accentColor};border-radius:5px;padding:6px 12px;font-family:'Oswald',sans-serif;text-align:center;min-width:52px">
              <div style="color:#fbbf24;font-size:.88rem;font-weight:700">${tr['animal'+(i+1)]}</div>
              <div style="color:${isPlus?'#e0a0ff':'#90c8ff'};font-size:.68rem">${tr.nombres[i]}</div>
            </div>
            ${i<2?`<span style="color:#3a4060;font-size:1rem;align-self:center">•</span>`:''}
          `).join('')}
        </div>

        <!-- Estado de salidos -->
        <div style="background:#05080f;border:1px solid #0a1a30;border-radius:4px;padding:8px 12px">
          <div style="margin-bottom:5px;font-size:.7rem">${infoConteo}${infoSorteos}</div>
          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
            <span style="color:#4a6090;font-size:.7rem;font-family:'Oswald',sans-serif">SALIDOS:</span>
            ${salStr}
            <span style="color:#2a4060;font-size:.7rem">(${tr.salieron.length}/3)</span>
            ${tr.gano?'<span style="color:#4ade80;font-weight:700;font-family:\'Oswald\',sans-serif;font-size:.75rem;margin-left:4px">✅ ¡GANÓ TRIPLETA!</span>':''}
          </div>
        </div>
      </div>`;
    });
    l.innerHTML=html;
  }).catch(()=>{
    document.getElementById('tri-lista').innerHTML='<div class="msg err">Error cargando tripletas</div>';
  });
}

function cargarRiesgo(){
  let hora = document.getElementById('riesgo-hora-sel').value;
  let loteria = document.getElementById('riesgo-loteria-sel').value||'peru';
  // Update hora options based on loteria
  let hSel=document.getElementById('riesgo-hora-sel');
  let horas = loteria==='plus' ? HORARIOS_PLUS : HORARIOS;
  let curVal = hSel.value;
  hSel.innerHTML = horas.map(h=>`<option value="${h}">${h}</option>`).join('');
  if(horas.includes(curVal)) hSel.value=curVal;
  hora = hSel.value;
  fetch('/admin/riesgo?hora='+encodeURIComponent(hora)+'&loteria='+loteria).then(r=>r.json()).then(d=>{
    // Auto-select sorteo objetivo en el selector si no se ha elegido manualmente
    if(d.sorteo_objetivo && !hora){
      document.getElementById('riesgo-hora-sel').value = d.sorteo_objetivo;
    }
    document.getElementById('riesgo-info').innerHTML=
      `<span style="background:#0d1828;border:2px solid #2a4a80;border-radius:3px;padding:4px 10px;font-size:.8rem">
        ⏱ SORTEO: <b style="color:#fbbf24">${d.sorteo_objetivo||'N/A'}</b>
        &nbsp;|&nbsp; CIERRE: <b style="color:#f87171">${d.minutos_cierre||3} min antes (al :57)</b>
        &nbsp;|&nbsp; 💰 TOTAL: <b style="color:#f87171">S/${(d.total_apostado||0).toFixed(2)}</b>
      </span>`;
    let l=document.getElementById('riesgo-lista');
    let riesgo=d.riesgo||{};
    let keys=Object.keys(riesgo);
    if(!keys.length){
      l.innerHTML='<p style="color:#2a4060;text-align:center;padding:20px;font-size:.75rem;letter-spacing:2px">SIN APUESTAS PARA ESE SORTEO</p>';
    } else {
      // Ordered by number ascending (already ordered from backend)
      let html='';
      for(let num of keys){
        let v=riesgo[num];
        let barW=Math.min(v.porcentaje*3,100);
        let bc=v.es_lechuza?'#d97706':'#1a3a90';
        let tc2=v.es_lechuza?'#fbbf24':'#90b8ff';
        let topeInfo = v.libre
          ? `<span style="color:#22c55e;font-size:.68rem;font-family:'Oswald',sans-serif">LIBRE</span>`
          : `<span style="color:${v.tope>0?'#f87171':'#22c55e'};font-size:.68rem;font-family:'Oswald',sans-serif">TOPE: S/${v.tope}</span>`;
        html+=`<div style="padding:8px 12px;margin:3px 0;background:#0d1828;border-left:4px solid ${v.es_lechuza?'#d97706':'#2060d0'};border-radius:4px;border:1px solid ${bc}">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <b style="color:${tc2};font-family:'Oswald',sans-serif;font-size:.83rem">${num} — ${v.nombre}${v.es_lechuza?' 🦉 x70':''}</b>
            <div style="display:flex;gap:8px;align-items:center">
              ${topeInfo}
              <span style="background:${bc};color:#fff;padding:2px 8px;border-radius:3px;font-family:'Oswald',sans-serif;font-size:.72rem;font-weight:700">${v.porcentaje}%</span>
            </div>
          </div>
          <div style="display:flex;gap:12px;font-size:.78rem;margin-bottom:4px">
            <span style="color:#6090c0">Apostado: <b style="color:#fbbf24">S/${v.apostado.toFixed(2)}</b></span>
            <span style="color:#6090c0">Pagaría: <b style="color:#f87171">S/${v.pagaria.toFixed(2)}</b></span>
          </div>
          <div style="background:#060c1a;border-radius:2px;height:5px;overflow:hidden">
            <div style="background:${v.es_lechuza?'#d97706':'#2060d0'};height:100%;width:${barW}%;border-radius:2px"></div>
          </div>
        </div>`;
      }
      l.innerHTML=html;
    }
    // Botones de agencias que vendieron en esa hora
    let btns=document.getElementById('riesgo-agencias-btns');
    let ags=d.agencias_hora||[];
    if(!ags.length){
      btns.innerHTML='<span style="color:#2a4060;font-size:.75rem;font-family:\'Oswald\',sans-serif;letter-spacing:1px">SIN AGENCIAS CON VENTAS EN ESTA HORA</span>';
    } else {
      btns.innerHTML='<span style="color:#4a6090;font-size:.7rem;font-family:\'Oswald\',sans-serif;letter-spacing:1px;margin-right:6px">AGENCIAS:</span>';
      ags.forEach(ag=>{
        let btn=document.createElement('button');
        btn.className='btn-sec';
        btn.textContent=ag.nombre_agencia;
        btn.style.fontSize='.72rem';
        btn.onclick=()=>verAgenciaRiesgo(ag.id, ag.nombre_agencia, d.hora_seleccionada);
        btns.appendChild(btn);
      });
    }
    document.getElementById('riesgo-agencia-detalle').innerHTML='';
  }).catch(()=>glMsg('Error cargando riesgo','err'));
}

function verAgenciaRiesgo(agid, nombre, hora){
  let det=document.getElementById('riesgo-agencia-detalle');
  det.innerHTML=`<p style="color:#4a6090;text-align:center;padding:10px;font-size:.75rem;letter-spacing:2px">CARGANDO ${nombre}...</p>`;
  fetch('/admin/riesgo-agencia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agencia_id:agid,hora:hora})})
  .then(r=>r.json()).then(d=>{
    if(d.error){det.innerHTML=`<div class="msg err">${d.error}</div>`;return;}
    let html=`<div style="background:#0d1020;border:1px solid #2a4a80;border-radius:4px;padding:12px;margin-top:8px">
      <div style="color:#00d8ff;font-family:'Oswald',sans-serif;font-size:.8rem;letter-spacing:2px;margin-bottom:10px">
        🏪 ${d.agencia} — ${d.hora}
      </div>`;
    if(!d.jugadas.length){
      html+='<p style="color:#2a4060;font-size:.75rem">Sin jugadas</p>';
    } else {
      d.jugadas.forEach(j=>{
        let col=j.tipo==='animal'?'#4ade80':'#60a5fa';
        html+=`<div style="display:flex;justify-content:space-between;align-items:center;padding:5px 8px;margin:2px 0;background:#060c1a;border-radius:3px;border-left:3px solid ${col};font-size:.78rem">
          <span style="color:${col};font-family:'Oswald',sans-serif;font-weight:700;min-width:50px">${j.seleccion}</span>
          <span style="flex:1;color:#c0d8f0">${j.nombre}</span>
          <span style="color:#fbbf24;font-family:'Oswald',sans-serif">S/${j.apostado.toFixed(2)}</span>
          ${j.pagaria>0?`<span style="color:#f87171;font-size:.7rem;margin-left:8px">→S/${j.pagaria.toFixed(2)}</span>`:''}
          <span style="color:#4a6090;font-size:.68rem;margin-left:8px">${j.tickets}t</span>
        </div>`;
      });
    }
    html+='</div>';
    det.innerHTML=html;
  }).catch(()=>{det.innerHTML='<div class="msg err">Error</div>';});
}

// ---- TOPES ----
function cargarTopes(){
  let hora=document.getElementById('tope-hora-sel').value;
  let loteria=document.getElementById('tope-loteria-sel').value||'peru';
  // Update hora options based on loteria
  let hSel=document.getElementById('tope-hora-sel');
  let horas = loteria==='plus' ? HORARIOS_PLUS : HORARIOS;
  let curVal = hSel.value;
  hSel.innerHTML = horas.map(h=>`<option value="${h}">${h}</option>`).join('');
  if(horas.includes(curVal)) hSel.value=curVal; else hora=horas[0];
  hora = hSel.value;
  fetch('/admin/topes?hora='+encodeURIComponent(hora)+'&loteria='+loteria).then(r=>r.json()).then(d=>{
    if(d.error){glMsg(d.error,'err');return;}
    let l=document.getElementById('topes-lista');
    if(!d.topes.length){
      l.innerHTML='<p style="color:#2a4060;text-align:center;padding:20px;font-size:.75rem;letter-spacing:2px">SIN APUESTAS NI TOPES PARA ESTA HORA</p>';
      return;
    }
    let html='<table><thead><tr><th>#</th><th>Animal</th><th>Apostado Hoy</th><th>Tope</th><th>Disponible</th><th>Acción</th></tr></thead><tbody>';
    d.topes.forEach(t=>{
      let estado = t.libre
        ? `<span style="color:#22c55e;font-family:'Oswald',sans-serif;font-size:.75rem">LIBRE</span>`
        : `<span style="color:#fbbf24;font-family:'Oswald',sans-serif;font-size:.75rem">S/${t.tope}</span>`;
      let disp = t.libre ? `<span style="color:#3a5060">—</span>`
        : `<span style="color:${t.disponible>0?'#4ade80':'#f87171'};font-weight:700;font-family:'Oswald',sans-serif">S/${t.disponible}</span>`;
      html+=`<tr>
        <td><b style="color:#fbbf24;font-family:'Oswald',sans-serif">${t.numero}</b></td>
        <td style="color:#c0d8f0">${t.nombre}</td>
        <td style="color:${t.apostado>0?'#f97316':'#3a5060'};font-family:'Oswald',sans-serif">S/${t.apostado}</td>
        <td>${estado}</td>
        <td>${disp}</td>
        <td><button class="btn-edit" onclick="preEditTope('${t.numero}',${t.tope})">✏️</button></td>
      </tr>`;
    });
    html+='</tbody></table>';
    l.innerHTML=html;
  });
}

function preEditTope(num, tope){
  document.getElementById('tope-num').value=num;
  document.getElementById('tope-monto').value=tope||'';
  document.getElementById('tope-monto').focus();
}

function guardarTope(){
  let hora=document.getElementById('tope-hora-sel').value;
  let num=document.getElementById('tope-num').value;
  let monto=parseFloat(document.getElementById('tope-monto').value)||0;
  let loteria=document.getElementById('tope-loteria-sel').value||'peru';
  fetch('/admin/topes/guardar',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({hora,numero:num,monto,loteria})})
  .then(r=>r.json()).then(d=>{
    if(d.status==='ok'){
      showMsg('tope-msg',monto>0?`✅ Tope S/${monto} guardado para ${num}`:'✅ Tope eliminado (jugada libre)','ok');
      cargarTopes();
    } else showMsg('tope-msg','❌ '+d.error,'err');
  });
}

function limpiarTopesHora(){
  let hora=document.getElementById('tope-hora-sel').value;
  let loteria=document.getElementById('tope-loteria-sel').value||'peru';
  if(!confirm(`¿Eliminar todos los topes de ${hora} (${loteria.toUpperCase()})?`))return;
  fetch('/admin/topes/limpiar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hora,loteria})})
  .then(r=>r.json()).then(d=>{
    if(d.status==='ok'){glMsg('✅ '+d.mensaje,'ok');cargarTopes();}
    else glMsg('❌ '+d.error,'err');
  });
}

// ---- REPORTE AGENCIA POR HORAS ----
function cargarAgsSel(){
  fetch('/admin/lista-agencias').then(r=>r.json()).then(d=>{
    let sel=document.getElementById('rep-ag-sel');
    if(!sel)return;
    sel.innerHTML='<option value="">— Seleccione agencia —</option>';
    d.forEach(a=>{sel.innerHTML+=`<option value="${a.id}">${a.nombre_agencia} (${a.usuario})</option>`;});
  });
}

function reporteAgenciaHoras(){
  let agid=document.getElementById('rep-ag-sel').value;
  let ini=document.getElementById('rep-ag-ini').value;
  let fin=document.getElementById('rep-ag-fin').value;
  if(!agid){glMsg('Seleccione agencia','err');return;}
  if(!ini||!fin){glMsg('Seleccione fechas','err');return;}
  let out=document.getElementById('rep-ag-out');
  out.innerHTML='<p style="color:#4a6090;text-align:center;padding:12px;font-size:.75rem;letter-spacing:2px">CARGANDO...</p>';
  fetch('/admin/reporte-agencia-horas',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({agencia_id:agid,fecha_inicio:ini,fecha_fin:fin})})
  .then(r=>r.json()).then(d=>{
    if(d.error){out.innerHTML=`<div class="msg err">${d.error}</div>`;return;}
    let html=`<div style="color:#00d8ff;font-family:'Oswald',sans-serif;font-size:.82rem;letter-spacing:2px;margin-bottom:10px">
      🏪 ${d.agencia} (${d.usuario}) — TOTAL: <span style="color:#fbbf24">S/${d.total_general.toFixed(2)}</span>
    </div>`;
    if(!d.resumen.length){
      html+='<p style="color:#2a4060;text-align:center;padding:20px;font-size:.75rem;letter-spacing:2px">SIN DATOS EN ESE PERÍODO</p>';
    } else {
      d.resumen.forEach(hr=>{
        html+=`<div style="background:#0d1020;border:1px solid #1a3060;border-radius:4px;padding:10px;margin-bottom:8px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;cursor:pointer" onclick="toggleDetalle(this)">
            <span style="color:#fbbf24;font-family:'Oswald',sans-serif;font-size:.85rem;font-weight:700">⏰ ${hr.hora}</span>
            <div style="display:flex;gap:12px;align-items:center">
              <span style="color:#4a6090;font-size:.72rem">${hr.conteo} jugadas</span>
              <span style="color:#4ade80;font-family:'Oswald',sans-serif;font-weight:700">S/${hr.total.toFixed(2)}</span>
              <span style="color:#4a6090;font-size:.72rem">▼</span>
            </div>
          </div>
          <div class="detalle-hr" style="display:none">`;
        hr.jugadas.forEach(j=>{
          let col=j.tipo==='animal'?'#4ade80':'#60a5fa';
          html+=`<div style="display:flex;gap:8px;padding:4px 6px;font-size:.75rem;border-left:2px solid ${col};margin-bottom:2px;background:#060c1a;border-radius:2px">
            <span style="color:${col};font-family:'Oswald',sans-serif;font-weight:700;min-width:30px">${j.seleccion}</span>
            <span style="flex:1;color:#c0d8f0">${j.nombre}</span>
            <span style="color:#fbbf24;font-family:'Oswald',sans-serif">S/${j.apostado.toFixed(2)}</span>
            <span style="color:#4a6090;font-size:.68rem">${j.cnt}x</span>
          </div>`;
        });
        html+='</div></div>';
      });
    }
    out.innerHTML=html;
  }).catch(()=>{out.innerHTML='<div class="msg err">Error de conexión</div>';});
}

function toggleDetalle(header){
  let d=header.nextElementSibling;
  let arrow=header.querySelector('span:last-child');
  if(d.style.display==='none'){d.style.display='block';if(arrow)arrow.textContent='▲';}
  else{d.style.display='none';if(arrow)arrow.textContent='▼';}
}

// ---- AUDITORÍA ----
function cargarAudit(){
  let ini=document.getElementById('aud-ini').value;
  let fin=document.getElementById('aud-fin').value;
  let filtro=document.getElementById('aud-filtro').value;
  fetch('/admin/audit-logs',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin,filtro:filtro,limit:300})})
  .then(r=>r.json()).then(d=>{
    if(d.error){glMsg(d.error,'err');return;}
    document.getElementById('aud-res').textContent=`${d.total} registros encontrados`;
    let tb=document.getElementById('aud-tbody'); tb.innerHTML='';
    let colores={'LOGIN':'#22c55e','VENTA':'#60a5fa','PAGO':'#fbbf24','ANULACION':'#f87171',
      'RESULTADO':'#c084fc','TOPE_SET':'#fb923c','TOPE_LIBRE':'#22c55e','TOPES_LIMPIAR':'#f87171',
      'EDITAR_AGENCIA':'#a78bfa','LOGIN_FAIL':'#f87171'};
    d.logs.forEach(l=>{
      let col=colores[l.accion]||'#6090c0';
      tb.innerHTML+=`<tr>
        <td style="color:#4a6090;font-size:.7rem">${l.id}</td>
        <td style="color:#4a6090;font-size:.72rem;white-space:nowrap">${l.fecha||''}</td>
        <td style="color:#a0c0e0">${l.agencia}</td>
        <td><span style="background:rgba(0,0,0,.3);color:${col};border:1px solid ${col};padding:2px 6px;border-radius:3px;font-size:.68rem;font-family:'Oswald',sans-serif;letter-spacing:1px">${l.accion}</span></td>
        <td style="color:#c0d8f0;font-size:.75rem">${l.detalle}</td>
        <td style="color:#3a5060;font-size:.68rem">${l.ip}</td>
      </tr>`;
    });
  }).catch(()=>glMsg('Error','err'));
}

function generarReporte(){
  let ini=document.getElementById('rep-ini').value; let fin=document.getElementById('rep-fin').value;
  if(!ini||!fin){glMsg('Seleccione fechas','err');return;}
  glMsg('Generando...','ok');
  Promise.all([
    fetch('/admin/estadisticas-rango',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin})}).then(r=>r.json()),
    fetch('/admin/reporte-agencias-rango',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin})}).then(r=>r.json())
  ]).then(([est,ag])=>{
    document.getElementById('rep-out').style.display='block';
    document.getElementById('rv').textContent='S/'+est.totales.ventas.toFixed(2);
    document.getElementById('rp').textContent='S/'+est.totales.premios.toFixed(2);
    document.getElementById('rc').textContent='S/'+est.totales.comisiones.toFixed(2);
    let rb=document.getElementById('rb'); rb.textContent='S/'+est.totales.balance.toFixed(2); rb.className=est.totales.balance>=0?'g':'r';
    let tb=document.getElementById('rep-tbody'); tb.innerHTML='';
    est.resumen_por_dia.forEach(d=>{
      let col=d.balance>=0?'var(--green)':'var(--red)';
      tb.innerHTML+=`<tr><td>${d.fecha}</td><td>${d.tickets}</td><td>S/${d.ventas.toFixed(2)}</td><td>S/${d.premios.toFixed(2)}</td><td>S/${d.comisiones.toFixed(2)}</td><td style="color:${col};font-weight:700;font-family:'Oswald',sans-serif">S/${d.balance.toFixed(2)}</td></tr>`;
    });
    let agHtml='';
    if(ag.agencias) ag.agencias.forEach(a=>{
      agHtml+=`<div class="rank-item">
        <div><b style="color:var(--gold);font-family:'Oswald',sans-serif">${a.nombre}</b>
          <span style="color:var(--text2);font-size:.72rem;margin-left:6px">${a.usuario} | ${a.tickets}t | ${a.porcentaje_ventas||0}%</span></div>
        <div style="text-align:right">
          <div style="color:var(--text);font-size:.85rem">S/${a.ventas.toFixed(2)}</div>
          <div style="color:${a.balance>=0?'var(--green)':'var(--red)'};font-family:'Oswald',sans-serif">S/${a.balance.toFixed(2)}</div>
        </div>
      </div>`;
    });
    document.getElementById('rep-ags').innerHTML=agHtml;
    glMsg('Reporte generado','ok');
  }).catch(()=>glMsg('Error','err'));
}

function exportarCSV(){
  let ini=document.getElementById('rep-ini').value; let fin=document.getElementById('rep-fin').value;
  if(!ini||!fin){glMsg('Seleccione fechas','err');return;}
  fetch('/admin/exportar-csv',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin})})
  .then(r=>r.blob()).then(b=>{let a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=`zoolo_${ini}_${fin}.csv`;a.click();});
}

function cargarAgs(){
  fetch('/admin/lista-agencias').then(r=>r.json()).then(d=>{
    let t=document.getElementById('tabla-ags'); t.innerHTML='';
    if(!d.length){t.innerHTML='<tr><td colspan="8" style="text-align:center;color:var(--text2);padding:16px">SIN AGENCIAS</td></tr>';return;}
    d.forEach(a=>{
      let tope=a.tope_taquilla>0?`<span style="color:#fbbf24;font-family:'Oswald',sans-serif">S/${a.tope_taquilla}</span>`:`<span style="color:#22c55e;font-size:.75rem">SIN LÍMITE</span>`;
      let banco=a.nombre_banco?`<span style="color:#a0cfff;font-size:.75rem">${a.nombre_banco}</span>`:`<span style="color:#4a6090;font-size:.72rem">—</span>`;
      t.innerHTML+=`<tr>
        <td>${a.id}</td>
        <td>${a.usuario}</td>
        <td><b style="color:var(--gold)">${a.nombre_agencia}</b><br>${banco}</td>
        <td>${(a.comision*100).toFixed(0)}%</td>
        <td>${tope}</td>
        <td><span style="color:${a.activa?'var(--green)':'var(--red)'}">● ${a.activa?'ACTIVA':'INACTIVA'}</span></td>
        <td style="display:flex;gap:4px">
          <button class="btn-edit" onclick="abrirEditAg(${a.id},'${a.nombre_agencia}','${(a.nombre_banco||'').replace(/'/g,"\\'")}',${(a.comision*100).toFixed(0)},${a.tope_taquilla||0})">✏️ Editar</button>
          <button class="btn-sec" onclick="toggleAg(${a.id},${a.activa})" style="font-size:.7rem">${a.activa?'Desactivar':'Activar'}</button>
          <button class="btn-sec" onclick="eliminarAg(${a.id},'${a.nombre_agencia.replace(/'/g,"\\'")}')" style="font-size:.7rem;background:#7f1d1d;border-color:#ef4444;color:#fca5a5">🗑️ Eliminar</button>
        </td>
      </tr>`;
    });
  });
}

function abrirEditAg(id, nombre, banco, com, tope){
  document.getElementById('edit-ag-id').value=id;
  document.getElementById('edit-ag-nombre').value=nombre;
  document.getElementById('edit-ag-banco').value=banco||'';
  document.getElementById('edit-ag-pass').value='';
  document.getElementById('edit-ag-com').value=com;
  document.getElementById('edit-ag-tope').value=tope||0;
  document.getElementById('edit-ag-box').style.display='block';
  document.getElementById('edit-ag-msg').innerHTML='';
  document.getElementById('edit-ag-box').scrollIntoView({behavior:'smooth'});
}

function guardarEditAg(){
  let id=document.getElementById('edit-ag-id').value;
  let pass=document.getElementById('edit-ag-pass').value.trim();
  let banco=document.getElementById('edit-ag-banco').value.trim();
  let com=document.getElementById('edit-ag-com').value;
  let tope=document.getElementById('edit-ag-tope').value;
  let payload={id:parseInt(id),nombre_banco:banco};
  if(pass) payload.password=pass;
  if(com!=='') payload.comision=parseFloat(com);
  if(tope!=='') payload.tope_taquilla=parseFloat(tope);
  fetch('/admin/editar-agencia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
  .then(r=>r.json()).then(d=>{
    if(d.status==='ok'){
      showMsg('edit-ag-msg','✅ Cambios guardados','ok');
      cargarAgs();
      setTimeout(()=>{document.getElementById('edit-ag-box').style.display='none';},1500);
    } else showMsg('edit-ag-msg','❌ '+d.error,'err');
  });
}
function crearAg(){
  let u=document.getElementById('ag-u').value.trim();
  let p=document.getElementById('ag-p').value.trim();
  let n=document.getElementById('ag-n').value.trim();
  let nb=document.getElementById('ag-nb').value.trim();
  if(!u||!p||!n){showMsg('ag-msg','Complete todos los campos','err');return;}
  let form=new FormData();
  form.append('usuario',u); form.append('password',p); form.append('nombre',n); form.append('nombre_banco',nb);
  fetch('/admin/crear-agencia',{method:'POST',body:form}).then(r=>r.json()).then(d=>{
    if(d.status==='ok'){
      showMsg('ag-msg','✅ '+d.mensaje,'ok');
      document.getElementById('ag-u').value='';
      document.getElementById('ag-p').value='';
      document.getElementById('ag-n').value='';
      document.getElementById('ag-nb').value='';
      cargarAgs();
    } else showMsg('ag-msg','❌ '+d.error,'err');
  });
}
function eliminarAgDesdeEdit(){
  let id = document.getElementById('edit-ag-id').value;
  let nombre = document.getElementById('edit-ag-nombre').value;
  eliminarAg(parseInt(id), nombre);
}
function eliminarAg(id, nombre){
  if(!confirm(`⚠️ ¿Eliminar la agencia "${nombre}"?\n\nEsta acción NO se puede deshacer.\nSolo se puede eliminar si no tiene tickets activos.`)) return;
  fetch('/admin/eliminar-agencia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:parseInt(id)})})
  .then(r=>r.json()).then(d=>{
    if(d.status==='ok'){
      glMsg('✅ '+d.mensaje,'ok');
      document.getElementById('edit-ag-box').style.display='none';
      cargarAgs();
    } else glMsg('❌ '+d.error,'err');
  }).catch(()=>glMsg('❌ Error de conexión','err'));
}
function toggleAg(id,a){
  fetch('/admin/editar-agencia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,activa:!a})})
  .then(r=>r.json()).then(d=>{if(d.status==='ok')cargarAgs();else glMsg(d.error,'err');});
}

function verificarAdm(){
  let s=document.getElementById('op-ser').value.trim(); if(!s)return;
  let c=document.getElementById('op-res');
  c.innerHTML='<p style="color:#4a6090;text-align:center;padding:8px;font-size:.75rem;letter-spacing:2px">VERIFICANDO...</p>';
  fetch('/api/consultar-ticket-detalle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({serial:s})})
  .then(r=>r.json()).then(d=>{
    if(d.error){c.innerHTML=`<div class="msg err">❌ ${d.error}</div>`;return;}
    let t=d.ticket; let premio=t.premio_total||0;
    let col=premio>0?'#22c55e':'#1a2a50';

    let jhtml='';
    if(d.jugadas&&d.jugadas.length){
      jhtml+=`<div style="color:#4080c0;font-size:.65rem;font-family:'Oswald',sans-serif;letter-spacing:2px;padding:6px 0 3px;border-top:1px solid #1a2a50;margin-top:8px">JUGADAS</div>`;
      d.jugadas.forEach(j=>{
        let rn=j.resultado?(j.resultado+' '+(j.resultado_nombre||'')):'PEND';
        let lotAdm=j.loteria==='plus'
          ?`<span style="background:#3b0764;border:1px solid #a855f7;color:#e9d5ff;font-family:'Oswald',sans-serif;font-size:.58rem;padding:1px 4px;border-radius:2px;flex-shrink:0">PLUS</span>`
          :`<span style="background:#0c2461;border:1px solid #0ea5e9;color:#bae6fd;font-family:'Oswald',sans-serif;font-size:.58rem;padding:1px 4px;border-radius:2px;flex-shrink:0">PERÚ</span>`;
        jhtml+=`<div style="display:flex;align-items:center;gap:6px;padding:4px 6px;margin:2px 0;background:#060c1a;border-left:3px solid ${j.gano?'#22c55e':'#1a2a50'};border-radius:2px;font-size:.75rem">
          <span style="color:#00c8e8;font-family:'Oswald',sans-serif;font-size:.7rem;min-width:48px;font-weight:700">${(j.hora||'').replace(':00 ','').replace(' ','')}</span>
          ${lotAdm}
          <span style="flex:1;color:#c0d8f0">${j.tipo==='animal'?(j.seleccion+' '+j.nombre_seleccion):j.seleccion}</span>
          <span style="color:#6090c0">S/${j.monto}</span>
          <span style="color:${j.gano?'#4ade80':'#3a5070'};min-width:60px;text-align:right">${j.gano?'✓ '+rn:'✗ '+rn}</span>
          ${j.gano?`<span style="color:#4ade80;font-weight:700;font-family:'Oswald',sans-serif">+${j.premio}</span>`:''}
        </div>`;
      });
    }

    let thtml='';
    if(d.tripletas&&d.tripletas.length){
      thtml+=`<div style="color:#c084fc;font-size:.65rem;font-family:'Oswald',sans-serif;letter-spacing:2px;padding:6px 0 3px;border-top:1px solid #1a2a50;margin-top:6px">🎯 TRIPLETAS</div>`;
      d.tripletas.forEach(tr=>{
        let salStr=tr.salieron&&tr.salieron.length?tr.salieron.join(', '):'Ninguno';
        thtml+=`<div style="padding:8px 10px;margin:3px 0;background:#0d0620;border-left:3px solid ${tr.gano?'#c084fc':'#3b0764'};border-radius:3px;font-size:.78rem">
          <div style="display:flex;justify-content:space-between;margin-bottom:4px">
            <span style="color:#e0a0ff;font-family:'Oswald',sans-serif">${tr.animal1} ${tr.nombre1} • ${tr.animal2} ${tr.nombre2} • ${tr.animal3} ${tr.nombre3}</span>
            <span style="color:#fbbf24;font-weight:700">S/${tr.monto} x60</span>
          </div>
          <div style="font-size:.72rem">
            <span style="color:#4a6090">Salidos: </span><span style="color:${tr.gano?'#4ade80':'#8060c0'}">${salStr} (${tr.salieron.length}/3)</span>
            ${tr.gano?`<span style="color:#4ade80;font-weight:700;margin-left:8px">✅ GANÓ +S/${tr.premio.toFixed(2)}</span>`:''}
          </div>
        </div>`;
      });
    }

    c.innerHTML=`<div style="border:2px solid ${col};border-radius:5px;padding:14px;margin-top:8px;background:#060c1a">
      <div style="color:#00d8ff;font-family:'Oswald',sans-serif;letter-spacing:2px;margin-bottom:8px;font-size:.88rem">🎫 TICKET #${s}</div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <div>
          <div style="color:#4a6090;font-size:.72rem">${t.fecha}</div>
          ${t.pagado?'<div style="background:#166534;color:#fff;display:inline-block;padding:2px 8px;border-radius:3px;font-size:.7rem;font-family:\'Oswald\',sans-serif;border:1px solid #22c55e">✅ YA PAGADO</div>':''}
          ${t.anulado?'<div style="background:#991b1b;color:#fff;display:inline-block;padding:2px 8px;border-radius:3px;font-size:.7rem;font-family:\'Oswald\',sans-serif">❌ ANULADO</div>':''}
        </div>
        <div style="text-align:right">
          <div style="color:#4a6090;font-size:.7rem">APOSTADO</div>
          <div style="color:#fbbf24;font-family:'Oswald',sans-serif;font-size:1rem;font-weight:700">S/${t.total_apostado}</div>
          ${premio>0?`<div style="color:#4ade80;font-family:'Oswald',sans-serif;font-size:1.1rem;font-weight:700">PREMIO: S/${premio.toFixed(2)}</div>`:''}
        </div>
      </div>
      ${jhtml}${thtml}
      ${premio>0&&!t.pagado&&!t.anulado?`<button onclick="pagarAdm(${t.id},${premio})" style="width:100%;padding:11px;background:#166534;color:#fff;border:2px solid #22c55e;border-radius:4px;font-weight:700;cursor:pointer;font-family:'Oswald',sans-serif;letter-spacing:2px;font-size:.85rem;margin-top:10px;transition:all .15s" onmouseover="this.style.background='#15803d'" onmouseout="this.style.background='#166534'">💰 PAGAR S/${premio.toFixed(2)}</button>`:''}
      ${premio===0&&!t.pagado?`<div class="msg err" style="margin-top:8px">SIN PREMIO AÚN</div>`:''}
    </div>`;
  });
}
function pagarAdm(tid,m){
  if(!confirm(`¿Confirmar pago S/${m}?`))return;
  fetch('/api/pagar-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticket_id:tid})})
  .then(r=>r.json()).then(d=>{
    if(d.status==='ok'){glMsg('✅ Ticket pagado exitosamente','ok');document.getElementById('op-res').innerHTML='';}
    else glMsg('❌ '+d.error,'err');
  });
}
function anularAdm(){
  let s=document.getElementById('an-ser').value.trim(); if(!s)return;
  if(!confirm('¿Anular ticket '+s+'? Esta acción no se puede deshacer.'))return;
  fetch('/api/anular-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({serial:s})})
  .then(r=>r.json()).then(d=>{
    let c=document.getElementById('an-res');
    if(d.status==='ok') c.innerHTML='<div class="msg ok">✅ '+d.mensaje+'</div>';
    else c.innerHTML='<div class="msg err">❌ '+d.error+'</div>';
  });
}

document.addEventListener('DOMContentLoaded',()=>{
  let hoy=new Date().toISOString().split('T')[0];
  ['rep-ini','rep-fin','ra-fecha','ra-fi','rep-ag-ini','rep-ag-fin','aud-ini','aud-fin'].forEach(id=>{let e=document.getElementById(id);if(e)e.value=hoy;});
  cargarDash();
  cargarAgsSel();
});
</script>
</body></html>'''

if __name__ == '__main__':
    init_db()
    print("=" * 60)
    print("  ZOOLO CASINO v6.0 — DOS LOTERÍAS")
    print("=" * 60)
    db_status = 'OK' if DATABASE_URL else 'NO CONFIGURADA!'
    print(f"  DB: PostgreSQL (DATABASE_URL: {db_status})")
    print(f"  ZOOLO CASINO PERU:  11 sorteos 8AM-6PM  (hora Lima)")
    print(f"  ZOOLO CASINO PLUS:  12 sorteos 8AM-7PM  (hora Caracas)")
    print(f"  Resultados: SOLO MANUAL — el admin carga cada resultado")
    print(f"  Admin: cuborubi / 15821462")
    print("=" * 60)
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
