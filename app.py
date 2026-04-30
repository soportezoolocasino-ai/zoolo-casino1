#!/usr/bin/env python3
"""
ZOOLO CASINO LOCAL v4.0 — Auto-Sorteo + 70/30
Cambios sobre v3.1:
  - APScheduler para auto-sorteo a la hora en punto
  - Toggle ON/OFF persistente en BD (tabla config_sistema)
  - Lógica 70/30 por sorteo independiente (PERU y PLUS separados)
  - Acumulado diario por lotería (se resetea cada día)
  - Dashboard con desglose 70/30 por jornada
  - Animales no se repiten en auto-sorteo dentro del mismo día
"""

import os, json, csv, io, re, hashlib, random, logging
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, render_template_string, request, session, redirect, jsonify, Response
from collections import defaultdict
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
_db_ready = False
app.secret_key = os.environ.get('SECRET_KEY', 'zoolo_local_2025_seguro')
DATABASE_URL = os.environ.get('DATABASE_URL', '')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# ── Detección automática: SQLite local vs PostgreSQL en Render ──────────────
USE_SQLITE = not DATABASE_URL
if USE_SQLITE:
    import sqlite3
    SQLITE_PATH = os.path.join(os.path.dirname(__file__), 'zoolo_local.db')
    logger.info("[DB] Modo LOCAL — SQLite: " + SQLITE_PATH)
else:
    import psycopg2
    import psycopg2.extras
    logger.info("[DB] Modo PRODUCCIÓN — PostgreSQL")

@app.before_request
def setup():
    global _db_ready
    if not _db_ready:
        init_db()
        _db_ready = True

PAGO_ANIMAL_NORMAL = 35
PAGO_LECHUZA       = 70
PAGO_ESPECIAL      = 2
PAGO_TRIPLETA      = 60
COMISION_AGENCIA   = 0.15
MINUTOS_BLOQUEO    = 3

HORARIOS_PERU = [
    "08:00 AM","09:00 AM","10:00 AM","11:00 AM","12:00 PM",
    "01:00 PM","02:00 PM","03:00 PM","04:00 PM","05:00 PM","06:00 PM"
]

HORARIOS_PLUS = [
    "08:00 AM","09:00 AM","10:00 AM","11:00 AM","12:00 PM",
    "01:00 PM","02:00 PM","03:00 PM","04:00 PM","05:00 PM","06:00 PM","07:00 PM"
]

# Horas en formato cron (hora24, minuto) para Peru (UTC-5)
HORARIOS_PERU_CRON = [
    (13,0),(14,0),(15,0),(16,0),(17,0),(18,0),
    (19,0),(20,0),(21,0),(22,0),(23,0)
]
# Horas en formato cron para Plus (Venezuela UTC-4, pero scheduler en UTC)
HORARIOS_PLUS_CRON = [
    (12,0),(13,0),(14,0),(15,0),(16,0),(17,0),
    (18,0),(19,0),(20,0),(21,0),(22,0),(23,0)
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

# Animales elegibles para auto-sorteo (sin Lechuza #40)
ANIMALES_AUTO = [str(i) for i in range(0, 40)] + ["00"]

# ── Secuencias de patrones para auto-sorteo ──────────────────────────────────
# Por cada animal que sale, estos 7 tienen prioridad en el siguiente sorteo
# (siempre respetando el presupuesto 70/30)
# Nota: 41 → "0" (Delfín), 42 → "00" (Ballena)
_SEQ_RAW = {
    0:  [6, 10, 23, 17, 35, 24, 16],
    1:  [8, 15, 22, 30, 5, 12, 40],
    2:  [9, 16, 23, 31, 6, 13, 39],
    3:  [10, 17, 24, 32, 7, 14, 38],
    4:  [11, 18, 25, 33, 1, 15, 39],
    5:  [12, 19, 26, 34, 2, 16, 38],
    6:  [13, 20, 27, 35, 3, 17, 37],
    7:  [14, 21, 28, 36, 4, 18, 35],
    8:  [15, 22, 29, 37, 5, 19, 35],
    9:  [16, 23, 30, 38, 6, 20, 34],
    10: [17, 24, 31, 39, 7, 21, 33],
    11: [18, 25, 32, 40, 8, 22, 31],
    12: [19, 26, 33, 0, 9, 23, 31],
    13: [20, 27, 34, 0, 10, 24, 30],
    14: [21, 28, 35, 1, 11, 25, 29],
    15: [21, 25, 38, 32, 8, 11, 31],
    16: [23, 27, 40, 34, 10, 13, 33],
    17: [24, 28, 0, 35, 11, 14, 34],
    18: [25, 29, 0, 36, 12, 1, 35],
    19: [26, 30, 1, 37, 13, 2, 36],
    20: [27, 31, 2, 38, 14, 3, 37],
    21: [28, 32, 3, 39, 15, 4, 38],
    22: [29, 33, 4, 40, 16, 5, 39],
    23: [30, 34, 5, 0, 17, 6, 40],
    24: [31, 35, 6, 0, 18, 7, 39],
    25: [32, 36, 7, 1, 19, 8, 0],
    26: [33, 37, 8, 2, 20, 9, 1],
    27: [34, 38, 9, 3, 21, 10, 2],
    28: [35, 39, 10, 4, 22, 11, 3],
    29: [36, 40, 11, 5, 23, 12, 4],
    30: [37, 0, 12, 6, 24, 13, 5],
    31: [38, 0, 13, 7, 25, 14, 6],
    32: [39, 1, 14, 8, 26, 15, 7],
    33: [40, 2, 15, 9, 27, 16, 8],
    34: [0, 3, 16, 10, 28, 17, 9],
    35: [0, 4, 17, 11, 29, 18, 10],
    36: [1, 5, 18, 12, 30, 19, 11],
    37: [2, 6, 19, 13, 31, 20, 12],
    38: [3, 7, 20, 14, 32, 21, 13],
    39: [4, 8, 21, 15, 33, 22, 14],
    40: [5, 9, 22, 16, 34, 23, 15],
    'oo': [7, 11, 24, 18, 36, 25, 17]
}
# Convertir a strings para coincidir con el formato del sistema
SECUENCIAS_ZOOLO = {}
def _to_str(n):
    if n == 'oo' or n == 0 and False: return '00'
    return str(n)
for k, v in _SEQ_RAW.items():
    key = '00' if k == 'oo' else str(k)
    SECUENCIAS_ZOOLO[key] = list(dict.fromkeys([str(x) for x in v]))  # deduplica

def get_secuencia(animal_str):
    """Retorna los 7 animales de la secuencia para un animal dado."""
    return SECUENCIAS_ZOOLO.get(str(animal_str), [])

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

# ─── Helpers de hash ───────────────────────────────────────────────────────────
def hash_password(plain):
    return hashlib.sha256((plain + app.secret_key).encode()).hexdigest()

def get_db():
    if USE_SQLITE:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        return _DBWrap(conn, sqlite_mode=True)
    else:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return _DBWrap(conn, sqlite_mode=False)

class _DBWrap:
    def __init__(self, conn, sqlite_mode=False):
        self._c = conn
        self._sqlite = sqlite_mode
        if sqlite_mode:
            self._c.execute("PRAGMA journal_mode=WAL")
            self._cur = conn.cursor()
        else:
            self._cur = conn.cursor()

    def __enter__(self):
        return self
    def __exit__(self, exc, val, tb):
        if exc:
            if not self._sqlite:
                self._c.rollback()
        else:
            self._c.commit()
        self._cur.close()
        self._c.close()
        return False

    def _adapt_sql(self, sql):
        """Convierte %s → ? para SQLite"""
        if self._sqlite:
            return sql.replace('%s', '?')
        return sql

    def execute(self, sql, params=None):
        self._cur.execute(self._adapt_sql(sql), params or ())
        return self

    def executemany(self, sql, seq):
        self._cur.executemany(self._adapt_sql(sql), seq)
        return self

    def executescript(self, script):
        for stmt in script.split(';'):
            s = stmt.strip()
            if s:
                try:
                    self._cur.execute(s)
                except Exception:
                    if not self._sqlite:
                        self._c.rollback()
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        if self._sqlite:
            return _Row(dict(zip(row.keys(), tuple(row))))
        cols = [d[0] for d in self._cur.description]
        return _Row(dict(zip(cols, row)))

    def fetchall(self):
        rows = self._cur.fetchall()
        if not rows:
            return []
        if self._sqlite:
            return [_Row(dict(zip(r.keys(), tuple(r)))) for r in rows]
        cols = [d[0] for d in self._cur.description]
        return [_Row(dict(zip(cols, r))) for r in rows]

    @property
    def lastrowid(self):
        if self._sqlite:
            return self._cur.lastrowid
        self._cur.execute("SELECT lastval()")
        return self._cur.fetchone()[0]

    def commit(self):
        self._c.commit()

    def rollback(self):
        if not self._sqlite:
            self._c.rollback()

    def close(self):
        self._cur.close()
        self._c.close()

    def __iter__(self):
        if self._sqlite:
            for row in self._cur:
                yield _Row(dict(zip(row.keys(), tuple(row))))
        else:
            cols = [d[0] for d in self._cur.description]
            for row in self._cur:
                yield _Row(dict(zip(cols, row)))


class _Row(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)
    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default
    def keys(self):
        return super().keys()


def _sql(pg_sql, sqlite_sql=None):
    """Retorna SQL correcto según el motor activo."""
    if USE_SQLITE:
        return sqlite_sql if sqlite_sql else pg_sql
    return pg_sql

TS_DEFAULT_PG = "DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))"
TS_DEFAULT_SQ = "DEFAULT (datetime('now'))"

def init_db():
    with get_db() as db:
        ts = TS_DEFAULT_SQ if USE_SQLITE else TS_DEFAULT_PG
        pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if USE_SQLITE else "SERIAL PRIMARY KEY"
        db.execute(f"""CREATE TABLE IF NOT EXISTS agencias (
            id {pk}, usuario TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
            nombre_agencia TEXT NOT NULL, nombre_banco TEXT DEFAULT '',
            es_admin INTEGER DEFAULT 0, comision REAL DEFAULT 0.15,
            activa INTEGER DEFAULT 1, tope_taquilla REAL DEFAULT 0,
            creado TEXT {ts})""")
        db.execute(f"""CREATE TABLE IF NOT EXISTS tickets (
            id {pk}, serial TEXT UNIQUE NOT NULL,
            agencia_id INTEGER NOT NULL, fecha TEXT NOT NULL, total REAL NOT NULL,
            pagado INTEGER DEFAULT 0, anulado INTEGER DEFAULT 0,
            creado TEXT {ts})""")
        db.execute(f"""CREATE TABLE IF NOT EXISTS jugadas (
            id {pk}, ticket_id INTEGER NOT NULL, hora TEXT NOT NULL,
            seleccion TEXT NOT NULL, monto REAL NOT NULL, tipo TEXT NOT NULL,
            loteria TEXT NOT NULL DEFAULT 'peru')""")
        db.execute(f"""CREATE TABLE IF NOT EXISTS tripletas (
            id {pk}, ticket_id INTEGER NOT NULL, animal1 TEXT NOT NULL,
            animal2 TEXT NOT NULL, animal3 TEXT NOT NULL, monto REAL NOT NULL,
            fecha TEXT NOT NULL, pagado INTEGER DEFAULT 0,
            loteria TEXT NOT NULL DEFAULT 'peru')""")
        db.execute(f"""CREATE TABLE IF NOT EXISTS resultados (
            id {pk}, fecha TEXT NOT NULL, hora TEXT NOT NULL,
            animal TEXT NOT NULL, loteria TEXT NOT NULL DEFAULT 'peru',
            UNIQUE(fecha, hora, loteria))""")
        db.execute(f"""CREATE TABLE IF NOT EXISTS topes (
            id {pk}, hora TEXT NOT NULL, numero TEXT NOT NULL,
            monto_tope REAL NOT NULL, loteria TEXT NOT NULL DEFAULT 'peru',
            UNIQUE(hora, numero, loteria))""")
        db.execute(f"""CREATE TABLE IF NOT EXISTS audit_logs (
            id {pk}, agencia_id INTEGER, usuario TEXT,
            accion TEXT NOT NULL, detalle TEXT, ip TEXT,
            creado TEXT {ts})""")
        db.execute(f"""CREATE TABLE IF NOT EXISTS config_sistema (
            clave TEXT PRIMARY KEY,
            valor TEXT NOT NULL,
            actualizado TEXT {ts})""")
        db.execute(f"""CREATE TABLE IF NOT EXISTS sorteo_acumulado (
            id {pk},
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            loteria TEXT NOT NULL DEFAULT 'peru',
            total_vendido REAL DEFAULT 0,
            presupuesto_70 REAL DEFAULT 0,
            premio_pagado REAL DEFAULT 0,
            acumulado_recibido REAL DEFAULT 0,
            acumulado_generado REAL DEFAULT 0,
            animal_ganador TEXT,
            modo TEXT DEFAULT 'auto',
            UNIQUE(fecha, hora, loteria))""")
        for idx in [
            "CREATE INDEX IF NOT EXISTS idx_tickets_agencia ON tickets(agencia_id)",
            "CREATE INDEX IF NOT EXISTS idx_tickets_fecha ON tickets(fecha)",
            "CREATE INDEX IF NOT EXISTS idx_jugadas_ticket ON jugadas(ticket_id)",
            "CREATE INDEX IF NOT EXISTS idx_tripletas_ticket ON tripletas(ticket_id)",
            "CREATE INDEX IF NOT EXISTS idx_resultados_fecha ON resultados(fecha)",
            "CREATE INDEX IF NOT EXISTS idx_audit_logs_fecha ON audit_logs(creado)",
            "CREATE INDEX IF NOT EXISTS idx_sorteo_acum_fecha ON sorteo_acumulado(fecha, loteria)",
        ]:
            db.execute(idx)
        # Migraciones seguras — cada una en conexión propia para no romper la transacción principal
        db.commit()  # commit tablas creadas antes de migrar
        migraciones = [
            "ALTER TABLE agencias ADD COLUMN tope_taquilla REAL DEFAULT 0",
            "ALTER TABLE agencias ADD COLUMN nombre_banco TEXT DEFAULT ''",
            "ALTER TABLE resultados ADD COLUMN loteria TEXT NOT NULL DEFAULT 'peru'",
            "ALTER TABLE topes ADD COLUMN loteria TEXT NOT NULL DEFAULT 'peru'",
            "ALTER TABLE jugadas ADD COLUMN loteria TEXT NOT NULL DEFAULT 'peru'",
            "ALTER TABLE tripletas ADD COLUMN loteria TEXT NOT NULL DEFAULT 'peru'",
        ]
        for sql in migraciones:
            try:
                with get_db() as db_mig:
                    db_mig.execute(sql)
                    db_mig.commit()
            except Exception:
                pass  # columna ya existe — ignorar
        # Config por defecto: auto-sorteo desactivado
        db.execute("""INSERT OR IGNORE INTO config_sistema (clave, valor)
            VALUES ('auto_sorteo', 'off')""" if USE_SQLITE else """INSERT INTO config_sistema (clave, valor)
            VALUES ('auto_sorteo', 'off')
            ON CONFLICT(clave) DO NOTHING""")
        db.commit()
        # Admin por defecto
        admin = db.execute("SELECT id FROM agencias WHERE es_admin=1").fetchone()
        if not admin:
            ph_admin = hash_password('15821462')
            db.execute("INSERT INTO agencias (usuario,password,nombre_agencia,es_admin,comision,activa) VALUES (%s,%s,%s,1,0,1)",
                       ('cuborubi', ph_admin, 'ADMINISTRADOR'))
            db.commit()


# ─── Helpers de tiempo ────────────────────────────────────────────────────────
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
    if hora_compra_ticket is None:
        return resultados_dia
    min_compra = hora_compra_ticket.hour * 60 + hora_compra_ticket.minute
    return {h: a for h, a in resultados_dia.items() if hora_a_min(h) >= min_compra}

def calcular_premio_ticket(ticket_id, db=None):
    close = False
    if db is None:
        db = get_db(); close = True
    try:
        t = db.execute("SELECT fecha FROM tickets WHERE id=%s", (ticket_id,)).fetchone()
        if not t: return 0
        fecha_ticket = parse_fecha(t['fecha'])
        if not fecha_ticket: return 0
        fecha_str = fecha_ticket.strftime("%d/%m/%Y")

        res_rows_peru = db.execute(
            "SELECT hora, animal FROM resultados WHERE fecha=%s AND loteria='peru'", (fecha_str,)
        ).fetchall()
        res_rows_plus = db.execute(
            "SELECT hora, animal FROM resultados WHERE fecha=%s AND loteria='plus'", (fecha_str,)
        ).fetchall()
        resultados_peru = {r['hora']: r['animal'] for r in res_rows_peru}
        resultados_plus = {r['hora']: r['animal'] for r in res_rows_plus}

        total = 0
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

# ─── Config sistema ──────────────────────────────────────────────────────────
def get_config(clave, default='off'):
    try:
        with get_db() as db:
            row = db.execute("SELECT valor FROM config_sistema WHERE clave=%s", (clave,)).fetchone()
            return row['valor'] if row else default
    except:
        return default

def set_config(clave, valor):
    with get_db() as db:
        if USE_SQLITE:
            db.execute("""INSERT OR REPLACE INTO config_sistema (clave, valor, actualizado)
                VALUES (?, ?, datetime('now'))""", (clave, valor))
        else:
            db.execute("""INSERT INTO config_sistema (clave, valor, actualizado)
                VALUES (%s, %s, to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
                ON CONFLICT(clave) DO UPDATE SET valor=EXCLUDED.valor, actualizado=EXCLUDED.actualizado""",
                (clave, valor))
        db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# LÓGICA CENTRAL DEL AUTO-SORTEO 70/30
# ═══════════════════════════════════════════════════════════════════════════════

def ejecutar_auto_sorteo(hora_str, loteria):
    """
    Ejecuta el sorteo automático para una hora y lotería dadas.
    Lógica 70/30:
      - Calcula total apostado en esa hora+lotería
      - Toma el 70% como presupuesto de premios
      - Suma acumulado de sorteos anteriores del mismo día
      - Elige animal ganador que no supere el presupuesto total disponible
      - Si ninguno califica → elige animal NO jugado ese sorteo (nadie gana)
      - Guarda el acumulado para el siguiente sorteo del día
      - Animales auto no se repiten en el mismo día
    """
    try:
        now_peru = ahora_peru()
        fecha_hoy = now_peru.strftime("%d/%m/%Y")
        logger.info(f"[AUTO-SORTEO] {loteria.upper()} {hora_str} — {fecha_hoy}")

        with get_db() as db:
            # 1. Verificar que no exista ya un resultado para esta hora
            ya_existe = db.execute(
                "SELECT id FROM resultados WHERE fecha=%s AND hora=%s AND loteria=%s",
                (fecha_hoy, hora_str, loteria)
            ).fetchone()
            if ya_existe:
                logger.info(f"[AUTO-SORTEO] Ya existe resultado para {hora_str} {loteria}, saltando.")
                return

            # 2. Calcular total apostado en este sorteo (solo jugadas tipo animal y especial)
            apostado_row = db.execute("""
                SELECT COALESCE(SUM(jg.monto), 0) as total
                FROM jugadas jg
                JOIN tickets tk ON jg.ticket_id = tk.id
                WHERE jg.hora=%s AND jg.loteria=%s AND tk.anulado=0 AND SUBSTR(tk.fecha, 1, 10) = %s
            """, (hora_str, loteria, fecha_hoy + '%')).fetchone()
            total_vendido = float(apostado_row['total'])
            presupuesto_70 = round(total_vendido * 0.70, 2)

            # 3. Obtener acumulado de sorteos anteriores del mismo día
            acum_row = db.execute("""
                SELECT COALESCE(SUM(acumulado_generado), 0) as total_acum
                FROM sorteo_acumulado
                WHERE fecha=%s AND loteria=%s
            """, (fecha_hoy, loteria)).fetchone()
            acumulado_recibido = round(float(acum_row['total_acum']), 2)

            presupuesto_total = round(presupuesto_70 + acumulado_recibido, 2)

            # 4. Obtener animales que ya salieron hoy en esta lotería (auto-sorteo no repite)
            salidos_hoy = db.execute(
                "SELECT animal FROM resultados WHERE fecha=%s AND loteria=%s",
                (fecha_hoy, loteria)
            ).fetchall()
            animales_ya_salidos = {r['animal'] for r in salidos_hoy}

            # 5. Calcular cuánto pagaría cada animal si sale
            apostado_por_animal = db.execute("""
                SELECT jg.seleccion, COALESCE(SUM(jg.monto), 0) as apostado
                FROM jugadas jg
                JOIN tickets tk ON jg.ticket_id = tk.id
                WHERE jg.hora=%s AND jg.tipo='animal' AND jg.loteria=%s
                  AND tk.anulado=0 AND SUBSTR(tk.fecha, 1, 10) = %s
                GROUP BY jg.seleccion
            """, (hora_str, loteria, fecha_hoy + '%')).fetchall()

            apostado_map = {r['seleccion']: float(r['apostado']) for r in apostado_por_animal}

            # También calcular pago por especiales si sale cada número
            especiales = db.execute("""
                SELECT jg.seleccion, COALESCE(SUM(jg.monto), 0) as apostado
                FROM jugadas jg
                JOIN tickets tk ON jg.ticket_id = tk.id
                WHERE jg.hora=%s AND jg.tipo='especial' AND jg.loteria=%s
                  AND tk.anulado=0 AND SUBSTR(tk.fecha, 1, 10) = %s
                GROUP BY jg.seleccion
            """, (hora_str, loteria, fecha_hoy + '%')).fetchall()

            esp_map = {r['seleccion']: float(r['apostado']) for r in especiales}

            def pago_especial_para(num_str):
                """Cuánto pagarían los especiales si sale este número."""
                if num_str in ["0", "00"]:
                    return 0  # especiales no aplican para 0/00
                num = int(num_str)
                total_esp = 0
                if str(num_str) in ROJOS:
                    total_esp += esp_map.get('ROJO', 0) * PAGO_ESPECIAL
                else:
                    total_esp += esp_map.get('NEGRO', 0) * PAGO_ESPECIAL
                if num % 2 == 0:
                    total_esp += esp_map.get('PAR', 0) * PAGO_ESPECIAL
                else:
                    total_esp += esp_map.get('IMPAR', 0) * PAGO_ESPECIAL
                return total_esp

            def pago_total_si_sale(num_str):
                ap = apostado_map.get(num_str, 0)
                mult = PAGO_LECHUZA if num_str == "40" else PAGO_ANIMAL_NORMAL
                return round(ap * mult + pago_especial_para(num_str), 2)

            # 6. Obtener último animal que salió hoy para aplicar secuencia
            ultimo_animal = None
            if animales_ya_salidos:
                # Buscar el resultado más reciente del día
                ultimos = db.execute("""
                    SELECT animal FROM resultados
                    WHERE fecha=%s AND loteria=%s
                    ORDER BY hora DESC
                """, (fecha_hoy, loteria)).fetchall()
                if ultimos:
                    ultimo_animal = ultimos[0]['animal']

            # Obtener secuencia de prioridad basada en el último animal
            secuencia_prioritaria = get_secuencia(ultimo_animal) if ultimo_animal else []
            # Filtrar: solo los de la secuencia que no hayan salido hoy
            secuencia_valida = [n for n in secuencia_prioritaria
                                if n in ANIMALES_AUTO and n not in animales_ya_salidos]

            logger.info(f"[SECUENCIA] Último:{ultimo_animal} → Prioridad:{secuencia_valida}")

            # 7. Candidatos elegibles: no repetidos hoy, dentro del presupuesto
            candidatos_jugados = []
            for num in ANIMALES_AUTO:
                if num in animales_ya_salidos:
                    continue
                pago = pago_total_si_sale(num)
                if pago <= presupuesto_total:
                    candidatos_jugados.append((num, pago))

            animal_elegido = None
            premio_a_pagar = 0

            def elegir_de(lista):
                """De una lista (num, pago), prioriza secuencia, luego elige al azar."""
                con_seq = [(n, p) for n, p in lista if n in secuencia_valida]
                sin_seq = [(n, p) for n, p in lista if n not in secuencia_valida]
                # Si hay candidatos en la secuencia, elegir de ellos
                if con_seq:
                    return random.choice(con_seq)
                return random.choice(sin_seq) if sin_seq else None

            if candidatos_jugados:
                # Preferir animales con apuestas que quepan en presupuesto
                con_apuestas = [(n, p) for n, p in candidatos_jugados
                                if n in apostado_map and apostado_map[n] > 0]
                sin_apuestas = [(n, p) for n, p in candidatos_jugados
                                if n not in apostado_map or apostado_map[n] == 0]

                if con_apuestas:
                    elegido = elegir_de(con_apuestas)
                    if elegido:
                        animal_elegido = elegido[0]
                        premio_a_pagar = elegido[1]
                else:
                    elegido = elegir_de(sin_apuestas)
                    if elegido:
                        animal_elegido = elegido[0]
                        premio_a_pagar = 0
            else:
                # Ningún animal con apuestas cabe en el presupuesto → elegir uno NO jugado
                no_jugados = [(n, 0) for n in ANIMALES_AUTO
                              if n not in apostado_map and n not in animales_ya_salidos]
                if no_jugados:
                    elegido = elegir_de(no_jugados)
                    animal_elegido = elegido[0] if elegido else random.choice([n for n, _ in no_jugados])
                    premio_a_pagar = 0
                else:
                    # Extremo: todos tienen apuestas y superan presupuesto
                    disponibles = [(n, pago_total_si_sale(n)) for n in ANIMALES_AUTO
                                   if n not in animales_ya_salidos]
                    if disponibles:
                        disponibles.sort(key=lambda x: x[1])
                        animal_elegido = disponibles[0][0]
                        premio_a_pagar = disponibles[0][1]

            if not animal_elegido:
                logger.error(f"[AUTO-SORTEO] No se pudo elegir animal para {hora_str} {loteria}")
                return

            # 7. Guardar resultado
            if USE_SQLITE:
                db.execute("INSERT OR REPLACE INTO resultados (fecha,hora,animal,loteria) VALUES (?,?,?,?)",
                    (fecha_hoy, hora_str, animal_elegido, loteria))
            else:
                db.execute("""INSERT INTO resultados (fecha,hora,animal,loteria)
                    VALUES (%s,%s,%s,%s)
                    ON CONFLICT(fecha,hora,loteria) DO UPDATE SET animal=EXCLUDED.animal""",
                    (fecha_hoy, hora_str, animal_elegido, loteria))

            # 8. Calcular acumulado generado para el siguiente sorteo
            acumulado_generado = round(max(0, presupuesto_70 - premio_a_pagar), 2)

            # 9. Guardar registro en sorteo_acumulado
            if USE_SQLITE:
                db.execute("""INSERT OR REPLACE INTO sorteo_acumulado
                    (fecha, hora, loteria, total_vendido, presupuesto_70,
                     premio_pagado, acumulado_recibido, acumulado_generado, animal_ganador, modo)
                    VALUES (?,?,?,?,?,?,?,?,?,'auto')""",
                    (fecha_hoy, hora_str, loteria, total_vendido, presupuesto_70,
                     premio_a_pagar, acumulado_recibido, acumulado_generado, animal_elegido))
            else:
                db.execute("""INSERT INTO sorteo_acumulado
                    (fecha, hora, loteria, total_vendido, presupuesto_70,
                     premio_pagado, acumulado_recibido, acumulado_generado, animal_ganador, modo)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'auto')
                ON CONFLICT(fecha, hora, loteria) DO UPDATE SET
                    total_vendido=EXCLUDED.total_vendido,
                    presupuesto_70=EXCLUDED.presupuesto_70,
                    premio_pagado=EXCLUDED.premio_pagado,
                    acumulado_recibido=EXCLUDED.acumulado_recibido,
                    acumulado_generado=EXCLUDED.acumulado_generado,
                    animal_ganador=EXCLUDED.animal_ganador,
                    modo=EXCLUDED.modo
                """, (fecha_hoy, hora_str, loteria, total_vendido, presupuesto_70,
                      premio_a_pagar, acumulado_recibido, acumulado_generado, animal_elegido))

            db.commit()

            nombre_animal = ANIMALES.get(animal_elegido, animal_elegido)
            logger.info(
                f"[AUTO-SORTEO] {loteria.upper()} {hora_str} → {animal_elegido}-{nombre_animal} | "
                f"Vendido:S/{total_vendido} | 70%:S/{presupuesto_70} | "
                f"Acum.recibido:S/{acumulado_recibido} | Premio:S/{premio_a_pagar} | "
                f"Acum.generado:S/{acumulado_generado}"
            )

    except Exception as e:
        import traceback
        logger.error(f"[AUTO-SORTEO] Error en {hora_str} {loteria}: {e}")
        logger.error(traceback.format_exc())


def job_auto_sorteo(hora_str, loteria):
    """Job que verifica el toggle antes de ejecutar."""
    estado = get_config('auto_sorteo', 'off')
    if estado == 'on':
        ejecutar_auto_sorteo(hora_str, loteria)
    else:
        logger.info(f"[AUTO-SORTEO] Desactivado, saltando {hora_str} {loteria}")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEDULER — registra jobs para cada hora de sorteo
# ═══════════════════════════════════════════════════════════════════════════════

def recuperar_sorteos_perdidos():
    """Al arrancar, ejecuta auto-sorteos que debieron haber corrido pero no lo hicieron."""
    try:
        estado = get_config('auto_sorteo', 'off')
        if estado != 'on':
            return
        
        now_utc = datetime.now(timezone.utc)
        now_peru = now_utc - timedelta(hours=5)
        now_ven = now_utc - timedelta(hours=4)
        fecha_peru = now_peru.strftime("%d/%m/%Y")
        
        # Horas PERU que ya debieron correr (más de 5 min pasados)
        import time as _time
        for hora_str, hora_utc in [
            ("08:00 AM", 13), ("09:00 AM", 14), ("10:00 AM", 15),
            ("11:00 AM", 16), ("12:00 PM", 17), ("01:00 PM", 18),
            ("02:00 PM", 19), ("03:00 PM", 20), ("04:00 PM", 21),
            ("05:00 PM", 22), ("06:00 PM", 23),
        ]:
            # ¿Ya pasó esta hora UTC?
            if now_utc.hour > hora_utc or (now_utc.hour == hora_utc and now_utc.minute > 5):
                # Verificar si ya tiene resultado
                with get_db() as db:
                    existe = db.execute(
                        "SELECT id FROM resultados WHERE fecha=%s AND hora=%s AND loteria='peru'",
                        (fecha_peru, hora_str)
                    ).fetchone()
                if not existe:
                    logger.info(f"[RECUPERACION] Ejecutando sorteo perdido PERU {hora_str}")
                    ejecutar_auto_sorteo(hora_str, 'peru')
                    _time.sleep(0.5)  # evitar saturar conexiones PG
        
        # Horas PLUS que ya debieron correr
        fecha_ven = now_ven.strftime("%d/%m/%Y")
        for hora_str, hora_utc in [
            ("08:00 AM", 12), ("09:00 AM", 13), ("10:00 AM", 14),
            ("11:00 AM", 15), ("12:00 PM", 16), ("01:00 PM", 17),
            ("02:00 PM", 18), ("03:00 PM", 19), ("04:00 PM", 20),
            ("05:00 PM", 21), ("06:00 PM", 22), ("07:00 PM", 23),
        ]:
            if now_utc.hour > hora_utc or (now_utc.hour == hora_utc and now_utc.minute > 5):
                with get_db() as db:
                    existe = db.execute(
                        "SELECT id FROM resultados WHERE fecha=%s AND hora=%s AND loteria='plus'",
                        (fecha_ven, hora_str)
                    ).fetchone()
                if not existe:
                    logger.info(f"[RECUPERACION] Ejecutando sorteo perdido PLUS {hora_str}")
                    ejecutar_auto_sorteo(hora_str, 'plus')
                    _time.sleep(0.5)  # evitar saturar conexiones PG
    except Exception as e:
        logger.error(f"[RECUPERACION] Error: {e}")

def iniciar_scheduler():
    # Protección multi-worker: solo el primer proceso que arranca el scheduler lo registra
    # En Render con workers=1 esto no es problema, pero por seguridad lo protegemos
    try:
        with get_db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS scheduler_lock (
                id INTEGER PRIMARY KEY,
                pid INTEGER,
                started TEXT
            )""")
            db.commit()
    except Exception:
        pass

    scheduler = BackgroundScheduler(timezone='UTC')

    # PERU: UTC-5 → sorteos a las 8AM-6PM Lima = 13:00-23:00 UTC
    horarios_peru_utc = [
        ("08:00 AM", 13), ("09:00 AM", 14), ("10:00 AM", 15),
        ("11:00 AM", 16), ("12:00 PM", 17), ("01:00 PM", 18),
        ("02:00 PM", 19), ("03:00 PM", 20), ("04:00 PM", 21),
        ("05:00 PM", 22), ("06:00 PM", 23),
    ]
    # PLUS: Venezuela UTC-4 → sorteos a las 8AM-7PM VEN = 12:00-23:00 UTC
    horarios_plus_utc = [
        ("08:00 AM", 12), ("09:00 AM", 13), ("10:00 AM", 14),
        ("11:00 AM", 15), ("12:00 PM", 16), ("01:00 PM", 17),
        ("02:00 PM", 18), ("03:00 PM", 19), ("04:00 PM", 20),
        ("05:00 PM", 21), ("06:00 PM", 22), ("07:00 PM", 23),
    ]

    for hora_str, hora_utc in horarios_peru_utc:
        h = hora_str  # captura correcta en closure
        scheduler.add_job(
            func=lambda hs=h: job_auto_sorteo(hs, 'peru'),
            trigger=CronTrigger(hour=hora_utc, minute=0, second=5),
            id=f'peru_{hora_utc}',
            replace_existing=True,
            misfire_grace_time=300
        )

    for hora_str, hora_utc in horarios_plus_utc:
        h = hora_str
        scheduler.add_job(
            func=lambda hs=h: job_auto_sorteo(hs, 'plus'),
            trigger=CronTrigger(hour=hora_utc, minute=0, second=10),
            id=f'plus_{hora_utc}',
            replace_existing=True,
            misfire_grace_time=300
        )

    # Job de guardia: cada 10 minutos verifica si hay sorteos perdidos
    scheduler.add_job(
        func=recuperar_sorteos_perdidos,
        trigger=CronTrigger(minute='*/10'),
        id='guardia_recuperacion',
        replace_existing=True,
        misfire_grace_time=60
    )

    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())
    logger.info("[SCHEDULER] APScheduler iniciado con todos los jobs de sorteo.")
    # Recuperar sorteos perdidos del día actual en un hilo separado
    import threading
    threading.Thread(target=recuperar_sorteos_perdidos, daemon=True).start()
    return scheduler

# ─── Decoradores ─────────────────────────────────────────────────────────────
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


# ═══════════════════════════════════════════════════════════════════════════════
# RUTAS — igual que v3.1, sin cambios en lógica de ventas/pagos
# ═══════════════════════════════════════════════════════════════════════════════

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
        ph = hash_password(p)
        with get_db() as db:
            row = db.execute("SELECT * FROM agencias WHERE usuario=%s AND password=%s AND activa=1",(u,ph)).fetchone()
        if row:
            session['user_id'] = row['id']
            session['nombre_agencia'] = row['nombre_agencia']
            session['nombre_banco'] = row.get('nombre_banco') or ''
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

# ── API general (sin cambios) ──────────────────────────────────────────────────
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

        jugadas_peru = [j for j in jugadas if j.get('loteria','peru') == 'peru']
        jugadas_plus = [j for j in jugadas if j.get('loteria','peru') == 'plus']

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
            ag = db.execute("SELECT tope_taquilla, comision FROM agencias WHERE id=%s", (agencia_id,)).fetchone()
            tope_taq = ag['tope_taquilla'] if ag else 0
            if tope_taq and tope_taq > 0:
                ventas_hoy = db.execute(
                    "SELECT COALESCE(SUM(total),0) as tot FROM tickets WHERE agencia_id=%s AND anulado=0 AND SUBSTR(fecha, 1, 10) = %s",
                    (agencia_id, hoy)
                ).fetchone()['tot']
                if ventas_hoy + total > tope_taq:
                    return jsonify({'error':f'Tope de taquilla alcanzado. Límite: S/{tope_taq}, vendido hoy: S/{ventas_hoy:.2f}'}),400

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
                            AND tk.anulado=0 AND SUBSTR(tk.fecha, 1, 10) = %s
                        """, (j['hora'], j['seleccion'], lot, hoy)).fetchone()['tot']
                        if ya_apostado + j['monto'] > tope_row['monto_tope']:
                            nombre = ANIMALES.get(j['seleccion'], j['seleccion'])
                            lot_label = 'PLUS' if lot=='plus' else 'PERU'
                            return jsonify({'error':f'Tope alcanzado para {j["seleccion"]}-{nombre} en {j["hora"]} ({lot_label}). Disponible: S/{tope_row["monto_tope"]-ya_apostado:.2f}'}),400

            serial = generar_serial()
            fecha  = ahora_peru().strftime("%d/%m/%Y %I:%M %p")

            if USE_SQLITE:
                db.execute("INSERT INTO tickets (serial,agencia_id,fecha,total) VALUES (?,?,?,?)",
                    (serial, agencia_id, fecha, total))
                ticket_id = db._cur.lastrowid
            else:
                db._cur.execute(
                    "INSERT INTO tickets (serial,agencia_id,fecha,total) VALUES (%s,%s,%s,%s) RETURNING id",
                    (serial, agencia_id, fecha, total))
                ticket_id = db._cur.fetchone()[0]

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
            m2 = re.match(r'(\d+):(\d+) (AM|PM)', h.strip())
            if not m2: return h.replace(' ','')
            hh, mm, ap = int(m2.group(1)), m2.group(2), m2.group(3)
            ven_label = f"{hh}{ap}" if mm=='00' else f"{hh}:{mm}{ap}"
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
    try:
        serial = request.json.get('serial')
        if not serial:
            return jsonify({'error':'Serial requerido'}),400
        with get_db() as db:
            t = db.execute("SELECT * FROM tickets WHERE serial=%s AND agencia_id=%s",
                          (serial, session['user_id'])).fetchone()
            if not t:
                return jsonify({'error':'Ticket no encontrado'}),404
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
            if not session.get('es_admin') and t['agencia_id']!=session['user_id']:
                return jsonify({'error':'No autorizado'})
            if t['pagado']:
                return jsonify({'error':'Ya pagado, no se puede anular'})
            if t['anulado']:
                return jsonify({'error':'Ticket ya estaba anulado'})
            if not session.get('es_admin'):
                jugs = db.execute("SELECT hora, loteria FROM jugadas WHERE ticket_id=%s",(t['id'],)).fetchall()
                for j in jugs:
                    lot_j = j['loteria'] if 'loteria' in j.keys() else 'peru'
                    cerrado = not puede_vender_plus(j['hora']) if lot_j == 'plus' else not puede_vender(j['hora'])
                    if cerrado:
                        lot_label = 'PLUS' if lot_j == 'plus' else 'PERÚ'
                        return jsonify({'error':f"No se puede anular: el sorteo {j['hora']} ({lot_label}) ya cerró"})
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
            tickets = db.execute("SELECT * FROM tickets WHERE agencia_id=%s AND anulado=0 AND SUBSTR(fecha, 1, 10) = %s",
                                (session['user_id'], hoy)).fetchall()
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
                p=calcular_premio_ticket(t['id'],db)
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


# ═══════════════════════════════════════════════════════════════════════════════
# RUTAS ADMIN — incluye nuevas rutas de auto-sorteo y 70/30
# ═══════════════════════════════════════════════════════════════════════════════


@app.route('/admin/secuencia-sugerida')
@admin_required
def secuencia_sugerida():
    """Retorna los 7 animales sugeridos por la secuencia basándose en el último resultado."""
    try:
        loteria = request.args.get('loteria', 'peru')
        fecha = ahora_peru().strftime("%d/%m/%Y")
        with get_db() as db:
            ultimo = db.execute("""
                SELECT animal, hora FROM resultados
                WHERE fecha=%s AND loteria=%s
                ORDER BY hora DESC LIMIT 1
            """, (fecha, loteria)).fetchone()
        if not ultimo:
            return jsonify({'status': 'ok', 'ultimo': None, 'sugeridos': [], 'mensaje': 'Sin resultados hoy'})
        ultimo_animal = ultimo['animal']
        ultima_hora = ultimo['hora']
        sugeridos = get_secuencia(ultimo_animal)
        return jsonify({
            'status': 'ok',
            'ultimo': ultimo_animal,
            'ultimo_nombre': ANIMALES.get(ultimo_animal, '?'),
            'ultima_hora': ultima_hora,
            'sugeridos': [{'num': n, 'nombre': ANIMALES.get(n, '?')} for n in sugeridos],
            'mensaje': f'Basado en {ultimo_animal}-{ANIMALES.get(ultimo_animal,"?")} ({ultima_hora})'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
            try: fecha = datetime.strptime(fi,"%Y-%m-%d").strftime("%d/%m/%Y")
            except: fecha = ahora_peru().strftime("%d/%m/%Y")
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
            if USE_SQLITE:
                db.execute("INSERT OR REPLACE INTO resultados (fecha,hora,animal,loteria) VALUES (?,?,?,?)",
                    (fecha, hora, animal, loteria))
            else:
                db.execute("""INSERT INTO resultados (fecha,hora,animal,loteria) VALUES (%s,%s,%s,%s)
                    ON CONFLICT(fecha,hora,loteria) DO UPDATE SET animal=EXCLUDED.animal""",
                    (fecha, hora, animal, loteria))
            db.commit()
        lot_label = 'PLUS' if loteria=='plus' else 'PERU'
        log_audit('RESULTADO', f"Loteria:{lot_label} Fecha:{fecha} Hora:{hora} Animal:{animal} ({ANIMALES[animal]}) [MANUAL]")
        return jsonify({'status':'ok','mensaje':f'[{lot_label}] {hora} = {animal} ({ANIMALES[animal]})','fecha':fecha})
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ── NUEVO v4.0: Toggle auto-sorteo ───────────────────────────────────────────
@app.route('/admin/toggle-autosorteo', methods=['POST'])
@admin_required
def toggle_autosorteo():
    try:
        data = request.get_json() or {}
        nuevo_estado = data.get('estado', 'off')
        if nuevo_estado not in ('on', 'off'):
            return jsonify({'error': 'Estado inválido'}), 400
        set_config('auto_sorteo', nuevo_estado)
        estado_label = 'ACTIVADO ✅' if nuevo_estado == 'on' else 'DESACTIVADO ⛔'
        log_audit('AUTO_SORTEO_TOGGLE', f"Auto-sorteo {estado_label}")
        return jsonify({'status': 'ok', 'estado': nuevo_estado, 'mensaje': f'Auto-sorteo {estado_label}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/estado-autosorteo')
@admin_required
def estado_autosorteo():
    estado = get_config('auto_sorteo', 'off')
    return jsonify({'estado': estado})

# ── NUEVO v4.0: Ejecutar auto-sorteo manualmente (para pruebas o corrección) ─
@app.route('/admin/forzar-autosorteo', methods=['POST'])
@admin_required
def forzar_autosorteo():
    try:
        data = request.get_json() or {}
        hora = data.get('hora')
        loteria = data.get('loteria', 'peru')
        horarios_validos = HORARIOS_PLUS if loteria == 'plus' else HORARIOS_PERU
        if hora not in horarios_validos:
            return jsonify({'error': 'Hora inválida'}), 400
        ejecutar_auto_sorteo(hora, loteria)
        # Verificar qué salió
        fecha_hoy = ahora_peru().strftime("%d/%m/%Y")
        with get_db() as db:
            res = db.execute(
                "SELECT animal FROM resultados WHERE fecha=%s AND hora=%s AND loteria=%s",
                (fecha_hoy, hora, loteria)
            ).fetchone()
        if res:
            animal = res['animal']
            return jsonify({
                'status': 'ok',
                'animal': animal,
                'nombre': ANIMALES.get(animal, '?'),
                'mensaje': f'Auto-sorteo ejecutado: {animal} — {ANIMALES.get(animal,"?")} ({loteria.upper()} {hora})'
            })
        else:
            return jsonify({'error': 'No se pudo ejecutar el sorteo'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── NUEVO v4.0: Reporte 70/30 por jornada ───────────────────────────────────
@app.route('/admin/reporte-7030', methods=['POST'])
@admin_required
def reporte_7030():
    try:
        data = request.get_json() or {}
        fecha = data.get('fecha')
        loteria = data.get('loteria', 'peru')
        if not fecha:
            fecha = ahora_peru().strftime("%d/%m/%Y")
        else:
            try:
                fecha = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
            except:
                fecha = ahora_peru().strftime("%d/%m/%Y")

        horarios = HORARIOS_PLUS if loteria == 'plus' else HORARIOS_PERU

        with get_db() as db:
            # Acumulados guardados por el auto-sorteo
            acum_rows = db.execute("""
                SELECT hora, total_vendido, presupuesto_70, premio_pagado,
                       acumulado_recibido, acumulado_generado, animal_ganador, modo
                FROM sorteo_acumulado
                WHERE fecha=%s AND loteria=%s
                ORDER BY hora
            """, (fecha, loteria)).fetchall()
            acum_map = {r['hora']: dict(r) for r in acum_rows}

            # Para sorteos sin registro en acumulado (resultados manuales),
            # calcular los datos directamente
            res_rows = db.execute(
                "SELECT hora, animal FROM resultados WHERE fecha=%s AND loteria=%s",
                (fecha, loteria)
            ).fetchall()
            res_map = {r['hora']: r['animal'] for r in res_rows}

            # Total vendido por hora
            total_por_hora = db.execute("""
                SELECT jg.hora, COALESCE(SUM(jg.monto), 0) as total
                FROM jugadas jg
                JOIN tickets tk ON jg.ticket_id = tk.id
                WHERE SUBSTR(tk.fecha, 1, 10) = %s AND jg.loteria=%s AND tk.anulado=0
                GROUP BY jg.hora
            """, (fecha + '%', loteria)).fetchall()
            vendido_map = {r['hora']: float(r['total']) for r in total_por_hora}

        sorteos = []
        total_vendido_dia = 0
        total_presupuesto_dia = 0
        total_premio_dia = 0
        total_casa_dia = 0

        # Acumulado calculado dinámicamente en cadena (no depende de sorteo_acumulado)
        acum_corriente = 0.0

        for hora in horarios:
            vendido = vendido_map.get(hora, 0)
            animal = res_map.get(hora)
            presupuesto_70 = round(vendido * 0.70, 2)

            if hora in acum_map:
                # Registro oficial del auto-sorteo — usar sus datos
                a = acum_map[hora]
                premio = float(a['premio_pagado'])
                acum_recibido = float(a['acumulado_recibido'])
                acum_generado = float(a['acumulado_generado'])
                modo = a['modo']
                # Sincronizar acumulado corriente con lo que realmente quedó
                acum_corriente = acum_generado
            else:
                # Sin registro oficial — calcular dinámicamente
                acum_recibido = round(acum_corriente, 2)
                presupuesto_total_temp = round(presupuesto_70 + acum_recibido, 2)

                if animal:
                    # Hubo resultado manual — calcular premio real pagado
                    # Buscar cuánto se apostó al animal ganador en esa hora
                    try:
                        with get_db() as db2:
                            ap_row = db2.execute("""
                                SELECT COALESCE(SUM(jg.monto),0) as ap
                                FROM jugadas jg JOIN tickets tk ON jg.ticket_id=tk.id
                                WHERE jg.hora=%s AND jg.seleccion=%s AND jg.tipo='animal'
                                AND jg.loteria=%s AND tk.anulado=0 AND SUBSTR(tk.fecha, 1, 10) = %s
                            """, (hora, animal, loteria, fecha+'%')).fetchone()
                            ap_animal = float(ap_row['ap']) if ap_row else 0
                        mult = 70 if animal == '40' else 35
                        premio = round(ap_animal * mult, 2)
                        # También sumar especiales
                        try:
                            with get_db() as db3:
                                esp_rows = db3.execute("""
                                    SELECT jg.seleccion, COALESCE(SUM(jg.monto),0) as monto
                                    FROM jugadas jg JOIN tickets tk ON jg.ticket_id=tk.id
                                    WHERE jg.hora=%s AND jg.tipo='especial' AND jg.loteria=%s
                                    AND tk.anulado=0 AND SUBSTR(tk.fecha, 1, 10) = %s
                                    GROUP BY jg.seleccion
                                """, (hora, loteria, fecha+'%')).fetchall()
                            esp_map_h = {r['seleccion']: float(r['monto']) for r in esp_rows}
                            if animal not in ['0','00']:
                                num = int(animal)
                                rojos_set = set(ROJOS)
                                if animal in rojos_set:
                                    premio += esp_map_h.get('ROJO', 0) * 2
                                else:
                                    premio += esp_map_h.get('NEGRO', 0) * 2
                                if num % 2 == 0:
                                    premio += esp_map_h.get('PAR', 0) * 2
                                else:
                                    premio += esp_map_h.get('IMPAR', 0) * 2
                            premio = round(premio, 2)
                        except:
                            pass
                    except:
                        premio = 0
                    modo = 'manual'
                else:
                    premio = 0
                    modo = 'pendiente'

                acum_generado = round(max(0, presupuesto_70 - premio + acum_recibido - acum_recibido), 2)
                # Si no se pagó premio, el 70% pasa al siguiente sorteo
                # max(0,...) evita acumulado negativo si premio > presupuesto (ej: Lechuza x70)
                acum_generado = round(max(0, presupuesto_70 - premio), 2)
                acum_corriente = round(max(0, acum_corriente + acum_generado - (premio - presupuesto_70 if premio > presupuesto_70 else 0)), 2)
                acum_corriente = max(0, acum_corriente)

            presupuesto_total = round(presupuesto_70 + acum_recibido, 2)
            para_casa = round(vendido * 0.30, 2)

            sorteos.append({
                'hora': hora,
                'animal': animal,
                'nombre': ANIMALES.get(animal, '—') if animal else '—',
                'vendido': vendido,
                'presupuesto_70': presupuesto_70,
                'acum_recibido': round(acum_recibido, 2),
                'presupuesto_total': presupuesto_total,
                'premio_pagado': round(premio, 2),
                'acum_generado': round(acum_generado, 2),
                'para_casa_30': para_casa,
                'modo': modo,
                'realizado': animal is not None
            })

            total_vendido_dia += vendido
            total_presupuesto_dia += presupuesto_70
            total_premio_dia += premio
            total_casa_dia += para_casa

        total_acumulado_fin = round(total_presupuesto_dia - total_premio_dia, 2)

        return jsonify({
            'status': 'ok',
            'fecha': fecha,
            'loteria': loteria,
            'sorteos': sorteos,
            'totales': {
                'vendido': round(total_vendido_dia, 2),
                'presupuesto_70': round(total_presupuesto_dia, 2),
                'premio_pagado': round(total_premio_dia, 2),
                'para_casa_30': round(total_casa_dia, 2),
                'acumulado_fin_jornada': total_acumulado_fin,
                'pct_pagado': round(total_premio_dia / total_vendido_dia * 100, 1) if total_vendido_dia > 0 else 0,
                'pct_casa': round((total_vendido_dia - total_premio_dia) / total_vendido_dia * 100, 1) if total_vendido_dia > 0 else 0,
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/resultados-fecha-admin', methods=['POST'])
@admin_required
def resultados_fecha_admin():
    data = request.get_json() or {}
    fs = data.get('fecha')
    loteria = data.get('loteria', 'peru')
    horarios = HORARIOS_PLUS if loteria == 'plus' else HORARIOS_PERU
    try: fecha_str = datetime.strptime(fs,"%Y-%m-%d").strftime("%d/%m/%Y")
    except: fecha_str = ahora_peru().strftime("%d/%m/%Y")
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
            ph = hash_password(p)
            db.execute("""
                INSERT INTO agencias (usuario,password,nombre_agencia,nombre_banco,es_admin,comision,activa)
                VALUES (%s,%s,%s,%s,0,%s,1)
            """,(u,ph,n,nb,COMISION_AGENCIA))
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
                ph = hash_password(data['password'])
                db.execute("UPDATE agencias SET password=%s WHERE id=%s AND es_admin=0",(ph,aid))
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
                WHERE jg.hora=%s AND jg.tipo='animal' AND jg.loteria=%s AND tk.anulado=0 AND SUBSTR(tk.fecha, 1, 10) = %s
                GROUP BY jg.seleccion
                ORDER BY jg.seleccion
            """, (hora, loteria, hoy)).fetchall()
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
                if USE_SQLITE:
                    db.execute("INSERT OR REPLACE INTO topes (hora, numero, monto_tope, loteria) VALUES (?,?,?,?)",
                        (hora, numero, monto, loteria))
                else:
                    db.execute("""INSERT INTO topes (hora, numero, monto_tope, loteria) VALUES (%s,%s,%s,%s)
                        ON CONFLICT(hora,numero,loteria) DO UPDATE SET monto_tope=EXCLUDED.monto_tope""",
                        (hora, numero, monto, loteria))
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
                WHERE jg.hora=%s AND jg.loteria=%s AND tk.anulado=0 AND SUBSTR(tk.fecha, 1, 10) = %s
                ORDER BY ag.nombre_agencia
            """, (sorteo, loteria, hoy)).fetchall()
            jugadas_rows = db.execute("""
                SELECT jg.seleccion, COALESCE(SUM(jg.monto),0) as apostado
                FROM jugadas jg
                JOIN tickets tk ON jg.ticket_id=tk.id
                WHERE jg.hora=%s AND jg.tipo='animal' AND jg.loteria=%s AND tk.anulado=0 AND SUBSTR(tk.fecha, 1, 10) = %s
                GROUP BY jg.seleccion
                ORDER BY jg.seleccion
            """, (sorteo, loteria, hoy)).fetchall()
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
            'presupuesto_70': round(total * 0.70, 2),
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
                WHERE tk.agencia_id=%s AND jg.hora=%s AND tk.anulado=0 AND SUBSTR(tk.fecha, 1, 10) = %s
                GROUP BY jg.seleccion, jg.tipo
                ORDER BY jg.seleccion
            """, (agencia_id, hora, hoy)).fetchall()
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

@app.route('/admin/reporte-agencia-horas', methods=['POST'])
@admin_required
def reporte_agencia_horas():
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
                SELECT jg.hora, jg.seleccion, jg.tipo, jg.monto, tk.fecha, tk.serial
                FROM jugadas jg
                JOIN tickets tk ON jg.ticket_id=tk.id
                WHERE tk.agencia_id=%s AND tk.anulado=0
                ORDER BY tk.fecha DESC
            """, (agencia_id,)).fetchall()
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
            found = next((x for x in por_hora[h]['jugadas'] if x['seleccion']==j['seleccion'] and x['tipo']==j['tipo']), None)
            if found:
                found['apostado'] = round(found['apostado'] + j['monto'], 2)
                found['cnt'] += 1
            else:
                por_hora[h]['jugadas'].append({'seleccion':j['seleccion'],'nombre':nombre,'tipo':j['tipo'],'apostado':round(j['monto'],2),'cnt':1})
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
            tickets = db.execute("SELECT * FROM tickets WHERE anulado=0 AND SUBSTR(fecha, 1, 10) = %s",(hoy,)).fetchall()
            data=[]; tv=tp=tc=0
            for ag in ags:
                mts=[t for t in tickets if t['agencia_id']==ag['id']]
                ventas=sum(t['total'] for t in mts); pp=0; pp_pend=0
                for t in mts:
                    p=calcular_premio_ticket(t['id'],db)
                    if t['pagado']:
                        pp+=p
                    elif p>0:
                        pp_pend+=p
                com=ventas*ag['comision']
                data.append({
                    'nombre':ag['nombre_agencia'],
                    'usuario':ag['usuario'],
                    'ventas':round(ventas,2),
                    'premios_pagados':round(pp,2),
                    'premios_pendientes':round(pp_pend,2),
                    'premios_total':round(pp+pp_pend,2),
                    'comision':round(com,2),
                    'balance':round(ventas-(pp+pp_pend)-com,2),
                    'tickets':len(mts)
                })
                tv+=ventas; tp+=(pp+pp_pend); tc+=com
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
            hora_compra_str = fecha_compra_dt.strftime("%I:%M %p").lstrip('0') if fecha_compra_dt else '?'
            res_validos = resultados_validos_para_tripleta(res_dia, fecha_compra_dt)
            salidos=list(dict.fromkeys([a for a in res_validos.values() if a in nums]))
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
        data=request.get_json()
        fi=data.get('fecha_inicio')
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
                    stats[aid]['premios']+=calcular_premio_ticket(t['id'],db)
        out=io.StringIO()
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
                s['nombre'], s['usuario'], s['tickets'],
                round(s['ventas'],2), round(s['premios'],2),
                round(com,2), round(s['ventas']-s['premios']-com,2)
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
                    prem+=calcular_premio_ticket(tid,db)
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
                p=calcular_premio_ticket(t['id'],db)
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


# ===================== HTML — LOGIN (sin cambios) =====================
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

# POS_HTML — sin cambios respecto a v3.1
POS_HTML = r'''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1,user-scalable=no">
<title>{{agencia}} — POS</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;600;700&family=Rajdhani:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#f0f4f8;--panel:#ffffff;--card:#f8fafc;--border:#e2e8f0;--gold:#c47b00;--blue:#1d4ed8;--teal:#0284c7;--red:#dc2626;--red-bg:#fef2f2;--red-border:#fca5a5;--negro:#1e3a5f;--negro-bg:#eff6ff;--negro-border:#bfdbfe;--verde:#166534;--verde-bg:#f0fdf4;--verde-border:#bbf7d0;--green:#16a34a;--orange:#ea580c;--purple:#7c3aed;--text:#1e293b;--text2:#64748b}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent;user-select:none}
html,body{height:100%;overflow:hidden}
body{background:var(--bg);color:var(--text);font-family:'Rajdhani',sans-serif;font-size:14px;display:flex;flex-direction:column}
.topbar{background:#1e293b;border-bottom:3px solid #f5a623;padding:0 10px;height:36px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.brand{font-family:'Oswald',sans-serif;font-size:1rem;font-weight:700;letter-spacing:2px;color:#fff}.brand em{color:var(--gold);font-style:normal}
.agent-name{color:#8ab0e0;font-size:.78rem;letter-spacing:1px;margin-left:10px}
.top-right{display:flex;align-items:center;gap:5px}
.clock{color:#f5a623;font-family:'Oswald',sans-serif;font-size:.8rem;background:#334155;padding:2px 6px;border-radius:3px;border:1px solid #475569;white-space:nowrap}
.tbtn{padding:4px 8px;border:none;background:#334155;color:#e2e8f0;border-radius:3px;cursor:pointer;font-size:.68rem;font-family:'Oswald',sans-serif;font-weight:700;letter-spacing:1px;white-space:nowrap}
.tbtn:hover{background:#475569;color:#fff}.tbtn.exit{background:#991b1b;color:#fff}.tbtn.exit:hover{background:#b91c1c}
.layout{display:flex;flex:1;overflow:hidden;gap:0;min-height:0}
.left-panel{display:flex;flex-direction:column;width:55%;border-right:2px solid var(--border);overflow:hidden;background:#ffffff;min-height:0}
.especiales-bar{display:flex;gap:4px;padding:5px 6px;background:#f1f5f9;border-bottom:2px solid var(--border);flex-shrink:0}
.esp-btn{flex:1;padding:9px 4px;text-align:center;border-radius:4px;cursor:pointer;font-family:'Oswald',sans-serif;font-size:.82rem;font-weight:700;letter-spacing:1px;border:2px solid transparent;transition:all .15s}
.esp-btn.rojo{background:#cc1a1a;border-color:#ff2a2a;color:#fff}.esp-btn.rojo.sel{background:#ff1a1a;border-color:#ff6060;box-shadow:0 0 12px rgba(255,40,40,.5)}.esp-btn.rojo:hover{background:#e02020;border-color:#ff4040}
.esp-btn.negro{background:#1a2a5a;border-color:#2a4090;color:#c0d8ff}.esp-btn.negro.sel{background:#2a3a80;border-color:#4060d0;box-shadow:0 0 12px rgba(60,100,240,.5)}.esp-btn.negro:hover{background:#223070;border-color:#3050c0}
.esp-btn.par{background:#0a7a90;border-color:#00c4d8;color:#fff}.esp-btn.par.sel{background:#00a0c0;border-color:#00e8ff;box-shadow:0 0 12px rgba(0,200,220,.5)}.esp-btn.par:hover{background:#0a8aa0;border-color:#00d0e8}
.esp-btn.impar{background:#6a20a0;border-color:#9a40d0;color:#fff}.esp-btn.impar.sel{background:#8030c0;border-color:#c060ff;box-shadow:0 0 12px rgba(160,80,240,.5)}.esp-btn.impar:hover{background:#7a28b0;border-color:#b050e8}
.manual-box{padding:6px;background:#f1f5f9;border-bottom:2px solid #e2e8f0}
.manual-input{width:100%;padding:8px;background:#fff;border:2px solid #0284c7;border-radius:4px;color:#c47b00;font-family:'Oswald',sans-serif;font-size:1rem;letter-spacing:1px;text-transform:uppercase}
.manual-input:focus{outline:none;border-color:#7c3aed}
.manual-label{color:#64748b;font-size:.65rem;font-family:'Oswald',sans-serif;letter-spacing:1px;margin-bottom:4px;display:flex;justify-content:space-between}
.manual-label span{color:#f5a623}
.animals-scroll{flex:1;overflow-y:auto;padding:4px 5px;min-height:0}
.animals-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px}
.acard{border-radius:5px;padding:8px 3px;text-align:center;cursor:pointer;transition:all .12s;border:2px solid transparent;position:relative;min-height:54px;display:flex;flex-direction:column;align-items:center;justify-content:center}
.acard:active{transform:scale(.95)}
.acard.cv{background:#166534;border-color:#166534}.acard.cv .anum{color:#ffffff}.acard.cv .anom{color:#f0fff0}.acard.cv:hover{background:#15803d;border-color:#15803d}.acard.cv.sel{box-shadow:0 0 8px rgba(2,132,199,.4);transform:scale(1.05);border-color:#0284c7!important}
.acard.cr{background:#780606;border-color:#780606}.acard.cr .anum{color:#ffffff}.acard.cr .anom{color:#fff5f5}.acard.cr:hover{background:#991b1b;border-color:#991b1b}.acard.cr.sel{box-shadow:0 0 8px rgba(2,132,199,.4);transform:scale(1.05);border-color:#0284c7!important}
.acard.cn{background:#000000;border-color:#000000}.acard.cn .anum{color:#ffffff}.acard.cn .anom{color:#f8f8ff}.acard.cn:hover{background:#1e293b;border-color:#1e293b}.acard.cn.sel{box-shadow:0 0 8px rgba(2,132,199,.4);transform:scale(1.05);border-color:#0284c7!important}
.acard.cl{background:#fef9c3;border-color:#d97706}.acard.cl .anum{color:#000000}.acard.cl .anom{color:#92400e}.acard.cl:hover{background:#fef08a;border-color:#b45309}.acard.cl.sel{box-shadow:0 0 8px rgba(2,132,199,.4);transform:scale(1.05);border-color:#0284c7!important}
.acard.sel::after{content:'✓';position:absolute;top:0;right:2px;font-size:.6rem;color:#fff;font-weight:700}
.anum{font-size:.9rem;font-weight:700;font-family:'Oswald',sans-serif;line-height:1.1}
.anom{font-size:.72rem;font-weight:600;line-height:1.2;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}
.right-panel{width:45%;display:flex;flex-direction:column;overflow-y:auto;background:#f8fafc;padding:6px;min-height:0}
.rsec{padding:6px 8px;border-bottom:1px solid var(--border)}
.rlabel{font-family:'Oswald',sans-serif;font-size:.65rem;font-weight:600;color:#64748b;letter-spacing:2px;text-transform:uppercase;margin-bottom:4px}
.horas-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:3px}
.hbtn{padding:6px 2px;text-align:center;background:#f1f5f9;border:2px solid #cbd5e1;border-radius:3px;cursor:pointer;font-size:.72rem;font-family:'Oswald',sans-serif;color:#475569;transition:all .15s;line-height:1.2}
.hbtn:hover{background:#0284c7;border-color:#0284c7;color:#fff}.hbtn.sel{background:#0284c7;border-color:#0369a1;color:#fff;font-weight:700}.hbtn.bloq{background:#fee2e2;border-color:#fca5a5;color:#ef4444;cursor:not-allowed;opacity:.7}
.hbtn .hperu{font-size:.82rem;font-weight:700}.hbtn .hven{font-size:.68rem;color:#94a3b8}.hbtn.sel .hven{color:#e0f2fe}
.horas-btns-row{display:flex;gap:3px;margin-top:3px}
.hsel-btn{flex:1;padding:5px;font-size:.65rem;background:#e2e8f0;border:2px solid #cbd5e1;color:#475569;border-radius:3px;cursor:pointer;font-family:'Oswald',sans-serif;font-weight:700;text-align:center;transition:all .15s}
.hsel-btn:hover{background:#0284c7;border-color:#0284c7;color:#fff}
.monto-sec{padding:5px 8px;border-bottom:1px solid var(--border)}
.presets{display:flex;flex-wrap:wrap;gap:3px;margin-bottom:4px}
.mpre{padding:7px 10px;background:#e2e8f0;border:2px solid #cbd5e1;border-radius:3px;color:#1e293b;cursor:pointer;font-size:.82rem;font-family:'Oswald',sans-serif;font-weight:700;transition:all .15s}
.mpre:hover,.mpre:active{background:#0284c7;border-color:#0284c7;color:#fff}
.monto-input-wrap{display:flex;align-items:center;gap:4px}
.monto-label{color:#f5a623;font-size:.85rem;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:1px;white-space:nowrap}
.monto-input{flex:1;padding:9px 8px;background:#fff;border:2px solid #d97706;border-radius:3px;color:#c47b00;font-size:1.1rem;font-family:'Oswald',sans-serif;font-weight:700;text-align:center;letter-spacing:1px}
.monto-input:focus{outline:none;border-color:#f59e0b;box-shadow:0 0 8px rgba(245,158,11,.25)}
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
.actions-sec{padding:5px 8px;display:flex;flex-direction:column;gap:3px;flex-shrink:0}
.btn-add{width:100%;padding:11px;background:#1a3a90;color:#fff;border:2px solid #4070d0;border-radius:4px;font-family:'Oswald',sans-serif;font-weight:700;font-size:.88rem;letter-spacing:2px;cursor:pointer;transition:all .15s}
.btn-add:hover{background:#2050c0;border-color:#60a0ff}
.btn-wa{width:100%;padding:11px;background:#16a34a;color:#fff;border:2px solid #22c55e;border-radius:4px;font-family:'Oswald',sans-serif;font-weight:700;font-size:.88rem;letter-spacing:2px;cursor:pointer;transition:all .15s}
.btn-wa:hover{background:#15803d}.btn-wa:disabled{background:#dcfce7;border-color:#bbf7d0;color:#86efac;cursor:not-allowed}
.btns-row{display:grid;grid-template-columns:1fr 1fr;gap:3px}.btns-row2{display:grid;grid-template-columns:1fr 1fr 1fr;gap:3px}
.abtn{padding:10px 4px;text-align:center;border-radius:4px;cursor:pointer;font-family:'Oswald',sans-serif;font-size:.75rem;font-weight:700;letter-spacing:1px;border:2px solid;transition:all .15s;white-space:nowrap;color:#fff}
.abtn.res{background:#006080;border-color:#00b8d8}.abtn.res:hover{background:#0080a8;border-color:#00e0ff}
.abtn.caja{background:#166534;border-color:#22c55e}.abtn.caja:hover{background:#15803d;border-color:#4ade80}
.abtn.pagar{background:#854d0e;border-color:#f59e0b}.abtn.pagar:hover{background:#a16207;border-color:#fbbf24}
.abtn.trip{background:#6b21a8;border-color:#a855f7}.abtn.trip:hover{background:#7e22ce;border-color:#c084fc}
.abtn.anular{background:#991b1b;border-color:#ef4444}.abtn.anular:hover{background:#b91c1c;border-color:#ff6060}
.abtn.borrar{background:#7c2d12;border-color:#f97316}.abtn.borrar:hover{background:#9a3412;border-color:#fb923c}
.abtn.rep{background:#1e40af;border-color:#3b82f6}.abtn.rep:hover{background:#2563eb;border-color:#60a5fa}
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
.tcard.gano{border-left-color:#16a34a;background:#f0fdf4}.tcard.pte{border-left-color:#f59e0b;background:#fffbeb}
.ts{color:#0284c7;font-weight:700;font-family:'Oswald',sans-serif}
.badge{display:inline-block;padding:2px 6px;border-radius:3px;font-size:.62rem;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:1px;color:#fff}
.badge.p{background:#16a34a;border:1px solid #22c55e}.badge.g{background:#854d0e;border:1px solid #f59e0b}.badge.n{background:#1e40af;border:1px solid #3b82f6}
.jrow{display:flex;justify-content:space-between;align-items:center;padding:3px 8px;margin:2px 0;border-radius:3px;background:#f1f5f9;border-left:3px solid #e2e8f0;font-size:.73rem}
.jrow.gano{background:#f0fdf4;border-left-color:#16a34a}
.trip-row{display:flex;justify-content:space-between;align-items:center;padding:5px 8px;margin:2px 0;border-radius:3px;background:#faf5ff;border-left:3px solid #7c3aed;font-size:.73rem}
.trip-row.gano{background:#060418;border-left-color:#c084fc}
.sbox{background:#f8fafc;border-radius:3px;padding:10px;margin:6px 0;border:1px solid #e2e8f0}
.srow{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #f1f5f9;font-size:.75rem}.srow:last-child{border-bottom:none}
.sl{color:#64748b}.sv{color:#c47b00;font-weight:700;font-family:'Oswald',sans-serif}
.caja-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}
.cg{background:#f8fafc;border:2px solid #e2e8f0;border-radius:3px;padding:10px;text-align:center}
.cgl{color:#64748b;font-size:.6rem;letter-spacing:2px;margin-bottom:3px;font-family:'Oswald',sans-serif}
.cgv{color:#c47b00;font-size:1rem;font-weight:700;font-family:'Oswald',sans-serif}.cgv.g{color:#16a34a}.cgv.r{color:#dc2626}
.trip-slots{display:flex;gap:8px;margin-bottom:12px}
.tslot{flex:1;background:#faf5ff;border:2px solid #c4b5fd;border-radius:4px;padding:8px;text-align:center;cursor:pointer;min-height:46px;display:flex;flex-direction:column;align-items:center;justify-content:center;transition:all .15s}
.tslot.act{border-color:#7c3aed;box-shadow:0 0 12px rgba(124,58,237,.3);background:#ede9fe}.tslot.fill{border-color:#7c3aed;background:#f5f3ff}
.tslot .snum{font-size:.9rem;font-weight:700;font-family:'Oswald',sans-serif;color:#7c3aed}
.tslot .snom{font-size:.58rem;color:#6d28d9}.tslot .sph{font-size:.65rem;color:#7c3aed;letter-spacing:1px}
.trip-modal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;margin-top:12px;max-height:300px;overflow-y:auto;padding:4px}
.trip-modal-grid .acard{padding:6px 2px}
.toast{position:fixed;bottom:10px;left:50%;transform:translateX(-50%);padding:8px 18px;border-radius:4px;font-family:'Oswald',sans-serif;font-size:.78rem;letter-spacing:1px;font-weight:700;z-index:9999;display:none;max-width:90%;text-align:center}
.toast.ok{background:#16a34a;color:#fff;border:2px solid #22c55e}.toast.err{background:#dc2626;color:#fff;border:2px solid #ef4444}
::-webkit-scrollbar{width:4px;height:4px}::-webkit-scrollbar-track{background:#f1f5f9}::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:2px}::-webkit-scrollbar-thumb:hover{background:#94a3b8}
.rep-info{background:#0a1a30;border:1px solid #1a4a80;border-radius:4px;padding:10px;margin-bottom:12px;font-size:.8rem;color:#80b0e0}
.rep-item{display:flex;align-items:center;gap:8px;padding:6px;background:#060c1a;border-radius:3px;margin-bottom:6px;border:1px solid #1a2a40}
.rep-item select{flex:1;padding:6px;background:#0a1828;border:1px solid #2a4a80;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem}
.rep-item input[type="number"]{width:80px;padding:6px;background:#0a1828;border:1px solid #d97706;color:#fbbf24;font-family:'Oswald',sans-serif;text-align:center}
@media(max-width:599px){html,body{overflow:auto}.layout{flex-direction:column}.left-panel{width:100%;border-right:none;border-bottom:2px solid var(--border);max-height:60vh}.right-panel{width:100%}.animals-grid{grid-template-columns:repeat(7,1fr)}.trip-modal-grid{grid-template-columns:repeat(7,1fr)}.topbar .agent-name{display:none}}
@media(min-width:600px) and (max-width:900px){.animals-grid{grid-template-columns:repeat(7,1fr)}.trip-modal-grid{grid-template-columns:repeat(7,1fr)}}
</style></head><body>
<div class="topbar">
  <div style="display:flex;align-items:center"><div class="brand">ZOO<em>LO</em></div><div class="agent-name">{{agencia}}</div></div>
  <div class="top-right">
    <div class="clock" id="clock">--:--</div>
    <button class="tbtn" onclick="openMod('mod-consultas')">📋 Consultas</button>
    <button class="tbtn" onclick="openMod('mod-archivo')">📁 Archivo</button>
    <button class="tbtn exit" onclick="location.href='/logout'">SALIR</button>
  </div>
</div>
<div id="offline-banner" style="display:none;background:#fef2f2;border-bottom:2px solid #ef4444;padding:6px 14px;align-items:center;justify-content:center;gap:10px;flex-shrink:0">
  <span style="color:#dc2626;font-family:'Oswald',sans-serif;font-size:.82rem;letter-spacing:2px;font-weight:700">⚠️ SIN CONEXIÓN — VENTA BLOQUEADA PARA EVITAR TICKETS FANTASMA</span>
</div>
<div class="layout">
  <div class="left-panel">
    <div class="especiales-bar">
      <div class="esp-btn rojo" id="esp-ROJO" onclick="selEsp('ROJO')">ROJO</div>
      <div class="esp-btn negro" id="esp-NEGRO" onclick="selEsp('NEGRO')">NEGRO</div>
      <div class="esp-btn par" id="esp-PAR" onclick="selEsp('PAR')">PAR</div>
      <div class="esp-btn impar" id="esp-IMPAR" onclick="selEsp('IMPAR')">IMPAR</div>
    </div>
    <div class="manual-box">
      <div class="manual-label"><span>📝 JUGADA MANUAL (pegar números)</span><span style="font-size:.6rem;color:#4a6090">Ej: 2.25.36.14.11</span></div>
      <div style="display:flex;gap:4px">
        <input type="text" class="manual-input" id="manual-input" placeholder="1.5.6.12 ó 5,6,8,40" style="flex:1" onpaste="handleManualPaste(event)" onkeyup="handleManualKeyup(event)">
        <button style="padding:6px 10px;background:#1a3a70;border:1px solid #2060c0;color:#80c0ff;font-size:.75rem;font-family:'Oswald',sans-serif;cursor:pointer;border-radius:3px;white-space:nowrap" onclick="confirmarManual()">✓ OK</button>
      </div>
    </div>
    <div class="animals-scroll"><div class="animals-grid" id="animals-grid"></div></div>
    <div class="ticket-sec">
      <div class="rlabel" style="padding:4px 0 2px;color:#854d0e;letter-spacing:2px">🎫 TICKET EN ELABORACIÓN</div>
      <div class="ticket-list" id="ticket-list"><div class="ticket-empty">TICKET VACÍO</div></div>
      <div id="ticket-total" style="display:none" class="ticket-total"></div>
    </div>
  </div>
  <div class="right-panel">
    <div class="rsec">
      <div style="display:flex;gap:4px;margin-bottom:6px">
        <button id="tab-peru" onclick="cambiarLoteria('peru')" style="flex:1;padding:7px 4px;background:#1a3a90;border:2px solid #4070d0;border-radius:4px;color:#fff;font-family:'Oswald',sans-serif;font-size:.72rem;font-weight:700;letter-spacing:1px;cursor:pointer;transition:all .15s" class="active">🇵🇪 ZOOLO PERU</button>
        <button id="tab-plus" onclick="cambiarLoteria('plus')" style="flex:1;padding:7px 4px;background:#3b0764;border:2px solid #a855f7;border-radius:4px;color:#fff;font-family:'Oswald',sans-serif;font-size:.72rem;font-weight:700;letter-spacing:1px;cursor:pointer;transition:all .15s">🎰 ZOOLO PLUS</button>
      </div>
      <div class="rlabel" id="horas-label">⏰ PERÚ — 11 Sorteos (Cierra 3 min antes (al :57))</div>
      <div class="horas-grid" id="horas-grid"></div>
      <div class="horas-btns-row"><button class="hsel-btn" onclick="selTodos()">☑ Todos</button><button class="hsel-btn" onclick="limpiarH()">✕ Limpiar</button></div>
    </div>
    <div class="monto-sec">
      <div class="presets">
        <button class="mpre" onclick="setM(.5)">0.5</button><button class="mpre" onclick="setM(1)">1</button><button class="mpre" onclick="setM(2)">2</button><button class="mpre" onclick="setM(5)">5</button><button class="mpre" onclick="setM(10)">10</button><button class="mpre" onclick="setM(20)">20</button><button class="mpre" onclick="setM(50)">50</button>
      </div>
      <div class="monto-input-wrap"><span class="monto-label">S/</span><input type="number" class="monto-input" id="monto" value="1" min="0.5" step="0.5"></div>
    </div>
    <div class="actions-sec">
      <button class="btn-add" onclick="agregar()">➕ AGREGAR AL TICKET</button>
      <button class="btn-wa" onclick="vender()" id="btn-wa" disabled>📤 ENVIAR POR WHATSAPP</button>
      <div class="btns-row"><div class="abtn res" onclick="openResultados()">📊 RESULTADOS</div><div class="abtn caja" onclick="openCaja()">💰 CAJA</div></div>
      <div class="btns-row"><div class="abtn pagar" onclick="openPagar()">💵 PAGAR</div><div class="abtn anular" onclick="openAnular()">❌ ANULAR</div></div>
      <div class="btns-row2"><div class="abtn trip" onclick="openTripletaModal()">🎯 TRIPLETA</div><div class="abtn rep" onclick="openRepetirModal()">🔄 REPETIR</div><div class="abtn borrar" onclick="borrarTodo()">🗑 BORRAR</div></div>
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>
<div class="modal" id="mod-repetir"><div class="mc"><div class="mh"><h3>🔄 REPETIR TICKET</h3><button class="btn-close" onclick="closeMod('mod-repetir')">✕</button></div><div class="mbody"><div class="frow"><input type="text" id="rep-serial" placeholder="Serial del ticket" style="flex:2"><button class="btn-q" onclick="cargarTicketRepetir()" style="flex:1;margin:0">CARGAR</button></div><div id="rep-contenido"></div></div></div></div>
<div class="modal" id="mod-tripleta"><div class="mc"><div class="mh" style="border-color:#7c3aed;background:linear-gradient(135deg,#1a0a30,#0c1a3a)"><h3 style="color:#e0d0ff;font-family:'Oswald',sans-serif;letter-spacing:2px">🎯 JUGAR TRIPLETA x60</h3><button class="btn-close" onclick="closeMod('mod-tripleta')">✕</button></div><div class="mbody">
<div style="display:flex;gap:0;border:2px solid #2a3a6a;border-radius:6px;overflow:hidden;margin-bottom:14px">
  <button id="trip-tab-peru" onclick="selTripLoteria('peru')" style="flex:1;padding:10px 6px;font-family:'Oswald',sans-serif;font-size:.8rem;letter-spacing:1px;cursor:pointer;border:none;transition:all .2s;background:#0c2461;color:#90b8ff">🇵🇪 ZOOLO PERÚ<br><span style="font-size:.62rem;opacity:.8">11 sorteos · 8AM–6PM Lima</span></button>
  <button id="trip-tab-plus" onclick="selTripLoteria('plus')" style="flex:1;padding:10px 6px;font-family:'Oswald',sans-serif;font-size:.8rem;letter-spacing:1px;cursor:pointer;border:none;transition:all .2s;background:#1a0540;color:#c084fc">🎰 ZOOLO PLUS<br><span style="font-size:.62rem;opacity:.8">12 sorteos · 8AM–7PM VEN</span></button>
</div>
<div class="trip-slots"><div class="tslot act" id="tms0" onclick="activarSlotModal(0)"><div class="sph">ANIMAL 1</div></div><div class="tslot" id="tms1" onclick="activarSlotModal(1)"><div class="sph">ANIMAL 2</div></div><div class="tslot" id="tms2" onclick="activarSlotModal(2)"><div class="sph">ANIMAL 3</div></div></div>
<div class="trip-modal-grid" id="trip-modal-grid"></div>
<div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border)"><div style="color:var(--purple);font-size:.75rem;margin-bottom:6px;font-family:'Oswald',sans-serif;letter-spacing:1px">MONTO PARA TRIPLETA</div><div class="monto-input-wrap"><span class="monto-label">S/</span><input type="number" class="monto-input" id="monto-tripleta" value="1" min="0.5" step="0.5"></div></div>
<div style="display:flex;gap:8px;margin-top:12px"><button class="btn-q" id="trip-btn-agregar" style="flex:1" onclick="agregarTripletaModal()">✅ AGREGAR AL TICKET</button><button class="btn-close" style="flex:1;background:#1e3050;border-color:#4080c0;color:#90c0ff" onclick="closeMod('mod-tripleta')">CANCELAR</button></div>
</div></div></div>
<div class="modal" id="mod-resultados"><div class="mc"><div class="mh"><h3>📊 RESULTADOS</h3><button class="btn-close" onclick="closeMod('mod-resultados')">✕</button></div><div class="mbody"><div class="frow"><input type="date" id="res-fecha"></div><button class="btn-q" onclick="cargarResultados()">VER RESULTADOS</button><div id="res-titulo" style="color:var(--teal);font-family:'Oswald',sans-serif;letter-spacing:2px;text-align:center;margin-bottom:8px;font-size:.8rem"></div><div id="res-lista" style="max-height:340px;overflow-y:auto"></div></div></div></div>
<div class="modal" id="mod-consultas"><div class="mc"><div class="mh"><h3>📋 CONSULTAS</h3><button class="btn-close" onclick="closeMod('mod-consultas')">✕</button></div><div class="mbody"><div class="frow"><input type="date" id="mt-ini"><input type="date" id="mt-fin"><select id="mt-estado"><option value="todos">Todos</option><option value="pagados">Pagados</option><option value="pendientes">Pendientes</option><option value="por_pagar">Con Premio</option></select></div><button class="btn-q" onclick="consultarTickets()">BUSCAR</button><div id="mt-resumen" style="display:none;background:rgba(0,180,216,.06);border:1px solid #0a4050;border-radius:3px;padding:8px;margin-bottom:8px;color:var(--teal);font-size:.78rem;font-family:'Oswald',sans-serif;letter-spacing:1px"></div><div id="mt-lista" style="max-height:400px;overflow-y:auto"><p style="color:var(--text2);text-align:center;padding:20px;letter-spacing:2px;font-size:.75rem">USE LOS FILTROS Y BUSQUE</p></div></div></div></div>
<div class="modal" id="mod-archivo"><div class="mc"><div class="mh"><h3>📁 ARCHIVO — CAJA HISTÓRICO</h3><button class="btn-close" onclick="closeMod('mod-archivo')">✕</button></div><div class="mbody"><div class="frow"><input type="date" id="ar-ini"><input type="date" id="ar-fin"></div><button class="btn-q" onclick="cajaHist()">VER HISTÓRICO</button><div id="ar-res"></div></div></div></div>
<div class="modal" id="mod-pagar"><div class="mc"><div class="mh"><h3>💵 VERIFICAR / PAGAR</h3><button class="btn-close" onclick="closeMod('mod-pagar')">✕</button></div><div class="mbody"><div class="frow"><input type="text" id="pag-serial" placeholder="Serial del ticket"></div><button class="btn-q" onclick="verificarTicket()">VERIFICAR</button><div id="pag-res"></div></div></div></div>
<div class="modal" id="mod-anular"><div class="mc"><div class="mh"><h3>❌ ANULAR TICKET</h3><button class="btn-close" onclick="closeMod('mod-anular')">✕</button></div><div class="mbody"><div class="frow"><input type="text" id="an-serial" placeholder="Serial del ticket"></div><button class="btn-q" style="background:linear-gradient(135deg,#3a1010,#280808);border-color:#6b1515;color:#e05050" onclick="anularTicket()">ANULAR</button><div id="an-res"></div></div></div></div>
<div class="modal" id="mod-caja"><div class="mc"><div class="mh"><h3>💰 CAJA HOY</h3><button class="btn-close" onclick="closeMod('mod-caja')">✕</button></div><div class="mbody" id="caja-body"></div></div></div>
<script>
const ANIMALES = {{ animales | tojson }};
const COLORES  = {{ colores | tojson }};
const HPERU = {{ horarios_peru | tojson }};
const HPLUS = {{ horarios_plus | tojson }};
const ROJOS = ["1","3","5","7","9","12","14","16","18","19","21","23","25","27","30","32","34","36","37","39"];
const ORDEN = ['00','0','1','2','3','4','5','6','7','8','9','10','11','12','13','14','15','16','17','18','19','20','21','22','23','24','25','26','27','28','29','30','31','32','33','34','35','36','37','38','39','40'];
let carrito=[],horasSel=[],horasSelPlus=[],animalesSel=[],espSel=null,horasBloq=[],horasBloqPlus=[],loteriaActiva='peru',tripSlotModal=0,tripAnimModal=[null,null,null];
function init(){renderAnimales();renderHoras();renderTripModalGrid();actualizarBloq();setInterval(actualizarBloq,30000);setInterval(actualizarClock,1000);setInterval(verificarConexion,10000);actualizarClock();verificarConexion();let hoy=new Date().toISOString().split('T')[0];['res-fecha','mt-ini','mt-fin','ar-ini','ar-fin'].forEach(id=>{let el=document.getElementById(id);if(el)el.value=hoy});}
let _sinConexion=false;
function verificarConexion(){fetch('/api/hora-actual',{cache:'no-store'}).then(r=>{if(r.ok&&_sinConexion){_sinConexion=false;document.getElementById('offline-banner').style.display='none';document.getElementById('btn-wa').disabled=window._carritoLen===0;}}).catch(()=>{_sinConexion=true;document.getElementById('offline-banner').style.display='flex';document.getElementById('btn-wa').disabled=true;});}
function actualizarClock(){let now=new Date(),utcMs=now.getTime()+now.getTimezoneOffset()*60000,peruMs=utcMs-5*3600000,peru=new Date(peruMs),h=peru.getHours(),m=peru.getMinutes(),ap=h>=12?'PM':'AM';h=h%12||12;document.getElementById('clock').textContent=`${h}:${String(m).padStart(2,'0')} ${ap} · LIMA`;}
function actualizarBloq(){fetch('/api/hora-actual').then(r=>r.json()).then(d=>{horasBloq=d.bloqueadas||[];horasBloqPlus=d.bloqueadas_plus||[];horasSel=horasSel.filter(h=>!horasBloq.includes(h));horasSelPlus=horasSelPlus.filter(h=>!horasBloqPlus.includes(h));renderHoras();}).catch(()=>{});}
function getCardClass(k){if(k==='40')return 'cl';let c=COLORES[k];if(c==='verde')return 'cv';if(c==='rojo')return 'cr';return 'cn';}
function renderAnimales(){let g=document.getElementById('animals-grid');g.innerHTML='';ORDEN.forEach(k=>{if(!ANIMALES[k])return;let d=document.createElement('div');d.className=`acard ${getCardClass(k)}`;d.dataset.k=k;d.innerHTML=`<div class="anum">${k}</div><div class="anom">${ANIMALES[k]}</div>`;d.onclick=()=>toggleAnimal(k,d);g.appendChild(d);});}
function toggleAnimal(k,el){let i=animalesSel.indexOf(k);if(i>=0){animalesSel.splice(i,1);el.classList.remove('sel');}else{animalesSel.push(k);el.classList.add('sel');}}
function handleManualPaste(e){e.preventDefault();let texto=(e.clipboardData||window.clipboardData).getData('text');document.getElementById('manual-input').value=texto;procesarManual(texto);}
function handleManualKeyup(e){let val=e.target.value;if(e.key==='Enter'){procesarManual(val);e.target.value='';}}
function procesarManual(texto){if(!texto||!texto.trim())return;let nums=texto.split(/[.,\-;\s\n\/|]+/).map(x=>x.trim()).filter(x=>x!=='');let validos=[],invalidos=[];nums.forEach(n=>{let num=n==='00'?'00':n.replace(/^0+/,'')||'0';if(ANIMALES[num]!==undefined){if(!validos.includes(num))validos.push(num);}else invalidos.push(n);});if(!validos.length){toast('No se encontraron números válidos (0-40 ó 00)','err');return;}validos.forEach(k=>{if(!animalesSel.includes(k))animalesSel.push(k);let card=document.querySelector(`.acard[data-k="${k}"]`);if(card)card.classList.add('sel');});let msg=`✅ Seleccionados: ${validos.map(k=>k+'-'+ANIMALES[k]).join(', ')}`;if(invalidos.length)msg+=` | Ignorados: ${invalidos.join(',')}`;toast(msg,'ok');document.getElementById('manual-input').value='';}
function confirmarManual(){let val=document.getElementById('manual-input').value;if(val.trim())procesarManual(val);}
function selEsp(v){if(espSel===v){espSel=null;document.getElementById('esp-'+v).classList.remove('sel');}else{if(espSel)document.getElementById('esp-'+espSel).classList.remove('sel');espSel=v;animalesSel=[];document.querySelectorAll('.animals-grid .acard').forEach(c=>c.classList.remove('sel'));document.getElementById('esp-'+v).classList.add('sel');}}
function renderHoras(){let g=document.getElementById('horas-grid');g.innerHTML='';let isPlus=loteriaActiva==='plus',lista=isPlus?HPLUS:HPERU,bloq=isPlus?horasBloqPlus:horasBloq,sel=isPlus?horasSelPlus:horasSel;lista.forEach(h=>{let b=document.createElement('div');b.className='hbtn';let isBloq=bloq.includes(h),isSel=sel.includes(h);if(isBloq)b.classList.add('bloq');if(isSel)b.classList.add('sel');b.innerHTML=`<div class="hperu">${h.replace(':00','')}</div>`;if(!isBloq)b.onclick=()=>toggleH(h);g.appendChild(b);});}
function toggleH(h){let isPlus=loteriaActiva==='plus',arr=isPlus?horasSelPlus:horasSel,i=arr.indexOf(h);if(i>=0)arr.splice(i,1);else arr.push(h);renderHoras();}
function selTodos(){if(loteriaActiva==='plus')horasSelPlus=HPLUS.filter(h=>!horasBloqPlus.includes(h));else horasSel=HPERU.filter(h=>!horasBloq.includes(h));renderHoras();}
function limpiarH(){if(loteriaActiva==='plus')horasSelPlus=[];else horasSel=[];renderHoras();}
function cambiarLoteria(lot){loteriaActiva=lot;let lbl=lot==='plus'?'⏰ PLUS — 12 Sorteos (Cierra 3 min antes (al :57))':'⏰ PERÚ — 11 Sorteos (Cierra 3 min antes (al :57))';document.getElementById('horas-label').textContent=lbl;renderHoras();}
function openTripletaModal(){tripAnimModal=[null,null,null];tripSlotModal=0;actualizarSlotsModal();renderTripModalGrid();selTripLoteria(loteriaActiva||'peru');openMod('mod-tripleta');}
function selTripLoteria(lot){window.tripLoteriaModal=lot;let tabPeru=document.getElementById('trip-tab-peru'),tabPlus=document.getElementById('trip-tab-plus'),btn=document.getElementById('trip-btn-agregar');if(lot==='plus'){tabPlus.style.background='#6b21a8';tabPlus.style.color='#f3e8ff';tabPlus.style.fontWeight='700';tabPlus.style.boxShadow='inset 0 -3px 0 #a855f7';tabPeru.style.background='#0c1020';tabPeru.style.color='#4a6090';tabPeru.style.fontWeight='normal';tabPeru.style.boxShadow='none';btn.style.background='linear-gradient(135deg,#6b21a8,#4c1d95)';btn.style.borderColor='#a855f7';btn.style.color='#f3e8ff';btn.textContent='✅ AGREGAR — ZOOLO PLUS';}else{tabPeru.style.background='#0c4a9e';tabPeru.style.color='#e0f0ff';tabPeru.style.fontWeight='700';tabPeru.style.boxShadow='inset 0 -3px 0 #3b9eff';tabPlus.style.background='#0c1020';tabPlus.style.color='#4a6090';tabPlus.style.fontWeight='normal';tabPlus.style.boxShadow='none';btn.style.background='linear-gradient(135deg,#166534,#14532d)';btn.style.borderColor='#22c55e';btn.style.color='#dcfce7';btn.textContent='✅ AGREGAR — ZOOLO PERÚ';}}
function renderTripModalGrid(){let g=document.getElementById('trip-modal-grid');if(!g)return;g.innerHTML='';ORDEN.forEach(k=>{if(!ANIMALES[k])return;let d=document.createElement('div');d.className=`acard ${getCardClass(k)}`;d.innerHTML=`<div class="anum">${k}</div><div class="anom">${ANIMALES[k]}</div>`;d.onclick=()=>selTripAnimModal(k);g.appendChild(d);});}
function activarSlotModal(i){tripSlotModal=i;actualizarSlotsModal();}
function selTripAnimModal(k){let otro=tripAnimModal.findIndex((x,idx)=>x===k&&idx!==tripSlotModal);if(otro>=0){toast('Animal ya seleccionado en otro slot','err');return;}tripAnimModal[tripSlotModal]=k;actualizarSlotsModal();if(tripSlotModal<2){let nextEmpty=tripAnimModal.findIndex(x=>x===null,tripSlotModal+1);if(nextEmpty===-1)nextEmpty=tripSlotModal+1;if(nextEmpty<3)tripSlotModal=nextEmpty;}actualizarSlotsModal();}
function actualizarSlotsModal(){for(let i=0;i<3;i++){let s=document.getElementById('tms'+i),k=tripAnimModal[i];if(k){s.innerHTML=`<div class="snum">${k}</div><div class="snom">${ANIMALES[k].substring(0,6)}</div>`;s.className=`tslot fill${i===tripSlotModal?' act':''}`;s.onclick=()=>{tripAnimModal[i]=null;activarSlotModal(i);};}else{s.innerHTML=`<div class="sph">ANIMAL ${i+1}</div>`;s.className=`tslot${i===tripSlotModal?' act':''}`;s.onclick=()=>activarSlotModal(i);}}}
function agregarTripletaModal(){if(tripAnimModal.includes(null)){toast('Selecciona los 3 animales','err');return;}let monto=parseFloat(document.getElementById('monto-tripleta').value)||0;if(monto<=0){toast('Monto inválido','err');return;}let lot=window.tripLoteriaModal||loteriaActiva||'peru',sel=tripAnimModal.join(','),desc=tripAnimModal.map(n=>n+'-'+ANIMALES[n].substring(0,4)).join(' ');carrito.push({tipo:'tripleta',hora:'TODO DÍA',seleccion:sel,monto,desc:'🎯 '+desc,loteria:lot});renderCarrito();closeMod('mod-tripleta');toast(`Tripleta agregada`,'ok');}
function openRepetirModal(){document.getElementById('rep-serial').value='';document.getElementById('rep-contenido').innerHTML='';openMod('mod-repetir');}
function cargarTicketRepetir(){let serial=document.getElementById('rep-serial').value.trim();if(!serial){toast('Ingrese serial','err');return;}fetch('/api/repetir-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({serial:serial})}).then(r=>r.json()).then(d=>{if(d.error){toast(d.error,'err');return;}mostrarEditorRepetir(d);}).catch(()=>toast('Error al cargar ticket','err'));}
function mostrarEditorRepetir(data){let html=`<div class="rep-info"><div>📋 Ticket Original: <b>${data.ticket_original.serial}</b></div><div>💰 Total Original: S/${data.ticket_original.total}</div><div style="margin-top:8px;color:#f5a623">Modifique horarios y montos antes de agregar:</div></div>`;data.jugadas.forEach((j,idx)=>{if(j.tipo==='tripleta'){let lotLabel=j.loteria==='plus'?'🟣 PLUS':'🔵 PERÚ';html+=`<div class="rep-item"><span style="color:#c084fc;font-family:'Oswald',sans-serif;min-width:60px">🎯 TRIP</span><span style="flex:1;color:#e0a0ff">${j.animal1}-${j.animal2}-${j.animal3} <span style="font-size:.65rem;opacity:.8">${lotLabel}</span></span><input type="number" id="rep-m-${idx}" value="${j.monto}" min="0.5" step="0.5"><button class="btn-close" style="padding:4px 8px;font-size:.7rem" onclick="agregarItemRepetir(${idx},'tripleta','${j.animal1},${j.animal2},${j.animal3}','${j.loteria||'peru'}')">➕</button></div>`;}else{let horaOpts=HPERU.map(h=>{let bloq=horasBloq.includes(h);return`<option value="${h}" ${bloq?'disabled':''}>${h}${bloq?' (CERRADO)':''}</option>`;}).join('');html+=`<div class="rep-item"><span style="color:${j.tipo==='animal'?'#4ade80':'#60a5fa'};font-family:'Oswald',sans-serif;min-width:60px">${j.tipo==='animal'?'🐾':'🎲'} ${j.seleccion}</span><select id="rep-h-${idx}">${horaOpts}</select><input type="number" id="rep-m-${idx}" value="${j.monto}" min="0.5" step="0.5"><button class="btn-close" style="padding:4px 8px;font-size:.7rem" onclick="agregarItemRepetir(${idx},'${j.tipo}','${j.seleccion}')">➕</button></div>`;}});html+=`<button class="btn-q" onclick="agregarTodoRepetir()" style="margin-top:12px;background:#166534;border-color:#22c55e">AGREGAR TODO AL TICKET</button>`;document.getElementById('rep-contenido').innerHTML=html;data.jugadas.forEach((j,idx)=>{if(j.tipo!=='tripleta'){let sel=document.getElementById(`rep-h-${idx}`);if(sel){for(let opt of sel.options){if(opt.value===j.hora&&!opt.disabled){sel.value=j.hora;break;}}}}});}
function agregarItemRepetir(idx,tipo,seleccion,loteria){let monto=parseFloat(document.getElementById(`rep-m-${idx}`).value)||0;if(monto<=0){toast('Monto inválido','err');return;}if(tipo==='tripleta'){let nums=seleccion.split(','),desc=nums.map(n=>n+'-'+ANIMALES[n].substring(0,4)).join(' '),lot=loteria||'peru';carrito.push({tipo:'tripleta',hora:'TODO DÍA',seleccion:seleccion,monto,desc:'🎯 '+desc,loteria:lot});toast('Tripleta agregada','ok');}else{let hora=document.getElementById(`rep-h-${idx}`).value;if(!hora){toast('Seleccione horario','err');return;}if(horasBloq.includes(hora)){toast('Ese horario ya cerró','err');return;}let nombre=tipo==='animal'?ANIMALES[seleccion]:seleccion;carrito.push({tipo:tipo,hora:hora,seleccion:seleccion,monto:monto,desc:tipo==='animal'?`${seleccion}-${nombre}`:`🎲 ${seleccion}`});toast('Jugada agregada','ok');}renderCarrito();}
function agregarTodoRepetir(){let btns=document.querySelectorAll('#rep-contenido .rep-item button');btns.forEach(btn=>btn.click());}
function setM(v){document.getElementById('monto').value=v;}
function agregar(){let monto=parseFloat(document.getElementById('monto').value)||0;if(monto<=0){toast('Monto inválido','err');return;}let lot=loteriaActiva,sel=lot==='plus'?horasSelPlus:horasSel;if(espSel){if(sel.length===0){toast('Seleccione horario','err');return;}sel.forEach(h=>{let labels={'ROJO':'🔴 ROJO','NEGRO':'⚫ NEGRO','PAR':'🔵 PAR','IMPAR':'🟡 IMPAR'};carrito.push({tipo:'especial',hora:h,seleccion:espSel,monto,desc:labels[espSel]+' x2',loteria:lot});});renderCarrito();toast('Especial(es) agregado','ok');return;}if(animalesSel.length===0){toast('Seleccione animal(es)','err');return;}if(sel.length===0){toast('Seleccione horario(s)','err');return;}sel.forEach(h=>{animalesSel.forEach(k=>{carrito.push({tipo:'animal',hora:h,seleccion:k,monto,desc:`${k}-${ANIMALES[k]}`,loteria:lot});});});animalesSel=[];document.querySelectorAll('.animals-grid .acard').forEach(c=>c.classList.remove('sel'));document.getElementById('manual-input').value='';renderCarrito();toast(`Jugadas agregadas (${lot.toUpperCase()})`,'ok');}
function renderCarrito(){let list=document.getElementById('ticket-list'),tot=document.getElementById('ticket-total');window._carritoLen=carrito.length;document.getElementById('btn-wa').disabled=(carrito.length===0||_sinConexion);if(!carrito.length){list.innerHTML='<div class="ticket-empty">TICKET VACÍO</div>';tot.style.display='none';return;}let html='',total=0;carrito.forEach((it,i)=>{total+=it.monto;let lot=it.loteria||'peru',isTrip=it.tipo==='tripleta';let lotLabel=lot==='plus'?`<span style="background:#4c1d95;border:1px solid #a855f7;color:#e9d5ff;font-size:.58rem;font-family:'Oswald',sans-serif;padding:1px 5px;border-radius:3px;flex-shrink:0">${isTrip?'🎯 ':''} PLUS</span>`:`<span style="background:#0c2461;border:1px solid #3b9eff;color:#bae6fd;font-size:.58rem;font-family:'Oswald',sans-serif;padding:1px 5px;border-radius:3px;flex-shrink:0">${isTrip?'🎯 ':''}PERÚ</span>`;let horaLabel=it.hora==='TODO DÍA'?'x60':it.hora.replace(':00','').replace(' ','');html+=`<div class="ti" style="${isTrip?'border-left:3px solid '+(lot==='plus'?'#a855f7':'#3b9eff')+';background:rgba(100,60,180,.08)':''}"><span class="ti-hora">${horaLabel}</span>${lotLabel}<span class="ti-desc">${it.desc}</span><span class="ti-monto">${it.monto}</span><button class="ti-del" onclick="quitarItem(${i})">✕</button></div>`;});list.innerHTML=html;tot.style.display='block';tot.textContent=`TOTAL: S/ ${total.toFixed(2)}`;}
function quitarItem(i){carrito.splice(i,1);renderCarrito();}
function borrarTodo(){carrito=[];animalesSel=[];espSel=null;horasSel=[];horasSelPlus=[];document.querySelectorAll('.acard').forEach(c=>c.classList.remove('sel'));document.querySelectorAll('.esp-btn').forEach(e=>e.classList.remove('sel'));renderCarrito();toast('Ticket borrado','err');}
async function vender(){if(!carrito.length){toast('Ticket vacío','err');return;}let btn=document.getElementById('btn-wa');btn.disabled=true;btn.textContent='⏳ PROCESANDO...';try{let r=await fetch('/api/procesar-venta',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({jugadas:carrito.map(c=>({hora:c.hora,seleccion:c.seleccion,monto:c.monto,tipo:c.tipo,loteria:c.loteria||'peru'}))})});let d=await r.json();if(d.error){toast(d.error,'err');}else{window.open(d.url_whatsapp,'_blank');toast(`✅ Ticket #${d.ticket_id} generado!`,'ok');carrito=[];animalesSel=[];if(espSel){document.getElementById('esp-'+espSel).classList.remove('sel');espSel=null;}horasSel=[];horasSelPlus=[];document.getElementById('manual-input').value='';renderCarrito();renderAnimales();renderHoras();}}catch(e){toast('Error de conexión','err');}finally{btn.disabled=false;btn.textContent='📤 ENVIAR POR WHATSAPP';}}
function openResultados(){if(!document.getElementById('res-fecha').value)document.getElementById('res-fecha').value=new Date().toISOString().split('T')[0];openMod('mod-resultados');cargarResultados();}
function cargarResultados(){let f=document.getElementById('res-fecha').value;if(!f)return;let c=document.getElementById('res-lista');c.innerHTML='<p style="color:var(--text2);text-align:center;padding:10px;font-size:.75rem;letter-spacing:2px">CARGANDO...</p>';let fd=new Date(f+'T12:00:00');document.getElementById('res-titulo').textContent=fd.toLocaleDateString('es-PE',{weekday:'long',day:'numeric',month:'long'}).toUpperCase();Promise.all([fetch('/api/resultados-fecha',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha:f,loteria:'peru'})}).then(r=>r.json()),fetch('/api/resultados-fecha',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha:f,loteria:'plus'})}).then(r=>r.json())]).then(([dp,dpl])=>{let html='<div style="color:#0ea5e9;font-family:\'Oswald\',sans-serif;font-size:.72rem;letter-spacing:2px;padding:4px 0 6px;border-bottom:1px solid #e2e8f0;margin-bottom:4px">🇵🇪 ZOOLO CASINO — PERÚ (11 SORTEOS)</div>';HPERU.forEach(h=>{let res=dp.resultados[h];html+=`<div class="ri ${res?'ok':''}"><span class="ri-hora">${h.replace(':00 AM',' AM').replace(':00 PM',' PM')}</span>${res?`<span class="ri-animal">${res.animal} — ${res.nombre}</span>`:'<span style="color:#4a6090;font-size:.78rem">PENDIENTE</span>'}</div>`;});html+='<div style="color:#a855f7;font-family:\'Oswald\',sans-serif;font-size:.72rem;letter-spacing:2px;padding:8px 0 6px;border-bottom:1px solid #e2e8f0;margin-top:10px;margin-bottom:4px">🎰 ZOOLO CASINO PLUS (12 SORTEOS)</div>';HPLUS.forEach(h=>{let res=dpl.resultados[h];html+=`<div class="ri ${res?'ok':''}"><span class="ri-hora">${h.replace(':00 AM',' AM').replace(':00 PM',' PM')}</span>${res?`<span class="ri-animal">${res.animal} — ${res.nombre}</span>`:'<span style="color:#4a6090;font-size:.78rem">PENDIENTE</span>'}</div>`;});c.innerHTML=html||'<p style="color:#4a6090;text-align:center;padding:20px;font-size:.75rem;letter-spacing:2px">SIN RESULTADOS</p>';}).catch(()=>{c.innerHTML='<p style="color:var(--red);text-align:center;padding:12px">Error de conexión</p>';});}
function consultarTickets(){let ini=document.getElementById('mt-ini').value,fin=document.getElementById('mt-fin').value,est=document.getElementById('mt-estado').value;if(!ini||!fin){toast('Seleccione fechas','err');return;}let lista=document.getElementById('mt-lista');lista.innerHTML='<p style="color:#6090c0;text-align:center;padding:15px;font-size:.75rem;letter-spacing:2px">CARGANDO...</p>';fetch('/api/mis-tickets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin,estado:est})}).then(r=>r.json()).then(d=>{if(d.error){lista.innerHTML=`<p style="color:#f87171;text-align:center">${d.error}</p>`;return;}let res=document.getElementById('mt-resumen');res.style.display='block';res.textContent=`${d.totales.cantidad} TICKET(S) — TOTAL: S/ ${d.totales.ventas.toFixed(2)}`;if(!d.tickets.length){lista.innerHTML='<p style="color:#4a6090;text-align:center;padding:20px;font-size:.75rem;letter-spacing:2px">SIN RESULTADOS</p>';return;}let html='';d.tickets.forEach(t=>{let bc=t.pagado?'p':(t.premio_calculado>0?'g':'n'),bt=t.pagado?'✅ PAGADO':(t.premio_calculado>0?'🏆 GANADOR':'⏳ PENDIENTE'),tc=t.pagado?'gano':(t.premio_calculado>0?'pte':'');let jhtml='';if(t.jugadas&&t.jugadas.length){jhtml+=`<div style="color:#4080c0;font-size:.65rem;font-family:'Oswald',sans-serif;letter-spacing:2px;padding:4px 0 2px">JUGADAS</div>`;t.jugadas.forEach(j=>{let rn=j.resultado?(j.resultado+' — '+(j.resultado_nombre||'')):'...';let tipoIcon=j.tipo==='especial'?'🎲':'🐾';let lotBadge=j.loteria==='plus'?`<span style="background:#3b0764;border:1px solid #a855f7;color:#e9d5ff;font-family:'Oswald',sans-serif;font-size:.58rem;padding:1px 4px;border-radius:2px;flex-shrink:0">PLUS</span>`:`<span style="background:#0c2461;border:1px solid #0ea5e9;color:#bae6fd;font-family:'Oswald',sans-serif;font-size:.58rem;padding:1px 4px;border-radius:2px;flex-shrink:0">PERÚ</span>`;jhtml+=`<div class="jrow ${j.gano?'gano':''}"><span style="color:#00c8e8;font-family:'Oswald',sans-serif;font-size:.68rem;min-width:52px;font-weight:700">${j.hora.replace(':00 ','').replace(' ','')}</span>${lotBadge}<span style="flex:1;color:#c0d8f0;font-size:.72rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-left:3px">${tipoIcon} ${j.tipo==='animal'?(j.seleccion+' '+j.nombre):j.seleccion}</span><span style="color:#6090c0;font-size:.68rem;margin:0 4px">S/${j.monto}</span><span style="font-size:.68rem;min-width:60px;text-align:right">${j.resultado?`<span style="color:${j.gano?'#4ade80':'#6090c0'}">${j.gano?'✓':'✗'} ${rn}</span>`:'<span style="color:#2a4060">PEND</span>'}</span>${j.gano?`<span style="color:#4ade80;font-weight:700;font-family:'Oswald',sans-serif;font-size:.72rem;margin-left:4px">+${j.premio}</span>`:''}</div>`;});}let thtml='';if(t.tripletas&&t.tripletas.length){thtml+=`<div style="color:#c084fc;font-size:.65rem;font-family:'Oswald',sans-serif;letter-spacing:2px;padding:4px 0 2px;margin-top:4px">🎯 TRIPLETAS x60</div>`;t.tripletas.forEach(tr=>{let salStr=tr.salieron&&tr.salieron.length?tr.salieron.join(', '):'Ninguno aún';let pend=3-tr.salieron.length;let trLotBadge=tr.loteria==='plus'?`<span style="background:#3b0764;border:1px solid #a855f7;color:#e9d5ff;font-family:'Oswald',sans-serif;font-size:.58rem;padding:1px 4px;border-radius:2px">PLUS</span>`:`<span style="background:#0c2461;border:1px solid #0ea5e9;color:#bae6fd;font-family:'Oswald',sans-serif;font-size:.58rem;padding:1px 4px;border-radius:2px">PERÚ</span>`;thtml+=`<div class="trip-row ${tr.gano?'gano':''}"><div style="flex:1"><div style="display:flex;gap:4px;flex-wrap:wrap;align-items:center">${trLotBadge}<span style="background:#3b0764;border:2px solid #7c3aed;border-radius:3px;padding:2px 5px;font-family:'Oswald',sans-serif;font-size:.72rem;color:#e0a0ff">${tr.animal1} ${tr.nombre1}</span><span style="color:#6040a0;font-size:.7rem">•</span><span style="background:#3b0764;border:2px solid #7c3aed;border-radius:3px;padding:2px 5px;font-family:'Oswald',sans-serif;font-size:.72rem;color:#e0a0ff">${tr.animal2} ${tr.nombre2}</span><span style="color:#6040a0;font-size:.7rem">•</span><span style="background:#3b0764;border:2px solid #7c3aed;border-radius:3px;padding:2px 5px;font-family:'Oswald',sans-serif;font-size:.72rem;color:#e0a0ff">${tr.animal3} ${tr.nombre3}</span></div><div style="margin-top:3px;font-size:.68rem"><span style="color:#6090c0">Salieron: </span><span style="color:${tr.gano?'#4ade80':'#a080c0'}">${salStr}</span>${!tr.gano&&pend>0?`<span style="color:#4a3080"> (faltan ${pend})</span>`:''}${tr.gano?'<span style="color:#4ade80;font-weight:700"> ✅ GANÓ</span>':''}</div></div><div style="text-align:right;flex-shrink:0;margin-left:8px"><div style="color:#fbbf24;font-family:'Oswald',sans-serif;font-weight:700">S/${tr.monto}</div>${tr.gano?`<div style="color:#4ade80;font-weight:700;font-family:'Oswald',sans-serif">+S/${tr.premio.toFixed(2)}</div>`:'<div style="color:#3a2060;font-size:.68rem">x60</div>'}${tr.pagado?'<div style="color:#22c55e;font-size:.65rem;font-weight:700">COBRADO</div>':''}</div></div>`;});}html+=`<div class="tcard ${tc}"><div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px;margin-bottom:6px"><div style="flex:1;min-width:0"><div class="ts">🎫 #${t.serial}</div><div style="color:#4a6090;font-size:.7rem">${t.fecha}</div></div><div style="text-align:right;flex-shrink:0"><span class="badge ${bc}">${bt}</span><div style="color:#fbbf24;font-family:'Oswald',sans-serif;font-size:.9rem;margin-top:3px;font-weight:700">S/${t.total}</div>${t.premio_calculado>0?`<div style="color:#4ade80;font-size:.82rem;font-weight:700;font-family:'Oswald',sans-serif">PREMIO: S/${t.premio_calculado.toFixed(2)}</div>`:''}</div></div>${jhtml}${thtml}</div>`;});lista.innerHTML=html;}).catch(()=>{lista.innerHTML='<p style="color:#f87171;text-align:center">Error de conexión</p>';});}
function cajaHist(){let ini=document.getElementById('ar-ini').value,fin=document.getElementById('ar-fin').value;if(!ini||!fin){toast('Seleccione fechas','err');return;}let c=document.getElementById('ar-res');c.innerHTML='<p style="color:var(--text2);text-align:center;padding:10px;font-size:.75rem;letter-spacing:2px">CARGANDO...</p>';fetch('/api/caja-historico',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin})}).then(r=>r.json()).then(d=>{if(d.error){c.innerHTML=`<p style="color:var(--red)">${d.error}</p>`;return;}let html='<div class="sbox">';d.resumen_por_dia.forEach(dia=>{let col=dia.balance>=0?'var(--green)':'var(--red)';html+=`<div class="srow"><span class="sl">${dia.fecha}</span><span style="font-size:.72rem;color:var(--text2)">V:${dia.ventas}</span><span class="sv" style="color:${col}">S/${dia.balance.toFixed(2)}</span></div>`;});html+=`</div><div class="sbox"><div class="srow"><span class="sl">Ventas</span><span class="sv">S/${d.totales.ventas.toFixed(2)}</span></div><div class="srow"><span class="sl">Premios</span><span class="sv" style="color:var(--red)">S/${d.totales.premios.toFixed(2)}</span></div><div class="srow"><span class="sl">Comisión</span><span class="sv">S/${d.totales.comision.toFixed(2)}</span></div><div class="srow"><span class="sl">Balance</span><span class="sv" style="color:${d.totales.balance>=0?'var(--green)':'var(--red)'}">S/${d.totales.balance.toFixed(2)}</span></div></div>`;c.innerHTML=html;});}
function openCaja(){openMod('mod-caja');fetch('/api/caja').then(r=>r.json()).then(d=>{if(d.error)return;let bc=d.balance>=0?'g':'r';document.getElementById('caja-body').innerHTML=`<div class="caja-grid"><div class="cg"><div class="cgl">VENTAS</div><div class="cgv">S/${d.ventas.toFixed(2)}</div></div><div class="cg"><div class="cgl">PREMIOS PAGADOS</div><div class="cgv r">S/${d.premios.toFixed(2)}</div></div><div class="cg"><div class="cgl">COMISIÓN</div><div class="cgv">S/${d.comision.toFixed(2)}</div></div><div class="cg"><div class="cgl">BALANCE</div><div class="cgv ${bc}">S/${d.balance.toFixed(2)}</div></div></div><div class="sbox"><div class="srow"><span class="sl">Tickets vendidos</span><span class="sv">${d.total_tickets}</span></div><div class="srow"><span class="sl">Con premio pendiente</span><span class="sv" style="color:#c08020">${d.tickets_pendientes}</span></div></div>`;});}
function openPagar(){openMod('mod-pagar');document.getElementById('pag-serial').value='';document.getElementById('pag-res').innerHTML='';}
function verificarTicket(){let s=document.getElementById('pag-serial').value.trim();if(!s)return;let c=document.getElementById('pag-res');fetch('/api/verificar-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({serial:s})}).then(r=>r.json()).then(d=>{if(d.error){c.innerHTML=`<div style="background:var(--red-bg);color:var(--red);padding:10px;border-radius:3px;text-align:center;margin-top:8px;border:1px solid var(--red-border)">❌ ${d.error}</div>`;return;}let col=d.total_ganado>0?'var(--green)':'var(--text2)';c.innerHTML=`<div style="border:1px solid ${col};border-radius:4px;padding:14px;margin-top:10px"><div style="color:var(--teal);font-family:'Oswald',sans-serif;letter-spacing:2px;margin-bottom:10px">TICKET #${s}</div><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><span style="color:var(--text2);font-size:.8rem">PREMIO</span><span style="color:${col};font-family:'Oswald',sans-serif;font-size:1.2rem;font-weight:700">S/${d.total_ganado.toFixed(2)}</span></div>${d.total_ganado>0?`<button onclick="pagarTicket(${d.ticket_id},${d.total_ganado})" style="width:100%;padding:11px;background:linear-gradient(135deg,#0a3020,#062018);color:var(--green);border:1px solid #0d5a2a;border-radius:3px;font-weight:700;cursor:pointer;font-family:'Oswald',sans-serif;letter-spacing:2px;font-size:.85rem">💰 CONFIRMAR PAGO S/${d.total_ganado.toFixed(2)}</button>`:'<div style="color:var(--text2);text-align:center;font-size:.8rem;padding:6px">SIN PREMIO</div>'}</div>`;});}
function pagarTicket(tid,m){if(!confirm(`¿Confirmar pago S/${m}?`))return;fetch('/api/pagar-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticket_id:tid})}).then(r=>r.json()).then(d=>{if(d.status==='ok'){toast('✅ Ticket pagado','ok');closeMod('mod-pagar');}else toast(d.error||'Error','err');});}
function openAnular(){openMod('mod-anular');document.getElementById('an-serial').value='';document.getElementById('an-res').innerHTML='';}
function anularTicket(){let s=document.getElementById('an-serial').value.trim();if(!s)return;fetch('/api/anular-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({serial:s})}).then(r=>r.json()).then(d=>{let c=document.getElementById('an-res');if(d.status==='ok')c.innerHTML=`<div style="background:#062012;color:var(--green);padding:10px;border-radius:3px;text-align:center;margin-top:8px;border:1px solid #0d5a2a">✅ ${d.mensaje}</div>`;else c.innerHTML=`<div style="background:var(--red-bg);color:var(--red);padding:10px;border-radius:3px;text-align:center;margin-top:8px;border:1px solid var(--red-border)">❌ ${d.error}</div>`;});}
function openMod(id){document.getElementById(id).classList.add('open');}
function closeMod(id){document.getElementById(id).classList.remove('open');}
document.querySelectorAll('.modal').forEach(m=>{m.addEventListener('click',e=>{if(e.target===m)m.classList.remove('open');});});
function toast(msg,tipo){let t=document.getElementById('toast');t.textContent=msg;t.className='toast '+tipo;t.style.display='block';clearTimeout(window._tt);window._tt=setTimeout(()=>t.style.display='none',2800);}
document.addEventListener('DOMContentLoaded',init);
</script>
</body></html>'''

ADMIN_HTML = r'''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ZOOLO ADMIN v4</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;600;700&family=Rajdhani:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#050a12;--panel:#0a1020;--card:#060e1c;--border:#1a2a4a;--gold:#f5a623;--blue:#2060d0;--teal:#00c8e8;--red:#e05050;--red-bg:rgba(220,40,40,.08);--red-border:rgba(200,40,40,.2);--green:#2ecc71;--orange:#f5a623;--text:#c0d8f0;--text2:#3a5080}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Rajdhani',sans-serif;font-size:14px}
.topbar{background:#030810;border-bottom:3px solid var(--gold);padding:0 16px;height:44px;display:flex;align-items:center;justify-content:space-between}
.brand{font-family:'Oswald',sans-serif;font-size:1.2rem;font-weight:700;letter-spacing:3px;color:#fff}.brand em{color:var(--gold);font-style:normal}
.tbtn{padding:6px 14px;border:1px solid var(--border);background:var(--card);color:var(--text);border-radius:3px;cursor:pointer;font-size:.72rem;font-family:'Oswald',sans-serif;font-weight:700;letter-spacing:1px}
.tbtn:hover{background:var(--border);color:#fff}.tbtn.exit{border-color:#4a1010;color:var(--red)}.tbtn.exit:hover{background:#3a0808;border-color:var(--red)}
.tabs{display:flex;gap:2px;padding:8px 12px;background:#030810;border-bottom:1px solid var(--border);overflow-x:auto;white-space:nowrap}
.tab{padding:8px 14px;background:var(--card);border:1px solid var(--border);border-radius:3px;cursor:pointer;font-family:'Oswald',sans-serif;font-size:.72rem;font-weight:700;letter-spacing:1px;color:var(--text2);transition:all .2s}
.tab:hover{background:var(--border);color:var(--text)}.tab.active{background:var(--blue);border-color:var(--teal);color:#fff;box-shadow:0 0 12px rgba(32,96,208,.3)}
.tc{display:none;padding:12px;max-width:1200px;margin:0 auto}.tc.active{display:block}
.card{background:var(--panel);border:1px solid var(--border);border-radius:6px;padding:14px;margin-bottom:12px}
.card-title{font-family:'Oswald',sans-serif;font-size:.75rem;font-weight:700;letter-spacing:2px;color:var(--gold);border-bottom:1px solid var(--border);padding-bottom:8px;margin-bottom:12px}
label{display:block;color:var(--text2);font-size:.68rem;letter-spacing:2px;margin-bottom:4px;font-family:'Oswald',sans-serif}
input,select{width:100%;padding:9px 10px;background:var(--card);border:1px solid var(--border);border-radius:3px;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.88rem}
input:focus,select:focus{outline:none;border-color:var(--blue)}
.btn{padding:9px 18px;background:var(--blue);color:#fff;border:1px solid #4080e0;border-radius:3px;cursor:pointer;font-family:'Oswald',sans-serif;font-weight:700;letter-spacing:1px;font-size:.75rem}
.btn:hover{background:#2a6ae8;border-color:#60a0ff}.btn.red{background:#4a0808;border-color:var(--red);color:var(--red)}.btn.red:hover{background:#6a0a0a}.btn.green{background:#0a3a18;border-color:var(--green);color:var(--green)}.btn.green:hover{background:#0e4a20}.btn.gold{background:#3a2000;border-color:var(--gold);color:var(--gold)}.btn.gold:hover{background:#4a2800}
.btn-block{width:100%;margin-top:8px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
.frow{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.frow .fg{flex:1;min-width:120px}
.fg{margin-bottom:10px}
.tag{display:inline-block;padding:2px 7px;border-radius:3px;font-size:.65rem;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:1px}
.tag.ok{background:#0a2a14;color:var(--green);border:1px solid #1a5a28}.tag.err{background:#2a0808;color:var(--red);border:1px solid #4a1010}.tag.warn{background:#2a1a00;color:var(--gold);border:1px solid #5a3000}.tag.info{background:#0a1a30;color:var(--teal);border:1px solid #1a4060}
.tbl{width:100%;border-collapse:collapse;font-size:.75rem}
.tbl th{background:#060c18;color:var(--text2);text-align:left;padding:7px 10px;border-bottom:2px solid var(--border);font-family:'Oswald',sans-serif;font-weight:700;letter-spacing:1px;font-size:.65rem}
.tbl td{padding:7px 10px;border-bottom:1px solid var(--border);vertical-align:middle}
.tbl tr:hover td{background:rgba(30,60,120,.1)}
.animals-mini-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:4px}
.amg-card{background:var(--card);border:1px solid var(--border);border-radius:3px;padding:5px 3px;text-align:center;cursor:pointer;transition:all .12s}
.amg-card:hover{background:#1a2a4a;border-color:var(--teal)}.amg-card.sel{background:#0a2a10;border-color:var(--green)}
.amg-card .anum{font-size:.72rem;font-weight:700;font-family:'Oswald',sans-serif;color:#fff}
.amg-card .anom{font-size:.55rem;color:var(--text2)}
.stat-box{background:var(--card);border:1px solid var(--border);border-radius:4px;padding:10px;text-align:center}
.stat-label{color:var(--text2);font-size:.6rem;letter-spacing:2px;margin-bottom:3px;font-family:'Oswald',sans-serif}
.stat-val{color:var(--gold);font-family:'Oswald',sans-serif;font-size:1.1rem;font-weight:700}
.stat-val.g{color:var(--green)}.stat-val.r{color:var(--red)}.stat-val.t{color:var(--teal)}
.msg{padding:9px 12px;border-radius:3px;margin-bottom:10px;font-size:.8rem;display:none}
.msg.ok{background:rgba(46,204,113,.08);color:var(--green);border:1px solid rgba(46,204,113,.25)}
.msg.err{background:var(--red-bg);color:var(--red);border:1px solid var(--red-border)}
.riesgo-bar{height:16px;border-radius:3px;background:#0a1828;overflow:hidden;position:relative;margin:2px 0}
.riesgo-fill{height:100%;border-radius:3px;transition:width .4s;min-width:2px}
.loteria-tabs{display:flex;gap:4px;margin-bottom:12px}
.lot-tab{flex:1;padding:9px 6px;text-align:center;border-radius:4px;cursor:pointer;font-family:'Oswald',sans-serif;font-size:.75rem;font-weight:700;letter-spacing:1px;border:2px solid var(--border);color:var(--text2);transition:all .2s}
.lot-tab.peru.active{background:#0c2461;border-color:#3b82f6;color:#bae6fd}
.lot-tab.plus.active{background:#2e1065;border-color:#a855f7;color:#e9d5ff}
.lot-tab:hover{background:var(--border);color:var(--text)}
.toggle-btn{display:inline-flex;align-items:center;gap:8px;padding:10px 20px;border-radius:5px;cursor:pointer;font-family:'Oswald',sans-serif;font-size:.85rem;font-weight:700;letter-spacing:2px;border:2px solid;transition:all .3s}
.toggle-btn.on{background:#0a3018;border-color:#22c55e;color:#4ade80;box-shadow:0 0 20px rgba(34,197,94,.2)}
.toggle-btn.off{background:#1a0808;border-color:#ef4444;color:#f87171}
.toggle-btn:hover{opacity:.85}
.reporte-7030-table{width:100%;border-collapse:collapse;font-size:.74rem}
.reporte-7030-table th{background:#060c18;color:var(--text2);padding:7px 8px;border-bottom:2px solid var(--border);font-family:'Oswald',sans-serif;font-size:.62rem;letter-spacing:1px;text-align:right}
.reporte-7030-table th:first-child,.reporte-7030-table th:nth-child(2){text-align:left}
.reporte-7030-table td{padding:6px 8px;border-bottom:1px solid var(--border);text-align:right;vertical-align:middle}
.reporte-7030-table td:first-child,.reporte-7030-table td:nth-child(2){text-align:left}
.reporte-7030-table tr:hover td{background:rgba(30,60,120,.1)}
.reporte-7030-table tr.pte td{opacity:.5}
.reporte-7030-table tfoot td{font-family:'Oswald',sans-serif;font-weight:700;font-size:.72rem;background:#060c18;border-top:2px solid var(--border);padding:8px}
.modo-badge{display:inline-block;padding:2px 6px;border-radius:3px;font-size:.6rem;font-family:'Oswald',sans-serif;font-weight:700}
.modo-badge.auto{background:#0a2a14;color:#4ade80;border:1px solid #166534}
.modo-badge.manual{background:#1a1a00;color:#fbbf24;border:1px solid #854d0e}
.modo-badge.pte{background:#0a0a1a;color:#4a6090;border:1px solid #1a2a4a}
</style></head><body>
<div class="topbar">
  <div class="brand">ZOO<em>LO</em> <span style="font-size:.75rem;color:var(--text2);font-weight:400;letter-spacing:1px">ADMIN</span></div>
  <div style="display:flex;gap:6px">
    <div id="clock-admin" style="color:var(--gold);font-family:'Oswald',sans-serif;font-size:.8rem;background:var(--card);padding:4px 10px;border-radius:3px;border:1px solid var(--border)">--:-- LIMA</div>
    <button class="tbtn exit" onclick="location.href='/logout'">SALIR</button>
  </div>
</div>
<div class="tabs">
  <div class="tab active" onclick="showTab('resultados')">📊 RESULTADOS</div>
  <div class="tab" onclick="showTab('riesgo')">⚡ RIESGO</div>
  <div class="tab" onclick="showTab('setentaytreinta')">📈 70/30</div>
  <div class="tab" onclick="showTab('agencias')">🏢 AGENCIAS</div>
  <div class="tab" onclick="showTab('topes')">🔒 TOPES</div>
  <div class="tab" onclick="showTab('reportes')">💼 REPORTES</div>
  <div class="tab" onclick="showTab('tripletas')">🎯 TRIPLETAS</div>
  <div class="tab" onclick="showTab('auditoria')">📋 AUDITORÍA</div>
</div>

<!-- TAB RESULTADOS -->
<div id="tc-resultados" class="tc active">
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:12px">
      <div class="card-title" style="border:none;padding:0;margin:0">📊 CARGAR RESULTADO</div>
      <div style="display:flex;align-items:center;gap:10px">
        <span style="color:var(--text2);font-size:.7rem;font-family:'Oswald',sans-serif;letter-spacing:1px">AUTO-SORTEO:</span>
        <button class="toggle-btn off" id="toggle-auto-btn" onclick="toggleAutoSorteo()">⏸ DESACTIVADO</button>
      </div>
    </div>
    <div class="loteria-tabs">
      <div class="lot-tab peru active" id="lot-res-peru" onclick="selLotRes('peru')">🇵🇪 ZOOLO PERU</div>
      <div class="lot-tab plus" id="lot-res-plus" onclick="selLotRes('plus')">🎰 ZOOLO PLUS</div>
    </div>
    <div class="frow">
      <div class="fg"><label>FECHA</label><input type="date" id="res-fecha" onchange="cargarResultadosAdmin()"></div>
      <div class="fg"><label>HORA SORTEO</label><select id="res-hora"></select></div>
      <div class="fg"><label>ANIMAL (0-40)</label>
        <div class="animals-mini-grid" id="amg"></div>
      </div>
    </div>
    <div id="seq-info" style="margin-bottom:6px;min-height:16px;padding:4px 6px;background:rgba(34,197,94,.05);border-radius:3px;border:1px solid rgba(34,197,94,.1)"></div>
    <div id="animal-sel-preview" style="margin-bottom:10px;color:var(--gold);font-family:'Oswald',sans-serif;font-size:.85rem;min-height:20px;text-align:center"></div>
    <div id="msg-res" class="msg"></div>
    <div style="display:flex;gap:8px">
      <button class="btn btn-block" onclick="guardarResultado()">✅ GUARDAR RESULTADO</button>
      <button class="btn btn-block" style="background:#3a2000;border-color:var(--gold);color:var(--gold)" onclick="forzarAutoSorteo()">⚡ AUTO-SORTEAR HORA</button>
    </div>
  </div>
  <div class="card">
    <div class="card-title">📋 RESULTADOS DEL DÍA</div>
    <div id="resultados-hoy-peru">
      <div style="color:var(--text2);font-size:.7rem;font-family:'Oswald',sans-serif;letter-spacing:2px;margin-bottom:6px">🇵🇪 PERÚ</div>
      <div id="res-lista-peru" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:4px"></div>
    </div>
    <div id="resultados-hoy-plus" style="margin-top:12px">
      <div style="color:#a855f7;font-size:.7rem;font-family:'Oswald',sans-serif;letter-spacing:2px;margin-bottom:6px">🎰 PLUS</div>
      <div id="res-lista-plus" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:4px"></div>
    </div>
  </div>
</div>

<!-- TAB RIESGO -->
<div id="tc-riesgo" class="tc">
  <div class="card">
    <div class="card-title">⚡ MONITOR DE RIESGO EN TIEMPO REAL</div>
    <div class="loteria-tabs">
      <div class="lot-tab peru active" id="lot-riesgo-peru" onclick="selLotRiesgo('peru')">🇵🇪 ZOOLO PERU</div>
      <div class="lot-tab plus" id="lot-riesgo-plus" onclick="selLotRiesgo('plus')">🎰 ZOOLO PLUS</div>
    </div>
    <div class="frow">
      <div class="fg"><label>SORTEO</label><select id="risk-hora"></select></div>
      <div class="fg" style="align-self:flex-end"><button class="btn" onclick="cargarRiesgo()">🔄 ACTUALIZAR</button></div>
    </div>
    <div id="riesgo-summary" style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px"></div>
    <div style="margin-bottom:8px;display:flex;justify-content:space-between;align-items:center">
      <div class="card-title" style="border:none;margin:0;padding:0">APUESTAS POR ANIMAL</div>
      <div id="riesgo-agencias-btn" style="display:none"><select id="riesgo-agencia-sel" style="width:auto;padding:4px 8px;font-size:.72rem" onchange="verRiesgoAgencia()"><option value="">-- Filtrar por agencia --</option></select></div>
    </div>
    <div id="riesgo-tabla"></div>
  </div>
</div>

<!-- TAB 70/30 (NUEVO v4.0) -->
<div id="tc-setentaytreinta" class="tc">
  <div class="card">
    <div class="card-title">📈 REPORTE 70/30 POR JORNADA</div>
    <div class="loteria-tabs">
      <div class="lot-tab peru active" id="lot-7030-peru" onclick="selLot7030('peru')">🇵🇪 ZOOLO PERU</div>
      <div class="lot-tab plus" id="lot-7030-plus" onclick="selLot7030('plus')">🎰 ZOOLO PLUS</div>
    </div>
    <div class="frow">
      <div class="fg"><label>FECHA</label><input type="date" id="fecha-7030"></div>
      <div class="fg" style="align-self:flex-end"><button class="btn" onclick="cargar7030()">📊 VER REPORTE</button></div>
    </div>
  </div>
  <div id="res-7030"></div>
</div>

<!-- TAB AGENCIAS -->
<div id="tc-agencias" class="tc">
  <div class="grid2">
    <div class="card">
      <div class="card-title">➕ NUEVA AGENCIA</div>
      <div class="fg"><label>USUARIO</label><input type="text" id="ag-user"></div>
      <div class="fg"><label>CONTRASEÑA</label><input type="password" id="ag-pass"></div>
      <div class="fg"><label>NOMBRE</label><input type="text" id="ag-nombre"></div>
      <div class="fg"><label>BANCO (opcional)</label><input type="text" id="ag-banco"></div>
      <div id="msg-ag" class="msg"></div>
      <button class="btn btn-block green" onclick="crearAgencia()">CREAR AGENCIA</button>
    </div>
    <div class="card">
      <div class="card-title">🏢 AGENCIAS ACTIVAS</div>
      <button class="btn btn-block" style="margin-bottom:10px" onclick="listarAgencias()">🔄 ACTUALIZAR LISTA</button>
      <div id="ag-lista"></div>
    </div>
  </div>
</div>

<!-- TAB TOPES -->
<div id="tc-topes" class="tc">
  <div class="card">
    <div class="card-title">🔒 GESTIÓN DE TOPES</div>
    <div class="loteria-tabs">
      <div class="lot-tab peru active" id="lot-topes-peru" onclick="selLotTopes('peru')">🇵🇪 ZOOLO PERU</div>
      <div class="lot-tab plus" id="lot-topes-plus" onclick="selLotTopes('plus')">🎰 ZOOLO PLUS</div>
    </div>
    <div class="frow">
      <div class="fg"><label>HORA</label><select id="tope-hora"></select></div>
      <div class="fg" style="align-self:flex-end">
        <button class="btn" onclick="cargarTopes()">VER TOPES</button>
        <button class="btn red" style="margin-left:6px" onclick="limpiarTopes()">LIMPIAR TODO</button>
      </div>
    </div>
    <div id="topes-body"></div>
  </div>
</div>

<!-- TAB REPORTES -->
<div id="tc-reportes" class="tc">
  <div class="card">
    <div class="card-title">💼 REPORTE HOY</div>
    <div style="display:flex;gap:8px;margin-bottom:10px">
      <button class="btn" onclick="cargarReporteHoy()">📊 REPORTE DEL DÍA</button>
      <button class="btn gold" onclick="location.href='/admin/exportar-csv';return false" id="btn-csv" style="opacity:.5" disabled>📥 EXPORTAR CSV</button>
    </div>
    <div id="rep-hoy"></div>
  </div>
  <div class="card">
    <div class="card-title">📅 REPORTE POR PERÍODO</div>
    <div class="frow">
      <div class="fg"><label>INICIO</label><input type="date" id="rep-ini"></div>
      <div class="fg"><label>FIN</label><input type="date" id="rep-fin"></div>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn" onclick="cargarEstadisticas()">📈 ESTADÍSTICAS</button>
      <button class="btn gold" onclick="exportarCSV()">📥 EXPORTAR CSV</button>
      <button class="btn" style="background:#1a0a30;border-color:#a855f7;color:#c084fc" onclick="cargarReporteAgencias()">🏢 POR AGENCIA</button>
    </div>
    <div id="rep-periodo"></div>
  </div>
</div>

<!-- TAB TRIPLETAS -->
<div id="tc-tripletas" class="tc">
  <div class="card">
    <div class="card-title">🎯 TRIPLETAS HOY</div>
    <button class="btn btn-block" onclick="cargarTripletas()">🔄 CARGAR TRIPLETAS</button>
    <div id="trip-body" style="margin-top:10px"></div>
  </div>
</div>

<!-- TAB AUDITORÍA -->
<div id="tc-auditoria" class="tc">
  <div class="card">
    <div class="card-title">📋 AUDITORÍA DEL SISTEMA</div>
    <div class="frow">
      <div class="fg"><label>INICIO</label><input type="date" id="aud-ini"></div>
      <div class="fg"><label>FIN</label><input type="date" id="aud-fin"></div>
      <div class="fg"><label>BUSCAR</label><input type="text" id="aud-filtro" placeholder="acción, usuario..."></div>
    </div>
    <button class="btn btn-block" onclick="cargarAudit()">CARGAR LOGS</button>
    <div id="aud-body" style="margin-top:10px;max-height:500px;overflow-y:auto"></div>
  </div>
</div>

<script>
const ANIMALES = {{ animales | tojson }};
const HPERU = {{ horarios | tojson }};
const HPLUS = {{ horarios_plus | tojson }};
const ORDEN = ['00','0','1','2','3','4','5','6','7','8','9','10','11','12','13','14','15','16','17','18','19','20','21','22','23','24','25','26','27','28','29','30','31','32','33','34','35','36','37','38','39','40'];
let animalSel=null, lotRes='peru', lotRiesgo='peru', lotTopes='peru', lot7030='peru';

function showTab(id){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tc').forEach(t=>t.classList.remove('active'));
  document.getElementById('tc-'+id).classList.add('active');
  let tabs=document.querySelectorAll('.tab');
  let tabMap={resultados:0,riesgo:1,setentaytreinta:2,agencias:3,topes:4,reportes:5,tripletas:6,auditoria:7};
  if(tabMap[id]!==undefined)tabs[tabMap[id]].classList.add('active');
  if(id==='riesgo'){fillHorasRiesgo();cargarRiesgo();}
  if(id==='tripletas')cargarTripletas();
  if(id==='agencias')listarAgencias();
}

// Clock
function actualizarClockAdmin(){let now=new Date(),utcMs=now.getTime()+now.getTimezoneOffset()*60000,peruMs=utcMs-5*3600000,peru=new Date(peruMs),h=peru.getHours(),m=peru.getMinutes(),ap=h>=12?'PM':'AM';h=h%12||12;document.getElementById('clock-admin').textContent=`${h}:${String(m).padStart(2,'0')} ${ap} · LIMA`;}
setInterval(actualizarClockAdmin,1000);actualizarClockAdmin();

// ── ANIMALES mini-grid ────────────────────────────────────────────────────────
let _secuenciaSugerida=[];
function renderAMG(){let g=document.getElementById('amg');g.innerHTML='';ORDEN.forEach(k=>{if(!ANIMALES[k])return;let esSug=_secuenciaSugerida.indexOf(k)>=0;let d=document.createElement('div');d.className='amg-card'+(k===animalSel?' sel':'')+(esSug?' sug':'');if(esSug)d.style.cssText='background:#0a2a18;border-color:#22c55e;box-shadow:0 0 8px rgba(34,197,94,.4)';d.innerHTML='<div class="anum">'+k+'</div><div class="anom">'+ANIMALES[k].substring(0,5)+(esSug?'<span style="color:#22c55e;font-size:.5rem;display:block">★SEQ</span>':'')+'</div>';d.onclick=()=>{animalSel=k;renderAMG();document.getElementById('animal-sel-preview').textContent='✅ '+k+' — '+ANIMALES[k];};g.appendChild(d);});}

function cargarSecuencia(){let lot=lotRes;fetch('/admin/secuencia-sugerida?loteria='+lot).then(r=>r.json()).then(d=>{if(d.status==='ok'&&d.sugeridos.length){_secuenciaSugerida=d.sugeridos.map(x=>x.num);let div=document.getElementById('seq-info');if(div){let txt=d.sugeridos.map(x=>x.num+'-'+x.nombre).join(', ');div.innerHTML='<span style="color:#22c55e;font-size:.7rem;font-weight:700">⭐ SEQ de '+d.ultimo+'-'+d.ultimo_nombre+': '+txt+'</span>';}}else{_secuenciaSugerida=[];}renderAMG();}).catch(()=>{});}
function cargarResultadosAdmin(){let f=document.getElementById('res-fecha').value;if(!f)return;Promise.all([
fetch('/api/resultados-fecha-admin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha:f,loteria:'peru'})}).then(r=>r.json()),
fetch('/api/resultados-fecha-admin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha:f,loteria:'plus'})}).then(r=>r.json())
]).then(([dp,dpl])=>{
  let renderLista=(data,lista,horarios)=>{
    lista.innerHTML='';horarios.forEach(h=>{let res=data[h];let d=document.createElement('div');
    d.style.cssText=`padding:5px 8px;border-radius:3px;font-size:.72rem;display:flex;justify-content:space-between;align-items:center;background:${res?'rgba(46,204,113,.06)':'var(--card)'};border:1px solid ${res?'rgba(46,204,113,.2)':'var(--border)'}`;
    d.innerHTML=`<span style="color:var(--teal);font-family:'Oswald',sans-serif;font-size:.7rem;font-weight:700">${h.replace(':00 ','')}</span>${res?`<span style="color:#4ade80;font-weight:700">${res.animal} — ${res.nombre}</span>`:'<span style="color:var(--text2);font-size:.65rem">PENDIENTE</span>'}`;
    lista.appendChild(d);});};
  renderLista(dp.resultados,document.getElementById('res-lista-peru'),HPERU);
  renderLista(dpl.resultados,document.getElementById('res-lista-plus'),HPLUS);
  }).catch(()=>{});}

function guardarResultado(){let hora=document.getElementById('res-hora').value,fecha=document.getElementById('res-fecha').value,animal=animalSel,loteria=lotRes;if(!animal){showMsg('msg-res','Selecciona un animal','err');return;}if(!hora){showMsg('msg-res','Selecciona la hora','err');return;}let fd=new FormData();fd.append('hora',hora);fd.append('animal',animal);fd.append('loteria',loteria);if(fecha)fd.append('fecha',fecha);fetch('/admin/guardar-resultado',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{if(d.status==='ok'){showMsg('msg-res',`✅ ${d.mensaje} [${d.fecha}]`,'ok');animalSel=null;renderAMG();document.getElementById('animal-sel-preview').textContent='';cargarResultadosAdmin();}else showMsg('msg-res',d.error,'err');}).catch(()=>showMsg('msg-res','Error','err'));}

function forzarAutoSorteo(){let hora=document.getElementById('res-hora').value,loteria=lotRes;if(!hora){showMsg('msg-res','Selecciona la hora','err');return;}if(!confirm(`¿Ejecutar auto-sorteo para ${hora} (${loteria.toUpperCase()})? Esto elegirá el animal automáticamente con lógica 70/30.`))return;fetch('/admin/forzar-autosorteo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hora:hora,loteria:loteria})}).then(r=>r.json()).then(d=>{if(d.status==='ok'){showMsg('msg-res',`✅ Auto-sorteo: ${d.mensaje}`,'ok');cargarResultadosAdmin();}else showMsg('msg-res',d.error||'Error','err');}).catch(()=>showMsg('msg-res','Error de conexión','err'));}

// ── RIESGO ────────────────────────────────────────────────────────────────────
// ── Selector horario resultados ───────────────────────────────────────────────
function fillHorasRes(){let h=document.getElementById('res-hora');if(!h)return;let lista=lotRes==='plus'?HPLUS:HPERU;h.innerHTML=lista.map(x=>'<option value="'+x+'">'+x+'</option>').join('');if(!h.value&&lista.length)h.value=lista[0];}

function selLotRes(l){lotRes=l;document.getElementById('lot-res-peru').classList.toggle('active',l==='peru');document.getElementById('lot-res-plus').classList.toggle('active',l==='plus');fillHorasRes();cargarSecuencia();}

function selLotRiesgo(l){lotRiesgo=l;document.getElementById('lot-riesgo-peru').classList.toggle('active',l==='peru');document.getElementById('lot-riesgo-plus').classList.toggle('active',l==='plus');fillHorasRiesgo();cargarRiesgo();}

function fillHorasRiesgo(){let s=document.getElementById('risk-hora');if(!s)return;let lista=lotRiesgo==='plus'?HPLUS:HPERU;s.innerHTML=lista.map(x=>'<option value="'+x+'">'+ x+'</option>').join('');if(!s.value&&lista.length)s.value=lista[0];}

function cargarRiesgo(){let hora=document.getElementById('risk-hora').value,lot=lotRiesgo;if(!hora)return;fetch(`/admin/riesgo?hora=${encodeURIComponent(hora)}&loteria=${lot}`).then(r=>r.json()).then(d=>{
  let sm=document.getElementById('riesgo-summary');
  sm.innerHTML=`<div class="stat-box"><div class="stat-label">TOTAL APOSTADO</div><div class="stat-val">S/${d.total_apostado.toFixed(2)}</div></div><div class="stat-box"><div class="stat-label">PRESUPUESTO 70%</div><div class="stat-val t">S/${d.presupuesto_70.toFixed(2)}</div></div><div class="stat-box"><div class="stat-label">SORTEO OBJETIVO</div><div class="stat-val">${d.sorteo_objetivo||hora}</div></div><div class="stat-box"><div class="stat-label">LOTE</div><div class="stat-val">${lot.toUpperCase()}</div></div>`;
  let agSel=document.getElementById('riesgo-agencia-sel');agSel.innerHTML='<option value="">-- Filtrar por agencia --</option>';if(d.agencias_hora&&d.agencias_hora.length){d.agencias_hora.forEach(a=>{let opt=document.createElement('option');opt.value=a.id;opt.textContent=a.nombre_agencia;agSel.appendChild(opt);});document.getElementById('riesgo-agencias-btn').style.display='block';}else{document.getElementById('riesgo-agencias-btn').style.display='none';}
  window._riesgoHora=hora;window._riesgoLot=lot;
  if(!d.riesgo||Object.keys(d.riesgo).length===0){document.getElementById('riesgo-tabla').innerHTML='<div style="color:var(--text2);text-align:center;padding:20px;letter-spacing:2px;font-size:.75rem">SIN APUESTAS EN ESTE SORTEO</div>';return;}
  let entries=Object.entries(d.riesgo).sort((a,b)=>b[1].apostado-a[1].apostado);let html='<table class="tbl"><thead><tr><th>N°</th><th>Animal</th><th>Apostado</th><th>Pagaría</th><th>%</th><th>Tope</th><th>%Bar</th></tr></thead><tbody>';
  let maxPag=Math.max(...entries.map(([_,v])=>v.pagaria));
  entries.forEach(([k,v])=>{let pct=Math.min(100,maxPag>0?v.pagaria/maxPag*100:0);let col=pct>80?'var(--red)':pct>50?'var(--gold)':'var(--green)';let topeStr=v.libre?'<span class="tag info">LIBRE</span>':`<span style="color:${v.apostado>v.tope*.9?'var(--red)':'var(--text)'};font-family:'Oswald',sans-serif;font-size:.75rem">S/${v.tope}</span>`;let lech=v.es_lechuza?`<span class="tag warn" style="margin-left:4px">x70</span>`:'';html+=`<tr><td style="font-family:'Oswald',sans-serif;color:var(--gold)">${k}</td><td>${v.nombre}${lech}</td><td style="color:var(--teal);font-family:'Oswald',sans-serif">S/${v.apostado.toFixed(2)}</td><td style="color:${col};font-family:'Oswald',sans-serif;font-weight:700">S/${v.pagaria.toFixed(2)}</td><td style="color:var(--text2)">${v.porcentaje}%</td><td>${topeStr}</td><td><div class="riesgo-bar"><div class="riesgo-fill" style="width:${pct}%;background:${col}"></div></div></td></tr>`;});
  html+='</tbody></table>';document.getElementById('riesgo-tabla').innerHTML=html;}).catch(()=>{});}

function verRiesgoAgencia(){let agId=document.getElementById('riesgo-agencia-sel').value,hora=window._riesgoHora;if(!agId||!hora)return;fetch('/admin/riesgo-agencia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agencia_id:agId,hora:hora})}).then(r=>r.json()).then(d=>{if(d.error){alert(d.error);return;}let html=`<div style="background:var(--card);border:1px solid var(--border);border-radius:4px;padding:10px;margin-top:8px"><div style="color:var(--gold);font-family:'Oswald',sans-serif;font-size:.75rem;margin-bottom:8px">${d.agencia} — ${d.hora}</div><table class="tbl"><thead><tr><th>Animal/Esp.</th><th>Apostado</th><th>Pagaría</th><th>Tickets</th></tr></thead><tbody>`;d.jugadas.forEach(j=>{html+=`<tr><td style="color:var(--teal)">${j.seleccion} ${j.nombre}</td><td style="font-family:'Oswald',sans-serif;color:var(--gold)">S/${j.apostado.toFixed(2)}</td><td style="color:${j.pagaria>0?'var(--red)':'var(--text2)'}">S/${j.pagaria.toFixed(2)}</td><td>${j.tickets}</td></tr>`;});html+='</tbody></table></div>';document.getElementById('riesgo-tabla').insertAdjacentHTML('afterend',html);}).catch(()=>{});}

// ── 70/30 ─────────────────────────────────────────────────────────────────────
function selLot7030(l){lot7030=l;document.getElementById('lot-7030-peru').classList.toggle('active',l==='peru');document.getElementById('lot-7030-plus').classList.toggle('active',l==='plus');}

function cargar7030(){let f=document.getElementById('fecha-7030').value,lot=lot7030;fetch('/admin/reporte-7030',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha:f||null,loteria:lot})}).then(r=>r.json()).then(d=>{if(d.error){document.getElementById('res-7030').innerHTML=`<div class="card"><div style="color:var(--red);padding:12px">${d.error}</div></div>`;return;}
let totales=d.totales,sorteos=d.sorteos;
let html=`<div class="card">
<div class="card-title">📊 ${lot7030.toUpperCase()} — ${d.fecha}</div>
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:14px">
  <div class="stat-box"><div class="stat-label">TOTAL VENDIDO</div><div class="stat-val">S/${totales.vendido.toFixed(2)}</div></div>
  <div class="stat-box"><div class="stat-label">PRESUPUESTO 70%</div><div class="stat-val t">S/${totales.presupuesto_70.toFixed(2)}</div></div>
  <div class="stat-box"><div class="stat-label">PREMIOS PAGADOS</div><div class="stat-val r">S/${totales.premio_pagado.toFixed(2)}</div></div>
  <div class="stat-box"><div class="stat-label">CASA 30% BRUTO</div><div class="stat-val g">S/${totales.para_casa_30.toFixed(2)}</div></div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:14px">
  <div class="stat-box"><div class="stat-label">ACUM. FIN JORNADA</div><div class="stat-val">${totales.acumulado_fin_jornada>=0?'':'<span style=\'color:var(--red)\'>-</span>'}S/${Math.abs(totales.acumulado_fin_jornada).toFixed(2)}</div></div>
  <div class="stat-box"><div class="stat-label">% PAGADO</div><div class="stat-val ${totales.pct_pagado>70?'r':'g'}">${totales.pct_pagado}%</div></div>
  <div class="stat-box"><div class="stat-label">% CASA</div><div class="stat-val g">${totales.pct_casa}%</div></div>
</div>
<div style="overflow-x:auto">
<table class="reporte-7030-table">
<thead><tr>
  <th>HORA</th><th>ANIMAL</th><th>VENDIDO</th><th>70%</th><th>ACUM.REC.</th><th>PRES.TOTAL</th><th>PREMIO</th><th>ACUM.GEN.</th><th>CASA 30%</th><th>MODO</th>
</tr></thead>
<tbody>`;
sorteos.forEach(s=>{let modoBadge=s.modo==='auto'?'<span class="modo-badge auto">AUTO</span>':s.modo==='manual'?'<span class="modo-badge manual">MANUAL</span>':'<span class="modo-badge pte">PEND.</span>';let animalStr=s.animal?`<span style="color:#4ade80;font-weight:700">${s.animal} — ${s.nombre}</span>`:`<span style="color:var(--text2)">—</span>`;let pres_col=s.premio_pagado>s.presupuesto_total?'style="color:var(--red)"':'';html+=`<tr class="${!s.realizado?'pte':''}"><td style="color:var(--teal);font-family:'Oswald',sans-serif;font-size:.7rem;font-weight:700">${s.hora.replace(':00 ','')}</td><td>${animalStr}</td><td>S/${s.vendido.toFixed(2)}</td><td style="color:var(--teal)">S/${s.presupuesto_70.toFixed(2)}</td><td style="color:#a855f7">S/${s.acum_recibido.toFixed(2)}</td><td style="color:var(--gold)" ${pres_col}>S/${s.presupuesto_total.toFixed(2)}</td><td style="color:var(--red)">S/${s.premio_pagado.toFixed(2)}</td><td style="color:var(--green)">S/${s.acum_generado.toFixed(2)}</td><td style="color:#22c55e">S/${s.para_casa_30.toFixed(2)}</td><td>${modoBadge}</td></tr>`;});
html+=`</tbody><tfoot><tr><td colspan="2" style="color:var(--gold)">TOTALES JORNADA</td><td>S/${totales.vendido.toFixed(2)}</td><td style="color:var(--teal)">S/${totales.presupuesto_70.toFixed(2)}</td><td>—</td><td>—</td><td style="color:var(--red)">S/${totales.premio_pagado.toFixed(2)}</td><td>—</td><td style="color:var(--green)">S/${totales.para_casa_30.toFixed(2)}</td><td></td></tr></tfoot>
</table></div></div>`;
document.getElementById('res-7030').innerHTML=html;}).catch(e=>document.getElementById('res-7030').innerHTML=`<div class="card"><div style="color:var(--red)">Error: ${e}</div></div>`);}

// ── AGENCIAS ──────────────────────────────────────────────────────────────────
function listarAgencias(){fetch('/admin/lista-agencias').then(r=>r.json()).then(ags=>{let html='';if(!ags.length){document.getElementById('ag-lista').innerHTML='<div style="color:var(--text2);text-align:center;padding:20px">Sin agencias</div>';return;}window._agMap={};ags.forEach(ag=>{window._agMap[ag.id]=ag.nombre_agencia;let topeStr=ag.tope_taquilla?'S/'+ag.tope_taquilla:'Sin limite';let bancoStr=ag.nombre_banco?'<div style="color:#a0b0c0;font-size:.68rem">Banco: '+ag.nombre_banco+'</div>':'';let estadoTag='<span class="tag '+(ag.activa?'ok':'err')+'">'+(ag.activa?'ACTIVA':'INACTIVA')+'</span>';html+='<div style="background:var(--card);border:1px solid var(--border);border-radius:4px;padding:10px;margin-bottom:8px">';html+='<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px"><div>';html+='<div style="color:var(--gold);font-weight:700">'+ag.nombre_agencia+'</div>';html+='<div style="color:var(--text2);font-size:.72rem">'+ag.usuario+' | Com: '+(ag.comision*100).toFixed(0)+'% | Tope: '+topeStr+'</div>'+bancoStr;html+='</div><div>'+estadoTag+'</div></div>';html+='<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:5px">';html+='<input id="nb-'+ag.id+'" placeholder="Banco" value="'+(ag.nombre_banco||'')+'" style="padding:4px;font-size:.7rem">';html+='<input id="pass-'+ag.id+'" placeholder="Nueva clave" type="password" style="padding:4px;font-size:.7rem">';html+='<input id="com-'+ag.id+'" placeholder="Comision%" value="'+(ag.comision*100).toFixed(0)+'" type="number" step="1" style="padding:4px;font-size:.7rem">';html+='<input id="tope-'+ag.id+'" placeholder="Tope taquilla" value="'+(ag.tope_taquilla||0)+'" type="number" step="10" style="padding:4px;font-size:.7rem">';html+='</div><div style="display:flex;gap:4px;margin-top:5px;flex-wrap:wrap">';html+='<button class="btn" style="padding:4px 10px;font-size:.65rem" onclick="editarAg('+ag.id+')">Guardar</button>';html+='<button class="btn '+(ag.activa?'red':'green')+'" style="padding:4px 10px;font-size:.65rem" onclick="toggleAg('+ag.id+','+(ag.activa?0:1)+')">'+(ag.activa?'Suspender':'Activar')+'</button>';html+='<button class="btn" style="padding:4px 10px;font-size:.65rem;background:#1a0a30;border-color:#a855f7;color:#c084fc" onclick="verReporteAgencia('+ag.id+')">Reporte</button>';html+='<button class="btn red" style="padding:4px 10px;font-size:.65rem" onclick="eliminarAgencia('+ag.id+')">Eliminar</button>';html+='</div></div>';});document.getElementById('ag-lista').innerHTML=html;});}
function crearAgencia(){let u=document.getElementById('ag-user').value.trim(),p=document.getElementById('ag-pass').value.trim(),n=document.getElementById('ag-nombre').value.trim(),nb=document.getElementById('ag-banco').value.trim();if(!u||!p||!n){showMsg('msg-ag','Complete todos los campos requeridos','err');return;}let fd=new FormData();fd.append('usuario',u);fd.append('password',p);fd.append('nombre',n);fd.append('nombre_banco',nb);fetch('/admin/crear-agencia',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{if(d.status==='ok'){showMsg('msg-ag',d.mensaje,'ok');['ag-user','ag-pass','ag-nombre','ag-banco'].forEach(i=>document.getElementById(i).value='');listarAgencias();}else showMsg('msg-ag',d.error,'err');});}
function editarAg(id){let data={id,nombre_banco:document.getElementById('nb-'+id).value,password:document.getElementById('pass-'+id).value,comision:parseFloat(document.getElementById('com-'+id).value)||0,tope_taquilla:parseFloat(document.getElementById('tope-'+id).value)||0};fetch('/admin/editar-agencia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}).then(r=>r.json()).then(d=>{if(d.status==='ok')alert('✅ Guardado');else alert(d.error);listarAgencias();});}
function toggleAg(id,activa){fetch('/admin/editar-agencia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,activa})}).then(r=>r.json()).then(()=>listarAgencias());}
function eliminarAgencia(id){let nombre=window._agMap&&window._agMap[id]?window._agMap[id]:'Agencia '+id;if(!confirm(`¿ELIMINAR la agencia "${nombre}"?\n\nEsta acción es permanente.`))return;fetch('/admin/eliminar-agencia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})}).then(r=>r.json()).then(d=>{if(d.status==='ok'){alert('✅ '+d.mensaje);listarAgencias();}else alert('❌ '+d.error);}).catch(()=>alert('Error de conexión'));}
function verReporteAgencia(id){let nombre=window._agMap&&window._agMap[id]?window._agMap[id]:'Agencia '+id;let ini=prompt('Fecha inicio (YYYY-MM-DD) para '+nombre+':');if(!ini)return;let fin=prompt('Fecha fin (YYYY-MM-DD):');if(!fin)return;fetch('/admin/reporte-agencia-horas',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agencia_id:id,fecha_inicio:ini,fecha_fin:fin})}).then(r=>r.json()).then(d=>{if(d.error){alert(d.error);return;}let ventana=window.open('','_blank');let w=ventana.document;w.open();w.write('<html><head><title>Reporte</title></head><body style="font-family:monospace;background:#050a12;color:#c0d8f0;padding:20px">');w.write('<h2 style="color:#f5a623">'+nombre+' ('+d.usuario+')</h2>');w.write('<h3>Total: S/'+d.total_general+'</h3>');d.resumen.forEach(function(h){w.write('<h4 style="color:#00c8e8">'+h.hora+' - S/'+h.total+' ('+h.conteo+' jugadas)</h4>');w.write('<table border=1 cellpadding=4 style="border-collapse:collapse;color:#c0d8f0;border-color:#1a2a4a"><tr><th>Animal</th><th>Tipo</th><th>Apostado</th><th>Tickets</th></tr>');h.jugadas.forEach(function(j){w.write('<tr><td>'+j.seleccion+' '+j.nombre+'</td><td>'+j.tipo+'</td><td>S/'+j.apostado+'</td><td>'+j.cnt+'</td></tr>');});w.write('</table><br>');});w.write('</body></html>');w.close();});}

// ── TOPES ─────────────────────────────────────────────────────────────────────
function selLotTopes(l){lotTopes=l;document.getElementById('lot-topes-peru').classList.toggle('active',l==='peru');document.getElementById('lot-topes-plus').classList.toggle('active',l==='plus');fillHorasTopes();cargarTopes();}
function fillHorasTopes(){let s=document.getElementById('tope-hora'),lista=lotTopes==='plus'?HPLUS:HPERU;s.innerHTML=lista.map(x=>`<option value="${x}">${x}</option>`).join('');}
function cargarTopes(){let hora=document.getElementById('tope-hora').value,lot=lotTopes;fetch(`/admin/topes?hora=${encodeURIComponent(hora)}&loteria=${lot}`).then(r=>r.json()).then(d=>{if(d.error){document.getElementById('topes-body').innerHTML=`<div style="color:var(--red)">${d.error}</div>`;return;}let html='<table class="tbl"><thead><tr><th>N°</th><th>Animal</th><th>Apostado Hoy</th><th>Tope</th><th>Disponible</th><th>Acción</th></tr></thead><tbody>';ORDEN.forEach(k=>{if(!ANIMALES[k])return;let t=d.topes.find(x=>x.numero===k);let apt=t?t.apostado:0,tope=t?t.tope:0,disp=t?t.disponible:null;let dispStr=disp!==null?`<span style="color:${disp<10?'var(--red)':disp<50?'var(--gold)':'var(--green)'};font-family:'Oswald',sans-serif">S/${disp.toFixed(2)}</span>`:'<span class="tag info">LIBRE</span>';html+=`<tr><td style="font-family:'Oswald',sans-serif;color:var(--gold)">${k}</td><td>${ANIMALES[k]}</td><td style="color:var(--teal);font-family:'Oswald',sans-serif">${apt>0?`S/${apt.toFixed(2)}`:'—'}</td><td><input type="number" id="tope-monto-${k}" value="${tope||''}" placeholder="Sin tope" style="width:90px;padding:4px;font-size:.75rem" min="0" step="5"></td><td>${dispStr}</td><td><button class="btn" style="padding:3px 8px;font-size:.65rem" onclick="guardarTope('${k}','${hora}','${lot}')">💾</button>${tope>0?`<button class="btn red" style="padding:3px 8px;font-size:.65rem;margin-left:4px" onclick="liberarTope('${k}','${hora}','${lot}')">✕</button>`:'&nbsp;'}</td></tr>`;});html+='</tbody></table>';document.getElementById('topes-body').innerHTML=html;});}
function guardarTope(num,hora,lot){let monto=parseFloat(document.getElementById(`tope-monto-${num}`).value)||0;fetch('/admin/topes/guardar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hora,numero:num,monto,loteria:lot})}).then(r=>r.json()).then(d=>{if(d.status==='ok')cargarTopes();else alert(d.error);});}
function liberarTope(num,hora,lot){fetch('/admin/topes/guardar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hora,numero:num,monto:0,loteria:lot})}).then(r=>r.json()).then(d=>{if(d.status==='ok')cargarTopes();});}
function limpiarTopes(){let hora=document.getElementById('tope-hora').value,lot=lotTopes;if(!confirm(`¿Eliminar TODOS los topes de ${hora} (${lot})?`))return;fetch('/admin/topes/limpiar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hora,loteria:lot})}).then(r=>r.json()).then(d=>{if(d.status==='ok')cargarTopes();else alert(d.error);});}

// ── REPORTES ──────────────────────────────────────────────────────────────────
function cargarReporteHoy(){fetch('/admin/reporte-agencias').then(r=>r.json()).then(d=>{let html='<table class="tbl"><thead><tr><th>Agencia</th><th>Tickets</th><th>Ventas</th><th>Premios Pagados</th><th>Pendientes</th><th>Total Premios</th><th>Comision</th><th>Balance</th></tr></thead><tbody>';d.agencias.forEach(a=>{let bc=a.balance>=0?'var(--green)':'var(--red)';let pend=a.premios_pendientes||0;html+='<tr><td><span style="color:var(--gold)">'+a.nombre+'</span><br><span style="color:var(--text2);font-size:.65rem">'+a.usuario+'</span></td><td>'+a.tickets+'</td><td>S/'+a.ventas.toFixed(2)+'</td><td style="color:var(--red)">S/'+a.premios_pagados.toFixed(2)+'</td><td style="color:var(--gold)">'+( pend>0?'S/'+pend.toFixed(2):'—')+'</td><td style="color:var(--red);font-weight:700">S/'+a.premios_total.toFixed(2)+'</td><td>S/'+a.comision.toFixed(2)+'</td><td style="color:'+bc+';font-weight:700">S/'+a.balance.toFixed(2)+'</td></tr>';});html+='<tfoot><tr><td colspan="2" style="color:var(--gold)">GLOBAL</td><td>S/'+d.global.ventas.toFixed(2)+'</td><td style="color:var(--red)">S/'+d.global.pagos.toFixed(2)+'</td><td></td><td></td><td>S/'+d.global.comisiones.toFixed(2)+'</td><td style="color:'+(d.global.balance>=0?'var(--green)':'var(--red)')+';font-weight:700">S/'+d.global.balance.toFixed(2)+'</td></tr></tfoot></table>';document.getElementById('rep-hoy').innerHTML=html;document.getElementById('btn-csv').disabled=false;document.getElementById('btn-csv').style.opacity=1;});}
function cargarEstadisticas(){let ini=document.getElementById('rep-ini').value,fin=document.getElementById('rep-fin').value;if(!ini||!fin){alert('Seleccione fechas');return;}fetch('/admin/estadisticas-rango',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin})}).then(r=>r.json()).then(d=>{let html=`<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0"><div class="stat-box"><div class="stat-label">VENTAS</div><div class="stat-val">S/${d.totales.ventas.toFixed(2)}</div></div><div class="stat-box"><div class="stat-label">PREMIOS</div><div class="stat-val r">S/${d.totales.premios.toFixed(2)}</div></div><div class="stat-box"><div class="stat-label">COMISIONES</div><div class="stat-val">S/${d.totales.comisiones.toFixed(2)}</div></div><div class="stat-box"><div class="stat-label">BALANCE</div><div class="stat-val ${d.totales.balance>=0?'g':'r'}">S/${d.totales.balance.toFixed(2)}</div></div></div>`;html+='<table class="tbl"><thead><tr><th>Fecha</th><th>Tickets</th><th>Ventas</th><th>Premios</th><th>Comisiones</th><th>Balance</th></tr></thead><tbody>';d.resumen_por_dia.forEach(dia=>{let bc=dia.balance>=0?'var(--green)':'var(--red)';html+=`<tr><td>${dia.fecha}</td><td>${dia.tickets}</td><td>S/${dia.ventas.toFixed(2)}</td><td style="color:var(--red)">S/${dia.premios.toFixed(2)}</td><td>S/${dia.comisiones.toFixed(2)}</td><td style="color:${bc};font-family:'Oswald',sans-serif">S/${dia.balance.toFixed(2)}</td></tr>`;});html+='</tbody></table>';document.getElementById('rep-periodo').innerHTML=html;});}
function cargarReporteAgencias(){let ini=document.getElementById('rep-ini').value,fin=document.getElementById('rep-fin').value;if(!ini||!fin){alert('Seleccione fechas');return;}fetch('/admin/reporte-agencias-rango',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin})}).then(r=>r.json()).then(d=>{let html=`<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0"><div class="stat-box"><div class="stat-label">TOTAL VENTAS</div><div class="stat-val">S/${d.total.ventas.toFixed(2)}</div></div><div class="stat-box"><div class="stat-label">PREMIOS</div><div class="stat-val r">S/${d.total.premios.toFixed(2)}</div></div><div class="stat-box"><div class="stat-label">COMISIONES</div><div class="stat-val">S/${d.total.comision.toFixed(2)}</div></div><div class="stat-box"><div class="stat-label">BALANCE</div><div class="stat-val ${d.total.balance>=0?'g':'r'}">S/${d.total.balance.toFixed(2)}</div></div></div>`;html+='<table class="tbl"><thead><tr><th>Agencia</th><th>Tickets</th><th>Ventas</th><th>% del Total</th><th>Premios</th><th>Comisión</th><th>Balance</th></tr></thead><tbody>';d.agencias.forEach(a=>{let bc=a.balance>=0?'var(--green)':'var(--red)';html+=`<tr><td><span style="color:var(--gold)">${a.nombre}</span><br><span style="color:var(--text2);font-size:.65rem">${a.usuario}</span></td><td>${a.tickets}</td><td>S/${a.ventas.toFixed(2)}</td><td style="color:var(--text2)">${a.porcentaje_ventas||0}%</td><td style="color:var(--red)">S/${a.premios_teoricos.toFixed(2)}</td><td>S/${a.comision.toFixed(2)}</td><td style="color:${bc};font-family:'Oswald',sans-serif">S/${a.balance.toFixed(2)}</td></tr>`;});html+='</tbody></table>';document.getElementById('rep-periodo').innerHTML=html;});}
function exportarCSV(){let ini=document.getElementById('rep-ini').value,fin=document.getElementById('rep-fin').value;if(!ini||!fin){alert('Seleccione fechas');return;}fetch('/admin/exportar-csv',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin})}).then(r=>r.blob()).then(blob=>{let a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`reporte_${ini}_${fin}.csv`;a.click();});}

// ── TRIPLETAS ─────────────────────────────────────────────────────────────────
function cargarTripletas(){fetch('/admin/tripletas-hoy').then(r=>r.json()).then(d=>{let html='<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px"><div class="stat-box"><div class="stat-label">TOTAL</div><div class="stat-val">'+d.total+'</div></div><div class="stat-box"><div class="stat-label">GANADORAS</div><div class="stat-val g">'+d.ganadoras+'</div></div><div class="stat-box"><div class="stat-label">PREMIOS</div><div class="stat-val r">S/'+(d.total_premios||0).toFixed(2)+'</div></div></div>';if(!d.tripletas.length){html+='<div style="color:var(--text2);text-align:center;padding:20px">Sin tripletas hoy</div>';document.getElementById('trip-body').innerHTML=html;return;}html+='<table class="tbl"><thead><tr><th>Serial</th><th>Agencia</th><th>Animals</th><th>Monto</th><th>Hora</th><th>Validez</th><th>Salieron</th><th>Faltan</th><th>Premio</th><th>Estado</th></tr></thead><tbody>';d.tripletas.forEach(function(t){let lotLabel=t.loteria==='plus'?'<span class="tag" style="background:#2e1065;color:#c084fc;border-color:#7c3aed">PLUS</span>':'<span class="tag info">PERÚ</span>';let ans=t.nombres.map(function(n,i){return t['animal'+(i+1)]+'-'+n;}).join(' • ');let animSet=[t.animal1,t.animal2,t.animal3];let salSet=t.salieron||[];let faltanArr=animSet.filter(function(a){return salSet.indexOf(a)<0;});let salStr=salSet.length?salSet.map(function(a){return a+'-'+(ANIMALES[a]||a);}).join(', '):'<span style="color:var(--text2)">Ninguno</span>';let faltanStr=faltanArr.length?faltanArr.map(function(a){return'<span style="color:var(--gold)">'+a+'-'+(ANIMALES[a]||a)+'</span>';}).join(', '):'<span style="color:var(--green)">✅ Todos</span>';let validezStr=t.sorteos_validos+'/'+t.sorteos_totales+' sorteos';html+='<tr style="'+(t.gano?'background:rgba(46,204,113,.04)':'')+'"><td style="color:var(--teal);font-size:.7rem">'+t.serial+'</td><td style="font-size:.72rem">'+t.agencia+'<br>'+lotLabel+'</td><td style="font-size:.72rem;color:#c084fc">'+ans+'</td><td style="color:var(--gold)">S/'+t.monto+'</td><td style="font-size:.68rem;color:var(--text2)">'+t.hora_compra+'</td><td style="font-size:.68rem;color:#6090c0">'+validezStr+'</td><td style="font-size:.72rem;color:#4ade80">'+salStr+'</td><td style="font-size:.72rem">'+faltanStr+'</td><td style="color:var(--red)">'+(t.gano?'S/'+t.premio.toFixed(2):'—')+'</td><td><span class="tag '+(t.gano?(t.pagado?'ok':'warn'):'err')+'">'+(t.gano?(t.pagado?'PAGADO':'PENDIENTE'):'NO GANÓ')+'</span></td></tr>';});html+='</tbody></table>';document.getElementById('trip-body').innerHTML=html;});}
// ── AUDITORÍA ─────────────────────────────────────────────────────────────────
function cargarAudit(){let ini=document.getElementById('aud-ini').value,fin=document.getElementById('aud-fin').value,filtro=document.getElementById('aud-filtro').value;fetch('/admin/audit-logs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin,filtro,limit:500})}).then(r=>r.json()).then(d=>{let html='<table class="tbl"><thead><tr><th>Fecha</th><th>Agencia</th><th>Acción</th><th>Detalle</th><th>IP</th></tr></thead><tbody>';d.logs.forEach(l=>{let colorAccion=l.accion.includes('AUTO')&&l.accion.includes('TOGGLE')?'var(--teal)':l.accion.includes('PAGO')?'var(--green)':l.accion.includes('ANUL')?'var(--red)':l.accion.includes('RESUL')?'var(--gold)':l.accion.includes('ELIMINAR')?'var(--red)':'var(--text)';html+=`<tr><td style="font-size:.68rem;color:var(--text2);white-space:nowrap">${l.fecha}</td><td style="font-size:.72rem">${l.agencia}</td><td><span class="tag info" style="color:${colorAccion}">${l.accion}</span></td><td style="font-size:.7rem;max-width:300px;overflow:hidden;text-overflow:ellipsis">${l.detalle||''}</td><td style="font-size:.7rem;color:var(--text2)">${l.ip||''}</td></tr>`;});html+='</tbody></table>';document.getElementById('aud-body').innerHTML=html;});}

// ── HELPERS ───────────────────────────────────────────────────────────────────
function showMsg(id,msg,tipo){let el=document.getElementById(id);el.textContent=msg;el.className='msg '+tipo;el.style.display='block';clearTimeout(el._t);el._t=setTimeout(()=>el.style.display='none',3500);}

// ── INIT ──────────────────────────────────────────────────────────────────────
function init(){
  let hoy=new Date().toISOString().split('T')[0];
  document.getElementById('res-fecha').value=hoy;
  document.getElementById('rep-ini').value=hoy;
  document.getElementById('rep-fin').value=hoy;
  document.getElementById('aud-ini').value=hoy;
  document.getElementById('aud-fin').value=hoy;
  document.getElementById('fecha-7030').value=hoy;
  fillHorasRes();fillHorasRiesgo();fillHorasTopes();
  renderAMG();
  cargarResultadosAdmin();
  cargarEstadoAutoSorteo();
  cargarSecuencia();
  setInterval(cargarEstadoAutoSorteo,30000);
  setInterval(cargarSecuencia,120000);
}
document.addEventListener('DOMContentLoaded',init);
</script>
</body></html>'''


# ═══════════════════════════════════════════════════════════════════════════════
# ARRANQUE
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    init_db()
    _db_ready = True
    iniciar_scheduler()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    # Producción (Render/Gunicorn): init_db se llama en before_request.
    # El scheduler se arranca aquí para que funcione con gunicorn --workers=1
    try:
        iniciar_scheduler()
    except Exception as e:
        logger.error(f"[SCHEDULER] Error al iniciar: {e}")
