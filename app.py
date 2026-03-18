#!/usr/bin/env python3
"""
SISTEMA MULTI-LOTERÍA v4.0
- Multi-administrador: Cada admin tiene sus agencias independientes
- Bloqueo de números por lotería/hora
- Límites de venta globales por número/hora
- Selección múltiple de loterías al agregar jugada
- Tripletas multi-lotería
- Taquillas pueden anular sus propios tickets
- Nueva lotería: LOTTO INTER (igual a LOTTO ACTIVO)
- Renombrado: SELVA PARAISO -> SELVA PLUS
- Pagos tripletas actualizados
- Super Admin: yampiero1 / 15821462
"""

import os, json, csv, io, sqlite3, urllib.parse
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, render_template_string, request, session, redirect, jsonify, Response
from collections import defaultdict

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'multi_loteria_2025_ultra')
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'multi_loteria.db')

# ========================= CONFIGURACIÓN POR LOTERÍA =========================

LOTERIAS = {
    'zoolo': {
        'nombre': 'ZOOLO CASINO',
        'emoji': '🦁',
        'color': '#f5a623',
        'pago_normal': 35,
        'pago_especial': 70,
        'pago_especiales': 2,
        'pago_tripleta': 60,
        'tiene_tripleta': True,
        'tiene_especiales': True,
        'animal_especial': '40',
        'offset_30min': False,
        'animales': {
            "00":"Ballena","0":"Delfin","1":"Carnero","2":"Toro","3":"Ciempies",
            "4":"Alacran","5":"Leon","6":"Rana","7":"Perico","8":"Raton","9":"Aguila",
            "10":"Tigre","11":"Gato","12":"Caballo","13":"Mono","14":"Paloma",
            "15":"Zorro","16":"Oso","17":"Pavo","18":"Burro","19":"Chivo","20":"Cochino",
            "21":"Gallo","22":"Camello","23":"Cebra","24":"Iguana","25":"Gallina",
            "26":"Vaca","27":"Perro","28":"Zamuro","29":"Elefante","30":"Caiman",
            "31":"Lapa","32":"Ardilla","33":"Pescado","34":"Venado","35":"Jirafa",
            "36":"Culebra","37":"Aviapa","38":"Conejo","39":"Tortuga","40":"Lechuza"
        }
    },
    'activo': {
        'nombre': 'LOTTO ACTIVO',
        'emoji': '🎰',
        'color': '#22c55e',
        'pago_normal': 30,
        'pago_especial': 60,
        'pago_especiales': 2,
        'pago_tripleta': 50,
        'tiene_tripleta': True,
        'tiene_especiales': False,
        'animal_especial': None,
        'offset_30min': False,
        'animales': {
            "00":"Ballena","0":"Delfin","1":"Carnero","2":"Toro","3":"Ciempies",
            "4":"Alacran","5":"Leon","6":"Rana","7":"Perico","8":"Raton","9":"Aguila",
            "10":"Tigre","11":"Gato","12":"Caballo","13":"Mono","14":"Paloma",
            "15":"Zorro","16":"Oso","17":"Pavo","18":"Burro","19":"Chivo","20":"Cochino",
            "21":"Gallo","22":"Camello","23":"Cebra","24":"Iguana","25":"Gallina",
            "26":"Vaca","27":"Perro","28":"Zamuro","29":"Elefante","30":"Caiman",
            "31":"Lapa","32":"Ardilla","33":"Pescado","34":"Venado","35":"Jirafa",
            "36":"Culebra"
        }
    },
    'granjita': {
        'nombre': 'GRANJITA',
        'emoji': '🌾',
        'color': '#86efac',
        'pago_normal': 30,
        'pago_especial': 60,
        'pago_especiales': 2,
        'pago_tripleta': 50,
        'tiene_tripleta': True,
        'tiene_especiales': False,
        'animal_especial': None,
        'offset_30min': False,
        'animales': {
            "00":"Ballena","0":"Delfin","1":"Carnero","2":"Toro","3":"Ciempies",
            "4":"Alacran","5":"Leon","6":"Rana","7":"Perico","8":"Raton","9":"Aguila",
            "10":"Tigre","11":"Gato","12":"Caballo","13":"Mono","14":"Paloma",
            "15":"Zorro","16":"Oso","17":"Pavo","18":"Burro","19":"Chivo","20":"Cochino",
            "21":"Gallo","22":"Camello","23":"Cebra","24":"Iguana","25":"Gallina",
            "26":"Vaca","27":"Perro","28":"Zamuro","29":"Elefante","30":"Caiman",
            "31":"Lapa","32":"Ardilla","33":"Pescado","34":"Venado","35":"Jirafa",
            "36":"Culebra"
        }
    },
    'guacharo': {
        'nombre': 'EL GUACHARO',
        'emoji': '🦅',
        'color': '#60a5fa',
        'pago_normal': 60,
        'pago_especial': 120,
        'pago_especiales': 2,
        'pago_tripleta': 100,
        'tiene_tripleta': True,
        'tiene_especiales': False,
        'animal_especial': '75',
        'offset_30min': False,
        'animales': {
            "0":"Delfin","00":"Ballena","1":"Carnero","2":"Toro","3":"Ciempies",
            "4":"Alacran","5":"Leon","6":"Rana","7":"Perico","8":"Raton","9":"Aguila",
            "10":"Tigre","11":"Gato","12":"Caballo","13":"Mono","14":"Paloma",
            "15":"Zorro","16":"Oso","17":"Pavo","18":"Burro","19":"Chivo","20":"Cochino",
            "21":"Gallo","22":"Camello","23":"Cebra","24":"Iguana","25":"Gallina",
            "26":"Vaca","27":"Perro","28":"Zamuro","29":"Elefante","30":"Caiman",
            "31":"Lapa","32":"Ardilla","33":"Pescado","34":"Venado","35":"Jirafa",
            "36":"Culebra","37":"Tortuga","38":"Bufalo","39":"Lechuza","40":"Avispa",
            "41":"Canguro","42":"Tucan","43":"Mariposa","44":"Chiguire","45":"Garza",
            "46":"Puma","47":"Pavo Real","48":"Puercoespin","49":"Pereza","50":"Canario",
            "51":"Pelicano","52":"Pulpo","53":"Caracol","54":"Grillo","55":"Oso Hormiguero",
            "56":"Tiburon","57":"Pato","58":"Hormiga","59":"Pantera","60":"Camaleon",
            "61":"Panda","62":"Cachicamo","63":"Cangrejo","64":"Gavilan","65":"Arana",
            "66":"Lobo","67":"Avestruz","68":"Jaguar","69":"Conejo","70":"Bisonte",
            "71":"Guacamaya","72":"Gorila","73":"Hipopotamo","74":"Turpial","75":"Guacharo"
        }
    },
    'guacharito': {
        'nombre': 'GUACHARITO',
        'emoji': '🐦',
        'color': '#c084fc',
        'pago_normal': 70,
        'pago_especial': 140,
        'pago_especiales': 2,
        'pago_tripleta': 130,
        'tiene_tripleta': True,
        'tiene_especiales': False,
        'animal_especial': '99',
        'offset_30min': True,
        'animales': {
            "0":"Delfin","00":"Ballena","1":"Carnero","2":"Toro","3":"Ciempies",
            "4":"Alacran","5":"Leon","6":"Rana","7":"Perico","8":"Raton","9":"Aguila",
            "10":"Tigre","11":"Gato","12":"Caballo","13":"Mono","14":"Paloma",
            "15":"Zorro","16":"Oso","17":"Pavo","18":"Burro","19":"Chivo","20":"Cochino",
            "21":"Gallo","22":"Camello","23":"Cebra","24":"Iguana","25":"Gallina",
            "26":"Vaca","27":"Perro","28":"Zamuro","29":"Elefante","30":"Caiman",
            "31":"Lapa","32":"Ardilla","33":"Pescado","34":"Venado","35":"Jirafa",
            "36":"Culebra","37":"Tortuga","38":"Bufalo","39":"Lechuza","40":"Avispa",
            "41":"Canguro","42":"Tucan","43":"Mariposa","44":"Chiguire","45":"Garza",
            "46":"Puma","47":"Pavo Real","48":"Puercoespin","49":"Pereza","50":"Canario",
            "51":"Pelicano","52":"Pulpo","53":"Caracol","54":"Grillo","55":"Oso Hormiguero",
            "56":"Tiburon","57":"Pato","58":"Hormiga","59":"Pantera","60":"Camaleon",
            "61":"Panda","62":"Cachicamo","63":"Cangrejo","64":"Gavilan","65":"Arana",
            "66":"Lobo","67":"Avestruz","68":"Jaguar","69":"Conejo","70":"Bisonte",
            "71":"Guacamaya","72":"Gorila","73":"Hipopotamo","74":"Turpial","75":"Guacharo",
            "76":"Rinoceronte","77":"Pingüino","78":"Antílope","79":"Calamar",
            "80":"Murciélago","81":"Cuervo","82":"Cucaracha","83":"Búho","84":"Camarón",
            "85":"Hámster","86":"Buey","87":"Cabra","88":"Erizo de Mar","89":"Anguila",
            "90":"Hurón","91":"Morrocoy","92":"Cisne","93":"Gaviota","94":"Paují",
            "95":"Escarabajo","96":"Caballito de Mar","97":"Loro","98":"Cocodrilo",
            "99":"Guacharito"
        }
    },
    'selva': {
        'nombre': 'SELVA PLUS',
        'emoji': '🌴',
        'color': '#34d399',
        'pago_normal': 30,
        'pago_especial': 60,
        'pago_especiales': 2,
        'pago_tripleta': 50,
        'tiene_tripleta': True,
        'tiene_especiales': False,
        'animal_especial': None,
        'offset_30min': False,
        'animales': {
            "00":"Ballena","0":"Delfin","1":"Carnero","2":"Toro","3":"Ciempies",
            "4":"Alacran","5":"Leon","6":"Rana","7":"Perico","8":"Raton","9":"Aguila",
            "10":"Tigre","11":"Gato","12":"Caballo","13":"Mono","14":"Paloma",
            "15":"Zorro","16":"Oso","17":"Pavo","18":"Burro","19":"Chivo","20":"Cochino",
            "21":"Gallo","22":"Camello","23":"Cebra","24":"Iguana","25":"Gallina",
            "26":"Vaca","27":"Perro","28":"Zamuro","29":"Elefante","30":"Caiman",
            "31":"Lapa","32":"Ardilla","33":"Pescado","34":"Venado","35":"Jirafa",
            "36":"Culebra"
        }
    },
    'rey': {
        'nombre': 'LOTTO REY',
        'emoji': '👑',
        'color': '#fbbf24',
        'pago_normal': 30,
        'pago_especial': 60,
        'pago_especiales': 2,
        'pago_tripleta': 50,
        'tiene_tripleta': True,
        'tiene_especiales': False,
        'animal_especial': None,
        'offset_30min': True,
        'animales': {
            "00":"Ballena","0":"Delfin","1":"Carnero","2":"Toro","3":"Ciempies",
            "4":"Alacran","5":"Leon","6":"Rana","7":"Perico","8":"Raton","9":"Aguila",
            "10":"Tigre","11":"Gato","12":"Caballo","13":"Mono","14":"Paloma",
            "15":"Zorro","16":"Oso","17":"Pavo","18":"Burro","19":"Chivo","20":"Cochino",
            "21":"Gallo","22":"Camello","23":"Cebra","24":"Iguana","25":"Gallina",
            "26":"Vaca","27":"Perro","28":"Zamuro","29":"Elefante","30":"Caiman",
            "31":"Lapa","32":"Ardilla","33":"Pescado","34":"Venado","35":"Jirafa",
            "36":"Culebra"
        }
    },
    'inter': {
        'nombre': 'LOTTO INTER',
        'emoji': '🌐',
        'color': '#38bdf8',
        'pago_normal': 30,
        'pago_especial': 60,
        'pago_especiales': 2,
        'pago_tripleta': 50,
        'tiene_tripleta': True,
        'tiene_especiales': False,
        'animal_especial': None,
        'offset_30min': True,
        'animales': {
            "00":"Ballena","0":"Delfin","1":"Carnero","2":"Toro","3":"Ciempies",
            "4":"Alacran","5":"Leon","6":"Rana","7":"Perico","8":"Raton","9":"Aguila",
            "10":"Tigre","11":"Gato","12":"Caballo","13":"Mono","14":"Paloma",
            "15":"Zorro","16":"Oso","17":"Pavo","18":"Burro","19":"Chivo","20":"Cochino",
            "21":"Gallo","22":"Camello","23":"Cebra","24":"Iguana","25":"Gallina",
            "26":"Vaca","27":"Perro","28":"Zamuro","29":"Elefante","30":"Caiman",
            "31":"Lapa","32":"Ardilla","33":"Pescado","34":"Venado","35":"Jirafa",
            "36":"Culebra"
        }
    }
}

# ZOOLO CASINO + Loterías base: 11 sorteos 8AM-6PM Perú
HORARIOS_ZOOLO = [
    "08:00 AM","09:00 AM","10:00 AM","11:00 AM","12:00 PM",
    "01:00 PM","02:00 PM","03:00 PM","04:00 PM","05:00 PM","06:00 PM"
]

# Loterías sin offset (zoolo, activo, granjita, selva, guacharo): 11 sorteos 8AM-6PM
HORARIOS_PERU_BASE = [
    "08:00 AM","09:00 AM","10:00 AM","11:00 AM","12:00 PM",
    "01:00 PM","02:00 PM","03:00 PM","04:00 PM","05:00 PM","06:00 PM"
]

# Venezuela sin offset: 11 sorteos 8AM-6PM (misma hora)
HORARIOS_VENEZUELA_BASE = [
    "08:00 AM","09:00 AM","10:00 AM","11:00 AM","12:00 PM",
    "01:00 PM","02:00 PM","03:00 PM","04:00 PM","05:00 PM","06:00 PM"
]

# Loterías con offset (inter, guacharito, rey): 11 sorteos 8:30AM-6:30PM Perú
HORARIOS_PERU_OFFSET = [
    "08:30 AM","09:30 AM","10:30 AM","11:30 AM","12:30 PM",
    "01:30 PM","02:30 PM","03:30 PM","04:30 PM","05:30 PM","06:30 PM"
]

# Venezuela con offset: 11 sorteos 9:30AM-7:30PM
HORARIOS_VENEZUELA_OFFSET = [
    "09:30 AM","10:30 AM","11:30 AM","12:30 PM","01:30 PM",
    "02:30 PM","03:30 PM","04:30 PM","05:30 PM","06:30 PM","07:30 PM"
]

ROJOS_ZOOLO = ["1","3","5","7","9","12","14","16","18","19",
               "21","23","25","27","30","32","34","36","37","39"]

COMISION_AGENCIA = 0.0   # Por defecto 0% — se configura individualmente por agencia
MINUTOS_BLOQUEO = 5

# ========================= BASE DE DATOS =========================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS agencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            nombre_agencia TEXT NOT NULL,
            es_admin INTEGER DEFAULT 0,
            es_super_admin INTEGER DEFAULT 0,
            admin_padre_id INTEGER DEFAULT NULL,
            comision REAL DEFAULT 0.15,
            activa INTEGER DEFAULT 1,
            tope_taquilla REAL DEFAULT 0,
            creado TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (admin_padre_id) REFERENCES agencias(id)
        );
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serial TEXT UNIQUE NOT NULL,
            agencia_id INTEGER NOT NULL,
            admin_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            total REAL NOT NULL,
            pagado INTEGER DEFAULT 0,
            anulado INTEGER DEFAULT 0,
            creado TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agencia_id) REFERENCES agencias(id),
            FOREIGN KEY (admin_id) REFERENCES agencias(id)
        );
        CREATE TABLE IF NOT EXISTS jugadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            loteria TEXT NOT NULL DEFAULT 'zoolo',
            hora TEXT NOT NULL,
            seleccion TEXT NOT NULL,
            monto REAL NOT NULL,
            tipo TEXT NOT NULL,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id)
        );
        CREATE TABLE IF NOT EXISTS tripletas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            loteria TEXT NOT NULL DEFAULT 'zoolo',
            animal1 TEXT NOT NULL,
            animal2 TEXT NOT NULL,
            animal3 TEXT NOT NULL,
            monto REAL NOT NULL,
            fecha TEXT NOT NULL,
            pagado INTEGER DEFAULT 0,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id)
        );
        CREATE TABLE IF NOT EXISTS resultados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loteria TEXT NOT NULL DEFAULT 'zoolo',
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            animal TEXT NOT NULL,
            UNIQUE(loteria, fecha, hora)
        );
        CREATE TABLE IF NOT EXISTS limites_venta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            loteria TEXT NOT NULL,
            numero TEXT NOT NULL,
            hora TEXT NOT NULL,
            monto_max REAL DEFAULT 0,
            bloqueado INTEGER DEFAULT 0,
            UNIQUE(admin_id, loteria, numero, hora),
            FOREIGN KEY (admin_id) REFERENCES agencias(id)
        );
        CREATE TABLE IF NOT EXISTS topes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            hora TEXT NOT NULL,
            numero TEXT NOT NULL,
            monto_tope REAL NOT NULL,
            UNIQUE(admin_id, hora, numero),
            FOREIGN KEY (admin_id) REFERENCES agencias(id)
        );
        CREATE TABLE IF NOT EXISTS topes_global (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            loteria TEXT NOT NULL,
            hora TEXT NOT NULL,
            numero TEXT NOT NULL,
            monto_tope REAL NOT NULL DEFAULT 0,
            UNIQUE(admin_id, loteria, hora, numero),
            FOREIGN KEY (admin_id) REFERENCES agencias(id)
        );
        CREATE TABLE IF NOT EXISTS topes_agencia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            agencia_id INTEGER NOT NULL,
            loteria TEXT NOT NULL,
            hora TEXT NOT NULL,
            numero TEXT NOT NULL,
            monto_tope REAL NOT NULL DEFAULT 0,
            porcentaje REAL NOT NULL DEFAULT 0,
            UNIQUE(admin_id, agencia_id, loteria, hora, numero),
            FOREIGN KEY (admin_id) REFERENCES agencias(id),
            FOREIGN KEY (agencia_id) REFERENCES agencias(id)
        );
        CREATE TABLE IF NOT EXISTS comisiones_loteria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            agencia_id INTEGER NOT NULL,
            loteria TEXT NOT NULL,
            comision REAL NOT NULL DEFAULT 0,
            UNIQUE(admin_id, agencia_id, loteria),
            FOREIGN KEY (admin_id) REFERENCES agencias(id),
            FOREIGN KEY (agencia_id) REFERENCES agencias(id)
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agencia_id INTEGER,
            usuario TEXT,
            accion TEXT NOT NULL,
            detalle TEXT,
            ip TEXT,
            creado TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_tickets_agencia ON tickets(agencia_id);
        CREATE INDEX IF NOT EXISTS idx_tickets_admin ON tickets(admin_id);
        CREATE INDEX IF NOT EXISTS idx_tickets_fecha ON tickets(fecha);
        CREATE INDEX IF NOT EXISTS idx_jugadas_ticket ON jugadas(ticket_id);
        CREATE INDEX IF NOT EXISTS idx_tripletas_ticket ON tripletas(ticket_id);
        CREATE INDEX IF NOT EXISTS idx_resultados_fecha ON resultados(fecha);
        CREATE INDEX IF NOT EXISTS idx_limites_admin ON limites_venta(admin_id);
        CREATE INDEX IF NOT EXISTS idx_audit_logs_fecha ON audit_logs(creado);
        """)
        # Migration: add tope_taquilla if missing
        try:
            db.execute("ALTER TABLE agencias ADD COLUMN tope_taquilla REAL DEFAULT 0")
            db.commit()
        except: pass
        # Migration: add topes_agencia if missing
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS topes_agencia (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                agencia_id INTEGER NOT NULL,
                loteria TEXT NOT NULL,
                hora TEXT NOT NULL,
                numero TEXT NOT NULL,
                monto_tope REAL NOT NULL DEFAULT 0,
                porcentaje REAL NOT NULL DEFAULT 0,
                UNIQUE(admin_id, agencia_id, loteria, hora, numero),
                FOREIGN KEY (admin_id) REFERENCES agencias(id),
                FOREIGN KEY (agencia_id) REFERENCES agencias(id)
            )""")
            db.commit()
        except: pass
        # Migration: add comisiones_loteria if missing
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS comisiones_loteria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                agencia_id INTEGER NOT NULL,
                loteria TEXT NOT NULL,
                comision REAL NOT NULL DEFAULT 0,
                UNIQUE(admin_id, agencia_id, loteria),
                FOREIGN KEY (admin_id) REFERENCES agencias(id),
                FOREIGN KEY (agencia_id) REFERENCES agencias(id)
            )""")
            db.commit()
        except: pass
        # Migration: add topes_global if missing
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS topes_global (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                loteria TEXT NOT NULL,
                hora TEXT NOT NULL,
                numero TEXT NOT NULL,
                monto_tope REAL NOT NULL DEFAULT 0,
                UNIQUE(admin_id, loteria, hora, numero),
                FOREIGN KEY (admin_id) REFERENCES agencias(id)
            )""")
            db.commit()
        except: pass

        super_admin = db.execute("SELECT id FROM agencias WHERE es_super_admin=1").fetchone()
        if not super_admin:
            db.execute("""INSERT INTO agencias 
                (usuario, password, nombre_agencia, es_admin, es_super_admin, comision, activa) 
                VALUES (?, ?, ?, 1, 1, 0, 1)""",
                ('yampiero1', '15821462', 'SUPER ADMIN'))
            db.commit()
            print("[DB] Super Admin creado: yampiero1 / 15821462")
        
        admin_normal = db.execute("SELECT id FROM agencias WHERE es_admin=1 AND es_super_admin=0").fetchone()
        if not admin_normal:
            db.execute("""INSERT INTO agencias 
                (usuario, password, nombre_agencia, es_admin, es_super_admin, admin_padre_id, comision, activa) 
                VALUES (?, ?, ?, 1, 0, NULL, 0, 1)""",
                ('cuborubi', '15821462', 'ADMINISTRADOR'))
            db.commit()
            print("[DB] Admin creado: cuborubi / 15821462")

# ========================= HELPERS =========================
def ahora_peru():
    return datetime.now(timezone.utc) - timedelta(hours=5)

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

def get_loteria(lid):
    return LOTERIAS.get(lid, LOTERIAS['zoolo'])

def get_horarios(loteria_id):
    if loteria_id == 'zoolo':
        # ZOOLO CASINO: 11 sorteos fijos 8AM-6PM, misma hora en Perú y Venezuela
        return HORARIOS_ZOOLO, HORARIOS_ZOOLO
    lot = get_loteria(loteria_id)
    if lot.get('offset_30min', False):
        return HORARIOS_PERU_OFFSET, HORARIOS_VENEZUELA_OFFSET
    return HORARIOS_PERU_BASE, HORARIOS_VENEZUELA_BASE

def get_comision_loteria(admin_id, agencia_id, loteria_id, db_conn):
    """
    Devuelve la comisión a aplicar para una agencia en una lotería específica.
    Prioridad: comisiones_loteria (por lotería) > agencias.comision (general)
    """
    row = db_conn.execute("""
        SELECT comision FROM comisiones_loteria
        WHERE admin_id=? AND agencia_id=? AND loteria=?
    """, (admin_id, agencia_id, loteria_id)).fetchone()
    if row is not None:
        return row['comision']
    ag = db_conn.execute("SELECT comision FROM agencias WHERE id=?", (agencia_id,)).fetchone()
    return ag['comision'] if ag else 0.0

def get_admin_id(user_id):
    with get_db() as db:
        row = db.execute("SELECT es_admin, admin_padre_id FROM agencias WHERE id=?", (user_id,)).fetchone()
        if not row: return None
        if row['es_admin']: return user_id
        return row['admin_padre_id']

def verificar_limites(admin_id, loteria, numero, hora, monto_nuevo, agencia_id=None):
    """
    Verifica tres capas de límites:
    1. limites_venta  → bloqueos/límites globales del admin por número+hora+lotería
    2. topes          → tope global del admin para cualquier agencia (tabla topes)
    3. topes_agencia  → tope específico por agencia+lotería+hora+número
    Cualquier capa que falle bloquea la venta.
    """
    hoy = ahora_peru().strftime("%d/%m/%Y")
    with get_db() as db:
        # --- Capa 1: bloqueos/límites de limites_venta ---
        limite = db.execute("""
            SELECT monto_max, bloqueado FROM limites_venta 
            WHERE admin_id=? AND loteria=? AND numero=? AND hora=?
        """, (admin_id, loteria, str(numero), hora)).fetchone()
        
        if limite and limite['bloqueado']:
            return False, f"Número {numero} bloqueado para {hora} en {get_loteria(loteria)['nombre']}", 0
        
        if limite and limite['monto_max'] > 0:
            ventas = db.execute("""
                SELECT COALESCE(SUM(j.monto),0) as total FROM jugadas j
                JOIN tickets t ON j.ticket_id = t.id
                WHERE t.admin_id=? AND j.loteria=? AND j.seleccion=? AND j.hora=? 
                AND t.fecha LIKE ? AND t.anulado=0
            """, (admin_id, loteria, str(numero), hora, hoy+'%')).fetchone()
            
            vendido = ventas['total'] or 0
            disponible = limite['monto_max'] - vendido
            
            if disponible <= 0:
                return False, f"Número {numero} agotado para {hora} (límite global: S/{limite['monto_max']:.0f})", 0
            if monto_nuevo > disponible:
                return False, f"Solo disponible S/{disponible:.0f} para {numero} en {hora}", disponible

        # --- Capa 2: tope global del admin (tabla topes, sin distinción de lotería) ---
        tope_global = db.execute("""
            SELECT monto_tope FROM topes
            WHERE admin_id=? AND hora=? AND numero=?
        """, (admin_id, hora, str(numero))).fetchone()

        if tope_global and tope_global['monto_tope'] > 0:
            tope_g = tope_global['monto_tope']
            vendido_g = db.execute("""
                SELECT COALESCE(SUM(j.monto),0) as total FROM jugadas j
                JOIN tickets t ON j.ticket_id = t.id
                WHERE t.admin_id=? AND j.seleccion=? AND j.hora=?
                AND j.tipo='animal' AND t.anulado=0 AND t.fecha LIKE ?
            """, (admin_id, str(numero), hora, hoy+'%')).fetchone()
            vendido = vendido_g['total'] or 0
            disponible = tope_g - vendido
            if disponible <= 0:
                return False, f"Tope global: número {numero} agotó S/{tope_g:.0f} para {hora}", 0
            if monto_nuevo > disponible:
                return False, f"Tope global: solo disponible S/{disponible:.0f} para {numero} en {hora}", disponible

        # --- Capa 2b: tope global por lotería (topes_global) — suma de TODAS las agencias ---
        tope_gl = db.execute("""
            SELECT monto_tope FROM topes_global
            WHERE admin_id=? AND loteria=? AND hora=? AND numero=?
        """, (admin_id, loteria, hora, str(numero))).fetchone()

        if tope_gl and tope_gl['monto_tope'] > 0:
            tope_g2 = tope_gl['monto_tope']
            # Suma vendida entre TODAS las agencias para ese número/hora/lotería hoy
            vendido_g2 = db.execute("""
                SELECT COALESCE(SUM(j.monto),0) as total FROM jugadas j
                JOIN tickets t ON j.ticket_id = t.id
                WHERE t.admin_id=? AND j.loteria=? AND j.seleccion=? AND j.hora=?
                AND j.tipo='animal' AND t.anulado=0 AND t.fecha LIKE ?
            """, (admin_id, loteria, str(numero), hora, hoy+'%')).fetchone()
            vendido2 = vendido_g2['total'] or 0
            disponible2 = tope_g2 - vendido2
            lot_nombre = get_loteria(loteria)['nombre']
            if disponible2 <= 0:
                return False, f"Cupo total agotado: número {numero} llegó al límite global de S/{tope_g2:.0f} en {lot_nombre} {hora}", 0
            if monto_nuevo > disponible2:
                return False, f"Cupo global: quedan S/{disponible2:.0f} disponibles para {numero} en {lot_nombre} {hora}", disponible2

        # --- Capa 3: tope específico por agencia ---
        if agencia_id:
            tope_row = db.execute("""
                SELECT monto_tope FROM topes_agencia
                WHERE admin_id=? AND agencia_id=? AND loteria=? AND hora=? AND numero=?
            """, (admin_id, agencia_id, loteria, hora, str(numero))).fetchone()
            
            if tope_row and tope_row['monto_tope'] > 0:
                tope = tope_row['monto_tope']
                vendido_ag = db.execute("""
                    SELECT COALESCE(SUM(j.monto),0) as total FROM jugadas j
                    JOIN tickets t ON j.ticket_id = t.id
                    WHERE t.agencia_id=? AND j.loteria=? AND j.seleccion=? AND j.hora=?
                    AND j.tipo='animal' AND t.anulado=0 AND t.fecha LIKE ?
                """, (agencia_id, loteria, str(numero), hora, hoy+'%')).fetchone()
                
                vendido = vendido_ag['total'] or 0
                disponible = tope - vendido
                
                if disponible <= 0:
                    return False, f"Tope de agencia: número {numero} agotó S/{tope:.0f} para {hora} ({get_loteria(loteria)['nombre']})", 0
                if monto_nuevo > disponible:
                    return False, f"Tope de agencia: solo disponible S/{disponible:.0f} para {numero} en {hora}", disponible

    return True, "", 0

def calcular_premio_jugada(j_tipo, j_seleccion, j_monto, resultado_animal, loteria_id):
    lot = get_loteria(loteria_id)
    if resultado_animal is None: return 0
    wa = str(resultado_animal)
    if j_tipo == 'animal':
        if wa == str(j_seleccion):
            if lot['animal_especial'] and wa == lot['animal_especial']:
                return j_monto * lot['pago_especial']
            return j_monto * lot['pago_normal']
    elif j_tipo == 'especial' and lot['tiene_especiales']:
        if wa in ["0","00"]: return 0
        try: num = int(wa)
        except: return 0
        sel = j_seleccion
        if (sel=='ROJO' and wa in ROJOS_ZOOLO) or \
           (sel=='NEGRO' and wa not in ROJOS_ZOOLO and wa not in ["0","00"]) or \
           (sel=='PAR' and num%2==0) or \
           (sel=='IMPAR' and num%2!=0):
            return j_monto * lot['pago_especiales']
    return 0

def calcular_premio_ticket(ticket_id, db_conn=None):
    close = False
    if db_conn is None:
        db_conn = get_db(); close = True
    try:
        t = db_conn.execute("SELECT fecha FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not t: return 0
        fecha_ticket = parse_fecha(t['fecha'])
        if not fecha_ticket: return 0
        fecha_str = fecha_ticket.strftime("%d/%m/%Y")
        total = 0
        jugadas = db_conn.execute("SELECT * FROM jugadas WHERE ticket_id=?", (ticket_id,)).fetchall()
        for j in jugadas:
            res_rows = db_conn.execute("SELECT animal FROM resultados WHERE fecha=? AND loteria=? AND hora=?", 
                                      (fecha_str, j['loteria'], j['hora'])).fetchall()
            if res_rows:
                wa = res_rows[0]['animal']
                total += calcular_premio_jugada(j['tipo'], j['seleccion'], j['monto'], wa, j['loteria'])
        trips = db_conn.execute("SELECT * FROM tripletas WHERE ticket_id=?", (ticket_id,)).fetchall()
        for tr in trips:
            es_zoolo = (tr['loteria'] == 'zoolo')
            if es_zoolo:
                # ZOOLO: los 11 sorteos fijos del día (08AM-6PM), todos del mismo día
                # La tripleta es válida para TODOS los sorteos del día sin importar hora de compra
                res_rows = db_conn.execute(
                    "SELECT animal, hora FROM resultados WHERE fecha=? AND loteria=?",
                    (fecha_str, tr['loteria'])).fetchall()
                # Solo incluir sorteos dentro del rango fijo de ZOOLO (08:00 AM - 06:00 PM)
                resultados = [r['animal'] for r in res_rows 
                              if r['hora'] in HORARIOS_ZOOLO]
            else:
                # Otras loterias: 11 sorteos consecutivos desde hora del ticket
                horas_peru_t, _ = get_horarios(tr['loteria'])
                hora_compra_min = hora_a_min(fecha_ticket.strftime("%I:%M %p"))
                # Encontrar el primer sorteo posterior a la compra
                hora_inicio_idx = 0
                for i, hp in enumerate(horas_peru_t):
                    if hora_a_min(hp) > hora_compra_min:
                        hora_inicio_idx = i
                        break
                # Tomar hasta 11 sorteos desde esa hora (pueden cruzar al dia siguiente)
                horas_validas_peru = []
                for i in range(11):
                    idx = hora_inicio_idx + i
                    dia_extra = idx // len(horas_peru_t)
                    idx_mod = idx % len(horas_peru_t)
                    fecha_sorteo = fecha_ticket + timedelta(days=dia_extra)
                    fecha_sorteo_str = fecha_sorteo.strftime("%d/%m/%Y")
                    horas_validas_peru.append((fecha_sorteo_str, horas_peru_t[idx_mod]))
                res_rows_all = []
                for (fs, hs) in horas_validas_peru:
                    r = db_conn.execute(
                        "SELECT animal FROM resultados WHERE fecha=? AND loteria=? AND hora=?",
                        (fs, tr['loteria'], hs)).fetchone()
                    if r: res_rows_all.append(r['animal'])
                resultados = res_rows_all

            nums = {tr['animal1'], tr['animal2'], tr['animal3']}
            salidos = {a for a in resultados if a in nums}
            if len(salidos) == 3:
                lot = get_loteria(tr['loteria'])
                total += tr['monto'] * lot['pago_tripleta']
        return total
    finally:
        if close: db_conn.close()

# ========================= DECORADORES =========================
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

def super_admin_required(f):
    @wraps(f)
    def d(*a,**k):
        if 'user_id' not in session or not session.get('es_super_admin'):
            return "No autorizado - Super Admin requerido", 403
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
                "INSERT INTO audit_logs (agencia_id, usuario, accion, detalle, ip) VALUES (?,?,?,?,?)",
                (session.get('user_id'), session.get('nombre_agencia','?'), accion, detalle, ip)
            )
            db.commit()
    except: pass

# ========================= RUTAS =========================
@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('es_super_admin'): return redirect('/super-admin')
        return redirect('/admin' if session.get('es_admin') else '/pos')
    return redirect('/login')

@app.route('/login', methods=['GET','POST'])
def login():
    error=""
    if request.method=='POST':
        u = request.form.get('usuario','').strip().lower()
        p = request.form.get('password','').strip()
        with get_db() as db:
            row = db.execute("SELECT * FROM agencias WHERE usuario=? AND password=? AND activa=1",(u,p)).fetchone()
        if row:
            session['user_id'] = row['id']
            session['nombre_agencia'] = row['nombre_agencia']
            session['es_admin'] = bool(row['es_admin'])
            session['es_super_admin'] = bool(row['es_super_admin'])
            session['admin_id'] = row['id'] if row['es_admin'] else row['admin_padre_id']
            return redirect('/')
        error="Usuario o clave incorrecta"
    return render_template_string(LOGIN_HTML, error=error)

@app.route('/logout')
def logout():
    session.clear(); return redirect('/login')

@app.route('/pos')
@login_required
def pos():
    if session.get('es_admin') or session.get('es_super_admin'): 
        return redirect('/admin' if session.get('es_admin') else '/super-admin')
    return render_template_string(POS_HTML, agencia=session['nombre_agencia'], loterias=LOTERIAS)

@app.route('/admin')
@admin_required
def admin():
    return render_template_string(ADMIN_HTML, loterias=LOTERIAS)

@app.route('/super-admin')
@super_admin_required
def super_admin():
    return render_template_string(SUPER_ADMIN_HTML, loterias=LOTERIAS)

# ========================= API HORA =========================
@app.route('/api/hora-actual')
@login_required
def hora_actual():
    ahora = ahora_peru()
    loteria_id = request.args.get('loteria', 'zoolo')
    horas_peru, _ = get_horarios(loteria_id)
    bloqueadas = [h for h in horas_peru if not puede_vender(h)]
    return jsonify({'hora_str': ahora.strftime("%I:%M %p"), 'bloqueadas': bloqueadas})

# ========================= API LIMITES =========================
@app.route('/api/guardar-limite', methods=['POST'])
@admin_required
def guardar_limite():
    try:
        data = request.get_json()
        loteria = data.get('loteria')
        numero = str(data.get('numero'))
        hora = data.get('hora')
        monto_max = float(data.get('monto_max', 0))
        bloqueado = 1 if data.get('bloqueado') else 0
        admin_id = session['user_id']
        with get_db() as db:
            db.execute("""
                INSERT INTO limites_venta (admin_id, loteria, numero, hora, monto_max, bloqueado)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(admin_id, loteria, numero, hora) 
                DO UPDATE SET monto_max=excluded.monto_max, bloqueado=excluded.bloqueado
            """, (admin_id, loteria, numero, hora, monto_max, bloqueado))
            db.commit()
        tipo = "Bloqueado" if bloqueado else f"Límite S/{monto_max}"
        return jsonify({'status': 'ok', 'mensaje': f'{tipo} para {numero} en {hora}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/limites-actuales')
@admin_required
def limites_actuales():
    try:
        loteria = request.args.get('loteria', 'zoolo')
        admin_id = session['user_id']
        with get_db() as db:
            rows = db.execute("""
                SELECT numero, hora, monto_max, bloqueado FROM limites_venta
                WHERE admin_id=? AND loteria=?
            """, (admin_id, loteria)).fetchall()
        limites = {}
        for r in rows:
            key = f"{r['numero']}_{r['hora']}"
            limites[key] = {'numero': r['numero'], 'hora': r['hora'], 'monto_max': r['monto_max'], 'bloqueado': bool(r['bloqueado'])}
        return jsonify({'status': 'ok', 'limites': limites})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/eliminar-limite', methods=['POST'])
@admin_required
def eliminar_limite():
    try:
        data = request.get_json()
        loteria = data.get('loteria')
        numero = data.get('numero')
        hora = data.get('hora')
        admin_id = session['user_id']
        with get_db() as db:
            db.execute("DELETE FROM limites_venta WHERE admin_id=? AND loteria=? AND numero=? AND hora=?",
                      (admin_id, loteria, numero, hora))
            db.commit()
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========================= API VENTA UNIFICADA =========================
@app.route('/api/validar-carrito', methods=['POST'])
@agencia_required
def validar_carrito():
    """
    Valida todos los items del carrito sin procesar la venta.
    Devuelve por cada jugada:
      ok=True  → puede venderse tal cual
      ok=False, disponible=0   → completamente agotado/bloqueado
      ok=False, disponible>0   → hay monto parcial disponible, se puede ajustar
    """
    try:
        data = request.get_json()
        jugadas = data.get('jugadas', [])
        admin_id = session.get('admin_id')
        agencia_id = session.get('user_id')
        if not admin_id:
            return jsonify({'error': 'Error de sesión'}), 403

        resultados = []
        for idx, j in enumerate(jugadas):
            if j['tipo'] == 'tripleta':
                resultados.append({'idx': idx, 'ok': True, 'msg': '', 'disponible': None, 'agotado_total': False})
                continue
            if not puede_vender(j['hora']):
                resultados.append({
                    'idx': idx, 'ok': False,
                    'msg': f"Sorteo {j['hora']} ya cerró",
                    'disponible': 0,
                    'agotado_total': True
                })
                continue
            puede, msg, disp = verificar_limites(
                admin_id, j['loteria'], j['seleccion'], j['hora'], j['monto'],
                agencia_id=agencia_id
            )
            resultados.append({
                'idx': idx,
                'ok': puede,
                'msg': msg,
                'disponible': disp,           # >0 → ajustable; 0 → agotado total
                'agotado_total': (not puede and disp == 0)
            })

        hay_errores = any(not r['ok'] for r in resultados)
        return jsonify({'status': 'ok', 'resultados': resultados, 'hay_errores': hay_errores})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/procesar-venta', methods=['POST'])
@agencia_required
def procesar_venta():
    try:
        data = request.get_json()
        jugadas = data.get('jugadas', [])
        if not jugadas: return jsonify({'error':'Ticket vacío'}),400
        admin_id = session.get('admin_id')
        if not admin_id: return jsonify({'error':'Error de sesión'}), 403
        
        for j in jugadas:
            if j['tipo']!='tripleta' and not puede_vender(j['hora']):
                return jsonify({'error':f"Sorteo {j['hora']} de {j['loteria'].upper()} ya cerró"}),400
            if j['tipo'] == 'animal':
                agencia_id_venta = session.get('user_id')
                puede, msg, disp = verificar_limites(admin_id, j['loteria'], j['seleccion'], j['hora'], j['monto'], agencia_id=agencia_id_venta)
                if not puede:
                    return jsonify({'error': msg, 'disponible': disp}), 400
        
        serial = generar_serial()
        fecha  = ahora_peru().strftime("%d/%m/%Y %I:%M %p")
        total  = sum(j['monto'] for j in jugadas)
        
        with get_db() as db:
            cur = db.execute("INSERT INTO tickets (serial, agencia_id, admin_id, fecha, total) VALUES (?,?,?,?,?)",
                           (serial, session['user_id'], admin_id, fecha, total))
            ticket_id = cur.lastrowid
            for j in jugadas:
                lot_id = j.get('loteria', 'zoolo')
                if j['tipo']=='tripleta':
                    nums = j['seleccion'].split(',')
                    db.execute("INSERT INTO tripletas (ticket_id, loteria, animal1, animal2, animal3, monto, fecha) VALUES (?,?,?,?,?,?,?)",
                              (ticket_id, lot_id, nums[0], nums[1], nums[2], j['monto'], fecha.split(' ')[0]))
                else:
                    db.execute("INSERT INTO jugadas (ticket_id, loteria, hora, seleccion, monto, tipo) VALUES (?,?,?,?,?,?)",
                              (ticket_id, lot_id, j['hora'], j['seleccion'], j['monto'], j['tipo']))
            db.commit()
        
        # ---- Fecha/hora de emisión ----
        ahora_dt = ahora_peru()
        fecha_fmt = ahora_dt.strftime("%d-%m-%Y")
        hora_fmt  = ahora_dt.strftime("%H:%M:%S")

        lineas = [
            session['nombre_agencia'],
            f"T#{ticket_id} S#{serial}",
            f"{fecha_fmt} {hora_fmt}",
            "-------juega y gana---------",
        ]

        # ---- Jugadas normales agrupadas por lotería ----
        por_loteria = defaultdict(list)
        for j in jugadas:
            if j['tipo'] != 'tripleta':
                por_loteria[j.get('loteria','zoolo')].append(j)

        def fmt_h(h):
            """Convierte '01:00 PM' -> '1PM', '08:30 AM' -> '8:30AM' """
            import re
            h2 = h.strip()
            m = re.match(r'(\d+):(\d+) (AM|PM)', h2)
            if m:
                hh, mm, ap = m.group(1), m.group(2), m.group(3)
                if mm == '00':
                    return f"{int(hh)}{ap}"
                else:
                    return f"{int(hh)}:{mm}{ap}"
            return h2.replace(' ','')

        def hora_vzla(hora_peru_str):
            """Devuelve la hora Venezuela = hora Perú + 1 hora."""
            import re
            m = re.match(r'(\d+):(\d+) (AM|PM)', hora_peru_str.strip())
            if not m: return hora_peru_str
            hh, mm, ap = int(m.group(1)), int(m.group(2)), m.group(3)
            # convertir a 24h, sumar 1, volver a 12h
            if ap == 'PM' and hh != 12: hh += 12
            elif ap == 'AM' and hh == 12: hh = 0
            hh += 1
            if hh >= 24: hh -= 24
            ap2 = 'AM' if hh < 12 else 'PM'
            hh12 = hh % 12 or 12
            if mm == 0:
                return f"{hh12:02d}:00 {ap2}"
            else:
                return f"{hh12:02d}:{mm:02d} {ap2}"

        def nom_loteria_ticket(lot_id, lot):
            nombres = {
                'zoolo':      'ZOOLOCAS',
                'activo':     'L-ACTIVO',
                'granjita':   'GRANJITA',
                'selva':      'SELVAPLS',
                'rey':        'LOTOREY',
                'inter':      'L-INTER',
                'guacharo':   'GUACHRO',
                'guacharito': 'GUACHRITO',
            }
            return nombres.get(lot_id, lot['nombre'][:8].upper())

        for lot_id, jugs in por_loteria.items():
            lot = get_loteria(lot_id)
            horas_peru, _ = get_horarios(lot_id)
            por_hora = defaultdict(list)
            for j in jugs: por_hora[j['hora']].append(j)

            for hp in horas_peru:
                if hp not in por_hora: continue
                hv = hora_vzla(hp)          # siempre Peru +1h
                hpc = fmt_h(hp)
                hvc = fmt_h(hv)
                nom = nom_loteria_ticket(lot_id, lot)

                # Todas las loterías muestran PERU / VENEZUELA
                lineas.append(f"{nom} {hpc}PERU/{hvc}VEN")

                agrupado = defaultdict(float)
                tipos_map = {}
                for j in por_hora[hp]:
                    agrupado[j['seleccion']] += j['monto']
                    tipos_map[j['seleccion']] = j['tipo']

                def sort_key(k):
                    try: return (0, int(k))
                    except: return (1, k)

                partes_linea = []
                for sel in sorted(agrupado.keys(), key=sort_key):
                    monto_total = agrupado[sel]
                    if tipos_map[sel] == 'animal':
                        n = lot['animales'].get(sel,'')[0:3].upper()
                        partes_linea.append(f"{sel} {n}x{fmt(monto_total)}")
                    else:
                        partes_linea.append(f"{sel[0:3]}x{fmt(monto_total)}")
                lineas.append("  " + "  ".join(partes_linea))

        # ---- Tripletas ----
        trips = [j for j in jugadas if j['tipo']=='tripleta']
        if trips:
            lineas.append("-------------------------------")
            nombres_trip = {
                'zoolo':      'TRPLZOOL',
                'activo':     'TRPLACTI',
                'granjita':   'TRPLGRAJ',
                'selva':      'TRPLSELV',
                'rey':        'TRPLREY',
                'inter':      'TRPLINTE',
                'guacharo':   'TRPLGUAC',
                'guacharito': 'TRPLGRIT',
            }
            fecha_hoy_fmt = ahora_dt.strftime("%d/%m/%Y")
            for t in trips:
                lot_id = t.get('loteria', 'zoolo')
                lot = get_loteria(lot_id)
                horas_peru_t, _ = get_horarios(lot_id)
                nums = t['seleccion'].split(',')
                nom_trip = nombres_trip.get(lot_id, 'TRPL'+lot['nombre'][:4].upper())
                es_zoolo_trip = (lot_id == 'zoolo')

                if es_zoolo_trip:
                    # ZOOLO: muestra hora Peru fija (8AM-6PM)
                    hora_ini_p = fmt_h(HORARIOS_ZOOLO[0])   # 8AM
                    hora_fin_p = fmt_h(HORARIOS_ZOOLO[-1])  # 6PM
                    lineas.append(f"-------{nom_trip}----------")
                    lineas.append(f"DESDE {fecha_hoy_fmt} Sorteo {hora_ini_p} PERU")
                    lineas.append(f"HASTA {fecha_hoy_fmt} Sorteo {hora_fin_p} PERU")
                    lineas.append(f"(11 sorteos: 8AM-6PM PERU)")
                else:
                    # Otras loterías: NO llevan hora, solo fecha DESDE/HASTA
                    # Desde: hoy. Hasta: calculado según 11 sorteos consecutivos
                    hora_inicio = None
                    for hp in horas_peru_t:
                        if puede_vender(hp):
                            hora_inicio = hp
                            break
                    if hora_inicio is None:
                        hora_inicio = horas_peru_t[0]
                    idx_inicio = horas_peru_t.index(hora_inicio) if hora_inicio in horas_peru_t else 0
                    idx_fin_raw = idx_inicio + 10
                    dias_extra  = idx_fin_raw // len(horas_peru_t)
                    fecha_fin_dt  = ahora_dt + timedelta(days=dias_extra)
                    fecha_fin_fmt = fecha_fin_dt.strftime("%d/%m/%Y")
                    lineas.append(f"-------{nom_trip}----------")
                    lineas.append(f"DESDE {fecha_hoy_fmt}")
                    lineas.append(f"HASTA {fecha_fin_fmt}")
                    lineas.append(f"(Valido por 11 sorteos)")

                # Números con abreviatura
                partes = []
                for n in nums:
                    abr = lot['animales'].get(n,'')[0:3].upper()
                    partes.append(f"{n}({abr})")
                lineas.append(f"  TRIPLETA: " + " - ".join(partes) + f" x {fmt(t['monto'])} SL")

        pie = [
            "-------------------------------",
            f"({len(jugadas)} JUG) Total: {fmt(total)}  S/",
            "-------------------------------",
        ]
        if trips:
            hay_zoolo_trip = any(t.get('loteria','zoolo') == 'zoolo' for t in trips)
            if hay_zoolo_trip:
                pie.append("ZOOLO CASINO: Valido 11 sorteos fijos del dia (8AM-6PM)")
            hay_otras_trip = any(t.get('loteria','zoolo') != 'zoolo' for t in trips)
            if hay_otras_trip:
                pie.append("Valido por 11 sorteos")
        pie += [
            "CADUCA EN 3 DIAS",
            "REVISE SU TICKET",
            "¡Buena suerte!"
        ]
        lineas += pie
        texto = "\n".join(lineas)
        url_wa = f"https://wa.me/?text={urllib.parse.quote(texto)}"
        return jsonify({'status':'ok','serial':serial,'ticket_id':ticket_id,'total':total,'url_whatsapp':url_wa})
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ========================= API REPETIR TICKET =========================
@app.route('/api/repetir-ticket', methods=['POST'])
@agencia_required
def repetir_ticket():
    """Carga las jugadas de un ticket existente por serial para re-venderlo."""
    try:
        serial = request.json.get('serial','').strip()
        if not serial: return jsonify({'error':'Ingrese serial'}), 400
        with get_db() as db:
            t = db.execute("SELECT * FROM tickets WHERE serial=?",(serial,)).fetchone()
            if not t: return jsonify({'error':'Ticket no encontrado'})
            # Verificar que pertenece al mismo admin
            if t['admin_id'] != session.get('admin_id'):
                return jsonify({'error':'No autorizado'})
            jugs = db.execute("SELECT * FROM jugadas WHERE ticket_id=?",(t['id'],)).fetchall()
            trips = db.execute("SELECT * FROM tripletas WHERE ticket_id=?",(t['id'],)).fetchall()
        jugadas_out = []
        for j in jugs:
            lot = get_loteria(j['loteria'])
            jugadas_out.append({
                'tipo': j['tipo'],
                'hora': j['hora'],
                'seleccion': j['seleccion'],
                'monto': j['monto'],
                'loteria': j['loteria'],
                'desc': f"{j['seleccion']} {lot['animales'].get(j['seleccion'],'')[:6]}" if j['tipo']=='animal' else j['seleccion']
            })
        for tr in trips:
            lot = get_loteria(tr['loteria'])
            nums = [tr['animal1'], tr['animal2'], tr['animal3']]
            noms = [lot['animales'].get(n,n)[:4].upper() for n in nums]
            jugadas_out.append({
                'tipo': 'tripleta',
                'hora': 'TODO DIA',
                'seleccion': ','.join(nums),
                'monto': tr['monto'],
                'loteria': tr['loteria'],
                'desc': f"🎯 {'-'.join(noms)}"
            })
        return jsonify({'status':'ok','jugadas': jugadas_out, 'serial_original': serial})
    except Exception as e:
        return jsonify({'error':str(e)}), 500


@app.route('/api/mis-tickets', methods=['POST'])
@agencia_required
def mis_tickets():
    try:
        data = request.get_json() or {}
        fi = data.get('fecha_inicio'); ff = data.get('fecha_fin')
        est = data.get('estado','todos')
        dti = datetime.strptime(fi,"%Y-%m-%d") if fi else None
        dtf = datetime.strptime(ff,"%Y-%m-%d").replace(hour=23,minute=59) if ff else None
        with get_db() as db:
            rows = db.execute("SELECT * FROM tickets WHERE agencia_id=? AND anulado=0 ORDER BY id DESC LIMIT 500",(session['user_id'],)).fetchall()
            tickets_out = []
            for t in rows:
                dt = parse_fecha(t['fecha'])
                if not dt: continue
                if dti and dt<dti: continue
                if dtf and dt>dtf: continue
                fecha_str = dt.strftime("%d/%m/%Y")
                jugadas_raw = db.execute("SELECT * FROM jugadas WHERE ticket_id=?",(t['id'],)).fetchall()
                tripletas_raw = db.execute("SELECT * FROM tripletas WHERE ticket_id=?",(t['id'],)).fetchall()
                premio_total = 0
                jugadas_det = []
                for j in jugadas_raw:
                    lot = get_loteria(j['loteria'])
                    res_rows = db.execute("SELECT animal FROM resultados WHERE fecha=? AND loteria=? AND hora=?", 
                                        (fecha_str, j['loteria'], j['hora'])).fetchall()
                    wa = res_rows[0]['animal'] if res_rows else None
                    pj = calcular_premio_jugada(j['tipo'],j['seleccion'],j['monto'],wa,j['loteria']) if wa else 0
                    gano = pj > 0
                    if gano: premio_total+=pj
                    jugadas_det.append({
                        'tipo':j['tipo'],'hora':j['hora'],'seleccion':j['seleccion'],
                        'loteria':j['loteria'],'loteria_nombre':lot['nombre'],'loteria_emoji':lot['emoji'],
                        'nombre':lot['animales'].get(j['seleccion'],j['seleccion']) if j['tipo']=='animal' else j['seleccion'],
                        'monto':j['monto'],'resultado':wa,
                        'resultado_nombre':lot['animales'].get(str(wa),str(wa)) if wa else None,
                        'gano':gano,'premio':round(pj,2)
                    })
                trips_det = []
                for tr in tripletas_raw:
                    lot = get_loteria(tr['loteria'])
                    res_rows = db.execute("SELECT animal FROM resultados WHERE fecha=? AND loteria=?", (fecha_str, tr['loteria'])).fetchall()
                    resultados = [r['animal'] for r in res_rows]
                    nums={tr['animal1'],tr['animal2'],tr['animal3']}
                    salidos=list(dict.fromkeys([a for a in resultados if a in nums]))
                    gano_t=len(salidos)==3
                    pt=tr['monto']*lot['pago_tripleta'] if gano_t else 0
                    if gano_t: premio_total+=pt
                    trips_det.append({
                        'loteria':tr['loteria'],'loteria_nombre':lot['nombre'],'loteria_emoji':lot['emoji'],
                        'animal1':tr['animal1'],'nombre1':lot['animales'].get(tr['animal1'],tr['animal1']),
                        'animal2':tr['animal2'],'nombre2':lot['animales'].get(tr['animal2'],tr['animal2']),
                        'animal3':tr['animal3'],'nombre3':lot['animales'].get(tr['animal3'],tr['animal3']),
                        'monto':tr['monto'],'salieron':salidos,'gano':gano_t,'premio':round(pt,2),'pagado':bool(tr['pagado'])
                    })
                if est=='por_pagar' and (t['pagado'] or premio_total==0): continue
                tickets_out.append({
                    'id':t['id'],'serial':t['serial'],'fecha':t['fecha'],
                    'total':t['total'],'pagado':bool(t['pagado']),
                    'premio_calculado':round(premio_total,2),
                    'jugadas':jugadas_det,'tripletas':trips_det
                })
        tv = sum(t['total'] for t in tickets_out)
        return jsonify({'status':'ok','tickets':tickets_out,'totales':{'cantidad':len(tickets_out),'ventas':round(tv,2)}})
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ========================= API VERIFICAR/PAGAR/ANULAR =========================
@app.route('/api/verificar-ticket', methods=['POST'])
@login_required
def verificar_ticket():
    try:
        serial = request.json.get('serial')
        with get_db() as db:
            t = db.execute("SELECT * FROM tickets WHERE serial=?",(serial,)).fetchone()
            if not t: return jsonify({'error':'Ticket no existe'})
            if session.get('es_super_admin'): pass
            elif session.get('es_admin'):
                if t['admin_id'] != session['user_id']: return jsonify({'error':'No autorizado'})
            else:
                if t['agencia_id']!=session['user_id']: return jsonify({'error':'No autorizado'})
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
            t = db.execute("SELECT * FROM tickets WHERE id=?",(tid,)).fetchone()
            if not t: return jsonify({'error':'Ticket no existe'})
            if session.get('es_super_admin'): pass
            elif session.get('es_admin'):
                if t['admin_id'] != session['user_id']: return jsonify({'error':'No autorizado'})
            else:
                if t['agencia_id']!=session['user_id']: return jsonify({'error':'No autorizado'})
            db.execute("UPDATE tickets SET pagado=1 WHERE id=?",(tid,))
            db.execute("UPDATE tripletas SET pagado=1 WHERE ticket_id=?",(tid,))
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
            t = db.execute("SELECT * FROM tickets WHERE serial=?",(serial,)).fetchone()
            if not t: return jsonify({'error':'Ticket no existe'})
            if session.get('es_super_admin'): pass
            elif session.get('es_admin'):
                if t['admin_id'] != session['user_id']: return jsonify({'error':'No autorizado'})
            else:
                # Taquilla: puede anular si el sorteo aún no ha cerrado (sin límite de 5 min)
                if t['agencia_id']!=session['user_id']: return jsonify({'error':'No autorizado'})
                jugs = db.execute("SELECT hora, loteria FROM jugadas WHERE ticket_id=?",(t['id'],)).fetchall()
                for j in jugs:
                    if not puede_vender(j['hora']):
                        return jsonify({'error':f"No se puede anular: el sorteo de {j['hora']} ya cerró"})
                # Tripletas: solo bloquear si hay resultados publicados para esa lotería hoy
                trips_t = db.execute("SELECT loteria FROM tripletas WHERE ticket_id=?",(t['id'],)).fetchall()
                hoy = ahora_peru().strftime("%d/%m/%Y")
                for tr in trips_t:
                    res_count = db.execute(
                        "SELECT COUNT(*) as c FROM resultados WHERE loteria=? AND fecha=?",
                        (tr['loteria'], hoy)).fetchone()
                    if res_count and res_count['c'] > 0:
                        lot = get_loteria(tr['loteria'])
                        return jsonify({'error':f"No se puede anular: ya hay resultados publicados para {lot['nombre']} hoy"})
            if t['pagado']: return jsonify({'error':'Ya pagado, no se puede anular'})
            db.execute("UPDATE tickets SET anulado=1 WHERE id=?",(t['id'],))
            db.commit()
        log_audit('ANULACION', f"Ticket serial:{serial} anulado")
        return jsonify({'status':'ok','mensaje':'Ticket anulado'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ========================= API CAJA =========================
@app.route('/api/caja')
@agencia_required
def caja_agencia():
    try:
        hoy = ahora_peru().strftime("%d/%m/%Y")
        admin_id = session.get('admin_id')
        agencia_id = session['user_id']
        with get_db() as db:
            tickets = db.execute(
                "SELECT * FROM tickets WHERE agencia_id=? AND admin_id=? AND anulado=0 AND fecha LIKE ?",
                (agencia_id, admin_id, hoy+'%')).fetchall()
            ventas=0; premios_pagados=0; pendientes=0; comision_total=0
            for t in tickets:
                ventas += t['total']
                p = calcular_premio_ticket(t['id'], db)
                if t['pagado']: premios_pagados += p
                elif p > 0: pendientes += 1
                # Calcular comisión por lotería para este ticket
                jugs = db.execute(
                    "SELECT DISTINCT loteria, SUM(monto) as subtotal FROM jugadas WHERE ticket_id=? GROUP BY loteria",
                    (t['id'],)).fetchall()
                trips = db.execute(
                    "SELECT DISTINCT loteria, SUM(monto) as subtotal FROM tripletas WHERE ticket_id=? GROUP BY loteria",
                    (t['id'],)).fetchall()
                ticket_com = 0
                for j in jugs:
                    pct = get_comision_loteria(admin_id, agencia_id, j['loteria'], db)
                    ticket_com += (j['subtotal'] or 0) * pct
                for tr in trips:
                    pct = get_comision_loteria(admin_id, agencia_id, tr['loteria'], db)
                    ticket_com += (tr['subtotal'] or 0) * pct
                # Si no hay jugadas desglosadas, usar comisión general del total
                if not jugs and not trips:
                    ag = db.execute("SELECT comision FROM agencias WHERE id=?", (agencia_id,)).fetchone()
                    ticket_com = t['total'] * (ag['comision'] if ag else 0)
                comision_total += ticket_com
        return jsonify({
            'ventas': round(ventas, 2),
            'premios': round(premios_pagados, 2),
            'comision': round(comision_total, 2),
            'balance': round(ventas - premios_pagados - comision_total, 2),
            'tickets_pendientes': pendientes,
            'total_tickets': len(tickets)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========================= API ADMIN =========================
@app.route('/admin/guardar-resultado', methods=['POST'])
@admin_required
def guardar_resultado():
    try:
        hora = request.form.get('hora','').strip()
        animal = request.form.get('animal','').strip()
        fi = request.form.get('fecha','').strip()
        loteria_id = request.form.get('loteria','zoolo').strip()
        lot = get_loteria(loteria_id)
        if animal not in lot['animales']:
            return jsonify({'error':f'Animal inválido para {lot["nombre"]}'}),400
        if fi:
            try: fecha = datetime.strptime(fi,"%Y-%m-%d").strftime("%d/%m/%Y")
            except: fecha = ahora_peru().strftime("%d/%m/%Y")
        else:
            fecha = ahora_peru().strftime("%d/%m/%Y")
        with get_db() as db:
            db.execute("""INSERT INTO resultados (loteria,fecha,hora,animal) VALUES (?,?,?,?) 
                ON CONFLICT(loteria,fecha,hora) DO UPDATE SET animal=excluded.animal""",
                (loteria_id, fecha, hora, animal))
            db.commit()
        log_audit('RESULTADO', f"Loteria:{loteria_id} Fecha:{fecha} Hora:{hora} Animal:{animal}")
        return jsonify({'status':'ok','mensaje':f'{lot["nombre"]}: {hora} = {animal} ({lot["animales"][animal]})','fecha':fecha})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/crear-agencia', methods=['POST'])
@admin_required
def crear_agencia():
    try:
        u = request.form.get('usuario','').strip().lower()
        p = request.form.get('password','').strip()
        n = request.form.get('nombre','').strip()
        if not u or not p or not n: return jsonify({'error':'Complete todos los campos'}),400
        admin_id = session['user_id']
        with get_db() as db:
            ex = db.execute("SELECT id FROM agencias WHERE usuario=?",(u,)).fetchone()
            if ex: return jsonify({'error':'Usuario ya existe'}),400
            db.execute("INSERT INTO agencias (usuario,password,nombre_agencia,es_admin,es_super_admin,admin_padre_id,comision,activa) VALUES (?,?,?,0,0,?,?,1)",
                      (u,p,n,admin_id,COMISION_AGENCIA))
            db.commit()
        log_audit('CREAR_AGENCIA', f"Agencia {n} creada por admin {admin_id}")
        return jsonify({'status':'ok','mensaje':f'Agencia {n} creada'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/lista-agencias')
@admin_required
def lista_agencias():
    admin_id = session['user_id']
    with get_db() as db:
        rows = db.execute("SELECT id,usuario,nombre_agencia,comision,activa,tope_taquilla FROM agencias WHERE es_admin=0 AND es_super_admin=0 AND admin_padre_id=?", (admin_id,)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/admin/editar-agencia', methods=['POST'])
@admin_required
def editar_agencia():
    try:
        data = request.get_json() or {}
        aid = data.get('id')
        admin_id = session['user_id']
        with get_db() as db:
            if 'password' in data and data['password']:
                db.execute("UPDATE agencias SET password=? WHERE id=? AND admin_padre_id=? AND es_admin=0",(data['password'],aid,admin_id))
            if 'comision' in data:
                db.execute("UPDATE agencias SET comision=? WHERE id=? AND admin_padre_id=? AND es_admin=0",(float(data['comision'])/100,aid,admin_id))
            if 'activa' in data:
                db.execute("UPDATE agencias SET activa=? WHERE id=? AND admin_padre_id=? AND es_admin=0",(1 if data['activa'] else 0,aid,admin_id))
            if 'tope_taquilla' in data:
                db.execute("UPDATE agencias SET tope_taquilla=? WHERE id=? AND admin_padre_id=? AND es_admin=0",(float(data['tope_taquilla']),aid,admin_id))
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
        admin_id = session['user_id']
        with get_db() as db:
            # Verificar que la agencia pertenece a este admin y no es admin
            ag = db.execute(
                "SELECT id, nombre_agencia FROM agencias WHERE id=? AND admin_padre_id=? AND es_admin=0 AND es_super_admin=0",
                (aid, admin_id)
            ).fetchone()
            if not ag:
                return jsonify({'error': 'Agencia no encontrada o no autorizado'}), 403
            # Verificar que no tenga tickets activos sin anular
            tickets_activos = db.execute(
                "SELECT COUNT(*) as c FROM tickets WHERE agencia_id=? AND anulado=0", (aid,)
            ).fetchone()
            if tickets_activos and tickets_activos['c'] > 0:
                return jsonify({'error': f'No se puede eliminar: tiene {tickets_activos["c"]} ticket(s) activo(s). Anúlalos primero.'}), 400
            nombre = ag['nombre_agencia']
            db.execute("DELETE FROM agencias WHERE id=?", (aid,))
            db.commit()
        log_audit('ELIMINAR_AGENCIA', f"Agencia '{nombre}' (id:{aid}) eliminada")
        return jsonify({'status': 'ok', 'mensaje': f'Agencia "{nombre}" eliminada'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
@app.route('/admin/topes', methods=['GET'])
@admin_required
def get_topes():
    try:
        hora = request.args.get('hora', HORARIOS_PERU_BASE[0])
        loteria_id = request.args.get('loteria', 'zoolo')
        hoy = ahora_peru().strftime("%d/%m/%Y")
        admin_id = session['user_id']
        lot = get_loteria(loteria_id)
        with get_db() as db:
            topes_rows = db.execute(
                "SELECT numero, monto_tope FROM topes WHERE admin_id=? AND hora=? ORDER BY CAST(numero AS INTEGER) ASC",
                (admin_id, hora)
            ).fetchall()
            jugadas_rows = db.execute("""
                SELECT jg.seleccion, COALESCE(SUM(jg.monto),0) as apostado
                FROM jugadas jg
                JOIN tickets tk ON jg.ticket_id=tk.id
                WHERE tk.admin_id=? AND jg.hora=? AND jg.loteria=? AND jg.tipo='animal' AND tk.anulado=0 AND tk.fecha LIKE ?
                GROUP BY jg.seleccion
                ORDER BY CAST(jg.seleccion AS INTEGER) ASC
            """, (admin_id, hora, loteria_id, hoy+'%')).fetchall()
        apostado_map = {r['seleccion']: r['apostado'] for r in jugadas_rows}
        topes_map = {r['numero']: r['monto_tope'] for r in topes_rows}
        numeros = sorted(set(list(topes_map.keys()) + list(apostado_map.keys())), key=lambda x: int(x) if x.isdigit() else -1)
        result = []
        for num in numeros:
            result.append({
                'numero': num,
                'nombre': lot['animales'].get(num, '?'),
                'tope': topes_map.get(num, 0),
                'apostado': round(apostado_map.get(num, 0), 2),
                'disponible': round(max(0, topes_map.get(num, 0) - apostado_map.get(num, 0)), 2) if num in topes_map else None,
                'libre': num not in topes_map
            })
        return jsonify({'status':'ok','topes':result,'hora':hora})
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
        loteria_id = data.get('loteria', 'zoolo')
        lot = get_loteria(loteria_id)
        admin_id = session['user_id']
        horas_peru, _ = get_horarios(loteria_id)
        if hora not in horas_peru:
            return jsonify({'error':'Hora inválida'}),400
        if numero not in lot['animales']:
            return jsonify({'error':'Número inválido'}),400
        with get_db() as db:
            if monto <= 0:
                db.execute("DELETE FROM topes WHERE admin_id=? AND hora=? AND numero=?", (admin_id, hora, numero))
                log_audit('TOPE_LIBRE', f"Hora:{hora} Num:{numero} puesto en libre")
            else:
                db.execute("""
                    INSERT INTO topes (admin_id, hora, numero, monto_tope) VALUES (?,?,?,?)
                    ON CONFLICT(admin_id, hora, numero) DO UPDATE SET monto_tope=excluded.monto_tope
                """, (admin_id, hora, numero, monto))
                log_audit('TOPE_SET', f"Hora:{hora} Num:{numero}-{lot['animales'][numero]} Tope:S/{monto}")
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
        admin_id = session['user_id']
        with get_db() as db:
            db.execute("DELETE FROM topes WHERE admin_id=? AND hora=?", (admin_id, hora))
            db.commit()
        log_audit('TOPES_LIMPIAR', f"Todos los topes de {hora} eliminados")
        return jsonify({'status':'ok','mensaje':f'Topes de {hora} eliminados'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ========================= API TOPES GLOBAL POR LOTERÍA =========================
@app.route('/admin/topes-global/guardar-masivo', methods=['POST'])
@admin_required
def guardar_topes_global_masivo():
    """Guarda topes globales (suma de todas las agencias) por lotería/hora/número."""
    try:
        data        = request.get_json() or {}
        admin_id    = session['user_id']
        loteria_ids = data.get('loteria_ids', [])
        horas       = data.get('horas', [])
        numeros     = data.get('numeros', [])
        monto_tope  = float(data.get('monto_tope', 0))
        count = 0
        with get_db() as db:
            for lot_id in loteria_ids:
                lot = get_loteria(lot_id)
                horas_validas, _ = get_horarios(lot_id)
                nums_validos = list(lot['animales'].keys()) if not numeros else [n for n in numeros if n in lot['animales']]
                if not nums_validos:
                    nums_validos = list(lot['animales'].keys())
                for hora in horas:
                    if hora not in horas_validas:
                        continue
                    for num in nums_validos:
                        if monto_tope <= 0:
                            db.execute("""DELETE FROM topes_global
                                WHERE admin_id=? AND loteria=? AND hora=? AND numero=?""",
                                (admin_id, lot_id, hora, str(num)))
                        else:
                            db.execute("""INSERT INTO topes_global
                                (admin_id, loteria, hora, numero, monto_tope) VALUES (?,?,?,?,?)
                                ON CONFLICT(admin_id, loteria, hora, numero)
                                DO UPDATE SET monto_tope=excluded.monto_tope""",
                                (admin_id, lot_id, hora, str(num), monto_tope))
                        count += 1
            db.commit()
        log_audit('TOPE_GLOBAL', f"{count} topes globales {'guardados' if monto_tope>0 else 'eliminados'}")
        return jsonify({'status':'ok', 'mensaje': f'{count} tope(s) global(es) aplicado(s)'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/topes-global/lista')
@admin_required
def lista_topes_global():
    try:
        admin_id   = session['user_id']
        loteria_id = request.args.get('loteria', '')
        hora       = request.args.get('hora', '')
        hoy        = ahora_peru().strftime("%d/%m/%Y")
        with get_db() as db:
            q = "SELECT * FROM topes_global WHERE admin_id=?"
            params = [admin_id]
            if loteria_id: q += " AND loteria=?"; params.append(loteria_id)
            if hora:       q += " AND hora=?";    params.append(hora)
            q += " ORDER BY loteria, hora, CAST(numero AS INTEGER)"
            rows = db.execute(q, params).fetchall()
            result = []
            for r in rows:
                lot = get_loteria(r['loteria'])
                vendido_row = db.execute("""
                    SELECT COALESCE(SUM(j.monto),0) as total FROM jugadas j
                    JOIN tickets t ON j.ticket_id=t.id
                    WHERE t.admin_id=? AND j.loteria=? AND j.seleccion=? AND j.hora=?
                    AND j.tipo='animal' AND t.anulado=0 AND t.fecha LIKE ?
                """, (admin_id, r['loteria'], r['numero'], r['hora'], hoy+'%')).fetchone()
                vendido = vendido_row['total'] or 0
                tope    = r['monto_tope']
                result.append({
                    'id': r['id'],
                    'loteria': r['loteria'],
                    'loteria_nombre': lot['nombre'],
                    'loteria_emoji': lot['emoji'],
                    'loteria_color': lot['color'],
                    'hora': r['hora'],
                    'numero': r['numero'],
                    'animal': lot['animales'].get(r['numero'], '?'),
                    'monto_tope': tope,
                    'vendido_hoy': round(vendido, 2),
                    'disponible': round(max(0, tope - vendido), 2),
                    'pct_usado': round(vendido/tope*100, 1) if tope > 0 else 0
                })
        return jsonify({'status':'ok', 'topes': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/topes-global/eliminar', methods=['POST'])
@admin_required
def eliminar_tope_global():
    try:
        data     = request.get_json() or {}
        admin_id = session['user_id']
        tid      = data.get('id')
        with get_db() as db:
            db.execute("DELETE FROM topes_global WHERE id=? AND admin_id=?", (tid, admin_id))
            db.commit()
        return jsonify({'status':'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========================= API TOPES POR AGENCIA =========================
@app.route('/admin/topes-agencia/guardar-masivo', methods=['POST'])
@admin_required
def guardar_topes_agencia_masivo():
    """Guarda topes para múltiples agencias, loterías, horas y números a la vez."""
    try:
        data = request.get_json() or {}
        admin_id = session['user_id']
        agencia_ids = data.get('agencia_ids', [])
        loteria_ids  = data.get('loteria_ids', [])
        horas        = data.get('horas', [])
        numeros      = data.get('numeros', [])   # lista de strings
        monto_tope   = float(data.get('monto_tope', 0))
        porcentaje   = float(data.get('porcentaje', 0))

        if not agencia_ids or not loteria_ids or not horas:
            return jsonify({'error': 'Seleccione agencia(s), lotería(s) y hora(s)'}), 400

        # Verificar que las agencias pertenezcan a este admin
        with get_db() as db:
            ags_validas = {r['id'] for r in db.execute(
                "SELECT id FROM agencias WHERE admin_padre_id=? AND es_admin=0",
                (admin_id,)).fetchall()}
            count = 0
            for ag_id in agencia_ids:
                if int(ag_id) not in ags_validas:
                    continue
                for lot_id in loteria_ids:
                    lot = get_loteria(lot_id)
                    horas_validas, _ = get_horarios(lot_id)
                    nums_validos = list(lot['animales'].keys()) if not numeros else [n for n in numeros if n in lot['animales']]
                    if not nums_validos:
                        nums_validos = list(lot['animales'].keys())
                    for hora in horas:
                        if hora not in horas_validas:
                            continue
                        for num in nums_validos:
                            if monto_tope <= 0 and porcentaje <= 0:
                                db.execute("""DELETE FROM topes_agencia 
                                    WHERE admin_id=? AND agencia_id=? AND loteria=? AND hora=? AND numero=?""",
                                    (admin_id, ag_id, lot_id, hora, str(num)))
                            else:
                                db.execute("""INSERT INTO topes_agencia 
                                    (admin_id, agencia_id, loteria, hora, numero, monto_tope, porcentaje)
                                    VALUES (?,?,?,?,?,?,?)
                                    ON CONFLICT(admin_id, agencia_id, loteria, hora, numero)
                                    DO UPDATE SET monto_tope=excluded.monto_tope, porcentaje=excluded.porcentaje""",
                                    (admin_id, ag_id, lot_id, hora, str(num), monto_tope, porcentaje))
                            count += 1
            db.commit()
        log_audit('TOPES_AGENCIA_MASIVO', f"Guardados {count} topes para {len(agencia_ids)} agencias")
        return jsonify({'status':'ok', 'mensaje': f'{count} tope(s) aplicado(s)'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/topes-agencia/lista', methods=['GET'])
@admin_required
def lista_topes_agencia():
    """Lista los topes configurados para una agencia."""
    try:
        admin_id  = session['user_id']
        agencia_id = request.args.get('agencia_id')
        loteria_id = request.args.get('loteria', '')
        hoy        = ahora_peru().strftime("%d/%m/%Y")
        with get_db() as db:
            q = """SELECT ta.*, ag.nombre_agencia
                   FROM topes_agencia ta
                   JOIN agencias ag ON ta.agencia_id = ag.id
                   WHERE ta.admin_id=?"""
            params = [admin_id]
            if agencia_id:
                q += " AND ta.agencia_id=?"; params.append(agencia_id)
            if loteria_id:
                q += " AND ta.loteria=?"; params.append(loteria_id)
            q += " ORDER BY ag.nombre_agencia, ta.loteria, ta.hora, CAST(ta.numero AS INTEGER)"
            rows = db.execute(q, params).fetchall()
            # Calcular apostado hoy por agencia/lot/hora/num
            apostados = {}
            for r in rows:
                key = (r['agencia_id'], r['loteria'], r['hora'], r['numero'])
                if key not in apostados:
                    res = db.execute("""
                        SELECT COALESCE(SUM(j.monto),0) as total FROM jugadas j
                        JOIN tickets t ON j.ticket_id=t.id
                        WHERE t.agencia_id=? AND j.loteria=? AND j.hora=? AND j.seleccion=?
                        AND j.tipo='animal' AND t.anulado=0 AND t.fecha LIKE ?
                    """, (r['agencia_id'], r['loteria'], r['hora'], r['numero'], hoy+'%')).fetchone()
                    apostados[key] = res['total'] if res else 0
        result = []
        for r in rows:
            key = (r['agencia_id'], r['loteria'], r['hora'], r['numero'])
            lot = get_loteria(r['loteria'])
            apostado = apostados.get(key, 0)
            tope = r['monto_tope']
            result.append({
                'id': r['id'],
                'agencia_id': r['agencia_id'],
                'agencia_nombre': r['nombre_agencia'],
                'loteria': r['loteria'],
                'loteria_nombre': lot['nombre'],
                'hora': r['hora'],
                'numero': r['numero'],
                'animal': lot['animales'].get(r['numero'], '?'),
                'monto_tope': tope,
                'porcentaje': r['porcentaje'],
                'apostado': round(apostado, 2),
                'disponible': round(max(0, tope - apostado), 2) if tope > 0 else None
            })
        return jsonify({'status':'ok', 'topes': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/topes-agencia/eliminar', methods=['POST'])
@admin_required
def eliminar_tope_agencia():
    try:
        data = request.get_json() or {}
        admin_id = session['user_id']
        tope_id  = data.get('id')
        with get_db() as db:
            db.execute("DELETE FROM topes_agencia WHERE id=? AND admin_id=?", (tope_id, admin_id))
            db.commit()
        return jsonify({'status':'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/topes-agencia/limpiar-agencia', methods=['POST'])
@admin_required
def limpiar_topes_agencia():
    """Elimina todos los topes de una agencia (o con filtros opcionales)."""
    try:
        data      = request.get_json() or {}
        admin_id  = session['user_id']
        agencia_id= data.get('agencia_id')
        loteria   = data.get('loteria','')
        hora      = data.get('hora','')
        with get_db() as db:
            q = "DELETE FROM topes_agencia WHERE admin_id=?"
            params = [admin_id]
            if agencia_id: q += " AND agencia_id=?"; params.append(agencia_id)
            if loteria:    q += " AND loteria=?";    params.append(loteria)
            if hora:       q += " AND hora=?";       params.append(hora)
            db.execute(q, params)
            db.commit()
        return jsonify({'status':'ok', 'mensaje':'Topes eliminados'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========================= API COMISIONES POR LOTERÍA =========================
@app.route('/admin/comisiones-loteria/guardar', methods=['POST'])
@admin_required
def guardar_comisiones_loteria():
    """Guarda % de comisión por lotería para una o varias agencias."""
    try:
        data = request.get_json() or {}
        admin_id = session['user_id']
        agencia_ids = data.get('agencia_ids', [])
        comisiones  = data.get('comisiones', {})
        if not agencia_ids or not comisiones:
            return jsonify({'error': 'Faltan agencias o comisiones'}), 400
        with get_db() as db:
            ags_validas = {r['id'] for r in db.execute(
                "SELECT id FROM agencias WHERE admin_padre_id=? AND es_admin=0", (admin_id,)).fetchall()}
            count = 0
            for ag_id in agencia_ids:
                if int(ag_id) not in ags_validas:
                    continue
                for lot_id, pct in comisiones.items():
                    pct_val = float(pct)
                    if pct_val < 0:
                        continue
                    db.execute("""
                        INSERT INTO comisiones_loteria (admin_id, agencia_id, loteria, comision)
                        VALUES (?,?,?,?)
                        ON CONFLICT(admin_id, agencia_id, loteria)
                        DO UPDATE SET comision=excluded.comision
                    """, (admin_id, int(ag_id), lot_id, pct_val))
                    count += 1
            db.commit()
        log_audit('COMISION_LOTERIA', f"{count} comisiones por lotería guardadas")
        return jsonify({'status': 'ok', 'mensaje': f'{count} comisión(es) guardada(s)'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/comisiones-loteria/lista')
@admin_required
def lista_comisiones_loteria():
    try:
        admin_id   = session['user_id']
        agencia_id = request.args.get('agencia_id')
        with get_db() as db:
            ags = db.execute(
                "SELECT id, nombre_agencia, comision FROM agencias WHERE admin_padre_id=? AND es_admin=0",
                (admin_id,)).fetchall()
            q = """SELECT cl.*, ag.nombre_agencia, ag.comision as com_general
                   FROM comisiones_loteria cl
                   JOIN agencias ag ON cl.agencia_id=ag.id
                   WHERE cl.admin_id=?"""
            params = [admin_id]
            if agencia_id:
                q += " AND cl.agencia_id=?"; params.append(agencia_id)
            q += " ORDER BY ag.nombre_agencia, cl.loteria"
            rows = db.execute(q, params).fetchall()
        result = []
        for r in rows:
            lot = get_loteria(r['loteria'])
            result.append({
                'id': r['id'],
                'agencia_id': r['agencia_id'],
                'agencia_nombre': r['nombre_agencia'],
                'com_general': round(r['com_general']*100, 2),
                'loteria': r['loteria'],
                'loteria_nombre': lot['nombre'],
                'loteria_emoji': lot['emoji'],
                'comision': round(r['comision']*100, 2)
            })
        ags_list = [{'id': a['id'], 'nombre': a['nombre_agencia'],
                     'com_general': round(a['comision']*100, 2)} for a in ags]
        return jsonify({'status': 'ok', 'comisiones': result, 'agencias': ags_list})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/comisiones-loteria/eliminar', methods=['POST'])
@admin_required
def eliminar_comision_loteria():
    try:
        data     = request.get_json() or {}
        admin_id = session['user_id']
        cid      = data.get('id')
        with get_db() as db:
            db.execute("DELETE FROM comisiones_loteria WHERE id=? AND admin_id=?", (cid, admin_id))
            db.commit()
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========================= RIESGO MEJORADO =========================
@app.route('/admin/riesgo')
@admin_required
def riesgo():
    try:
        hoy = ahora_peru().strftime("%d/%m/%Y")
        now = ahora_peru()
        am  = now.hour*60+now.minute
        admin_id = session['user_id']
        loteria_id = request.args.get('loteria', 'zoolo')
        lot = get_loteria(loteria_id)
        horas_peru, _ = get_horarios(loteria_id)

        sorteo = None
        for h in horas_peru:
            m = hora_a_min(h)
            if am >= m-MINUTOS_BLOQUEO and am < m+60:
                sorteo = h; break
        if not sorteo:
            for h in horas_peru:
                if (hora_a_min(h)-am) > MINUTOS_BLOQUEO:
                    sorteo = h; break
        if not sorteo:
            sorteo = horas_peru[-1]

        with get_db() as db:
            agencias_hora = db.execute("""
                SELECT DISTINCT ag.id, ag.nombre_agencia, ag.usuario
                FROM agencias ag
                JOIN tickets tk ON ag.id=tk.agencia_id
                JOIN jugadas jg ON tk.id=jg.ticket_id
                WHERE tk.admin_id=? AND jg.hora=? AND jg.loteria=? AND tk.anulado=0 AND tk.fecha LIKE ?
                ORDER BY ag.nombre_agencia
            """, (admin_id, sorteo, loteria_id, hoy+'%')).fetchall()
            jugadas_rows = db.execute("""
                SELECT jg.seleccion, COALESCE(SUM(jg.monto),0) as apostado
                FROM jugadas jg
                JOIN tickets tk ON jg.ticket_id=tk.id
                WHERE tk.admin_id=? AND jg.hora=? AND jg.loteria=? AND jg.tipo='animal' AND tk.anulado=0 AND tk.fecha LIKE ?
                GROUP BY jg.seleccion
                ORDER BY CAST(jg.seleccion AS INTEGER) ASC
            """, (admin_id, sorteo, loteria_id, hoy+'%')).fetchall()
            topes_rows = db.execute("SELECT numero, monto_tope FROM topes WHERE admin_id=? AND hora=?", (admin_id, sorteo)).fetchall()
            topes_map = {r['numero']: r['monto_tope'] for r in topes_rows}

        total = sum(r['apostado'] for r in jugadas_rows)
        riesgo_d = {}
        for r in jugadas_rows:
            sel = r['seleccion']
            monto = r['apostado']
            if lot['animal_especial'] and sel == lot['animal_especial']:
                mult = lot['pago_especial']
            else:
                mult = lot['pago_normal']
            riesgo_d[sel] = {
                'nombre': lot['animales'].get(sel, sel),
                'apostado': round(monto, 2),
                'pagaria': round(monto*mult, 2),
                'es_especial': lot['animal_especial'] == sel,
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
            'loteria': loteria_id
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
        loteria_id = data.get('loteria', 'zoolo')
        if not agencia_id or not hora:
            return jsonify({'error':'Parámetros requeridos'}),400
        hoy = ahora_peru().strftime("%d/%m/%Y")
        admin_id = session['user_id']
        lot = get_loteria(loteria_id)
        with get_db() as db:
            jugadas = db.execute("""
                SELECT jg.seleccion, jg.tipo, COALESCE(SUM(jg.monto),0) as apostado, COUNT(*) as cnt
                FROM jugadas jg
                JOIN tickets tk ON jg.ticket_id=tk.id
                WHERE tk.agencia_id=? AND tk.admin_id=? AND jg.hora=? AND jg.loteria=? AND tk.anulado=0 AND tk.fecha LIKE ?
                GROUP BY jg.seleccion, jg.tipo
                ORDER BY CAST(jg.seleccion AS INTEGER) ASC
            """, (agencia_id, admin_id, hora, loteria_id, hoy+'%')).fetchall()
            ag = db.execute("SELECT nombre_agencia FROM agencias WHERE id=?", (agencia_id,)).fetchone()
        result = []
        for j in jugadas:
            if lot['animal_especial'] and j['seleccion'] == lot['animal_especial']:
                mult = lot['pago_especial']
            else:
                mult = lot['pago_normal']
            nombre = lot['animales'].get(j['seleccion'], j['seleccion']) if j['tipo']=='animal' else j['seleccion']
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

# ========================= TRIPLETAS HOY =========================
@app.route('/admin/tripletas-hoy')
@admin_required
def tripletas_hoy():
    try:
        hoy = ahora_peru().strftime("%d/%m/%Y")
        admin_id = session['user_id']
        with get_db() as db:
            trips = db.execute("""
                SELECT tr.*, tk.serial, tk.agencia_id
                FROM tripletas tr
                JOIN tickets tk ON tr.ticket_id=tk.id
                WHERE tk.admin_id=? AND tr.fecha=?
            """, (admin_id, hoy)).fetchall()
            ags = {ag['id']:ag['nombre_agencia'] for ag in db.execute("SELECT id,nombre_agencia FROM agencias").fetchall()}
        out = []; ganadoras = 0
        for tr in trips:
            lot = get_loteria(tr['loteria'])
            with get_db() as db2:
                res_rows = db2.execute("SELECT animal FROM resultados WHERE fecha=? AND loteria=?", (hoy, tr['loteria'])).fetchall()
            resultados = [r['animal'] for r in res_rows]
            nums = {tr['animal1'], tr['animal2'], tr['animal3']}
            salidos = list(dict.fromkeys([a for a in resultados if a in nums]))
            gano = len(salidos) == 3
            if gano: ganadoras += 1
            out.append({
                'id': tr['id'], 'serial': tr['serial'],
                'agencia': ags.get(tr['agencia_id'], '?'),
                'loteria': tr['loteria'], 'loteria_nombre': lot['nombre'],
                'animal1': tr['animal1'], 'animal2': tr['animal2'], 'animal3': tr['animal3'],
                'nombres': [lot['animales'].get(tr['animal1'],''), lot['animales'].get(tr['animal2'],''), lot['animales'].get(tr['animal3'],'')],
                'monto': tr['monto'],
                'premio': tr['monto'] * lot['pago_tripleta'] if gano else 0,
                'gano': gano, 'salieron': salidos, 'pagado': bool(tr['pagado'])
            })
        return jsonify({'tripletas':out,'total':len(out),'ganadoras':ganadoras,'total_premios':sum(x['premio'] for x in out)})
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ========================= AUDIT LOGS =========================
@app.route('/admin/audit-logs', methods=['POST'])
@admin_required
def get_audit_logs():
    try:
        data = request.get_json() or {}
        fi = data.get('fecha_inicio')
        ff = data.get('fecha_fin')
        filtro = data.get('filtro', '')
        limit = int(data.get('limit', 200))
        admin_id = session['user_id']
        # Obtener IDs de agencias de este admin
        with get_db() as db:
            ag_ids = [r['id'] for r in db.execute("SELECT id FROM agencias WHERE admin_padre_id=? OR id=?", (admin_id, admin_id)).fetchall()]
            rows = db.execute("""
                SELECT al.*, ag.nombre_agencia
                FROM audit_logs al
                LEFT JOIN agencias ag ON al.agencia_id=ag.id
                WHERE al.agencia_id IN ({})
                ORDER BY al.id DESC LIMIT ?
            """.format(','.join('?'*len(ag_ids))), ag_ids + [limit]).fetchall() if ag_ids else []
        result = []
        for r in rows:
            dt_str = r['creado']
            if fi and dt_str[:10] < fi: continue
            if ff and dt_str[:10] > ff: continue
            if filtro and filtro.lower() not in (r['accion']+r['usuario']+str(r['detalle'] or '')).lower(): continue
            result.append({
                'id': r['id'], 'fecha': r['creado'],
                'agencia': r['nombre_agencia'] or r['usuario'] or '?',
                'accion': r['accion'], 'detalle': r['detalle'] or '', 'ip': r['ip'] or ''
            })
        return jsonify({'status':'ok','logs':result,'total':len(result)})
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ========================= REPORTE POR AGENCIA / HORAS =========================
@app.route('/admin/reporte-agencia-horas', methods=['POST'])
@admin_required
def reporte_agencia_horas():
    try:
        data = request.get_json() or {}
        agencia_id = data.get('agencia_id')
        fi = data.get('fecha_inicio')
        ff = data.get('fecha_fin')
        loteria_id = data.get('loteria', 'zoolo')
        if not agencia_id or not fi or not ff:
            return jsonify({'error':'Parámetros requeridos'}),400
        dti = datetime.strptime(fi, "%Y-%m-%d")
        dtf = datetime.strptime(ff, "%Y-%m-%d").replace(hour=23, minute=59)
        horas_peru, _ = get_horarios(loteria_id)
        lot = get_loteria(loteria_id)
        admin_id = session['user_id']
        with get_db() as db:
            ag = db.execute("SELECT nombre_agencia, usuario FROM agencias WHERE id=? AND admin_padre_id=?", (agencia_id, admin_id)).fetchone()
            jugadas_rows = db.execute("""
                SELECT jg.hora, jg.seleccion, jg.tipo, jg.monto, tk.fecha, tk.serial
                FROM jugadas jg
                JOIN tickets tk ON jg.ticket_id=tk.id
                WHERE tk.agencia_id=? AND tk.admin_id=? AND jg.loteria=? AND tk.anulado=0
                ORDER BY tk.fecha DESC
            """, (agencia_id, admin_id, loteria_id)).fetchall()
        por_hora = {}
        for j in jugadas_rows:
            dt = parse_fecha(j['fecha'])
            if not dt or dt<dti or dt>dtf: continue
            h = j['hora']
            if h not in por_hora:
                por_hora[h] = {'hora': h, 'total': 0, 'jugadas': [], 'conteo': 0}
            nombre = lot['animales'].get(j['seleccion'], j['seleccion']) if j['tipo']=='animal' else j['seleccion']
            por_hora[h]['total'] = round(por_hora[h]['total'] + j['monto'], 2)
            por_hora[h]['conteo'] += 1
            found = next((x for x in por_hora[h]['jugadas'] if x['seleccion']==j['seleccion'] and x['tipo']==j['tipo']), None)
            if found:
                found['apostado'] = round(found['apostado'] + j['monto'], 2); found['cnt'] += 1
            else:
                por_hora[h]['jugadas'].append({'seleccion':j['seleccion'],'nombre':nombre,'tipo':j['tipo'],'apostado':round(j['monto'],2),'cnt':1})
        resumen = []
        for h in horas_peru:
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

# ========================= REPORTE AGENCIAS RANGO =========================
@app.route('/admin/reporte-agencias-rango', methods=['POST'])
@admin_required
def reporte_agencias_rango():
    try:
        data = request.get_json()
        fi = data.get('fecha_inicio'); ff = data.get('fecha_fin')
        if not fi or not ff: return jsonify({'error':'Fechas requeridas'}),400
        dti = datetime.strptime(fi,"%Y-%m-%d")
        dtf = datetime.strptime(ff,"%Y-%m-%d").replace(hour=23,minute=59)
        admin_id = session['user_id']
        with get_db() as db:
            ags = db.execute("SELECT * FROM agencias WHERE admin_padre_id=? AND es_admin=0 AND es_super_admin=0", (admin_id,)).fetchall()
            all_t = db.execute("SELECT * FROM tickets WHERE admin_id=? AND anulado=0 ORDER BY id DESC LIMIT 50000", (admin_id,)).fetchall()
        stats = {ag['id']:{'nombre':ag['nombre_agencia'],'usuario':ag['usuario'],'tickets':0,'ventas':0,'premios_teoricos':0,'comision_pct':ag['comision']} for ag in ags}
        for t in all_t:
            dt = parse_fecha(t['fecha'])
            if not dt or dt<dti or dt>dtf: continue
            aid = t['agencia_id']
            if aid not in stats: continue
            stats[aid]['tickets'] += 1; stats[aid]['ventas'] += t['total']
            with get_db() as db2: p = calcular_premio_ticket(t['id'],db2)
            stats[aid]['premios_teoricos'] += p
        out = []
        for s in stats.values():
            if s['tickets']==0: continue
            com = s['ventas']*s['comision_pct']
            s['comision'] = round(com,2); s['balance'] = round(s['ventas']-s['premios_teoricos']-com,2)
            s['ventas'] = round(s['ventas'],2); s['premios_teoricos'] = round(s['premios_teoricos'],2)
            out.append(s)
        out.sort(key=lambda x:x['ventas'],reverse=True)
        tv = sum(x['ventas'] for x in out)
        if tv>0:
            for x in out: x['porcentaje_ventas'] = round(x['ventas']/tv*100,1)
        total = {'tickets':sum(x['tickets'] for x in out),'ventas':round(tv,2),'premios':round(sum(x['premios_teoricos'] for x in out),2),'comision':round(sum(x['comision'] for x in out),2),'balance':round(sum(x['balance'] for x in out),2)}
        return jsonify({'agencias':out,'total':total,'periodo':{'inicio':fi,'fin':ff}})
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ========================= ESTADÍSTICAS RANGO =========================
@app.route('/admin/estadisticas-rango', methods=['POST'])
@admin_required
def estadisticas_rango():
    try:
        data = request.get_json()
        fi = data.get('fecha_inicio'); ff = data.get('fecha_fin')
        if not fi or not ff: return jsonify({'error':'Fechas requeridas'}),400
        dti = datetime.strptime(fi,"%Y-%m-%d")
        dtf = datetime.strptime(ff,"%Y-%m-%d").replace(hour=23,minute=59)
        admin_id = session['user_id']
        with get_db() as db:
            all_t = db.execute("SELECT * FROM tickets WHERE admin_id=? AND anulado=0 ORDER BY id DESC LIMIT 10000", (admin_id,)).fetchall()
            # Cargar comisión real de cada agencia
            ags_com = {r['id']: r['comision'] for r in db.execute(
                "SELECT id, comision FROM agencias WHERE admin_padre_id=? OR id=?", (admin_id, admin_id)).fetchall()}
        dias = {}; total_v = total_t = 0; total_com = 0
        for t in all_t:
            dt = parse_fecha(t['fecha'])
            if not dt or dt<dti or dt>dtf: continue
            dk = dt.strftime("%d/%m/%Y")
            com_pct = ags_com.get(t['agencia_id'], 0)
            if dk not in dias: dias[dk] = {'ventas':0,'tickets':0,'ids':[],'comision':0}
            dias[dk]['ventas'] += t['total']
            dias[dk]['tickets'] += 1
            dias[dk]['ids'].append(t['id'])
            dias[dk]['comision'] += t['total'] * com_pct
            total_v += t['total']
            total_t += 1
            total_com += t['total'] * com_pct
        resumen = []; total_p2 = 0
        for dk in sorted(dias.keys()):
            d = dias[dk]; prem = 0
            for tid in d['ids']:
                with get_db() as db2: prem += calcular_premio_ticket(tid,db2)
            total_p2 += prem
            cd = d['comision']
            resumen.append({'fecha':dk,'ventas':round(d['ventas'],2),'premios':round(prem,2),'comisiones':round(cd,2),'balance':round(d['ventas']-prem-cd,2),'tickets':d['tickets']})
        return jsonify({'resumen_por_dia':resumen,'totales':{'ventas':round(total_v,2),'premios':round(total_p2,2),'comisiones':round(total_com,2),'balance':round(total_v-total_p2-total_com,2),'tickets':total_t}})
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ========================= EXPORTAR CSV =========================
@app.route('/admin/exportar-csv', methods=['POST'])
@admin_required
def exportar_csv():
    try:
        data = request.get_json()
        fi = data.get('fecha_inicio'); ff = data.get('fecha_fin')
        dti = datetime.strptime(fi,"%Y-%m-%d")
        dtf = datetime.strptime(ff,"%Y-%m-%d").replace(hour=23,minute=59)
        admin_id = session['user_id']
        with get_db() as db:
            ags = db.execute("SELECT * FROM agencias WHERE admin_padre_id=? AND es_admin=0", (admin_id,)).fetchall()
            all_t = db.execute("SELECT * FROM tickets WHERE admin_id=? AND anulado=0 ORDER BY id DESC LIMIT 50000", (admin_id,)).fetchall()
        stats = {ag['id']:{'nombre':ag['nombre_agencia'],'usuario':ag['usuario'],'tickets':0,'ventas':0,'premios':0,'comision_pct':ag['comision']} for ag in ags}
        for t in all_t:
            dt = parse_fecha(t['fecha'])
            if not dt or dt<dti or dt>dtf: continue
            aid = t['agencia_id']
            if aid not in stats: continue
            stats[aid]['tickets'] += 1; stats[aid]['ventas'] += t['total']
            if t['pagado']:
                with get_db() as db2: stats[aid]['premios'] += calcular_premio_ticket(t['id'],db2)
        out = io.StringIO(); w = csv.writer(out)
        w.writerow(['REPORTE MULTI-LOTERÍA v4']); w.writerow([f'Periodo: {fi} al {ff}']); w.writerow([])
        w.writerow(['Agencia','Usuario','Tickets','Ventas','Premios','Comision','Balance'])
        tv = 0
        for s in sorted(stats.values(), key=lambda x:x['ventas'], reverse=True):
            if s['tickets']==0: continue
            com = s['ventas']*s['comision_pct']
            w.writerow([s['nombre'],s['usuario'],s['tickets'],round(s['ventas'],2),round(s['premios'],2),round(com,2),round(s['ventas']-s['premios']-com,2)])
            tv += s['ventas']
        w.writerow([]); w.writerow(['TOTAL','',sum(s['tickets'] for s in stats.values()),round(tv,2),'','',''])
        out.seek(0)
        return Response(out.getvalue(), mimetype='text/csv', headers={'Content-Disposition':f'attachment; filename=reporte_{fi}_{ff}.csv'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ========================= CAJA HISTORICO =========================
@app.route('/api/caja-historico', methods=['POST'])
@agencia_required
def caja_historico():
    try:
        data = request.get_json()
        fi, ff = data.get('fecha_inicio'), data.get('fecha_fin')
        if not fi or not ff: return jsonify({'error':'Fechas requeridas'}),400
        dti = datetime.strptime(fi,"%Y-%m-%d")
        dtf = datetime.strptime(ff,"%Y-%m-%d").replace(hour=23,minute=59)
        admin_id = session.get('admin_id')
        agencia_id = session['user_id']
        with get_db() as db:
            tickets = db.execute(
                "SELECT * FROM tickets WHERE agencia_id=? AND admin_id=? AND anulado=0 ORDER BY id DESC LIMIT 2000",
                (agencia_id, admin_id)).fetchall()
            dias = {}; tv = 0; tp = 0; tc = 0
            for t in tickets:
                dt = parse_fecha(t['fecha'])
                if not dt or dt<dti or dt>dtf: continue
                dk = dt.strftime("%d/%m/%Y")
                if dk not in dias: dias[dk] = {'ventas':0,'tickets':0,'premios':0,'comision':0}
                dias[dk]['ventas'] += t['total']
                dias[dk]['tickets'] += 1
                tv += t['total']
                p = calcular_premio_ticket(t['id'], db)
                if t['pagado']:
                    dias[dk]['premios'] += p; tp += p
                # Comisión por lotería
                jugs = db.execute(
                    "SELECT loteria, SUM(monto) as sub FROM jugadas WHERE ticket_id=? GROUP BY loteria",
                    (t['id'],)).fetchall()
                trips = db.execute(
                    "SELECT loteria, SUM(monto) as sub FROM tripletas WHERE ticket_id=? GROUP BY loteria",
                    (t['id'],)).fetchall()
                ticket_com = 0
                for j in jugs:
                    pct = get_comision_loteria(admin_id, agencia_id, j['loteria'], db)
                    ticket_com += (j['sub'] or 0) * pct
                for tr in trips:
                    pct = get_comision_loteria(admin_id, agencia_id, tr['loteria'], db)
                    ticket_com += (tr['sub'] or 0) * pct
                if not jugs and not trips:
                    ag = db.execute("SELECT comision FROM agencias WHERE id=?", (agencia_id,)).fetchone()
                    ticket_com = t['total'] * (ag['comision'] if ag else 0)
                dias[dk]['comision'] += ticket_com
                tc += ticket_com
        resumen = []
        for dk in sorted(dias.keys()):
            d = dias[dk]
            resumen.append({'fecha':dk,'tickets':d['tickets'],'ventas':round(d['ventas'],2),
                           'premios':round(d['premios'],2),'comision':round(d['comision'],2),
                           'balance':round(d['ventas']-d['premios']-d['comision'],2)})
        return jsonify({'resumen_por_dia':resumen,'totales':{'ventas':round(tv,2),'premios':round(tp,2),'comision':round(tc,2),'balance':round(tv-tp-tc,2)}})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/reporte-agencias')
@admin_required
def reporte_agencias():
    try:
        hoy = ahora_peru().strftime("%d/%m/%Y")
        admin_id = session['user_id']
        with get_db() as db:
            ags = db.execute("SELECT * FROM agencias WHERE admin_padre_id=? AND es_admin=0 AND es_super_admin=0", (admin_id,)).fetchall()
            tickets = db.execute("SELECT * FROM tickets WHERE admin_id=? AND anulado=0 AND fecha LIKE ?", (admin_id, hoy+'%')).fetchall()
        data=[]; tv=tp=tc=0
        for ag in ags:
            mts=[t for t in tickets if t['agencia_id']==ag['id']]
            ventas=sum(t['total'] for t in mts); pp=0
            for t in mts:
                with get_db() as db2: p=calcular_premio_ticket(t['id'],db2)
                if t['pagado']: pp+=p
            com=ventas*ag['comision']
            data.append({'nombre':ag['nombre_agencia'],'usuario':ag['usuario'],
                        'ventas':round(ventas,2),'premios_pagados':round(pp,2),
                        'comision':round(com,2),'balance':round(ventas-pp-com,2),'tickets':len(mts)})
            tv+=ventas; tp+=pp; tc+=com
        return jsonify({'agencias':data,'global':{'ventas':round(tv,2),'pagos':round(tp,2),'comisiones':round(tc,2),'balance':round(tv-tp-tc,2)}})
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ========================= API SUPER ADMIN =========================
@app.route('/super-admin/lista-admins')
@super_admin_required
def lista_admins():
    with get_db() as db:
        rows = db.execute("""
            SELECT a.*, 
                   (SELECT COUNT(*) FROM agencias WHERE admin_padre_id=a.id) as num_agencias,
                   (SELECT COALESCE(SUM(total),0) FROM tickets WHERE admin_id=a.id AND anulado=0) as total_ventas
            FROM agencias a WHERE a.es_admin=1 AND a.es_super_admin=0
        """).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/super-admin/crear-admin', methods=['POST'])
@super_admin_required
def crear_admin():
    try:
        data = request.get_json()
        u = data.get('usuario','').strip().lower()
        p = data.get('password','').strip()
        n = data.get('nombre','').strip()
        if not u or not p or not n: return jsonify({'error':'Complete todos los campos'}),400
        with get_db() as db:
            ex = db.execute("SELECT id FROM agencias WHERE usuario=?",(u,)).fetchone()
            if ex: return jsonify({'error':'Usuario ya existe'}),400
            db.execute("INSERT INTO agencias (usuario,password,nombre_agencia,es_admin,es_super_admin,admin_padre_id,comision,activa) VALUES (?,?,?,1,0,NULL,0,1)", (u,p,n))
            db.commit()
        return jsonify({'status':'ok','mensaje':f'Administrador {n} creado'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/super-admin/reporte-global')
@super_admin_required
def reporte_global():
    try:
        hoy = ahora_peru().strftime("%d/%m/%Y")
        with get_db() as db:
            admins = db.execute("""
                SELECT a.id, a.nombre_agencia, a.usuario,
                       (SELECT COALESCE(SUM(total),0) FROM tickets WHERE admin_id=a.id AND anulado=0 AND fecha LIKE ?) as ventas_hoy,
                       (SELECT COUNT(*) FROM agencias WHERE admin_padre_id=a.id) as num_agencias
                FROM agencias a WHERE a.es_admin=1 AND a.es_super_admin=0
            """, (hoy+'%',)).fetchall()
            global_stats = db.execute("SELECT COALESCE(SUM(total),0) as ventas, COUNT(*) as tickets FROM tickets WHERE anulado=0").fetchone()
        return jsonify({'admins': [dict(a) for a in admins], 'global': dict(global_stats)})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/resultados-hoy')
@login_required
def resultados_hoy():
    try:
        hoy = ahora_peru().strftime("%d/%m/%Y")
        loteria_id = request.args.get('loteria', 'zoolo')
        lot = get_loteria(loteria_id)
        horas_peru, _ = get_horarios(loteria_id)
        with get_db() as db:
            rows = db.execute("SELECT hora,animal FROM resultados WHERE fecha=? AND loteria=?", (hoy, loteria_id)).fetchall()
        rd = {r['hora']:{'animal':r['animal'],'nombre':lot['animales'].get(r['animal'],'?')} for r in rows}
        for h in horas_peru:
            if h not in rd: rd[h]=None
        return jsonify({'status':'ok','fecha':hoy,'resultados':rd,'horarios':horas_peru})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/resultados-fecha', methods=['POST'])
@login_required
def resultados_fecha():
    try:
        data = request.get_json() or {}
        fs = data.get('fecha')
        loteria_id = data.get('loteria', 'zoolo')
        lot = get_loteria(loteria_id)
        horas_peru, _ = get_horarios(loteria_id)
        try: fecha_obj = datetime.strptime(fs, "%Y-%m-%d") if fs else ahora_peru()
        except: fecha_obj = ahora_peru()
        fecha_str = fecha_obj.strftime("%d/%m/%Y")
        with get_db() as db:
            rows = db.execute("SELECT hora,animal FROM resultados WHERE fecha=? AND loteria=?", (fecha_str, loteria_id)).fetchall()
        rd = {r['hora']:{'animal':r['animal'],'nombre':lot['animales'].get(r['animal'],'?')} for r in rows}
        for h in horas_peru:
            if h not in rd: rd[h]=None
        return jsonify({'status':'ok','fecha_consulta':fecha_str,'resultados':rd,'horarios':horas_peru})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/super-admin/toggle-admin', methods=['POST'])
@super_admin_required
def toggle_admin():
    try:
        data = request.get_json()
        admin_id = data.get('admin_id')
        with get_db() as db:
            row = db.execute("SELECT activa FROM agencias WHERE id=? AND es_admin=1 AND es_super_admin=0", (admin_id,)).fetchone()
            if not row: return jsonify({'error':'Admin no encontrado'}),404
            nuevo = 0 if row['activa'] else 1
            db.execute("UPDATE agencias SET activa=? WHERE id=?", (nuevo, admin_id))
            db.commit()
        return jsonify({'status':'ok','activa':nuevo})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/super-admin/cambiar-password', methods=['POST'])
@super_admin_required
def cambiar_password_admin():
    try:
        data = request.get_json()
        admin_id = data.get('admin_id')
        password = data.get('password','').strip()
        if not password: return jsonify({'error':'Password requerido'}),400
        with get_db() as db:
            db.execute("UPDATE agencias SET password=? WHERE id=? AND es_super_admin=0", (password, admin_id))
            db.commit()
        return jsonify({'status':'ok'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ========================= HTML TEMPLATES =========================
LOGIN_HTML = '''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MULTI-LOTERÍA v4.0</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;700&family=Rajdhani:wght@500;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#050a12;min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:'Rajdhani',sans-serif}
.box{background:#0a1020;padding:44px 36px;border-radius:8px;border:1px solid #1e3060;width:100%;max-width:400px;text-align:center;box-shadow:0 0 60px rgba(0,80,200,.1)}
.logo{font-family:'Oswald',sans-serif;font-size:2.2rem;font-weight:700;color:#fff;letter-spacing:3px;margin-bottom:4px}
.logo em{color:#f5a623;font-style:normal}
.sub{color:#3a5080;font-size:.78rem;letter-spacing:3px;margin-bottom:32px}
.fg{margin-bottom:16px;text-align:left}
.fg label{display:block;color:#3a5080;font-size:.75rem;letter-spacing:2px;margin-bottom:6px}
.fg input{width:100%;padding:13px 16px;background:#060e1e;border:1px solid #1e3060;border-radius:4px;color:#7ab0ff;font-size:.95rem;font-family:'Rajdhani',sans-serif}
.fg input:focus{outline:none;border-color:#2060d0}
.btn{width:100%;padding:15px;background:linear-gradient(135deg,#1a4cd0,#0d32a0);color:#fff;border:none;border-radius:4px;font-size:.95rem;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:3px;cursor:pointer;margin-top:8px}
.btn:hover{background:linear-gradient(135deg,#2060e8,#1440c0)}
.err{background:rgba(200,40,40,.1);color:#e05050;padding:11px;border-radius:4px;margin-bottom:16px;border:1px solid rgba(200,40,40,.2);font-size:.85rem}
.lotlist{display:flex;flex-wrap:wrap;justify-content:center;gap:6px;margin-top:20px}
.lotbadge{padding:4px 10px;border-radius:20px;font-size:.7rem;font-family:'Oswald',sans-serif;letter-spacing:1px;border:1px solid #1a3060;color:#4a6090}
</style></head><body>
<div class="box">
<div class="logo">MULTI<em>LOT</em> <span style="font-size:1rem;color:#00b4d8">v4.0</span></div>
<div class="sub">SISTEMA MULTI-ADMINISTRADOR</div>
{% if error %}<div class="err">⚠ {{error}}</div>{% endif %}
<form method="POST">
<div class="fg"><label>USUARIO</label><input type="text" name="usuario" required autofocus autocomplete="off"></div>
<div class="fg"><label>CONTRASEÑA</label><input type="password" name="password" required></div>
<button type="submit" class="btn">INGRESAR</button>
</form>
<div class="lotlist">
  <span class="lotbadge">🦁 ZOOLO</span>
  <span class="lotbadge">🎰 ACTIVO</span>
  <span class="lotbadge">🌾 GRANJA PLUS</span>
  <span class="lotbadge">🦅 GUACHARO</span>
  <span class="lotbadge">🐦 GUACHARITO</span>
  <span class="lotbadge">🌴 SELVA PLUS</span>
  <span class="lotbadge">👑 REY</span>
  <span class="lotbadge">🌐 INTER</span>
</div>
</div></body></html>'''

POS_HTML = r'''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1,user-scalable=no">
<title>{{agencia}} — POS UNIFICADO v4</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;600;700&family=Rajdhani:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#06090f;--panel:#0a0e18;--card:#0d1220;--border:#1a2540;--gold:#f5a623;--teal:#00b4d8;--red:#e53e3e;--green:#22c55e;--purple:#a855f7;--text:#c8d8f0;--text2:#4a6090}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent;user-select:none}
html,body{height:100%;overflow:hidden}
body{background:var(--bg);color:var(--text);font-family:'Rajdhani',sans-serif;font-size:14px;display:flex;flex-direction:column}

.topbar{background:#0d1428;border-bottom:2px solid #f5a623;padding:0 8px;height:36px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;gap:4px}
.brand{font-family:'Oswald',sans-serif;font-size:.9rem;font-weight:700;color:#fff;letter-spacing:1px;white-space:nowrap}
.brand em{color:var(--gold);font-style:normal}
.clock{color:var(--gold);font-family:'Oswald',sans-serif;font-size:.8rem;background:#1a2040;padding:2px 6px;border-radius:3px;border:1px solid #2a3a60;white-space:nowrap}
.tbtn{padding:4px 8px;border:none;background:#1e3060;color:#90c0ff;border-radius:3px;cursor:pointer;font-size:.68rem;font-family:'Oswald',sans-serif;font-weight:700;letter-spacing:1px;white-space:nowrap}
.tbtn:hover{background:#2a4a90;color:#fff}
.tbtn.exit{background:#8b1515;color:#fff}

.layout{display:flex;flex:1;overflow:hidden}
.left-panel{display:flex;flex-direction:column;width:55%;border-right:2px solid var(--border);overflow:hidden}
.right-panel{width:45%;display:flex;flex-direction:column;overflow-y:auto;background:var(--panel);padding:6px}

/* ---- INPUT SECTION ---- */
.input-section{background:#050810;border-bottom:2px solid #1a2540;padding:6px}
.input-row{display:flex;gap:4px;margin-bottom:5px;align-items:flex-end}
.input-group{flex:1;display:flex;flex-direction:column;gap:2px}
.input-group label{color:#4a6090;font-size:.62rem;letter-spacing:1px;font-family:'Oswald',sans-serif}
.numero-input,.monto-input{width:100%;padding:9px 6px;background:#0a1828;border:2px solid #2a4a80;border-radius:4px;color:#fbbf24;font-family:'Oswald',sans-serif;font-size:1rem;font-weight:700;text-align:center}
.numero-input:focus,.monto-input:focus{outline:none;border-color:#00b4d8}
.monto-input{border-color:#d97706}

/* ---- LOTERIA MULTI-SELECT ---- */
.lot-section{padding:5px 6px;border-bottom:1px solid #1a2540;background:#050810}
.lot-section label{color:#4a6090;font-size:.62rem;letter-spacing:1px;font-family:'Oswald',sans-serif;display:block;margin-bottom:3px}
.lot-tags{display:flex;gap:3px;flex-wrap:wrap}
.ltag{padding:4px 7px;border-radius:10px;font-size:.6rem;font-family:'Oswald',sans-serif;letter-spacing:1px;border:2px solid transparent;cursor:pointer;background:#0a0e18;color:#4a6090;transition:all .15s;white-space:nowrap}
.ltag.sel{color:#fff}
.ltag-count{display:inline-block;background:rgba(0,0,0,.4);border-radius:8px;padding:0 4px;font-size:.55rem;margin-left:2px;vertical-align:middle}

/* ---- HORAS SECTION ---- */
.horas-section{padding:6px;border-bottom:1px solid var(--border)}
.horas-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:3px;margin-bottom:4px}
.hbtn{padding:5px 2px;text-align:center;background:#162040;border:2px solid #2a4080;border-radius:3px;cursor:pointer;font-size:.62rem;font-family:'Oswald',sans-serif;color:#a0c0ff;transition:all .15s;line-height:1.2}
.hbtn.sel{background:#006080;border-color:#00c8e8;color:#fff;font-weight:700}
.hbtn.bloq{background:#180a0a;border-color:#4a1010;color:#5a2020;cursor:not-allowed;opacity:.5}
.hbtn .hperu{font-size:.6rem;font-weight:700}
.hbtn .hven{font-size:.5rem;color:#608090}
.horas-btns{display:flex;gap:4px}
.hsel-btn{flex:1;padding:4px;font-size:.6rem;background:#1a3050;border:2px solid #2a5080;color:#80b0e0;border-radius:3px;cursor:pointer;font-family:'Oswald',sans-serif;font-weight:700;text-align:center}
.hsel-btn:hover{background:#006080;border-color:#00b8d8;color:#fff}

/* ---- ANIMALES ---- */
.animales-section{flex:1;overflow-y:auto;padding:6px}
.animales-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:3px}
.acard{border-radius:4px;padding:4px 2px;text-align:center;cursor:pointer;transition:all .12s;border:2px solid transparent;position:relative}
.acard:active{transform:scale(.92)}
.acard.cv{background:#0d5c1e;border-color:#16a34a}
.acard.cv .anum{color:#bbf7d0}.acard.cv .anom{color:#86efac}
.acard.cr{background:#8b1a1a;border-color:#dc2626}
.acard.cr .anum{color:#fecaca}.acard.cr .anom{color:#fca5a5}
.acard.cn{background:#162040;border-color:#2a4080}
.acard.cn .anum{color:#bfdbfe}.acard.cn .anom{color:#93c5fd}
.acard.cl{background:#6b4a08;border-color:#d97706}
.acard.cl .anum{color:#fef3c7}.acard.cl .anom{color:#fde68a}
.acard.sel{box-shadow:0 0 8px rgba(255,255,255,.3);transform:scale(1.05)}
.acard.sel::after{content:'✓';position:absolute;top:0;right:2px;font-size:.5rem;color:#fff;font-weight:700}
.anum{font-size:.72rem;font-weight:700;font-family:'Oswald',sans-serif;line-height:1}
.anom{font-size:.48rem;line-height:1;margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* ---- TICKET LIST ---- */
.ticket-list{flex:1;overflow-y:auto;min-height:40px;background:#060c1a;border:1px solid #1a2540;border-radius:4px;padding:4px;margin-bottom:4px}
.ti{display:flex;align-items:center;gap:3px;padding:3px;border-bottom:1px solid #0a1828;font-size:.7rem}
.ti-lots{display:flex;gap:2px;flex-wrap:wrap;min-width:28px}
.ti-lotbadge{font-size:.52rem;padding:1px 3px;border-radius:2px;font-weight:700;color:#fff}
.ti-desc{flex:1;color:#c0d8f0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.68rem}
.ti-hora{color:#00c8e8;font-size:.6rem;min-width:34px;font-family:'Oswald',sans-serif;font-weight:700}
.ti-monto{color:#22c55e;font-weight:700;font-family:'Oswald',sans-serif;min-width:30px;text-align:right;font-size:.7rem}
.ti-del{background:#6b1515;border:none;color:#fff;cursor:pointer;font-size:.55rem;padding:2px 4px;border-radius:2px}
.ticket-empty{color:#2a4060;text-align:center;padding:20px;font-size:.72rem;letter-spacing:2px}
.ticket-total{text-align:right;padding:5px 6px;font-family:'Oswald',sans-serif;color:#fbbf24;font-size:.95rem;font-weight:700;border-top:2px solid #d97706;background:#0a0e18}

.action-btns{display:grid;grid-template-columns:1fr 1fr;gap:3px;margin-top:3px}
.action-btn{padding:9px 4px;text-align:center;border-radius:4px;cursor:pointer;font-family:'Oswald',sans-serif;font-size:.65rem;font-weight:700;letter-spacing:1px;border:2px solid;transition:all .15s;color:#fff}
.action-btn.wa{background:#166534;border-color:#22c55e}
.action-btn.wa:hover{background:#15803d}
.action-btn.wa:disabled{background:#0f2e1a;border-color:#1a4a28;color:#2a6038;cursor:not-allowed}
.action-btn.sec{background:#1a3050;border-color:#2a5080;color:#90b8e0}
.action-btn.sec:hover{background:#006080;border-color:#00b4d8;color:#fff}
.action-btn.danger{background:#991b1b;border-color:#ef4444}
.action-btn.trip{background:#6b21a8;border-color:#a855f7}

.toast{position:fixed;bottom:10px;left:50%;transform:translateX(-50%);padding:8px 18px;border-radius:4px;font-family:'Oswald',sans-serif;font-size:.78rem;letter-spacing:1px;font-weight:700;z-index:9999;display:none;max-width:90%;text-align:center}
.toast.ok{background:#166534;color:#fff;border:2px solid #22c55e}
.toast.err{background:#991b1b;color:#fff;border:2px solid #ef4444}

.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:1000;overflow-y:auto;padding:8px;align-items:flex-start;justify-content:center}
.modal.open{display:flex}
.mc{background:#080e1c;border:1px solid #1a2a50;border-radius:6px;width:100%;max-width:640px;margin:auto}
.mh{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-bottom:2px solid #00b4d8;background:#050a14}
.mh h3{font-family:'Oswald',sans-serif;color:#00d8ff;font-size:.85rem;letter-spacing:2px}
.mbody{padding:12px}
.btn-close{background:#7f1d1d;color:#fff;border:2px solid #dc2626;border-radius:3px;padding:4px 10px;cursor:pointer;font-size:.72rem;font-family:'Oswald',sans-serif;font-weight:700}
.frow{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.frow input,.frow select{flex:1;min-width:100px;padding:8px 10px;background:#0a1828;border:2px solid #2a4a80;border-radius:3px;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600}
.frow input:focus,.frow select:focus{outline:none;border-color:#00b4d8}
.btn-q{width:100%;padding:10px;background:#1a3a90;color:#fff;border:2px solid #4070d0;border-radius:3px;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:2px;cursor:pointer;margin-bottom:8px;font-size:.78rem}
.btn-q:hover{background:#2050c0}
.ri{display:flex;justify-content:space-between;align-items:center;padding:7px 10px;margin:3px 0;background:#0a1020;border-radius:3px;border-left:3px solid #1a2a50;font-size:.78rem}
.ri.ok{border-left-color:#22c55e;background:#050f08}
.tcard{background:#060c1a;padding:10px;margin:5px 0;border-radius:4px;border-left:3px solid #1a2a50;font-size:.75rem}
.tcard.gano{border-left-color:#22c55e;background:#040f08}
.tcard.pte{border-left-color:#f59e0b;background:#0a0800}
.ts{color:#00d8ff;font-weight:700;font-family:'Oswald',sans-serif}
.badge{display:inline-block;padding:2px 6px;border-radius:3px;font-size:.62rem;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:1px;color:#fff}
.badge.p{background:#166534;border:1px solid #22c55e}
.badge.g{background:#854d0e;border:1px solid #f59e0b}
.badge.n{background:#1e3050;border:1px solid #4080c0}
.jrow{display:flex;justify-content:space-between;align-items:center;padding:3px 8px;margin:2px 0;border-radius:3px;background:#070d1a;border-left:3px solid #1a2a50;font-size:.73rem}
.jrow.gano{background:#040d06;border-left-color:#22c55e}
.trip-row{display:flex;justify-content:space-between;align-items:center;padding:5px 8px;margin:2px 0;border-radius:3px;background:#0d0620;border-left:3px solid #6b21a8;font-size:.73rem}
.sbox{background:#060c1a;border-radius:3px;padding:10px;margin:6px 0;border:1px solid #1a2a50}
.srow{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #0a1020;font-size:.75rem}
.srow:last-child{border-bottom:none}
.sl{color:#6090c0}.sv{color:#fbbf24;font-weight:700;font-family:'Oswald',sans-serif}
.caja-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:8px 0}
.cg{background:#060c1a;border:2px solid #1a2a50;border-radius:3px;padding:10px;text-align:center}
.cgl{color:#6090c0;font-size:.6rem;letter-spacing:2px;margin-bottom:3px;font-family:'Oswald',sans-serif}
.cgv{color:#fbbf24;font-size:1rem;font-weight:700;font-family:'Oswald',sans-serif}
.cgv.g{color:#4ade80}.cgv.r{color:#f87171}

/* ---- TRIPLETA MODAL ---- */
.trip-modal-body{padding:12px}
.trip-lot-tags{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:10px}
.trip-ltag{padding:4px 10px;border-radius:10px;cursor:pointer;font-size:.65rem;font-family:'Oswald',sans-serif;border:2px solid #1a2540;background:#0a0e18;color:#4a6090;transition:all .15s}
.trip-ltag.sel{color:#fff}
.trip-slots{display:flex;gap:6px;margin-bottom:10px}
.tslot{flex:1;background:#1a0a40;border:2px solid #5020a0;border-radius:4px;padding:8px;text-align:center;cursor:pointer;min-height:46px;display:flex;flex-direction:column;align-items:center;justify-content:center;transition:all .15s}
.tslot.act{border-color:#c060ff;box-shadow:0 0 12px rgba(180,80,255,.5);background:#280a60}
.tslot.fill{border-color:#9040f0;background:#200850}
.tslot .snum{font-size:.9rem;font-weight:700;font-family:'Oswald',sans-serif;color:#e0a0ff}
.tslot .snom{font-size:.58rem;color:#a060e0}
.trip-modal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px;max-height:220px;overflow-y:auto;margin-top:8px}
.trip-lots-sel{background:#0d0620;border:1px solid #5b21b6;border-radius:4px;padding:8px;margin-bottom:10px}
.trip-lots-sel-title{font-family:'Oswald',sans-serif;font-size:.68rem;color:#a855f7;letter-spacing:2px;margin-bottom:6px}

::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:#0a0e18}
::-webkit-scrollbar-thumb{background:#1a2a50;border-radius:2px}
</style></head><body>

<div class="topbar">
  <div style="display:flex;align-items:center;gap:6px">
    <div class="brand">MULTI<em>LOT</em></div>
    <div style="color:#4a6090;font-size:.68rem;overflow:hidden;text-overflow:ellipsis;max-width:90px">{{agencia}}</div>
  </div>
  <div style="display:flex;align-items:center;gap:4px">
    <div class="clock" id="clock">--:--</div>
    <button class="tbtn" onclick="openMod('mod-consultas')">🎫</button>
    <button class="tbtn" onclick="openCaja()">💰</button>
    <button class="tbtn exit" onclick="location.href='/logout'">✕</button>
  </div>
</div>

<div class="layout">
  <div class="left-panel">
    <!-- INPUTS -->
    <div class="input-section">
      <div class="input-row">
        <div class="input-group" style="flex:1.5">
          <label>🎱 NÚMERO(S) — separar con punto o espacio</label>
          <input type="text" class="numero-input" id="input-numero" placeholder="Ej: 5.25.36" autocomplete="off">
        </div>
        <div class="input-group" style="flex:1">
          <label>💰 MONTO S/</label>
          <input type="number" class="monto-input" id="input-monto" value="1" min="0.5" step="0.5">
        </div>
      </div>
    </div>

    <!-- LOTERÍA MULTI-SELECT -->
    <div class="lot-section">
      <label>🎲 LOTERÍAS (selecciona una o varias)</label>
      <div class="lot-tags" id="lot-tags"></div>
    </div>

    <!-- HORAS -->
    <div class="horas-section">
      <div class="horas-grid" id="horas-grid"></div>
      <div class="horas-btns">
        <button class="hsel-btn" onclick="selTodos()">☑ TODOS</button>
        <button class="hsel-btn" onclick="limpiarH()">✕ LIMPIAR HORAS</button>
      </div>
    </div>

    <!-- ANIMALES GRID (referencia de la primera loteria sel) -->
    <div class="animales-section">
      <div style="color:#4a6090;font-size:.62rem;letter-spacing:1px;margin-bottom:4px;font-family:'Oswald',sans-serif" id="anim-ref-title">REFERENCIA DE ANIMALES</div>
      <div class="animales-grid" id="animales-grid"></div>
    </div>
  </div>

  <!-- PANEL DERECHO -->
  <div class="right-panel">
    <div style="color:#f5a623;font-family:'Oswald',sans-serif;font-size:.75rem;letter-spacing:2px;margin-bottom:4px">🎫 TICKET UNIFICADO</div>
    <div class="ticket-list" id="ticket-list"><div class="ticket-empty">TICKET VACÍO<br>Ingresa número y monto</div></div>
    <div id="ticket-total" style="display:none" class="ticket-total">TOTAL: S/0.00</div>
    
    <div class="action-btns">
      <button class="action-btn" style="background:#1a3a90;border-color:#4070d0" onclick="agregarJugada()">➕ AGREGAR</button>
      <button class="action-btn trip" onclick="openTripletaModal()">🎯 TRIPLETA</button>
      <button class="action-btn wa" onclick="vender()" id="btn-wa" disabled>📤 WHATSAPP</button>
      <button class="action-btn" style="background:#0a2a1a;border-color:#16a34a;color:#4ade80" onclick="validarCarritoUI()">🔍 VERIFICAR</button>
      <button class="action-btn sec" onclick="borrarTodo()">🗑 BORRAR TODO</button>
      <button class="action-btn sec" onclick="openPagar()">💵 PAGAR</button>
      <button class="action-btn danger" onclick="openAnular()">❌ ANULAR</button>
      <button class="action-btn sec" onclick="openRepetir()">🔁 REPETIR</button>
      <button class="action-btn sec" onclick="openResultados()">📊 RESULTADOS</button>
      <button class="action-btn sec" onclick="openCaja()">💰 CAJA</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<!-- MODAL TRIPLETA MULTI-LOTERIA -->
<div class="modal" id="mod-tripleta">
<div class="mc">
  <div class="mh"><h3>🎯 TRIPLETA MULTI-LOTERÍA</h3><button class="btn-close" onclick="closeMod('mod-tripleta')">✕</button></div>
  <div class="trip-modal-body">
    <div class="trip-lots-sel">
      <div class="trip-lots-sel-title">SELECCIONA LOTERÍAS PARA LA TRIPLETA</div>
      <div class="trip-lot-tags" id="trip-lot-tags"></div>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:10px;align-items:center">
      <input type="number" id="trip-monto" value="1" min="0.5" step="0.5" placeholder="Monto S/" style="flex:1;padding:8px;background:#0a1828;border:2px solid #d97706;border-radius:3px;color:#fbbf24;font-family:'Oswald',sans-serif;text-align:center">
    </div>
    <div style="color:var(--text2);font-size:.7rem;margin-bottom:8px;text-align:center">Selecciona 3 animales · se jugará en cada lotería marcada</div>
    <div class="trip-slots">
      <div class="tslot act" id="tms0" onclick="activarSlotModal(0)"><div class="sph">ANIMAL 1</div></div>
      <div class="tslot" id="tms1" onclick="activarSlotModal(1)"><div class="sph">ANIMAL 2</div></div>
      <div class="tslot" id="tms2" onclick="activarSlotModal(2)"><div class="sph">ANIMAL 3</div></div>
    </div>
    <div class="trip-modal-grid" id="trip-modal-grid"></div>
    <div style="display:flex;gap:8px;margin-top:10px">
      <button class="btn-q" style="background:#166534;border-color:#22c55e;margin-bottom:0" onclick="agregarTripleta()">✅ AGREGAR TRIPLETA(S)</button>
      <button class="btn-close" style="flex:1;background:#1e3050;border-color:#4080c0;color:#90c0ff" onclick="closeMod('mod-tripleta')">CANCELAR</button>
    </div>
  </div>
</div></div>

<!-- MODAL RESULTADOS -->
<div class="modal" id="mod-resultados">
<div class="mc">
  <div class="mh"><h3>📊 RESULTADOS</h3><button class="btn-close" onclick="closeMod('mod-resultados')">✕</button></div>
  <div class="mbody">
    <div class="frow">
      <input type="date" id="res-fecha">
      <select id="res-loteria"></select>
    </div>
    <button class="btn-q" onclick="cargarResultados()">VER RESULTADOS</button>
    <div id="res-lista" style="max-height:340px;overflow-y:auto;margin-top:10px"></div>
  </div>
</div></div>

<!-- MODAL MIS TICKETS -->
<div class="modal" id="mod-consultas">
<div class="mc">
  <div class="mh"><h3>📋 MIS TICKETS</h3><button class="btn-close" onclick="closeMod('mod-consultas')">✕</button></div>
  <div class="mbody">
    <div class="frow">
      <input type="date" id="mt-ini">
      <input type="date" id="mt-fin">
      <select id="mt-estado">
        <option value="todos">Todos</option>
        <option value="por_pagar">Con Premio</option>
      </select>
    </div>
    <button class="btn-q" onclick="consultarTickets()">BUSCAR</button>
    <div id="mt-resumen" style="display:none;background:rgba(0,180,216,.06);border:1px solid #0a4050;border-radius:3px;padding:7px;margin:8px 0;color:var(--teal);font-size:.72rem;font-family:'Oswald',sans-serif;letter-spacing:1px"></div>
    <div id="mt-lista" style="max-height:400px;overflow-y:auto"><p style="color:var(--text2);text-align:center;padding:20px;font-size:.7rem;letter-spacing:2px">USE LOS FILTROS</p></div>
  </div>
</div></div>

<!-- MODAL CAJA -->
<div class="modal" id="mod-caja">
<div class="mc">
  <div class="mh"><h3>💰 CAJA HOY</h3><button class="btn-close" onclick="closeMod('mod-caja')">✕</button></div>
  <div class="mbody" id="caja-body"></div>
</div></div>

<!-- MODAL PAGAR -->
<div class="modal" id="mod-pagar">
<div class="mc">
  <div class="mh"><h3>💵 VERIFICAR / PAGAR</h3><button class="btn-close" onclick="closeMod('mod-pagar')">✕</button></div>
  <div class="mbody">
    <div class="frow"><input type="text" id="pag-serial" placeholder="Serial del ticket"></div>
    <button class="btn-q" onclick="verificarTicket()">VERIFICAR</button>
    <div id="pag-res"></div>
  </div>
</div></div>

<!-- MODAL ANULAR -->
<div class="modal" id="mod-anular">
<div class="mc">
  <div class="mh"><h3>❌ ANULAR TICKET</h3><button class="btn-close" onclick="closeMod('mod-anular')">✕</button></div>
  <div class="mbody">
    <div style="color:#f87171;font-size:.72rem;margin-bottom:8px;border:1px solid #6b1515;border-radius:3px;padding:6px;background:#1a0808">
      ⚠ Solo puedes anular si el sorteo aún no ha cerrado.
    </div>
    <div class="frow"><input type="text" id="an-serial" placeholder="Serial del ticket"></div>
    <button class="btn-q" style="background:linear-gradient(135deg,#3a1010,#280808);border-color:#6b1515;color:#e05050" onclick="anularTicket()">ANULAR TICKET</button>
    <div id="an-res"></div>
  </div>
</div></div>

<!-- MODAL REPETIR TICKET -->
<div class="modal" id="mod-repetir">
<div class="mc">
  <div class="mh"><h3>🔁 REPETIR TICKET POR SERIAL</h3><button class="btn-close" onclick="closeMod('mod-repetir')">✕</button></div>
  <div class="mbody">
    <div style="color:#a0c0e0;font-size:.72rem;margin-bottom:8px">Ingresa el serial del ticket anterior para cargar sus jugadas en el ticket actual.</div>
    <div class="frow"><input type="text" id="rep-serial" placeholder="Serial del ticket" autocomplete="off" inputmode="numeric"></div>
    <button class="btn-q" onclick="repetirTicket()">🔁 CARGAR JUGADAS</button>
    <div id="rep-res"></div>
  </div>
</div></div>

<script>
const LOTERIAS_DATA = {{ loterias | tojson }};
const ROJOS_Z = ["1","3","5","7","9","12","14","16","18","19","21","23","25","27","30","32","34","36","37","39"];

// Estado global
let carrito = [];
let horasSel = [];
let horasBloq = [];
let loteriasSelActual = []; // Multi-select de loterías
let primerLotActual = 'zoolo'; // Para referencia del grid de animales
let numerosSelGrid = [];

// Estado tripleta
let tripSlotModal = 0;
let tripAnimModal = [null, null, null];
let tripLoteriasSelModal = []; // Multi-select loterías tripleta

function getHorarios(lid){
  let lot = LOTERIAS_DATA[lid];
  if(lot && lot.offset_30min){
    return {
      peru:     ["08:30 AM","09:30 AM","10:30 AM","11:30 AM","12:30 PM","01:30 PM","02:30 PM","03:30 PM","04:30 PM","05:30 PM","06:30 PM"],
      venezuela:["09:30 AM","10:30 AM","11:30 AM","12:30 PM","01:30 PM","02:30 PM","03:30 PM","04:30 PM","05:30 PM","06:30 PM","07:30 PM"]
    };
  }
  return {
    peru:     ["08:00 AM","09:00 AM","10:00 AM","11:00 AM","12:00 PM","01:00 PM","02:00 PM","03:00 PM","04:00 PM","05:00 PM","06:00 PM"],
    venezuela:["08:00 AM","09:00 AM","10:00 AM","11:00 AM","12:00 PM","01:00 PM","02:00 PM","03:00 PM","04:00 PM","05:00 PM","06:00 PM"]
  };
}

function init(){
  renderLotTags();
  renderLotTagsTripleta();
  
  // Hora actual para bloqueos (base no-offset por defecto)
  actualizarBloq();
  setInterval(actualizarBloq, 30000);
  setInterval(actualizarClock, 1000);
  actualizarClock();
  
  let hoy = new Date().toISOString().split('T')[0];
  ['res-fecha','mt-ini','mt-fin'].forEach(id=>{
    let e = document.getElementById(id);
    if(e) e.value = hoy;
  });
  
  let selR = document.getElementById('res-loteria');
  Object.entries(LOTERIAS_DATA).forEach(([k,v])=>{
    selR.innerHTML += `<option value="${k}">${v.emoji} ${v.nombre}</option>`;
  });
  
  document.getElementById('input-numero').focus();
  
  document.getElementById('input-numero').addEventListener('input', function(){
    let raw = this.value.trim();
    let vals = raw.split(/[.\s,]+/).map(s=>s.trim()).filter(s=>s.length>0);
    // Filtrar solo los números válidos para la lotería actual
    let lid = primerLotActual || 'zoolo';
    let lot = LOTERIAS_DATA[lid];
    numerosSelGrid = vals.filter(n => lot.animales && lot.animales[n]);
    syncGridSel();
  });
  
  document.getElementById('input-numero').addEventListener('keypress', function(e){
    if(e.key === 'Enter'){
      e.preventDefault();
      document.getElementById('input-monto').focus();
      document.getElementById('input-monto').select();
    }
  });
  
  document.getElementById('input-monto').addEventListener('keypress', function(e){
    if(e.key === 'Enter'){ e.preventDefault(); agregarJugada(); }
  });
}

function actualizarClock(){
  let now = new Date();
  let peru = new Date(now.getTime() - (now.getTimezoneOffset()+300)*60000);
  let h = peru.getUTCHours(), m = peru.getUTCMinutes();
  let ap = h>=12?'PM':'AM'; h = h%12||12;
  document.getElementById('clock').textContent = `${h}:${String(m).padStart(2,'0')} ${ap}`;
}

function actualizarBloq(){
  // Tomamos las horas del primer grupo seleccionado (base o offset)
  let refLot = loteriasSelActual.length > 0 ? loteriasSelActual[0] : 'zoolo';
  fetch('/api/hora-actual?loteria='+refLot)
    .then(r=>r.json())
    .then(d=>{
      horasBloq = d.bloqueadas || [];
      horasSel = horasSel.filter(h=>!horasBloq.includes(h));
      renderHoras();
    }).catch(()=>{});
}

// ========================= LOT TAGS MULTI-SELECT =========================
function renderLotTags(){
  let c = document.getElementById('lot-tags');
  c.innerHTML = '';
  Object.entries(LOTERIAS_DATA).forEach(([k,v])=>{
    let tag = document.createElement('span');
    tag.className = 'ltag' + (loteriasSelActual.includes(k) ? ' sel' : '');
    tag.style.setProperty('--c', v.color);
    if(loteriasSelActual.includes(k)){
      tag.style.borderColor = v.color;
      tag.style.background = `color-mix(in srgb,${v.color} 18%,#050810)`;
      tag.style.color = v.color;
    }
    tag.innerHTML = `${v.emoji} ${v.nombre}`;
    tag.onclick = () => toggleLoteria(k);
    c.appendChild(tag);
  });
  
  // Si ninguna está seleccionada, seleccionar la primera
  if(loteriasSelActual.length === 0){
    toggleLoteria('zoolo');
  }
  
  renderAnimalesGrid();
  renderHoras();
}

function toggleLoteria(lid){
  let idx = loteriasSelActual.indexOf(lid);
  if(idx >= 0){
    // No deseleccionar si es la única
    if(loteriasSelActual.length === 1) return;
    loteriasSelActual.splice(idx, 1);
  } else {
    loteriasSelActual.push(lid);
  }
  primerLotActual = loteriasSelActual[0];
  renderLotTags();
  document.getElementById('anim-ref-title').textContent = 
    'REF: ' + loteriasSelActual.map(l=>LOTERIAS_DATA[l].emoji+' '+LOTERIAS_DATA[l].nombre.split(' ').pop()).join(' · ');
  actualizarBloq();
}

// ========================= GRID DE ANIMALES =========================
function getCardClass(k, lid){
  let lot = LOTERIAS_DATA[lid];
  if(lot.animal_especial && k === lot.animal_especial) return 'cl';
  if(k==='0'||k==='00') return 'cv';
  if(ROJOS_Z.includes(k)) return 'cr';
  return 'cn';
}

function syncGridSel(){
  document.querySelectorAll('#animales-grid .acard').forEach(c=>{
    if(numerosSelGrid.includes(c.dataset.k)) c.classList.add('sel');
    else c.classList.remove('sel');
  });
}

function renderAnimalesGrid(){
  let lid = primerLotActual || 'zoolo';
  let lot = LOTERIAS_DATA[lid];
  let g = document.getElementById('animales-grid');
  g.innerHTML = '';
  
  let orden = Object.keys(lot.animales).sort((a,b)=>{
    let na = a==='00'?-1:parseInt(a); let nb = b==='00'?-1:parseInt(b);
    if(isNaN(na)) na=999; if(isNaN(nb)) nb=999;
    return na-nb;
  });
  
  orden.forEach(k=>{
    if(!lot.animales[k]) return;
    let d = document.createElement('div');
    let selClass = numerosSelGrid.includes(k) ? ' sel' : '';
    d.className = `acard ${getCardClass(k,lid)}${selClass}`;
    d.dataset.k = k;
    d.innerHTML = `<div class="anum">${k}</div><div class="anom">${lot.animales[k]}</div>`;
    d.onclick = ()=>{
      let i = numerosSelGrid.indexOf(k);
      if(i>=0){ numerosSelGrid.splice(i,1); d.classList.remove('sel'); }
      else { numerosSelGrid.push(k); d.classList.add('sel'); }
      document.getElementById('input-numero').value = numerosSelGrid.join('.');
    };
    g.appendChild(d);
  });
}

// ========================= HORAS =========================
function renderHoras(){
  let g = document.getElementById('horas-grid');
  g.innerHTML = '';
  // Usamos horarios del primer lot seleccionado
  let lid = loteriasSelActual.length > 0 ? loteriasSelActual[0] : 'zoolo';
  let {peru: horasP, venezuela: horasV} = getHorarios(lid);
  
  horasP.forEach((h, i)=>{
    let bloq = horasBloq.includes(h);
    let sel = horasSel.includes(h);
    let d = document.createElement('div');
    d.className = `hbtn ${sel?'sel':''} ${bloq?'bloq':''}`;
    d.innerHTML = `<div class="hperu">${h.replace(':00 ','').replace(' ','')}</div><div class="hven">${horasV[i].replace(':00 ','').replace(' ','')}</div>`;
    if(!bloq) d.onclick = ()=>toggleHora(h, d);
    g.appendChild(d);
  });
}

function toggleHora(h, el){
  let i = horasSel.indexOf(h);
  if(i>=0){ horasSel.splice(i,1); el.classList.remove('sel'); }
  else { horasSel.push(h); el.classList.add('sel'); }
}

function selTodos(){
  let lid = loteriasSelActual.length > 0 ? loteriasSelActual[0] : 'zoolo';
  let {peru: horasP} = getHorarios(lid);
  horasSel = horasP.filter(h=>!horasBloq.includes(h));
  renderHoras();
}

function limpiarH(){ horasSel = []; renderHoras(); }

// ========================= AGREGAR JUGADA MULTI-LOTERÍA =========================
function agregarJugada(){
  let raw = document.getElementById('input-numero').value.trim();
  let monto = parseFloat(document.getElementById('input-monto').value) || 0;
  
  // Lista cruda con repeticiones (ej: 1.1.1.2.2 → [1,1,1,2,2])
  let numerosRaw = numerosSelGrid.length > 0 ? numerosSelGrid.slice()
                  : raw.split(/[.\s,]+/).map(s=>s.trim()).filter(s=>s.length>0);
  
  if(numerosRaw.length === 0){ toast('Ingrese o seleccione número(s)','err'); return; }
  if(monto <= 0){ toast('Monto inválido','err'); return; }
  if(horasSel.length === 0){ toast('Seleccione al menos 1 hora','err'); return; }
  if(loteriasSelActual.length === 0){ toast('Seleccione al menos 1 lotería','err'); return; }

  // Contar repeticiones → monto total por número único
  // Ej: [1,1,1,2,2] monto=1 → {1: 3, 2: 2}
  let conteo = {};
  for(let n of numerosRaw){
    conteo[n] = (conteo[n] || 0) + 1;
  }
  let numerosUnicos = Object.keys(conteo);

  // Validar que todos los números únicos sean válidos en TODAS las loterías
  let errores = [];
  for(let lid of loteriasSelActual){
    let lot = LOTERIAS_DATA[lid];
    let inv = numerosUnicos.filter(n => !lot.animales[n]);
    if(inv.length > 0) errores.push(`${lot.nombre}: ${inv.join(',')}`);
  }
  if(errores.length > 0){ toast('Número inválido: ' + errores.join(' | '), 'err'); return; }
  
  let totalAgregadas = 0;
  for(let lid of loteriasSelActual){
    let lot = LOTERIAS_DATA[lid];
    for(let numero of numerosUnicos){
      let montoFinal = monto * conteo[numero]; // monto × repeticiones
      for(let h of horasSel){
        // Buscar si ya existe esa combinación en el carrito → sumar monto
        let existe = carrito.find(c => c.tipo==='animal' && c.loteria===lid && c.hora===h && c.seleccion===numero);
        if(existe){
          existe.monto += montoFinal;
          existe.desc = `${numero} ${lot.animales[numero].substring(0,6)}`;
        } else {
          carrito.push({
            tipo: 'animal',
            hora: h,
            seleccion: numero,
            monto: montoFinal,
            loteria: lid,
            desc: `${numero} ${lot.animales[numero].substring(0,6)}`
          });
        }
        totalAgregadas++;
      }
    }
  }
  
  renderCarrito();
  // Resumen: mostrar números únicos con su monto agrupado
  let resumen = numerosUnicos.map(n=>{
    let lot0 = LOTERIAS_DATA[loteriasSelActual[0]];
    let abr = lot0.animales[n] ? lot0.animales[n].substring(0,3).toUpperCase() : n;
    let mt = monto * conteo[n];
    return `${abr}${n}x${mt}`;
  }).join(' ');
  toast(`✓ ${resumen} · ${horasSel.length} hr(s) · ${loteriasSelActual.length} lot`, 'ok');
  
  numerosSelGrid = [];
  document.getElementById('input-numero').value = '';
  document.getElementById('input-numero').focus();
  syncGridSel();
}

// ========================= RENDER CARRITO =========================
let carritoErrores = {}; // idx -> {msg, disponible, agotado_total}

function renderCarrito(){
  let list = document.getElementById('ticket-list');
  let tot = document.getElementById('ticket-total');
  
  if(carrito.length === 0){
    list.innerHTML = '<div class="ticket-empty">TICKET VACÍO<br>Ingresa número y monto</div>';
    tot.style.display = 'none';
    document.getElementById('btn-wa').disabled = true;
    carritoErrores = {};
    return;
  }
  
  let html = ''; let total = 0;
  carrito.forEach((item, i)=>{
    total += item.monto;
    let lot = LOTERIAS_DATA[item.loteria];
    let esTripleta = item.tipo === 'tripleta';
    let err = carritoErrores[i];
    let horaLabel = esTripleta
      ? '<span style="color:#c084fc;font-size:.58rem;font-weight:700;font-family:\'Oswald\',sans-serif;letter-spacing:1px">TRIPLETA</span>'
      : `<span class="ti-hora">${item.hora.replace(':00 ','').replace(' ','')}</span>`;

    if(err){
      let esAjustable = (!err.agotado_total && err.disponible > 0);
      // Fila con error — rojo si agotado total, naranja si ajustable
      let rowColor  = esAjustable ? '#1a0e00' : '#1a0505';
      let bordColor = esAjustable ? '#d97706' : '#dc2626';
      let txtColor  = esAjustable ? '#fbbf24' : '#fca5a5';
      let icono     = esAjustable ? '⚠️' : '⛔';
      let msgCorto  = err.msg.length > 26 ? err.msg.substring(0,26)+'…' : err.msg;

      let botonesErr = `<button onclick="quitarItem(${i})" style="padding:2px 5px;background:#7f1d1d;border:1px solid #dc2626;color:#fca5a5;font-size:.58rem;font-family:'Oswald',sans-serif;cursor:pointer;border-radius:2px;white-space:nowrap">✕ QUITAR</button>`;
      if(esAjustable){
        botonesErr += `<button onclick="ajustarMonto(${i},${err.disponible})" style="padding:2px 5px;background:#78350f;border:1px solid #d97706;color:#fde68a;font-size:.58rem;font-family:'Oswald',sans-serif;cursor:pointer;border-radius:2px;white-space:nowrap">→ S/${err.disponible.toFixed(1)}</button>`;
      }

      html += `<div class="ti" style="background:${rowColor};border-left:3px solid ${bordColor};border-top:1px solid ${bordColor}40;flex-wrap:wrap;gap:2px;padding:4px 3px;">
        <span class="ti-lotbadge" style="background:${bordColor}30;color:${txtColor};border:1px solid ${bordColor}50">${lot.emoji}</span>
        ${horaLabel}
        <span style="flex:1;color:${txtColor};font-size:.6rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${err.msg}">${icono} ${item.seleccion} ${msgCorto}</span>
        <span class="ti-monto" style="color:${txtColor}">${item.monto.toFixed(1)}</span>
        <div style="display:flex;gap:2px;width:100%;justify-content:flex-end;margin-top:1px">${botonesErr}</div>
      </div>`;
    } else {
      let rowStyle = esTripleta ? 'background:#0d0620;border-left:3px solid #a855f7;' : '';
      let descColor = esTripleta ? 'color:#e0a0ff;' : '';
      html += `<div class="ti" style="${rowStyle}">
        <span class="ti-lotbadge" style="background:${lot.color}30;color:${lot.color};border:1px solid ${lot.color}50">${lot.emoji}</span>
        ${horaLabel}
        <span class="ti-desc" style="${descColor}">${item.desc}</span>
        <span class="ti-monto">${item.monto.toFixed(1)}</span>
        <button class="ti-del" onclick="quitarItem(${i})">✕</button>
      </div>`;
    }
  });

  // Banner de errores encima del ticket
  let numErrores  = Object.keys(carritoErrores).length;
  let numAgotados = Object.values(carritoErrores).filter(e=>e.agotado_total).length;
  let numAjust    = Object.values(carritoErrores).filter(e=>!e.agotado_total && e.disponible>0).length;

  if(numErrores > 0){
    let bannerColor = numAgotados > 0 ? '#dc2626' : '#d97706';
    let bannerBg    = numAgotados > 0 ? '#1a0505'  : '#1a0e00';
    let bannerMsg   = [];
    if(numAgotados > 0) bannerMsg.push(`⛔ ${numAgotados} agotado(s)`);
    if(numAjust    > 0) bannerMsg.push(`⚠️ ${numAjust} ajustable(s)`);

    let btns = `<button onclick="quitarTodosErrores()" style="flex:1;padding:5px;background:#7f1d1d;border:1px solid #dc2626;color:#fca5a5;font-size:.63rem;font-family:'Oswald',sans-serif;font-weight:700;cursor:pointer;border-radius:2px">🗑 QUITAR AGOTADOS</button>`;
    if(numAjust > 0){
      btns += `<button onclick="ajustarTodos()" style="flex:1;padding:5px;background:#78350f;border:1px solid #d97706;color:#fde68a;font-size:.63rem;font-family:'Oswald',sans-serif;font-weight:700;cursor:pointer;border-radius:2px">⚡ AJUSTAR TODOS</button>`;
    }
    btns += `<button onclick="validarCarritoUI()" style="flex:1;padding:5px;background:#1a2a50;border:1px solid #4070d0;color:#90b8ff;font-size:.63rem;font-family:'Oswald',sans-serif;font-weight:700;cursor:pointer;border-radius:2px">🔄 REVERIFICAR</button>`;

    html = `<div style="background:${bannerBg};border:2px solid ${bannerColor};border-radius:4px;padding:6px 8px;margin-bottom:4px">
      <div style="color:${bannerColor==='#dc2626'?'#f87171':'#fbbf24'};font-family:'Oswald',sans-serif;font-size:.7rem;letter-spacing:1px;margin-bottom:4px">${bannerMsg.join(' — ')}</div>
      <div style="display:flex;gap:3px;flex-wrap:wrap">${btns}</div>
    </div>` + html;
  }
  
  list.innerHTML = html;
  tot.style.display = 'block';

  if(numErrores > 0){
    let partes = [];
    if(numAgotados > 0) partes.push(`<span style="color:#f87171">⛔ ${numAgotados} agotado(s)</span>`);
    if(numAjust    > 0) partes.push(`<span style="color:#fbbf24">⚠️ ${numAjust} ajustable(s)</span>`);
    tot.innerHTML = partes.join(' — ') + ` <span style="color:#c8d8f0">— TOTAL: S/${total.toFixed(2)}</span>`;
  } else {
    tot.textContent = `TOTAL: S/${total.toFixed(2)} (${carrito.length} jugadas)`;
  }

  // Bloquear WHATSAPP si hay cualquier error (agotado O ajustable pendiente de ajuste)
  document.getElementById('btn-wa').disabled = (carrito.length === 0 || numErrores > 0);
}

function ajustarMonto(idx, disponible){
  if(disponible <= 0){ quitarItem(idx); return; }
  carrito[idx].monto = disponible;
  delete carritoErrores[idx];
  renderCarrito();
  toast(`✓ Monto ajustado a S/${disponible.toFixed(1)}`, 'ok');
}

function ajustarTodos(){
  // Ajustar todos los que tienen disponible > 0, quitar los agotados totales
  let idxsAgotados = [];
  Object.entries(carritoErrores).forEach(([k,v])=>{
    let i = parseInt(k);
    if(!v.agotado_total && v.disponible > 0){
      carrito[i].monto = v.disponible;
      delete carritoErrores[i];
    } else {
      idxsAgotados.push(i);
    }
  });
  // Quitar agotados totales en orden inverso
  idxsAgotados.sort((a,b)=>b-a).forEach(i=>{
    carrito.splice(i,1);
  });
  carritoErrores = {};
  renderCarrito();
  toast('✓ Ajuste aplicado a todos', 'ok');
}

function quitarItem(i){
  carrito.splice(i,1);
  let newErr = {};
  Object.entries(carritoErrores).forEach(([k,v])=>{
    let ki = parseInt(k);
    if(ki < i) newErr[ki] = v;
    else if(ki > i) newErr[ki-1] = v;
  });
  carritoErrores = newErr;
  renderCarrito();
}

function quitarTodosErrores(){
  let idxs = Object.keys(carritoErrores).map(Number).sort((a,b)=>b-a);
  idxs.forEach(i => carrito.splice(i,1));
  carritoErrores = {};
  renderCarrito();
}

function borrarTodo(){ if(carrito.length && !confirm('¿Borrar todo?')) return; carrito=[]; carritoErrores={}; renderCarrito(); }

async function validarCarritoUI(){
  if(carrito.length === 0) return;
  try{
    let r = await fetch('/api/validar-carrito',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({jugadas: carrito})
    });
    let d = await r.json();
    if(d.error){ toast(d.error,'err'); return; }
    carritoErrores = {};
    d.resultados.forEach(res=>{
      if(!res.ok) carritoErrores[res.idx] = {
        msg: res.msg,
        disponible: res.disponible || 0,
        agotado_total: res.agotado_total || false
      };
    });
    renderCarrito();
    if(d.hay_errores){
      let nAg = Object.values(carritoErrores).filter(e=>e.agotado_total).length;
      let nAj = Object.values(carritoErrores).filter(e=>!e.agotado_total&&e.disponible>0).length;
      let partes = [];
      if(nAg>0) partes.push(`${nAg} agotado(s)`);
      if(nAj>0) partes.push(`${nAj} con disponible parcial — usa ⚡ AJUSTAR`);
      toast('⛔ ' + partes.join(' | '), 'err');
    } else {
      toast('✓ Todas las jugadas disponibles','ok');
    }
  } catch(e){ toast('Error al verificar','err'); }
}

async function vender(){
  if(carrito.length===0){ toast('Ticket vacío','err'); return; }
  let btn = document.getElementById('btn-wa');
  btn.disabled = true; btn.textContent = '⏳ VERIFICANDO...';

  try{
    let rv = await fetch('/api/validar-carrito',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({jugadas: carrito})
    });
    let dv = await rv.json();
    if(dv.error){ toast(dv.error,'err'); btn.disabled=false; btn.textContent='📤 WHATSAPP'; return; }
    if(dv.hay_errores){
      carritoErrores = {};
      dv.resultados.forEach(res=>{
        if(!res.ok) carritoErrores[res.idx] = {
          msg: res.msg,
          disponible: res.disponible || 0,
          agotado_total: res.agotado_total || false
        };
      });
      renderCarrito();
      let nAg = Object.values(carritoErrores).filter(e=>e.agotado_total).length;
      let nAj = Object.values(carritoErrores).filter(e=>!e.agotado_total&&e.disponible>0).length;
      let partes = [];
      if(nAg>0) partes.push(`${nAg} agotado(s)`);
      if(nAj>0) partes.push(`${nAj} ajustable(s) — presiona ⚡ AJUSTAR TODOS`);
      toast('⛔ ' + partes.join(' | '), 'err');
      btn.disabled = true; btn.textContent='📤 WHATSAPP';
      return;
    }
  } catch(e){ toast('Error de conexión al verificar','err'); btn.disabled=false; btn.textContent='📤 WHATSAPP'; return; }

  btn.textContent = '⏳ PROCESANDO...';
  try{
    let r = await fetch('/api/procesar-venta',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({jugadas: carrito})
    });
    let d = await r.json();
    if(d.error){ toast(d.error,'err'); }
    else{
      if(/Android|iPhone|iPad/i.test(navigator.userAgent)) window.location.href = d.url_whatsapp;
      else window.open(d.url_whatsapp,'_blank');
      carrito=[]; carritoErrores={}; renderCarrito(); toast('¡Ticket generado!','ok');
    }
  } catch(e){ toast('Error de conexión','err'); }
  finally{ btn.disabled = carrito.length===0; btn.textContent = '📤 WHATSAPP'; }
}

// ========================= TRIPLETA MULTI-LOTERÍA =========================
function renderLotTagsTripleta(){
  let c = document.getElementById('trip-lot-tags');
  c.innerHTML = '';
  Object.entries(LOTERIAS_DATA).forEach(([k,v])=>{
    if(!v.tiene_tripleta) return;
    let tag = document.createElement('span');
    tag.className = 'trip-ltag' + (tripLoteriasSelModal.includes(k) ? ' sel' : '');
    if(tripLoteriasSelModal.includes(k)){
      tag.style.borderColor = v.color;
      tag.style.background = `color-mix(in srgb,${v.color} 18%,#050810)`;
      tag.style.color = v.color;
    }
    tag.textContent = `${v.emoji} ${v.nombre} (x${v.pago_tripleta})`;
    tag.onclick = ()=>{
      let i = tripLoteriasSelModal.indexOf(k);
      if(i>=0) tripLoteriasSelModal.splice(i,1);
      else tripLoteriasSelModal.push(k);
      renderLotTagsTripleta();
      renderTripModalGrid();
    };
    c.appendChild(tag);
  });
}

function openTripletaModal(){
  tripSlotModal = 0;
  tripAnimModal = [null,null,null];
  // Pre-llenar con las loterías actuales que tienen tripleta
  tripLoteriasSelModal = loteriasSelActual.filter(l => LOTERIAS_DATA[l].tiene_tripleta);
  if(tripLoteriasSelModal.length === 0) tripLoteriasSelModal = ['zoolo'];
  renderLotTagsTripleta();
  renderTripModalGrid();
  updateTripSlots();
  openMod('mod-tripleta');
}

function renderTripModalGrid(){
  // Mostrar animales comunes a todas las loterías seleccionadas para tripleta
  let refLid = tripLoteriasSelModal.length > 0 ? tripLoteriasSelModal[0] : 'zoolo';
  let lot = LOTERIAS_DATA[refLid];
  let g = document.getElementById('trip-modal-grid');
  g.innerHTML = '';
  
  let orden = Object.keys(lot.animales).sort((a,b)=>{
    let na=a==='00'?-1:parseInt(a); let nb=b==='00'?-1:parseInt(b);
    if(isNaN(na)) na=999; if(isNaN(nb)) nb=999;
    return na-nb;
  });
  
  orden.forEach(k=>{
    if(!lot.animales[k]) return;
    let d = document.createElement('div');
    d.className = `acard ${getCardClass(k, refLid)}`;
    d.innerHTML = `<div class="anum" style="font-size:.78rem">${k}</div><div class="anom">${lot.animales[k]}</div>`;
    d.onclick = ()=> selTripAnimal(k);
    g.appendChild(d);
  });
}

function activarSlotModal(i){ tripSlotModal=i; updateTripSlots(); }

function selTripAnimal(k){
  if(tripAnimModal.includes(k) && tripAnimModal[tripSlotModal]!==k){
    toast('Ya seleccionado en otro slot','err'); return;
  }
  tripAnimModal[tripSlotModal] = k;
  updateTripSlots();
  if(tripSlotModal < 2) tripSlotModal++;
}

function updateTripSlots(){
  let refLid = tripLoteriasSelModal.length > 0 ? tripLoteriasSelModal[0] : 'zoolo';
  let lot = LOTERIAS_DATA[refLid];
  for(let i=0;i<3;i++){
    let sl = document.getElementById('tms'+i);
    sl.className = 'tslot' + (i===tripSlotModal?' act':'') + (tripAnimModal[i]?' fill':'');
    if(tripAnimModal[i]){
      sl.innerHTML = `<div class="snum">${tripAnimModal[i]}</div><div class="snom">${lot.animales[tripAnimModal[i]]||''}</div>`;
    } else {
      sl.innerHTML = `<div class="sph">ANIMAL ${i+1}</div>`;
    }
  }
}

function agregarTripleta(){
  if(tripAnimModal.some(x=>x===null)){ toast('Selecciona 3 animales','err'); return; }
  if(tripLoteriasSelModal.length === 0){ toast('Selecciona al menos 1 lotería','err'); return; }
  
  let monto = parseFloat(document.getElementById('trip-monto').value)||0;
  if(monto<=0){ toast('Monto inválido','err'); return; }
  
  let count = 0;
  for(let lid of tripLoteriasSelModal){
    let lot = LOTERIAS_DATA[lid];
    let noms = tripAnimModal.map(k=>(lot.animales[k]||k).substring(0,4).toUpperCase());
    carrito.push({
      tipo: 'tripleta',
      hora: 'TODO DIA',
      seleccion: tripAnimModal.join(','),
      monto: monto,
      loteria: lid,
      desc: `🎯 ${noms.join('-')}`
    });
    count++;
  }
  
  renderCarrito();
  closeMod('mod-tripleta');
  toast(`✓ ${count} tripleta(s) agregada(s)`, 'ok');
  tripAnimModal = [null,null,null]; tripSlotModal=0; updateTripSlots();
}

// ========================= RESULTADOS, CAJA, PAGAR, ANULAR =========================
function openResultados(){
  let refLot = loteriasSelActual.length > 0 ? loteriasSelActual[0] : 'zoolo';
  document.getElementById('res-loteria').value = refLot;
  openMod('mod-resultados');
}

function cargarResultados(){
  let f = document.getElementById('res-fecha').value;
  let lid = document.getElementById('res-loteria').value;
  if(!f) return;
  let c = document.getElementById('res-lista');
  c.innerHTML = '<p style="color:var(--text2);font-size:.7rem;text-align:center">CARGANDO...</p>';
  fetch('/api/resultados-fecha',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha:f,loteria:lid})})
  .then(r=>r.json()).then(d=>{
    let lot = LOTERIAS_DATA[lid];
    let horas = d.horarios||[];
    let html = `<div style="color:${lot.color};font-family:'Oswald',sans-serif;font-size:.78rem;margin-bottom:8px">${lot.emoji} ${lot.nombre} — ${d.fecha_consulta}</div>`;
    horas.forEach(h=>{
      let res = d.resultados[h];
      html += `<div class="ri ${res?'ok':''}">
        <span style="color:#fbbf24;font-weight:700;font-family:'Oswald',sans-serif;font-size:.75rem">${h.replace(':00 ','').replace(' ','')}</span>
        ${res?`<span style="color:#4ade80;font-weight:700">${res.animal} — ${res.nombre}</span>`:'<span style="color:#1e2a40;font-size:.72rem">PENDIENTE</span>'}
      </div>`;
    });
    c.innerHTML = html;
  }).catch(()=>{ c.innerHTML='<p style="color:var(--red)">Error</p>'; });
}

function consultarTickets(){
  let ini=document.getElementById('mt-ini').value;
  let fin=document.getElementById('mt-fin').value;
  let est=document.getElementById('mt-estado').value;
  if(!ini||!fin){ toast('Seleccione fechas','err'); return; }
  let lista=document.getElementById('mt-lista');
  lista.innerHTML='<p style="color:#6090c0;text-align:center;padding:15px;font-size:.7rem">CARGANDO...</p>';
  fetch('/api/mis-tickets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin,estado:est})})
  .then(r=>r.json()).then(d=>{
    if(d.error){ lista.innerHTML=`<p style="color:#f87171;text-align:center">${d.error}</p>`; return; }
    let res=document.getElementById('mt-resumen'); res.style.display='block';
    res.textContent=`${d.totales.cantidad} ticket(s) — TOTAL: S/${d.totales.ventas.toFixed(2)}`;
    if(!d.tickets.length){ lista.innerHTML='<p style="color:#4a6090;text-align:center;padding:20px;font-size:.7rem">SIN RESULTADOS</p>'; return; }
    let html='';
    d.tickets.forEach(t=>{
      let bc=t.pagado?'p':(t.premio_calculado>0?'g':'n');
      let bt=t.pagado?'✅ PAGADO':(t.premio_calculado>0?'🏆 GANADOR':'⏳');
      let tc=t.pagado?'gano':(t.premio_calculado>0?'pte':'');
      let jhtml='';
      if(t.jugadas&&t.jugadas.length){
        t.jugadas.forEach(j=>{
          let lot=LOTERIAS_DATA[j.loteria]||LOTERIAS_DATA['zoolo'];
          jhtml+=`<div class="jrow ${j.gano?'gano':''}">
            <span style="color:${lot.color};font-size:.58rem;font-weight:700">${lot.emoji}</span>
            <span style="color:#00c8e8;font-family:'Oswald',sans-serif;font-size:.63rem;min-width:38px">${j.hora.replace(':00 ','').replace(' ','')}</span>
            <span style="flex:1;color:#c0d8f0;font-size:.68rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${j.tipo==='animal'?(j.seleccion+' '+j.nombre):j.seleccion}</span>
            <span style="color:#6090c0;font-size:.63rem;margin:0 3px">S/${j.monto}</span>
            ${j.gano?`<span style="color:#4ade80;font-weight:700;font-family:'Oswald',sans-serif;font-size:.68rem">+${j.premio}</span>`:''}
          </div>`;
        });
      }
      let thtml='';
      if(t.tripletas&&t.tripletas.length){
        t.tripletas.forEach(tr=>{
          let lot=LOTERIAS_DATA[tr.loteria]||LOTERIAS_DATA['zoolo'];
          thtml+=`<div class="trip-row ${tr.gano?'gano':''}">
            <span style="color:${lot.color};font-size:.58rem;font-weight:700">${lot.emoji}</span>
            <div style="flex:1;margin-left:4px">
              <span style="color:#e0a0ff;font-size:.68rem">${tr.nombre1} · ${tr.nombre2} · ${tr.nombre3}</span>
              <div style="font-size:.62rem;color:${tr.gano?'#4ade80':'#a080c0'}">Salieron: ${tr.salieron&&tr.salieron.length?tr.salieron.join(', '):'Ninguno'}${tr.gano?' ✅':''}</div>
            </div>
            <div style="text-align:right">
              <div style="color:#fbbf24;font-family:'Oswald',sans-serif;font-size:.72rem">S/${tr.monto}</div>
              ${tr.gano?`<div style="color:#4ade80;font-weight:700;font-size:.72rem">+S/${tr.premio.toFixed(2)}</div>`:''}
            </div>
          </div>`;
        });
      }
      html+=`<div class="tcard ${tc}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:4px;margin-bottom:5px">
          <div><div class="ts" style="font-size:.78rem">🎫 #${t.serial}</div><div style="color:#4a6090;font-size:.62rem">${t.fecha}</div></div>
          <div style="text-align:right">
            <span class="badge ${bc}">${bt}</span>
            <div style="color:#fbbf24;font-family:'Oswald',sans-serif;font-size:.85rem;margin-top:2px">S/${t.total}</div>
            ${t.premio_calculado>0?`<div style="color:#4ade80;font-size:.78rem;font-weight:700">PREMIO: S/${t.premio_calculado.toFixed(2)}</div>`:''}
          </div>
        </div>
        ${jhtml}${thtml}
      </div>`;
    });
    lista.innerHTML=html;
  }).catch(()=>{ lista.innerHTML='<p style="color:#f87171;text-align:center">Error</p>'; });
}

function openCaja(){
  openMod('mod-caja');
  fetch('/api/caja').then(r=>r.json()).then(d=>{
    if(d.error) return;
    let bc=d.balance>=0?'g':'r';
    document.getElementById('caja-body').innerHTML=`
      <div class="caja-grid">
        <div class="cg"><div class="cgl">VENTAS</div><div class="cgv">S/${d.ventas.toFixed(2)}</div></div>
        <div class="cg"><div class="cgl">PREMIOS PAG.</div><div class="cgv r">S/${d.premios.toFixed(2)}</div></div>
        <div class="cg"><div class="cgl">COMISIÓN</div><div class="cgv">S/${d.comision.toFixed(2)}</div></div>
        <div class="cg"><div class="cgl">BALANCE</div><div class="cgv ${bc}">S/${d.balance.toFixed(2)}</div></div>
      </div>
      <div class="sbox">
        <div class="srow"><span class="sl">Tickets</span><span class="sv">${d.total_tickets}</span></div>
        <div class="srow"><span class="sl">Con premio pendiente</span><span class="sv" style="color:#c08020">${d.tickets_pendientes}</span></div>
      </div>`;
  });
}

function openPagar(){ openMod('mod-pagar'); document.getElementById('pag-serial').value=''; document.getElementById('pag-res').innerHTML=''; }

function verificarTicket(){
  let s=document.getElementById('pag-serial').value.trim(); if(!s) return;
  fetch('/api/verificar-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({serial:s})})
  .then(r=>r.json()).then(d=>{
    let c=document.getElementById('pag-res');
    if(d.error){ c.innerHTML=`<div style="background:#1a0808;color:#e05050;padding:10px;border-radius:3px;text-align:center;border:1px solid #6b1515">❌ ${d.error}</div>`; return; }
    let col=d.total_ganado>0?'var(--green)':'var(--text2)';
    c.innerHTML=`<div style="border:1px solid ${col};border-radius:4px;padding:12px;margin-top:10px">
      <div style="color:var(--teal);font-family:'Oswald',sans-serif;letter-spacing:2px;margin-bottom:8px">TICKET #${s}</div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <span style="color:var(--text2);font-size:.75rem">PREMIO</span>
        <span style="color:${col};font-family:'Oswald',sans-serif;font-size:1.1rem;font-weight:700">S/${d.total_ganado.toFixed(2)}</span>
      </div>
      ${d.total_ganado>0?`<button onclick="pagarTicket(${d.ticket_id},${d.total_ganado})" style="width:100%;padding:10px;background:linear-gradient(135deg,#0a3020,#062018);color:var(--green);border:1px solid #0d5a2a;border-radius:3px;font-weight:700;cursor:pointer;font-family:'Oswald',sans-serif;letter-spacing:2px;font-size:.78rem">💰 CONFIRMAR PAGO S/${d.total_ganado.toFixed(2)}</button>`:'<div style="color:var(--text2);text-align:center;font-size:.75rem">SIN PREMIO</div>'}
    </div>`;
  });
}

function pagarTicket(tid,m){
  if(!confirm(`¿Confirmar pago S/${m}?`)) return;
  fetch('/api/pagar-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticket_id:tid})})
  .then(r=>r.json()).then(d=>{
    if(d.status==='ok'){ toast('✅ Ticket pagado','ok'); closeMod('mod-pagar'); }
    else toast(d.error||'Error','err');
  });
}

function openAnular(){ openMod('mod-anular'); document.getElementById('an-serial').value=''; document.getElementById('an-res').innerHTML=''; }

function anularTicket(){
  let s=document.getElementById('an-serial').value.trim(); if(!s) return;
  fetch('/api/anular-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({serial:s})})
  .then(r=>r.json()).then(d=>{
    let c=document.getElementById('an-res');
    if(d.status==='ok') c.innerHTML='<div style="background:#062012;color:var(--green);padding:10px;border-radius:3px;text-align:center;border:1px solid #0d5a2a">✅ '+d.mensaje+'</div>';
    else c.innerHTML='<div style="background:#1a0808;color:#e05050;padding:10px;border-radius:3px;text-align:center;border:1px solid #6b1515">❌ '+d.error+'</div>';
  });
}

function openRepetir(){ openMod('mod-repetir'); document.getElementById('rep-serial').value=''; document.getElementById('rep-res').innerHTML=''; setTimeout(()=>document.getElementById('rep-serial').focus(),100); }

function repetirTicket(){
  let s = document.getElementById('rep-serial').value.trim();
  if(!s){ toast('Ingrese el serial','err'); return; }
  let c = document.getElementById('rep-res');
  c.innerHTML = '<p style="color:#6090c0;font-size:.72rem;text-align:center">CARGANDO...</p>';
  fetch('/api/repetir-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({serial:s})})
  .then(r=>r.json()).then(d=>{
    if(d.error){ c.innerHTML=`<div style="background:#1a0808;color:#e05050;padding:10px;border-radius:3px;text-align:center;border:1px solid #6b1515">❌ ${d.error}</div>`; return; }
    // Verificar jugadas con horas bloqueadas y filtrar
    let validas = d.jugadas.filter(j => j.tipo==='tripleta' || !horasBloq.includes(j.hora));
    let omitidas = d.jugadas.length - validas.length;
    validas.forEach(j => carrito.push(j));
    renderCarrito();
    closeMod('mod-repetir');
    let msg = `✓ ${validas.length} jugada(s) cargadas`;
    if(omitidas > 0) msg += ` (${omitidas} omitidas por sorteo cerrado)`;
    toast(msg, 'ok');
  }).catch(()=>{ c.innerHTML='<p style="color:#f87171;text-align:center">Error de conexión</p>'; });
}

function openMod(id){ document.getElementById(id).classList.add('open'); }
function closeMod(id){ document.getElementById(id).classList.remove('open'); }

document.querySelectorAll('.modal').forEach(m=>{
  m.addEventListener('click', e=>{ if(e.target===m) m.classList.remove('open'); });
});

function toast(msg, tipo){
  let t=document.getElementById('toast');
  t.textContent=msg; t.className='toast '+tipo; t.style.display='block';
  clearTimeout(window._tt);
  window._tt=setTimeout(()=>t.style.display='none', 3000);
}

document.addEventListener('DOMContentLoaded', init);
</script>
</body></html>'''

ADMIN_HTML = r'''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ADMIN — MULTI-LOTERÍA v4</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;600;700&family=Rajdhani:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#06090f;--panel:#0a0e18;--card:#0d1220;--border:#1a2540;--gold:#f5a623;--blue:#2060d0;--teal:#00b4d8;--red:#e53e3e;--green:#22c55e;--purple:#a855f7;--text:#c8d8f0;--text2:#4a6090}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Rajdhani',sans-serif;min-height:100vh}
.topbar{background:#0d1428;border-bottom:2px solid #f5a623;padding:0 16px;height:40px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.brand{font-family:'Oswald',sans-serif;font-size:1rem;font-weight:700;color:#fff;letter-spacing:2px}
.brand em{color:var(--gold);font-style:normal}
.btn-exit{background:#991b1b;color:#fff;border:2px solid #ef4444;padding:5px 12px;border-radius:3px;cursor:pointer;font-family:'Oswald',sans-serif;font-weight:700;font-size:.75rem;letter-spacing:1px}
.tabs{display:flex;background:#050810;border-bottom:2px solid #1a2a50;overflow-x:auto;position:sticky;top:40px;z-index:99}
.tab{padding:10px 12px;cursor:pointer;color:#4a6090;font-size:.7rem;font-family:'Oswald',sans-serif;letter-spacing:2px;border-bottom:3px solid transparent;transition:all .2s;white-space:nowrap;font-weight:600}
.tab:hover{color:#90b8e0;background:#060c1a}
.tab.active{color:#00d8ff;border-bottom-color:#00b4d8;background:#060e18}
.tc{display:none;padding:14px;max-width:960px;margin:auto}
.tc.active{display:block}
.fbox{background:#090f1e;border:2px solid #1a2a50;border-radius:5px;padding:15px;margin-bottom:12px}
.fbox h3{font-family:'Oswald',sans-serif;color:#00d8ff;margin-bottom:12px;font-size:.82rem;letter-spacing:2px;border-bottom:1px solid #1a2a50;padding-bottom:8px}
.frow{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.frow input,.frow select{flex:1;min-width:100px;padding:9px 11px;background:#0a1828;border:2px solid #2a4a80;border-radius:3px;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600}
.frow input:focus,.frow select:focus{outline:none;border-color:#00b4d8}
.btn-s{padding:9px 14px;background:#166534;color:#fff;border:2px solid #22c55e;border-radius:3px;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:1px;cursor:pointer;font-size:.75rem;white-space:nowrap}
.btn-s:hover{background:#15803d}
.btn-d{padding:9px 14px;background:#991b1b;color:#fff;border:2px solid #ef4444;border-radius:3px;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:1px;cursor:pointer;font-size:.75rem}
.btn-sec{padding:7px 10px;background:#1a3050;color:#90b8e0;border:2px solid #2a5080;border-radius:3px;cursor:pointer;font-size:.75rem;font-family:'Oswald',sans-serif;letter-spacing:1px;font-weight:700}
.btn-sec:hover{background:#006080;border-color:#00b4d8;color:#fff}
.sgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-bottom:16px}
.sc{background:#0d1828;border:2px solid #1a2a50;border-radius:4px;padding:12px;text-align:center}
.sc h3{color:#4a6090;font-size:.62rem;letter-spacing:2px;font-family:'Oswald',sans-serif;margin-bottom:5px}
.sc p{color:#fbbf24;font-size:1.25rem;font-weight:700;font-family:'Oswald',sans-serif}
.sc p.g{color:#4ade80}.sc p.r{color:#f87171}
.ri{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;margin:3px 0;background:#0d1828;border-radius:3px;border-left:3px solid #1a2a50;font-size:.8rem}
.ri.ok{border-left-color:#22c55e;background:#070f0a}
.msg{padding:9px 12px;border-radius:3px;margin:6px 0;font-size:.8rem;font-family:'Oswald',sans-serif;letter-spacing:1px;text-align:center;font-weight:700;border:2px solid}
.msg.ok{background:#166534;color:#fff;border-color:#22c55e}
.msg.err{background:#991b1b;color:#fff;border-color:#ef4444}
table{width:100%;border-collapse:collapse;font-size:.78rem}
th{background:#0d1828;color:#00d8ff;padding:8px;text-align:left;border-bottom:2px solid #1a2a50;font-family:'Oswald',sans-serif;letter-spacing:1px;font-size:.7rem}
td{padding:6px 8px;border-bottom:1px solid #0a1020;color:var(--text)}
tr:hover td{background:#0d1828}
.lot-tabs{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:12px}
.lot-tab{padding:6px 12px;border-radius:4px;cursor:pointer;font-family:'Oswald',sans-serif;font-size:.72rem;font-weight:700;letter-spacing:1px;border:2px solid #1a2540;background:#0a0e18;color:#4a6090;transition:all .15s}
.lot-tab:hover{border-color:#2a4080;color:#c0d8f0}
.lot-tab.sel{color:#fff}
.glmsg{position:fixed;top:48px;left:50%;transform:translateX(-50%);z-index:999;min-width:240px;display:none}
.animals-mini{display:grid;grid-template-columns:repeat(auto-fill,minmax(52px,1fr));gap:4px;max-height:260px;overflow-y:auto;padding:4px}
.am-item{background:#0d1828;border:1px solid #1a2a50;border-radius:3px;padding:5px;text-align:center;cursor:pointer;transition:all .1s}
.am-item:hover,.am-item.sel{border-color:#00b4d8;background:#050e1c;color:#00d8ff}
.am-item .anum{font-family:'Oswald',sans-serif;font-size:.82rem;font-weight:700;color:#fbbf24}
.am-item .anom{font-size:.55rem;color:#4a6090}
.lim-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:6px;margin-top:10px}
.lim-item{padding:8px;border:2px solid #1a2a50;border-radius:3px;background:#0a0e18;font-size:.75rem}
.lim-item.bloq{border-color:#dc2626;background:#1a0808}
.lim-item .ln{font-family:'Oswald',sans-serif;color:#fbbf24;font-weight:700}
.lim-item .lh{color:#4a6090;font-size:.65rem}
.lim-item .lm{color:#4ade80;font-size:.8rem}
.rank-item{display:flex;justify-content:space-between;align-items:center;padding:11px 13px;margin:5px 0;background:#0d1828;border-radius:3px;border-left:3px solid #f5a623}
.sbox{background:#0d1828;border-radius:3px;padding:10px;margin:6px 0;border:1px solid #1a2a50}
.srow{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #0a1020;font-size:.8rem}
.srow:last-child{border-bottom:none}
.sl{color:#4a6090}.sv{color:#fbbf24;font-weight:700;font-family:'Oswald',sans-serif}
.btn-edit{padding:5px 12px;background:#1a3a90;color:#fff;border:2px solid #4070d0;border-radius:3px;cursor:pointer;font-size:.72rem;font-family:'Oswald',sans-serif;letter-spacing:1px;font-weight:700;transition:all .15s}
.btn-edit:hover{background:#2050c0}
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:#0a0e18}
::-webkit-scrollbar-thumb{background:#1a2a50;border-radius:2px}
</style></head><body>

<div class="topbar">
  <div class="brand">MULTI<em>LOT</em> ADMIN <span style="color:#4a6090;font-size:.6rem">v4</span></div>
  <button class="btn-exit" onclick="location.href='/logout'">SALIR</button>
</div>

<div id="glmsg" class="glmsg"></div>
<div class="tabs">
  <div class="tab active" onclick="showTab('dashboard')">📊 DASHBOARD</div>
  <div class="tab" onclick="showTab('resultados')">🎯 RESULTADOS</div>
  <div class="tab" onclick="showTab('tripletas')">🔮 TRIPLETAS</div>
  <div class="tab" onclick="showTab('riesgo')">⚠️ RIESGO</div>
  <div class="tab" onclick="showTab('topes')">🛡️ TOPES</div>
  <div class="tab" onclick="showTab('topes-ag')">🏪 TOPES AGENCIAS</div>
  <div class="tab" onclick="showTab('bloqueos')">🔒 BLOQUEOS</div>
  <div class="tab" onclick="showTab('reportes')">📈 REPORTES</div>
  <div class="tab" onclick="showTab('agencias')">🏪 AGENCIAS</div>
  <div class="tab" onclick="showTab('comisiones')">💹 COMISIONES</div>
  <div class="tab" onclick="showTab('operaciones')">💰 OPERACIONES</div>
  <div class="tab" onclick="showTab('auditoria')">📋 AUDITORÍA</div>
</div>

<!-- DASHBOARD -->
<div id="tc-dashboard" class="tc active">
  <div class="sgrid">
    <div class="sc"><h3>VENTAS HOY</h3><p id="d-v">--</p></div>
    <div class="sc"><h3>PREMIOS PAGADOS</h3><p id="d-p" class="r">--</p></div>
    <div class="sc"><h3>COMISIONES</h3><p id="d-c">--</p></div>
    <div class="sc"><h3>BALANCE</h3><p id="d-b">--</p></div>
  </div>
  <div class="fbox"><h3>🏪 POR AGENCIA (HOY)</h3><div id="dash-ags"></div></div>
</div>

<!-- RESULTADOS -->
<div id="tc-resultados" class="tc">
  <div class="fbox">
    <h3>📅 FECHA & LOTERÍA</h3>
    <div class="frow">
      <input type="date" id="ra-fecha">
      <button class="btn-s" onclick="cargarRA()">VER</button>
    </div>
    <div class="lot-tabs" id="lot-tabs-res" style="margin-bottom:8px"></div>
  </div>
  <div class="fbox">
    <h3>📋 RESULTADOS</h3>
    <div id="ra-lista" style="max-height:400px;overflow-y:auto"></div>
  </div>
  <div class="fbox">
    <h3>✏️ CARGAR RESULTADO</h3>
    <div class="frow">
      <select id="ra-hora"></select>
      <input type="date" id="ra-fi" style="max-width:160px">
    </div>
    <div style="color:var(--text2);font-size:.72rem;margin-bottom:6px">Selecciona el animal ganador:</div>
    <div class="animals-mini" id="animals-mini-res"></div>
    <div id="animal-sel-info" style="color:#fbbf24;font-family:'Oswald',sans-serif;font-size:.82rem;margin:8px 0;min-height:20px"></div>
    <button class="btn-s" onclick="guardarResultado()">💾 GUARDAR RESULTADO</button>
    <div id="ra-msg" style="margin-top:6px"></div>
  </div>
</div>

<!-- TRIPLETAS -->
<div id="tc-tripletas" class="tc">
  <div class="fbox">
    <h3>🔮 TRIPLETAS HOY</h3>
    <button class="btn-s" onclick="cargarTrip()" style="margin-bottom:10px">🔄 ACTUALIZAR</button>
    <div id="tri-stats" style="margin-bottom:10px"></div>
    <div id="tri-lista" style="max-height:500px;overflow-y:auto"></div>
  </div>
</div>

<!-- RIESGO -->
<div id="tc-riesgo" class="tc">
  <div class="fbox">
    <h3>⚠️ RIESGO EN TIEMPO REAL</h3>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center">
      <select id="riesgo-hora-sel" style="padding:8px 12px;background:#0a1828;border:2px solid #2a4a80;border-radius:3px;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600"></select>
      <button class="btn-s" onclick="cargarRiesgo()">🔄 ACTUALIZAR</button>
      <div id="riesgo-info" style="color:var(--gold);font-family:'Oswald',sans-serif;font-size:.8rem;letter-spacing:1px"></div>
    </div>
    <div class="lot-tabs" id="lot-tabs-riesgo" style="margin-bottom:10px"></div>
    <div id="riesgo-lista" style="max-height:420px;overflow-y:auto;margin-bottom:10px"></div>
    <div id="riesgo-agencias-btns" style="display:flex;flex-wrap:wrap;gap:6px;padding-top:10px;border-top:1px solid #1a2a50"></div>
    <div id="riesgo-agencia-detalle" style="margin-top:10px"></div>
  </div>
</div>

<!-- TOPES -->
<div id="tc-topes" class="tc">
  <div class="fbox">
    <h3>🛡️ TOPES INDIVIDUALES POR AGENCIA</h3>
    <div style="color:var(--text2);font-size:.78rem;margin-bottom:12px">Tope por número para una agencia específica. Tope 0 = elimina tope.</div>
    <div class="lot-tabs" id="lot-tabs-topes" style="margin-bottom:10px"></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center">
      <select id="tope-hora-sel" style="padding:8px 12px;background:#0a1828;border:2px solid #2a4a80;border-radius:3px;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600"></select>
      <button class="btn-s" onclick="cargarTopes()">🔄 VER TOPES</button>
      <button class="btn-d" onclick="limpiarTopesHora()">🗑 LIMPIAR HORA</button>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center">
      <div class="animals-mini" id="animals-topes" style="flex:1;min-height:80px"></div>
    </div>
    <div id="tope-sel-info" style="color:#fbbf24;font-size:.8rem;margin-bottom:8px;min-height:20px"></div>
    <div class="frow">
      <input type="number" id="tope-monto" placeholder="Monto tope (0=libre)" min="0" step="1" style="max-width:200px">
      <button class="btn-s" onclick="guardarTope()">💾 GUARDAR TOPE</button>
    </div>
    <div id="tope-msg" style="margin-bottom:8px"></div>
    <div id="topes-lista" style="max-height:500px;overflow-y:auto"></div>
  </div>

  <!-- TOPE GLOBAL COMBINADO -->
  <div class="fbox" style="border:2px solid #d97706;background:#0a0800">
    <h3 style="color:#fbbf24">🌐 TOPE GLOBAL — LÍMITE COMBINADO DE TODAS LAS AGENCIAS</h3>
    <div style="color:#a0800a;font-size:.76rem;margin-bottom:12px">
      Define cuánto se puede vender en TOTAL entre todas las agencias para un número/sorteo/lotería.
      Ejemplo: tope S/20 para el número 5 en 1PM de LOTTO ACTIVO — cuando la suma de todas las agencias llegue a S/20, nadie más puede vender ese número en ese sorteo.
    </div>

    <!-- Loterías -->
    <div class="fbox" style="background:#080a00;border:1px solid #3a2a00;margin-bottom:8px">
      <h3 style="font-size:.78rem;color:#fbbf24;margin-bottom:6px">LOTERÍAS</h3>
      <div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:6px">
        <button class="btn-sec" style="font-size:.65rem" onclick="glSelAllLots()">✅ TODAS</button>
        <button class="btn-sec" style="font-size:.65rem" onclick="glDeselAllLots()">⬜ NINGUNA</button>
      </div>
      <div id="gl-loterias" style="display:flex;flex-wrap:wrap;gap:4px"></div>
    </div>

    <!-- Horas -->
    <div class="fbox" style="background:#080a00;border:1px solid #3a2a00;margin-bottom:8px">
      <h3 style="font-size:.78rem;color:#fbbf24;margin-bottom:6px">HORAS DE SORTEO</h3>
      <div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:6px">
        <button class="btn-sec" style="font-size:.65rem" onclick="glSelAllHoras()">✅ TODAS</button>
        <button class="btn-sec" style="font-size:.65rem" onclick="glDeselAllHoras()">⬜ NINGUNA</button>
      </div>
      <div id="gl-horas" style="display:flex;flex-wrap:wrap;gap:3px"></div>
    </div>

    <!-- Números -->
    <div class="fbox" style="background:#080a00;border:1px solid #3a2a00;margin-bottom:8px">
      <h3 style="font-size:.78rem;color:#fbbf24;margin-bottom:6px">NÚMEROS <span style="color:#4a6090;font-size:.65rem">(vacío = todos)</span></h3>
      <div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:6px">
        <button class="btn-sec" style="font-size:.65rem" onclick="glSelAllNums()">✅ TODOS</button>
        <button class="btn-sec" style="font-size:.65rem" onclick="glDeselAllNums()">⬜ NINGUNO</button>
      </div>
      <div id="gl-numeros" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(62px,1fr));gap:3px;max-height:200px;overflow-y:auto"></div>
    </div>

    <!-- Monto global -->
    <div style="display:flex;align-items:flex-end;gap:10px;flex-wrap:wrap;margin-bottom:10px">
      <div style="display:flex;flex-direction:column;gap:4px;flex:1;min-width:180px">
        <label style="color:#a07020;font-size:.7rem;letter-spacing:1px">MONTO GLOBAL MÁXIMO S/ (0 = eliminar tope)</label>
        <input type="number" id="gl-monto" placeholder="Ej: 20" min="0" step="1"
          style="padding:12px;background:#0a0800;border:2px solid #d97706;border-radius:4px;color:#fbbf24;font-family:'Oswald',sans-serif;font-size:1.3rem;font-weight:700;text-align:center">
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        <button class="btn-s" style="background:#78350f;border-color:#d97706" onclick="guardarTopeGlobal()">💾 APLICAR TOPE GLOBAL</button>
        <button class="btn-d" onclick="if(confirm('¿Eliminar topes globales seleccionados?')){document.getElementById('gl-monto').value=0;guardarTopeGlobal();}">🗑 ELIMINAR</button>
      </div>
    </div>
    <div id="gl-msg" style="font-size:.78rem;margin-bottom:8px"></div>

    <!-- Tabla de topes globales configurados -->
    <div style="border-top:1px solid #3a2a00;padding-top:10px;margin-top:4px">
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;align-items:center">
        <select id="gl-filtro-lot" style="padding:6px 10px;background:#0a0800;border:1px solid #3a2a00;border-radius:3px;color:#fbbf24;font-size:.78rem">
          <option value="">— Todas las loterías —</option>
        </select>
        <select id="gl-filtro-hora" style="padding:6px 10px;background:#0a0800;border:1px solid #3a2a00;border-radius:3px;color:#fbbf24;font-size:.78rem">
          <option value="">— Todas las horas —</option>
        </select>
        <button class="btn-sec" style="font-size:.65rem" onclick="cargarTablaGlobal()">🔄 ACTUALIZAR</button>
      </div>
      <div id="gl-tabla" style="max-height:400px;overflow-y:auto;overflow-x:auto"></div>
    </div>
  </div>
</div>

<!-- TOPES AGENCIAS -->
<div id="tc-topes-ag" class="tc">
  <div class="fbox">
    <h3>🏪 TOPES POR AGENCIA — CONFIGURACIÓN MASIVA</h3>
    <div style="color:var(--text2);font-size:.76rem;margin-bottom:12px">
      Selecciona una o varias agencias, loterías, horas y números para aplicar el tope de una sola vez.
      Tope 0 = elimina el tope. El porcentaje es referencial para tu control interno.
    </div>

    <!-- PASO 1: Agencias -->
    <div class="fbox" style="margin-bottom:10px;background:#080d18;border:1px solid #1a2a50">
      <h3 style="font-size:.82rem;margin-bottom:8px">① AGENCIAS</h3>
      <div style="display:flex;gap:6px;margin-bottom:6px;flex-wrap:wrap">
        <button class="btn-sec" style="font-size:.68rem" onclick="tapSelAllAgs()">✅ TODAS</button>
        <button class="btn-sec" style="font-size:.68rem" onclick="tapDeselAllAgs()">⬜ NINGUNA</button>
      </div>
      <div id="tap-agencias" style="display:flex;flex-wrap:wrap;gap:5px"></div>
    </div>

    <!-- PASO 2: Loterías -->
    <div class="fbox" style="margin-bottom:10px;background:#080d18;border:1px solid #1a2a50">
      <h3 style="font-size:.82rem;margin-bottom:8px">② LOTERÍAS</h3>
      <div style="display:flex;gap:6px;margin-bottom:6px;flex-wrap:wrap">
        <button class="btn-sec" style="font-size:.68rem" onclick="tapSelAllLots()">✅ TODAS</button>
        <button class="btn-sec" style="font-size:.68rem" onclick="tapDeselAllLots()">⬜ NINGUNA</button>
      </div>
      <div id="tap-loterias" style="display:flex;flex-wrap:wrap;gap:5px"></div>
    </div>

    <!-- PASO 3: Horas -->
    <div class="fbox" style="margin-bottom:10px;background:#080d18;border:1px solid #1a2a50">
      <h3 style="font-size:.82rem;margin-bottom:8px">③ HORAS DE SORTEO</h3>
      <div style="display:flex;gap:6px;margin-bottom:6px;flex-wrap:wrap">
        <button class="btn-sec" style="font-size:.68rem" onclick="tapSelAllHoras()">✅ TODAS</button>
        <button class="btn-sec" style="font-size:.68rem" onclick="tapDeselAllHoras()">⬜ NINGUNA</button>
      </div>
      <div id="tap-horas" style="display:flex;flex-wrap:wrap;gap:4px"></div>
    </div>

    <!-- PASO 4: Números -->
    <div class="fbox" style="margin-bottom:10px;background:#080d18;border:1px solid #1a2a50">
      <h3 style="font-size:.82rem;margin-bottom:8px">④ NÚMEROS / ANIMALES <span style="color:#4a6090;font-size:.68rem">(vacío = todos)</span></h3>
      <div style="display:flex;gap:6px;margin-bottom:6px;flex-wrap:wrap">
        <button class="btn-sec" style="font-size:.68rem" onclick="tapSelAllNums()">✅ TODOS</button>
        <button class="btn-sec" style="font-size:.68rem" onclick="tapDeselAllNums()">⬜ NINGUNO</button>
      </div>
      <div id="tap-numeros" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(68px,1fr));gap:4px;max-height:280px;overflow-y:auto"></div>
    </div>

    <!-- PASO 5: Tope y porcentaje -->
    <div class="fbox" style="margin-bottom:10px;background:#080d18;border:1px solid #1a2a50">
      <h3 style="font-size:.82rem;margin-bottom:8px">⑤ MONTO Y PORCENTAJE</h3>
      <div class="frow" style="flex-wrap:wrap;gap:10px">
        <div style="display:flex;flex-direction:column;gap:4px;flex:1;min-width:160px">
          <label style="color:#4a6090;font-size:.7rem;letter-spacing:1px">MONTO MÁXIMO POR NÚMERO (S/)</label>
          <input type="number" id="tap-monto" placeholder="Ej: 5" min="0" step="0.5"
            style="padding:10px;background:#0a1828;border:2px solid #2a4a80;border-radius:4px;color:#fbbf24;font-family:'Oswald',sans-serif;font-size:1.1rem;font-weight:700;text-align:center">
        </div>
        <div style="display:flex;flex-direction:column;gap:4px;flex:1;min-width:160px">
          <label style="color:#4a6090;font-size:.7rem;letter-spacing:1px">PORCENTAJE DE VENTAS (%) — REFERENCIAL</label>
          <input type="number" id="tap-pct" placeholder="Ej: 15" min="0" max="100" step="0.5"
            style="padding:10px;background:#0a1828;border:2px solid #2a4a80;border-radius:4px;color:#c084fc;font-family:'Oswald',sans-serif;font-size:1.1rem;font-weight:700;text-align:center">
        </div>
      </div>
      <div id="tap-resumen" style="color:#4a6090;font-size:.72rem;margin-top:8px;min-height:18px"></div>
      <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
        <button class="btn-s" onclick="guardarTopesAgMasivo()">💾 APLICAR TOPES</button>
        <button class="btn-d" onclick="limpiarTopesAgSel()">🗑 ELIMINAR SELECCIONADOS</button>
      </div>
      <div id="tap-msg" style="margin-top:8px;font-size:.8rem"></div>
    </div>

    <!-- Tabla de topes configurados -->
    <div class="fbox" style="background:#080d18;border:1px solid #1a2a50">
      <h3 style="font-size:.82rem;margin-bottom:8px">📋 TOPES CONFIGURADOS POR AGENCIA</h3>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;align-items:center">
        <select id="tap-filtro-ag" style="padding:7px 10px;background:#0a1828;border:2px solid #2a4a80;border-radius:3px;color:#fbbf24;font-size:.8rem">
          <option value="">— Todas las agencias —</option>
        </select>
        <select id="tap-filtro-lot" style="padding:7px 10px;background:#0a1828;border:2px solid #2a4a80;border-radius:3px;color:#4ade80;font-size:.8rem">
          <option value="">— Todas las loterías —</option>
        </select>
        <button class="btn-sec" onclick="cargarTablaTopesAg()">🔄 ACTUALIZAR</button>
        <button class="btn-d" style="font-size:.68rem" onclick="if(confirm('¿Borrar TODOS los topes de la agencia filtrada?'))limpiarTopesAgFiltro()">🗑 LIMPIAR FILTRO</button>
      </div>
      <div id="tap-tabla" style="max-height:500px;overflow-y:auto;overflow-x:auto"></div>
    </div>
  </div>
</div>

<!-- BLOQUEOS (sistema limites_venta existente del 18) -->
<div id="tc-bloqueos" class="tc">
  <div class="fbox">
    <h3>🔒 BLOQUEOS Y LÍMITES DE VENTA</h3>
    <div class="lot-tabs" id="lot-tabs-lim"></div>
    <div style="color:var(--text2);font-size:.72rem;margin-bottom:10px">
      Selecciona un número → elige hora → monto máximo (0 = bloquear totalmente)
    </div>
    <div class="frow">
      <select id="lim-hora"></select>
      <input type="number" id="lim-monto" placeholder="Monto máx (0=bloquear)" min="0" step="0.5" style="flex:1">
      <button class="btn-s" onclick="guardarLimite()">APLICAR</button>
    </div>
    <div class="animals-mini" id="animals-lim" style="margin-bottom:10px"></div>
    <div id="lim-sel-info" style="color:#fbbf24;font-size:.8rem;margin-bottom:10px;min-height:20px"></div>
    <button class="btn-sec" onclick="cargarLimites()" style="width:100%;margin-bottom:10px">🔄 ACTUALIZAR</button>
    <div style="color:#00d8ff;font-size:.75rem;font-family:'Oswald',sans-serif;margin-bottom:6px">LÍMITES ACTIVOS:</div>
    <div id="lista-limites" class="lim-grid"></div>
  </div>
</div>

<!-- REPORTES -->
<div id="tc-reportes" class="tc">
  <div class="fbox">
    <h3>📈 REPORTE GLOBAL POR RANGO</h3>
    <div class="frow">
      <input type="date" id="rep-ini">
      <input type="date" id="rep-fin">
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
      <select id="rep-ag-lot" style="padding:9px 11px;background:#0a1828;border:2px solid #2a4a80;border-radius:3px;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600"></select>
      <input type="date" id="rep-ag-ini">
      <input type="date" id="rep-ag-fin">
      <button class="btn-s" onclick="reporteAgenciaHoras()">VER DETALLE</button>
    </div>
    <div id="rep-ag-out"></div>
  </div>
</div>

<!-- AGENCIAS -->
<div id="tc-agencias" class="tc">
  <div class="fbox">
    <h3>➕ NUEVA AGENCIA</h3>
    <div class="frow">
      <input type="text" id="ag-u" placeholder="Usuario">
      <input type="password" id="ag-p" placeholder="Contraseña">
      <input type="text" id="ag-n" placeholder="Nombre agencia">
      <button class="btn-s" onclick="crearAg()">CREAR</button>
    </div>
    <div id="ag-msg"></div>
  </div>
  <div class="fbox">
    <h3>🏪 AGENCIAS</h3>
    <button class="btn-sec" onclick="cargarAgs()" style="margin-bottom:8px">🔄 Actualizar</button>
    <div style="overflow-x:auto"><table>
      <thead><tr><th>ID</th><th>Usuario</th><th>Nombre</th><th>Comisión %</th><th>Tope S/</th><th>Estado</th><th>Acción</th></tr></thead>
      <tbody id="tabla-ags"></tbody>
    </table></div>
  </div>
  <div class="fbox" id="edit-ag-box" style="display:none">
    <h3>✏️ EDITAR AGENCIA — <span id="edit-ag-nombre-title" style="color:var(--gold)"></span></h3>
    <div style="background:#0a1828;border:1px solid #1a3060;border-radius:4px;padding:10px;margin-bottom:10px">
      <div style="color:#4a6090;font-size:.68rem;letter-spacing:1px;margin-bottom:6px">COMISIÓN ACTUAL</div>
      <div id="edit-ag-com-actual" style="color:#fbbf24;font-family:'Oswald',sans-serif;font-size:1.4rem;font-weight:700">---%</div>
      <div style="color:#4a6090;font-size:.65rem;margin-top:2px">Esta es la comisión que se descuenta de las ventas en caja e informes</div>
    </div>
    <div class="frow">
      <div style="display:flex;flex-direction:column;gap:3px;flex:1">
        <label style="color:#4a6090;font-size:.68rem;letter-spacing:1px">NUEVA COMISIÓN % (ej: 12 para 12%)</label>
        <input type="number" id="edit-ag-com" placeholder="Ej: 12" min="0" max="100" step="0.5"
          style="padding:10px;background:#0a1828;border:2px solid #d97706;border-radius:4px;color:#fbbf24;font-family:'Oswald',sans-serif;font-size:1.1rem;font-weight:700;text-align:center">
      </div>
      <div style="display:flex;flex-direction:column;gap:3px;flex:1">
        <label style="color:#4a6090;font-size:.68rem;letter-spacing:1px">CONTRASEÑA (vacío = no cambiar)</label>
        <input type="password" id="edit-ag-pass" placeholder="Nueva contraseña">
      </div>
      <div style="display:flex;flex-direction:column;gap:3px;flex:1">
        <label style="color:#4a6090;font-size:.68rem;letter-spacing:1px">TOPE TAQUILLA S/ (0 = sin límite)</label>
        <input type="number" id="edit-ag-tope" placeholder="0" min="0" step="10">
      </div>
    </div>
    <div style="display:flex;gap:6px">
      <button class="btn-s" onclick="guardarEditAg()">💾 GUARDAR CAMBIOS</button>
      <button class="btn-sec" onclick="document.getElementById('edit-ag-box').style.display='none'">CANCELAR</button>
    </div>
    <input type="hidden" id="edit-ag-id">
    <div id="edit-ag-msg" style="margin-top:6px"></div>
  </div>
</div>

<!-- COMISIONES POR LOTERÍA -->
<div id="tc-comisiones" class="tc">
  <div class="fbox">
    <h3>💹 COMISIONES POR LOTERÍA</h3>
    <div style="color:var(--text2);font-size:.76rem;margin-bottom:12px">
      Define un % de comisión diferente para cada lotería. Si una lotería no tiene % específico, se usa el % general de la agencia.
      <br>Ejemplo: ZOOLO 15%, resto de loterías 12%.
    </div>

    <!-- Selección de agencias -->
    <div class="fbox" style="background:#080d18;border:1px solid #1a2a50;margin-bottom:10px">
      <h3 style="font-size:.8rem;margin-bottom:8px">① AGENCIAS A CONFIGURAR</h3>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <button class="btn-sec" style="font-size:.68rem" onclick="comSelAllAgs()">✅ TODAS</button>
        <button class="btn-sec" style="font-size:.68rem" onclick="comDeselAllAgs()">⬜ NINGUNA</button>
      </div>
      <div id="com-agencias" style="display:flex;flex-wrap:wrap;gap:5px"></div>
    </div>

    <!-- Loterías con % individual -->
    <div class="fbox" style="background:#080d18;border:1px solid #1a2a50;margin-bottom:10px">
      <h3 style="font-size:.8rem;margin-bottom:8px">② PORCENTAJE POR LOTERÍA</h3>
      <div style="color:#4a6090;font-size:.68rem;margin-bottom:8px">Deja en blanco o 0 para usar el % general de la agencia</div>
      <div id="com-loterias-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px"></div>
    </div>

    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">
      <button class="btn-s" onclick="guardarComisionesLot()">💾 GUARDAR COMISIONES</button>
      <button class="btn-d" style="font-size:.72rem" onclick="borrarComisionesLot()">🗑 BORRAR CONFIGURACIÓN</button>
    </div>
    <div id="com-msg" style="margin-top:8px;font-size:.8rem"></div>
  </div>

  <!-- Tabla de comisiones configuradas -->
  <div class="fbox" style="background:#080d18;border:1px solid #1a2a50">
    <h3 style="font-size:.82rem;margin-bottom:8px">📋 COMISIONES CONFIGURADAS</h3>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">
      <select id="com-filtro-ag" style="padding:7px 10px;background:#0a1828;border:2px solid #2a4a80;border-radius:3px;color:#fbbf24;font-size:.8rem">
        <option value="">— Todas las agencias —</option>
      </select>
      <button class="btn-sec" onclick="cargarTablaComisiones()">🔄 ACTUALIZAR</button>
    </div>
    <div id="com-tabla" style="max-height:500px;overflow-y:auto;overflow-x:auto"></div>
  </div>
</div>

<!-- OPERACIONES -->
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

<!-- AUDITORÍA -->
<div id="tc-auditoria" class="tc">
  <div class="fbox">
    <h3>📋 REGISTRO DE AUDITORÍA</h3>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center">
      <input type="date" id="aud-ini">
      <input type="date" id="aud-fin">
      <input type="text" id="aud-filtro" placeholder="Filtrar..." style="flex:1;min-width:140px;padding:9px 11px;background:#0a1828;border:2px solid #2a4a80;border-radius:3px;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600">
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
const LOTERIAS_DATA = {{ loterias | tojson }};
const TABS=['dashboard','resultados','tripletas','riesgo','topes','topes-ag','bloqueos','reportes','agencias','comisiones','operaciones','auditoria'];
let lotResActual='zoolo', lotLimActual='zoolo', lotRiesgoActual='zoolo', lotTopesActual='zoolo';
let animalSelAdmin=null, animalSelLim=null, animalSelTope=null;

function getHorarios(lid){
  let lot=LOTERIAS_DATA[lid];
  if(lid==='zoolo') return ["08:00 AM","09:00 AM","10:00 AM","11:00 AM","12:00 PM","01:00 PM","02:00 PM","03:00 PM","04:00 PM","05:00 PM","06:00 PM"];
  if(lot&&lot.offset_30min) return ["08:30 AM","09:30 AM","10:30 AM","11:30 AM","12:30 PM","01:30 PM","02:30 PM","03:30 PM","04:30 PM","05:30 PM","06:30 PM"];
  return ["08:00 AM","09:00 AM","10:00 AM","11:00 AM","12:00 PM","01:00 PM","02:00 PM","03:00 PM","04:00 PM","05:00 PM","06:00 PM"];
}

function showTab(id){
  TABS.forEach(t=>{
    document.getElementById('tc-'+t).classList.toggle('active',t===id);
    document.querySelectorAll('.tab')[TABS.indexOf(t)].classList.toggle('active',t===id);
  });
  if(id==='dashboard') cargarDash();
  if(id==='resultados'){setHoy('ra-fecha');setHoy('ra-fi');cargarRA();}
  if(id==='tripletas') cargarTrip();
  if(id==='riesgo') cargarRiesgo();
  if(id==='topes'){cargarTopes();if(!window._glInited){window._glInited=true;initTopeGlobal();}else{cargarTablaGlobal();}}
  if(id==='topes-ag'){if(typeof initTabTopesAg==='function'){if(!window._tapInited){window._tapInited=true;initTabTopesAg();}else{cargarTablaTopesAg();}}}
  if(id==='bloqueos'){renderLotTabs('lot-tabs-lim',lotLimActual,selLotLim);updateHorarioSelect(lotLimActual,'lim-hora');renderAnimalesMini(lotLimActual,'animals-lim',(k)=>{animalSelLim=k;document.getElementById('lim-sel-info').textContent='✓ '+k+' — '+(LOTERIAS_DATA[lotLimActual].animales[k]||'');});cargarLimites();}
  if(id==='agencias'){cargarAgs();cargarAgsSel();}
  if(id==='comisiones'){if(!window._comInited){window._comInited=true;initTabComisiones();}else{cargarTablaComisiones();}}
  if(id==='auditoria'){setHoy('aud-ini');setHoy('aud-fin');cargarAudit();}
}
function setHoy(id){let e=document.getElementById(id);if(e)e.value=new Date().toISOString().split('T')[0];}
function showMsg(id,msg,t){let e=document.getElementById(id);if(!e)return;e.innerHTML=`<div class="msg ${t}">${msg}</div>`;setTimeout(()=>e.innerHTML='',4000);}
function glMsg(msg,t){let e=document.getElementById('glmsg');e.innerHTML=`<div class="msg ${t}" style="box-shadow:0 4px 20px rgba(0,0,0,.8)">${msg}</div>`;e.style.display='block';setTimeout(()=>e.style.display='none',4000);}

// ---- LOT TABS ----
function renderLotTabs(cId,current,onClickFn){
  let c=document.getElementById(cId); if(!c)return; c.innerHTML='';
  Object.entries(LOTERIAS_DATA).forEach(([k,v])=>{
    let b=document.createElement('button'); b.className='lot-tab '+(k===current?'sel':'');
    b.style.borderColor=k===current?v.color:'#1a2540'; b.style.color=k===current?v.color:'#4a6090';
    b.style.background=k===current?`color-mix(in srgb,${v.color} 10%,#050810)`:'#0a0e18';
    b.textContent=v.emoji+' '+v.nombre; b.onclick=()=>onClickFn(k); c.appendChild(b);
  });
}
function updateHorarioSelect(lid,selId){
  let horas=getHorarios(lid); let sel=document.getElementById(selId); if(!sel)return; sel.innerHTML='';
  horas.forEach(h=>{let opt=document.createElement('option');opt.value=h;opt.textContent=h;sel.appendChild(opt);});
}
function renderAnimalesMini(lid,cId,onClickFn){
  let lot=LOTERIAS_DATA[lid]; let g=document.getElementById(cId); if(!g)return; g.innerHTML='';
  let animales=lot.animales;
  let orden=Object.keys(animales).sort((a,b)=>{let na=a==='00'?-1:parseInt(a);let nb=b==='00'?-1:parseInt(b);if(isNaN(na))na=999;if(isNaN(nb))nb=999;return na-nb;});
  orden.forEach(k=>{
    let d=document.createElement('div'); d.className='am-item';
    d.innerHTML=`<div class="anum">${k}</div><div class="anom">${animales[k]}</div>`;
    d.onclick=()=>{document.querySelectorAll('#'+cId+' .am-item').forEach(e=>e.classList.remove('sel'));d.classList.add('sel');onClickFn(k);};
    g.appendChild(d);
  });
}

// ---- DASHBOARD ----
function cargarDash(){
  fetch('/admin/reporte-agencias').then(r=>r.json()).then(d=>{
    if(d.error)return;
    document.getElementById('d-v').textContent='S/'+d.global.ventas.toFixed(2);
    document.getElementById('d-p').textContent='S/'+d.global.pagos.toFixed(2);
    document.getElementById('d-c').textContent='S/'+d.global.comisiones.toFixed(2);
    let bp=document.getElementById('d-b'); bp.textContent='S/'+d.global.balance.toFixed(2);
    bp.className=d.global.balance>=0?'g':'r';
    let html=d.agencias.length?'':'<p style="color:var(--text2);text-align:center;padding:20px;font-size:.78rem">SIN ACTIVIDAD HOY</p>';
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

// ---- RESULTADOS ----
function selLotRes(lid){
  lotResActual=lid;
  renderLotTabs('lot-tabs-res',lid,selLotRes);
  updateHorarioSelect(lid,'ra-hora');
  renderAnimalesMini(lid,'animals-mini-res',(k)=>{animalSelAdmin=k;document.getElementById('animal-sel-info').textContent='✓ '+k+' — '+(LOTERIAS_DATA[lid].animales[k]||'');});
  animalSelAdmin=null; document.getElementById('animal-sel-info').textContent=''; cargarRA();
}
function cargarRA(){
  let f=document.getElementById('ra-fecha').value; if(!f)return;
  let c=document.getElementById('ra-lista');
  c.innerHTML='<p style="color:var(--text2);text-align:center;padding:12px;font-size:.75rem">CARGANDO...</p>';
  fetch('/api/resultados-fecha',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha:f,loteria:lotResActual})})
  .then(r=>r.json()).then(d=>{
    let lot=LOTERIAS_DATA[lotResActual]; let horas=d.horarios||getHorarios(lotResActual); let html='';
    horas.forEach(h=>{
      let res=d.resultados[h];
      html+=`<div class="ri ${res?'ok':''}">
        <span style="color:${lot.color};font-weight:700;font-family:'Oswald',sans-serif;font-size:.82rem">${h}</span>
        <div style="display:flex;align-items:center;gap:8px">
          ${res?`<span style="color:var(--green);font-weight:600">${res.animal} — ${res.nombre}</span>`:'<span style="color:#1e2a40;font-size:.78rem">PENDIENTE</span>'}
          <button class="btn-edit" onclick="preRA('${h}','${f}',${res?`'${res.animal}'`:'null'})">${res?'✏️':'➕'}</button>
        </div>
      </div>`;
    });
    c.innerHTML=html||'<p style="color:var(--text2);text-align:center;padding:10px;font-size:.75rem">Sin resultados</p>';
  });
}
function preRA(h,f,a){
  document.getElementById('ra-hora').value=h; document.getElementById('ra-fi').value=f;
  if(a&&a!=='null'){
    document.querySelectorAll('#animals-mini-res .am-item').forEach(e=>{
      e.classList.toggle('sel',e.querySelector('.anum').textContent===a);
    });
    animalSelAdmin=a; document.getElementById('animal-sel-info').textContent='✓ '+a+' — '+(LOTERIAS_DATA[lotResActual].animales[a]||'');
  }
}
function guardarResultado(){
  let hora=document.getElementById('ra-hora').value;
  let fecha=document.getElementById('ra-fi').value;
  if(!animalSelAdmin){glMsg('⚠ Seleccione un animal','err');return;}
  if(!hora){glMsg('⚠ Seleccione hora','err');return;}
  let fd=new FormData(); fd.append('hora',hora);fd.append('animal',animalSelAdmin);fd.append('fecha',fecha);fd.append('loteria',lotResActual);
  fetch('/admin/guardar-resultado',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(d.status==='ok'){glMsg('✅ '+d.mensaje,'ok');cargarRA();}
    else glMsg('❌ '+d.error,'err');
  });
}

// ---- TRIPLETAS ----
function cargarTrip(){
  let l=document.getElementById('tri-lista');
  l.innerHTML='<p style="color:#4a6090;text-align:center;padding:12px;font-size:.75rem">CARGANDO...</p>';
  fetch('/admin/tripletas-hoy').then(r=>r.json()).then(d=>{
    document.getElementById('tri-stats').innerHTML=`
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <div class="sc" style="flex:1"><h3>TOTAL</h3><p>${d.total}</p></div>
        <div class="sc" style="flex:1"><h3>GANADORAS</h3><p class="g">${d.ganadoras}</p></div>
        <div class="sc" style="flex:1"><h3>PREMIOS</h3><p class="r">S/${d.total_premios.toFixed(2)}</p></div>
      </div>`;
    if(!d.tripletas||!d.tripletas.length){l.innerHTML='<p style="color:var(--text2);text-align:center;padding:20px;font-size:.78rem">No hay tripletas hoy</p>';return;}
    let html='';
    d.tripletas.forEach(tr=>{
      let lot=LOTERIAS_DATA[tr.loteria]||LOTERIAS_DATA['zoolo'];
      let salStr=tr.salieron&&tr.salieron.length?tr.salieron.join(', '):'Ninguno';
      html+=`<div style="padding:8px 10px;margin:3px 0;background:#0d0620;border-left:3px solid ${tr.gano?'#c084fc':'#3b0764'};border-radius:3px;font-size:.78rem">
        <div style="display:flex;justify-content:space-between;margin-bottom:4px">
          <span style="color:${lot.color};font-size:.7rem">${lot.emoji} ${lot.nombre}</span>
          <span style="color:#4a6090;font-size:.7rem">${tr.agencia}</span>
          <span style="color:#fbbf24;font-weight:700">S/${tr.monto} ×${lot.pago_tripleta}</span>
        </div>
        <div style="color:#e0a0ff;font-family:'Oswald',sans-serif">${tr.animal1}(${tr.nombres[0]}) · ${tr.animal2}(${tr.nombres[1]}) · ${tr.animal3}(${tr.nombres[2]})</div>
        <div style="font-size:.72rem;margin-top:3px">
          <span style="color:#4a6090">Salidos: </span><span style="color:${tr.gano?'#4ade80':'#8060c0'}">${salStr} (${tr.salieron.length}/3)</span>
          ${tr.gano?`<span style="color:#4ade80;font-weight:700;margin-left:8px">✅ GANÓ +S/${tr.premio.toFixed(2)}</span>`:''}
          ${tr.pagado?'<span style="color:#22c55e;margin-left:6px">PAGADO</span>':''}
        </div>
      </div>`;
    });
    l.innerHTML=html;
  });
}

// ---- RIESGO ----
function selLotRiesgo(lid){
  lotRiesgoActual=lid;
  renderLotTabs('lot-tabs-riesgo',lid,selLotRiesgo);
  let horas=getHorarios(lid);
  let sel=document.getElementById('riesgo-hora-sel'); sel.innerHTML='';
  horas.forEach(h=>{let opt=document.createElement('option');opt.value=h;opt.textContent=h;sel.appendChild(opt);});
  cargarRiesgo();
}
function cargarRiesgo(){
  let hora=document.getElementById('riesgo-hora-sel').value||'';
  fetch('/admin/riesgo?loteria='+lotRiesgoActual).then(r=>r.json()).then(d=>{
    if(d.error){glMsg('Error: '+d.error,'err');return;}
    document.getElementById('riesgo-hora-sel').value=d.hora_seleccionada||hora;
    document.getElementById('riesgo-info').textContent=`Sorteo: ${d.sorteo_objetivo} | Total: S/${d.total_apostado.toFixed(2)}`;
    let lot=LOTERIAS_DATA[lotRiesgoActual];
    if(!d.riesgo||!Object.keys(d.riesgo).length){
      document.getElementById('riesgo-lista').innerHTML='<p style="color:var(--text2);text-align:center;padding:15px;font-size:.78rem">Sin jugadas en este sorteo</p>';
    } else {
      let items=Object.entries(d.riesgo).sort((a,b)=>b[1].apostado-a[1].apostado);
      let html='';
      items.forEach(([sel,r])=>{
        let pct=r.porcentaje||0; let danger=r.pagaria>d.total_apostado*2;
        html+=`<div class="ri ${danger?'':'ok'}" style="border-left-color:${danger?'#dc2626':'#22c55e'}">
          <div><span style="color:var(--gold);font-family:'Oswald',sans-serif;font-weight:700">${sel}</span>
          <span style="color:var(--text2);font-size:.72rem;margin-left:6px">${r.nombre}</span></div>
          <div style="text-align:right">
            <div style="color:var(--text);font-size:.78rem">S/${r.apostado}</div>
            <div style="color:${danger?'var(--red)':'#4a6090'};font-size:.7rem">pagaría S/${r.pagaria}</div>
            <div style="color:#2a4080;font-size:.65rem">${pct}%${r.libre?'':(r.tope?' | tope:S/'+r.tope:'')}</div>
          </div>
        </div>`;
      });
      document.getElementById('riesgo-lista').innerHTML=html;
    }
    let btns='';
    (d.agencias_hora||[]).forEach(ag=>{
      btns+=`<button class="btn-sec" style="font-size:.68rem" onclick="verRiesgoAgencia(${ag.id},'${d.sorteo_objetivo}','${lotRiesgoActual}')">${ag.nombre_agencia}</button>`;
    });
    document.getElementById('riesgo-agencias-btns').innerHTML=btns||'<span style="color:var(--text2);font-size:.72rem">Sin agencias activas en este sorteo</span>';
  });
}
function verRiesgoAgencia(aid,hora,loteria){
  fetch('/admin/riesgo-agencia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agencia_id:aid,hora:hora,loteria:loteria})})
  .then(r=>r.json()).then(d=>{
    if(!d.status){glMsg(d.error,'err');return;}
    let html=`<div style="color:var(--gold);font-family:'Oswald',sans-serif;font-size:.78rem;margin-bottom:8px">🏪 ${d.agencia} — ${d.hora}</div>`;
    d.jugadas.forEach(j=>{
      html+=`<div class="ri"><span style="color:var(--teal);font-weight:700">${j.seleccion} ${j.nombre}</span>
        <span style="color:var(--text2);font-size:.7rem">${j.tipo}</span>
        <span style="color:var(--text)">S/${j.apostado}</span>
        <span style="color:#4a6090;font-size:.7rem">→S/${j.pagaria}</span></div>`;
    });
    document.getElementById('riesgo-agencia-detalle').innerHTML=html;
  });
}

// ---- TOPES ----
function selLotTopes(lid){
  lotTopesActual=lid;
  renderLotTabs('lot-tabs-topes',lid,selLotTopes);
  updateHorarioSelect(lid,'tope-hora-sel');
  renderAnimalesMini(lid,'animals-topes',(k)=>{animalSelTope=k;document.getElementById('tope-sel-info').textContent='✓ '+k+' — '+(LOTERIAS_DATA[lid].animales[k]||'');});
  animalSelTope=null; document.getElementById('tope-sel-info').textContent=''; cargarTopes();
}
function cargarTopes(){
  let hora=document.getElementById('tope-hora-sel').value; if(!hora)return;
  fetch('/admin/topes?hora='+encodeURIComponent(hora)+'&loteria='+lotTopesActual).then(r=>r.json()).then(d=>{
    if(!d.status){glMsg(d.error,'err');return;}
    if(!d.topes||!d.topes.length){document.getElementById('topes-lista').innerHTML='<p style="color:var(--text2);font-size:.75rem;padding:8px">Sin topes configurados</p>';return;}
    let html='<div style="overflow-x:auto"><table><thead><tr><th>Núm</th><th>Animal</th><th>Tope</th><th>Apostado</th><th>Disponible</th><th>Acción</th></tr></thead><tbody>';
    d.topes.forEach(t=>{
      let disp=t.disponible!==null?`S/${t.disponible}`:'libre';
      let danger=t.disponible!==null&&t.disponible<(t.tope*0.2);
      html+=`<tr style="${danger?'background:#1a0808':''}">
        <td style="color:var(--gold);font-family:'Oswald',sans-serif;font-weight:700">${t.numero}</td>
        <td>${t.nombre}</td>
        <td style="color:var(--teal)">${t.libre?'LIBRE':`S/${t.tope}`}</td>
        <td>S/${t.apostado}</td>
        <td style="color:${danger?'var(--red)':'var(--green)'}">${disp}</td>
        <td><button onclick="eliminarTope('${t.numero}')" style="padding:3px 8px;background:#1a0808;border:1px solid #6b1515;color:#e05050;font-size:.6rem;cursor:pointer;border-radius:2px">QUITAR</button></td>
      </tr>`;
    });
    html+='</tbody></table></div>';
    document.getElementById('topes-lista').innerHTML=html;
  });
}
function guardarTope(){
  if(!animalSelTope){glMsg('Seleccione un número','err');return;}
  let hora=document.getElementById('tope-hora-sel').value;
  let monto=parseFloat(document.getElementById('tope-monto').value)||0;
  fetch('/admin/topes/guardar',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({loteria:lotTopesActual,numero:animalSelTope,hora:hora,monto:monto})})
  .then(r=>r.json()).then(d=>{
    if(d.status==='ok'){glMsg('✅ Tope guardado','ok');cargarTopes();}
    else glMsg('❌ '+d.error,'err');
  });
}
function eliminarTope(numero){
  let hora=document.getElementById('tope-hora-sel').value;
  fetch('/admin/topes/guardar',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({loteria:lotTopesActual,numero:numero,hora:hora,monto:0})})
  .then(r=>r.json()).then(d=>{if(d.status==='ok'){cargarTopes();glMsg('Tope eliminado','ok');}});
}
function limpiarTopesHora(){
  let hora=document.getElementById('tope-hora-sel').value;
  if(!confirm('¿Limpiar todos los topes de '+hora+'?'))return;
  fetch('/admin/topes/limpiar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hora:hora})})
  .then(r=>r.json()).then(d=>{if(d.status==='ok'){glMsg(d.mensaje,'ok');cargarTopes();}else glMsg(d.error,'err');});
}

// ======================== TOPE GLOBAL ========================
let glLotsSelSet=new Set(), glHorasSelSet=new Set(), glNumsSelSet=new Set();
let glAllHoras=[], glAllNums={};

function initTopeGlobal(){
  // Loterías
  let c=document.getElementById('gl-loterias'); if(!c)return; c.innerHTML='';
  let filtLot=document.getElementById('gl-filtro-lot');
  filtLot.innerHTML='<option value="">— Todas las loterías —</option>';
  Object.entries(LOTERIAS_DATA).forEach(([lid,lot])=>{
    let btn=document.createElement('button');
    btn.className='ltag'+(glLotsSelSet.has(lid)?' sel':'');
    btn.dataset.id=lid;
    btn.innerHTML=`${lot.emoji} ${lot.nombre}`;
    btn.style.borderColor=glLotsSelSet.has(lid)?lot.color:'#3a2a00';
    if(glLotsSelSet.has(lid)) btn.style.background=lot.color+'33';
    btn.onclick=()=>{
      if(glLotsSelSet.has(lid)){glLotsSelSet.delete(lid);btn.classList.remove('sel');btn.style.background='';btn.style.borderColor='#3a2a00';}
      else{glLotsSelSet.add(lid);btn.classList.add('sel');btn.style.background=lot.color+'33';btn.style.borderColor=lot.color;}
      recalcGlHorasNums();
    };
    c.appendChild(btn);
    filtLot.innerHTML+=`<option value="${lid}">${lot.emoji} ${lot.nombre}</option>`;
  });
  // Poblar filtro horas
  let filtH=document.getElementById('gl-filtro-hora');
  let todasH=["08:00 AM","09:00 AM","10:00 AM","11:00 AM","12:00 PM","01:00 PM","02:00 PM","03:00 PM","04:00 PM","05:00 PM","06:00 PM",
               "08:30 AM","09:30 AM","10:30 AM","11:30 AM","12:30 PM","01:30 PM","02:30 PM","03:30 PM","04:30 PM","05:30 PM","06:30 PM"];
  filtH.innerHTML='<option value="">— Todas las horas —</option>';
  todasH.forEach(h=>filtH.innerHTML+=`<option value="${h}">${h}</option>`);
  recalcGlHorasNums();
  cargarTablaGlobal();
}

function recalcGlHorasNums(){
  glAllHoras=[]; glAllNums={};
  glLotsSelSet.forEach(lid=>{
    let lot=LOTERIAS_DATA[lid]; let horas=getHorarios(lid);
    horas.forEach(h=>{if(!glAllHoras.includes(h))glAllHoras.push(h);});
    Object.entries(lot.animales).forEach(([n,nom])=>{glAllNums[n]=nom;});
  });
  glHorasSelSet.forEach(h=>{if(!glAllHoras.includes(h))glHorasSelSet.delete(h);});
  glNumsSelSet.forEach(n=>{if(!(n in glAllNums))glNumsSelSet.delete(n);});
  renderGlHoras(); renderGlNums();
}

function renderGlHoras(){
  let c=document.getElementById('gl-horas'); if(!c)return; c.innerHTML='';
  glAllHoras.forEach(h=>{
    let btn=document.createElement('button');
    btn.className='hbtn'+(glHorasSelSet.has(h)?' sel':'');
    btn.dataset.h=h; btn.textContent=h.replace(':00','').replace(' ','');
    btn.onclick=()=>{
      if(glHorasSelSet.has(h)){glHorasSelSet.delete(h);btn.classList.remove('sel');}
      else{glHorasSelSet.add(h);btn.classList.add('sel');}
    };
    c.appendChild(btn);
  });
}

function renderGlNums(){
  let c=document.getElementById('gl-numeros'); if(!c)return; c.innerHTML='';
  let sorted=Object.keys(glAllNums).sort((a,b)=>{let ia=parseInt(a),ib=parseInt(b);return isNaN(ia)||isNaN(ib)?0:ia-ib;});
  sorted.forEach(n=>{
    let btn=document.createElement('button');
    btn.className='am-item'+(glNumsSelSet.has(n)?' sel':'');
    btn.dataset.n=n;
    btn.innerHTML=`<div class="anum">${n}</div><div class="anom">${(glAllNums[n]||'').substring(0,7)}</div>`;
    btn.onclick=()=>{
      if(glNumsSelSet.has(n)){glNumsSelSet.delete(n);btn.classList.remove('sel');}
      else{glNumsSelSet.add(n);btn.classList.add('sel');}
    };
    c.appendChild(btn);
  });
}

function glSelAllLots(){Object.keys(LOTERIAS_DATA).forEach(lid=>{glLotsSelSet.add(lid);});initTopeGlobal();}
function glDeselAllLots(){glLotsSelSet.clear();initTopeGlobal();}
function glSelAllHoras(){glAllHoras.forEach(h=>{glHorasSelSet.add(h);let b=document.querySelector(`#gl-horas button[data-h='${h}']`);if(b)b.classList.add('sel');});}
function glDeselAllHoras(){glHorasSelSet.clear();document.querySelectorAll('#gl-horas button').forEach(b=>b.classList.remove('sel'));}
function glSelAllNums(){Object.keys(glAllNums).forEach(n=>{glNumsSelSet.add(n);let b=document.querySelector(`#gl-numeros button[data-n='${n}']`);if(b)b.classList.add('sel');});}
function glDeselAllNums(){glNumsSelSet.clear();document.querySelectorAll('#gl-numeros button').forEach(b=>b.classList.remove('sel'));}

async function guardarTopeGlobal(){
  let m=document.getElementById('gl-msg');
  if(!glLotsSelSet.size){m.innerHTML='<span style="color:#e05050">Selecciona al menos una lotería</span>';return;}
  if(!glHorasSelSet.size){m.innerHTML='<span style="color:#e05050">Selecciona al menos una hora</span>';return;}
  let monto=parseFloat(document.getElementById('gl-monto').value)||0;
  m.innerHTML='<span style="color:#a07020">Guardando...</span>';
  let body={
    loteria_ids:[...glLotsSelSet],
    horas:[...glHorasSelSet],
    numeros:glNumsSelSet.size>0?[...glNumsSelSet]:[],
    monto_tope:monto
  };
  let d=await fetch('/admin/topes-global/guardar-masivo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(r=>r.json());
  if(d.status==='ok'){
    m.innerHTML=`<span style="color:#4ade80">✅ ${d.mensaje}</span>`;
    glMsg('✅ '+d.mensaje,'ok'); cargarTablaGlobal();
  } else { m.innerHTML=`<span style="color:#e05050">❌ ${d.error}</span>`; }
}

function cargarTablaGlobal(){
  let lotFil=document.getElementById('gl-filtro-lot')?document.getElementById('gl-filtro-lot').value:'';
  let horaFil=document.getElementById('gl-filtro-hora')?document.getElementById('gl-filtro-hora').value:'';
  let url='/admin/topes-global/lista?';
  if(lotFil)  url+='loteria='+encodeURIComponent(lotFil)+'&';
  if(horaFil) url+='hora='+encodeURIComponent(horaFil);
  let c=document.getElementById('gl-tabla'); if(!c)return;
  c.innerHTML='<p style="color:#a07020;font-size:.75rem;padding:6px">Cargando...</p>';
  fetch(url).then(r=>r.json()).then(d=>{
    if(d.error){c.innerHTML=`<p style="color:#e05050">${d.error}</p>`;return;}
    if(!d.topes||!d.topes.length){c.innerHTML='<p style="color:#4a4000;font-size:.75rem;padding:6px">Sin topes globales configurados</p>';return;}
    let html='<table><thead><tr><th>LOTERÍA</th><th>HORA</th><th>NUM</th><th>ANIMAL</th><th>TOPE GLOBAL</th><th>VENDIDO HOY</th><th>DISPONIBLE</th><th>%</th><th>❌</th></tr></thead><tbody>';
    d.topes.forEach(t=>{
      let danger=t.pct_usado>=80;
      let barColor=t.pct_usado>=100?'#dc2626':(t.pct_usado>=80?'#f59e0b':'#22c55e');
      html+=`<tr style="${t.pct_usado>=100?'background:#1a0808':''}">
        <td style="color:${t.loteria_color};font-size:.7rem">${t.loteria_emoji} ${t.loteria_nombre}</td>
        <td style="color:#fbbf24;font-family:'Oswald',sans-serif;font-size:.7rem">${t.hora}</td>
        <td style="color:#00d8ff;font-family:'Oswald',sans-serif;font-weight:700">${t.numero}</td>
        <td style="font-size:.65rem;color:#c0d8f0">${t.animal}</td>
        <td style="color:#fbbf24;font-weight:700;font-family:'Oswald',sans-serif">S/${t.monto_tope}</td>
        <td style="color:${barColor};font-family:'Oswald',sans-serif">S/${t.vendido_hoy}</td>
        <td style="color:${t.disponible<=0?'#dc2626':'#4ade80'};font-weight:700">S/${t.disponible}</td>
        <td>
          <div style="background:#0a0800;border-radius:3px;height:8px;width:60px;overflow:hidden">
            <div style="background:${barColor};width:${Math.min(t.pct_usado,100)}%;height:100%"></div>
          </div>
          <span style="color:${barColor};font-size:.6rem">${t.pct_usado}%</span>
        </td>
        <td><button onclick="eliminarTopeGlobal(${t.id})" style="padding:2px 5px;background:#1a0808;border:1px solid #6b1515;color:#e05050;font-size:.58rem;cursor:pointer;border-radius:2px">✕</button></td>
      </tr>`;
    });
    html+='</tbody></table>';
    c.innerHTML=html;
  });
}

function eliminarTopeGlobal(id){
  fetch('/admin/topes-global/eliminar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})})
  .then(r=>r.json()).then(d=>{if(d.status==='ok'){glMsg('Tope global eliminado','ok');cargarTablaGlobal();}else glMsg(d.error,'err');});
}

// ======================== TOPES POR AGENCIA ========================
let tapAgsData=[];    // [{id,nombre}]
let tapAgsSelSet=new Set();
let tapLotsSelSet=new Set();
let tapHorasSelSet=new Set();
let tapNumsSelSet=new Set();
let tapAllHoras=[];   // union de horas de loterías seleccionadas
let tapAllNums={};    // {num: nombre} union de loterías seleccionadas

function initTabTopesAg(){
  // Cargar agencias
  fetch('/admin/lista-agencias').then(r=>r.json()).then(ags=>{
    tapAgsData=ags;
    let c=document.getElementById('tap-agencias');
    c.innerHTML='';
    // Populate filtro select
    let fag=document.getElementById('tap-filtro-ag');
    fag.innerHTML='<option value="">— Todas las agencias —</option>';
    ags.forEach(ag=>{
      let btn=document.createElement('button');
      btn.className='ltag'; btn.dataset.id=ag.id;
      btn.textContent=ag.nombre_agencia;
      btn.style.border='2px solid #2a4a80';
      btn.onclick=()=>tapToggleAg(ag.id,btn);
      c.appendChild(btn);
      fag.innerHTML+=`<option value="${ag.id}">${ag.nombre_agencia}</option>`;
    });
    // Populate filtro lot
    let flot=document.getElementById('tap-filtro-lot');
    flot.innerHTML='<option value="">— Todas las loterías —</option>';
    Object.entries(LOTERIAS_DATA).forEach(([k,v])=>{
      flot.innerHTML+=`<option value="${k}">${v.emoji} ${v.nombre}</option>`;
    });
    renderTopesAgLots();
    cargarTablaTopesAg();
  });
}

function renderTopesAgLots(){
  let c=document.getElementById('tap-loterias');
  c.innerHTML='';
  Object.entries(LOTERIAS_DATA).forEach(([lid,lot])=>{
    let btn=document.createElement('button');
    btn.className='ltag'+(tapLotsSelSet.has(lid)?' sel':'');
    btn.dataset.id=lid;
    btn.innerHTML=`${lot.emoji} ${lot.nombre}`;
    btn.style.borderColor=tapLotsSelSet.has(lid)?lot.color:'#2a4a80';
    if(tapLotsSelSet.has(lid)) btn.style.background=lot.color+'33';
    btn.onclick=()=>tapToggleLot(lid,btn,lot);
    c.appendChild(btn);
  });
  recalcHorasNums();
}

function tapToggleAg(id,btn){
  if(tapAgsSelSet.has(id)){tapAgsSelSet.delete(id);btn.classList.remove('sel');btn.style.background='';btn.style.borderColor='#2a4a80';}
  else{tapAgsSelSet.add(id);btn.classList.add('sel');btn.style.background='#0a2a5a';btn.style.borderColor='#00b4d8';}
  updateTapResumen();
}
function tapToggleLot(lid,btn,lot){
  if(tapLotsSelSet.has(lid)){tapLotsSelSet.delete(lid);btn.classList.remove('sel');btn.style.background='';btn.style.borderColor='#2a4a80';}
  else{tapLotsSelSet.add(lid);btn.classList.add('sel');btn.style.background=lot.color+'33';btn.style.borderColor=lot.color;}
  recalcHorasNums();
}
function tapToggleHora(h,btn){
  if(tapHorasSelSet.has(h)){tapHorasSelSet.delete(h);btn.classList.remove('sel');}
  else{tapHorasSelSet.add(h);btn.classList.add('sel');}
  updateTapResumen();
}
function tapToggleNum(n,btn){
  if(tapNumsSelSet.has(n)){tapNumsSelSet.delete(n);btn.classList.remove('sel');}
  else{tapNumsSelSet.add(n);btn.classList.add('sel');}
  updateTapResumen();
}

function tapSelAllAgs(){
  tapAgsData.forEach(ag=>{
    tapAgsSelSet.add(ag.id);
    let btn=document.querySelector(`#tap-agencias button[data-id='${ag.id}']`);
    if(btn){btn.classList.add('sel');btn.style.background='#0a2a5a';btn.style.borderColor='#00b4d8';}
  });
  updateTapResumen();
}
function tapDeselAllAgs(){
  tapAgsSelSet.clear();
  document.querySelectorAll('#tap-agencias button').forEach(btn=>{btn.classList.remove('sel');btn.style.background='';btn.style.borderColor='#2a4a80';});
  updateTapResumen();
}
function tapSelAllLots(){
  Object.keys(LOTERIAS_DATA).forEach(lid=>{tapLotsSelSet.add(lid);});
  renderTopesAgLots();
}
function tapDeselAllLots(){
  tapLotsSelSet.clear();
  renderTopesAgLots();
}
function tapSelAllHoras(){
  tapAllHoras.forEach(h=>{
    tapHorasSelSet.add(h);
    let btn=document.querySelector(`#tap-horas button[data-h='${h}']`);
    if(btn) btn.classList.add('sel');
  });
  updateTapResumen();
}
function tapDeselAllHoras(){
  tapHorasSelSet.clear();
  document.querySelectorAll('#tap-horas button').forEach(b=>b.classList.remove('sel'));
  updateTapResumen();
}
function tapSelAllNums(){
  Object.keys(tapAllNums).forEach(n=>{
    tapNumsSelSet.add(n);
    let btn=document.querySelector(`#tap-numeros button[data-n='${n}']`);
    if(btn) btn.classList.add('sel');
  });
  updateTapResumen();
}
function tapDeselAllNums(){
  tapNumsSelSet.clear();
  document.querySelectorAll('#tap-numeros button').forEach(b=>b.classList.remove('sel'));
  updateTapResumen();
}

function recalcHorasNums(){
  // Recalcular unión de horas y números de las loterías seleccionadas
  tapAllHoras=[];
  tapAllNums={};
  tapLotsSelSet.forEach(lid=>{
    let lot=LOTERIAS_DATA[lid];
    let horas=getHorarios(lid);
    horas.forEach(h=>{if(!tapAllHoras.includes(h)) tapAllHoras.push(h);});
    Object.entries(lot.animales).forEach(([n,nom])=>{tapAllNums[n]=nom;});
  });
  // Limpiar selecciones que ya no aplican
  tapHorasSelSet.forEach(h=>{if(!tapAllHoras.includes(h)) tapHorasSelSet.delete(h);});
  tapNumsSelSet.forEach(n=>{if(!(n in tapAllNums)) tapNumsSelSet.delete(n);});
  renderTopesAgHoras(); renderTopesAgNums(); updateTapResumen();
}

function renderTopesAgHoras(){
  let c=document.getElementById('tap-horas'); c.innerHTML='';
  tapAllHoras.forEach(h=>{
    let btn=document.createElement('button');
    btn.className='hbtn'+(tapHorasSelSet.has(h)?' sel':'');
    btn.dataset.h=h;
    btn.textContent=h.replace(':00','').replace(' ','');
    btn.onclick=()=>tapToggleHora(h,btn);
    c.appendChild(btn);
  });
}

function renderTopesAgNums(){
  let c=document.getElementById('tap-numeros'); c.innerHTML='';
  let sorted=Object.keys(tapAllNums).sort((a,b)=>{let ia=parseInt(a),ib=parseInt(b);return isNaN(ia)||isNaN(ib)?0:ia-ib;});
  sorted.forEach(n=>{
    let btn=document.createElement('button');
    btn.className='am-item'+(tapNumsSelSet.has(n)?' sel':'');
    btn.dataset.n=n;
    btn.innerHTML=`<div class="anum">${n}</div><div class="anom">${(tapAllNums[n]||'').substring(0,8)}</div>`;
    btn.onclick=()=>tapToggleNum(n,btn);
    c.appendChild(btn);
  });
}

function updateTapResumen(){
  let nAg=tapAgsSelSet.size, nLot=tapLotsSelSet.size, nH=tapHorasSelSet.size;
  let nN=tapNumsSelSet.size||Object.keys(tapAllNums).length;
  let total=nAg*nLot*nH*nN;
  document.getElementById('tap-resumen').textContent=
    `${nAg} agencia(s) × ${nLot} lotería(s) × ${nH} hora(s) × ${tapNumsSelSet.size||'TODOS ('+Object.keys(tapAllNums).length+')'} números → ${total} tope(s) a aplicar`;
}

async function guardarTopesAgMasivo(){
  let monto=parseFloat(document.getElementById('tap-monto').value)||0;
  let pct=parseFloat(document.getElementById('tap-pct').value)||0;
  let m=document.getElementById('tap-msg');
  if(!tapAgsSelSet.size){m.innerHTML='<span style="color:#e05050">Seleccione al menos una agencia</span>';return;}
  if(!tapLotsSelSet.size){m.innerHTML='<span style="color:#e05050">Seleccione al menos una lotería</span>';return;}
  if(!tapHorasSelSet.size){m.innerHTML='<span style="color:#e05050">Seleccione al menos una hora</span>';return;}
  m.innerHTML='<span style="color:#60a0d0">Guardando...</span>';
  let body={
    agencia_ids:[...tapAgsSelSet],
    loteria_ids:[...tapLotsSelSet],
    horas:[...tapHorasSelSet],
    numeros:tapNumsSelSet.size>0?[...tapNumsSelSet]:[],
    monto_tope:monto,
    porcentaje:pct
  };
  let d=await fetch('/admin/topes-agencia/guardar-masivo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(r=>r.json());
  if(d.status==='ok'){m.innerHTML=`<span style="color:#4ade80">✅ ${d.mensaje}</span>`;glMsg('✅ '+d.mensaje,'ok');cargarTablaTopesAg();}
  else{m.innerHTML=`<span style="color:#e05050">❌ ${d.error}</span>`;glMsg('❌ '+d.error,'err');}
}

async function limpiarTopesAgSel(){
  if(!confirm('¿Eliminar los topes seleccionados (monto=0)?'))return;
  document.getElementById('tap-monto').value='0';
  document.getElementById('tap-pct').value='0';
  await guardarTopesAgMasivo();
}

function cargarTablaTopesAg(){
  let agFil=document.getElementById('tap-filtro-ag').value;
  let lotFil=document.getElementById('tap-filtro-lot').value;
  let url='/admin/topes-agencia/lista?';
  if(agFil) url+='agencia_id='+agFil+'&';
  if(lotFil) url+='loteria='+lotFil;
  let c=document.getElementById('tap-tabla');
  c.innerHTML='<p style="color:#4a6090;font-size:.75rem;padding:8px">Cargando...</p>';
  fetch(url).then(r=>r.json()).then(d=>{
    if(d.error){c.innerHTML=`<p style="color:#e05050">${d.error}</p>`;return;}
    if(!d.topes||!d.topes.length){c.innerHTML='<p style="color:var(--text2);font-size:.75rem;padding:8px">Sin topes configurados</p>';return;}
    let html='<table><thead><tr><th>AGENCIA</th><th>LOTERÍA</th><th>HORA</th><th>NUM</th><th>ANIMAL</th><th>TOPE S/</th><th>%</th><th>APOST.</th><th>DISP.</th><th>❌</th></tr></thead><tbody>';
    d.topes.forEach(t=>{
      let lot=LOTERIAS_DATA[t.loteria]||{color:'#fff',emoji:''};
      let danger=t.disponible!==null&&t.disponible<t.monto_tope*0.2;
      html+=`<tr style="${danger?'background:#1a0808':''}">
        <td style="color:var(--gold);font-size:.72rem">${t.agencia_nombre}</td>
        <td style="color:${lot.color||'#fff'};font-size:.7rem">${lot.emoji||''} ${t.loteria_nombre}</td>
        <td style="color:#fbbf24;font-family:'Oswald',sans-serif;font-size:.7rem">${t.hora}</td>
        <td style="color:#00d8ff;font-family:'Oswald',sans-serif;font-weight:700">${t.numero}</td>
        <td style="font-size:.68rem;color:#c0d8f0">${t.animal}</td>
        <td style="color:#4ade80;font-weight:700">S/${t.monto_tope}</td>
        <td style="color:#c084fc">${t.porcentaje>0?t.porcentaje+'%':'—'}</td>
        <td>S/${t.apostado}</td>
        <td style="color:${danger?'#e05050':'#4ade80'}">${t.disponible!==null?'S/'+t.disponible:'libre'}</td>
        <td><button onclick="eliminarTopeAg(${t.id})" style="padding:2px 6px;background:#1a0808;border:1px solid #6b1515;color:#e05050;font-size:.58rem;cursor:pointer;border-radius:2px">✕</button></td>
      </tr>`;
    });
    html+='</tbody></table>';
    c.innerHTML=html;
  });
}

function eliminarTopeAg(id){
  fetch('/admin/topes-agencia/eliminar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})})
  .then(r=>r.json()).then(d=>{if(d.status==='ok'){glMsg('Tope eliminado','ok');cargarTablaTopesAg();}else glMsg(d.error,'err');});
}

function limpiarTopesAgFiltro(){
  let agFil=document.getElementById('tap-filtro-ag').value;
  let lotFil=document.getElementById('tap-filtro-lot').value;
  fetch('/admin/topes-agencia/limpiar-agencia',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({agencia_id:agFil||null,loteria:lotFil||''})})
  .then(r=>r.json()).then(d=>{if(d.status==='ok'){glMsg(d.mensaje,'ok');cargarTablaTopesAg();}else glMsg(d.error,'err');});
}

// ---- BLOQUEOS (limites_venta) ----
function selLotLim(lid){
  lotLimActual=lid;
  renderLotTabs('lot-tabs-lim',lid,selLotLim);
  updateHorarioSelect(lid,'lim-hora');
  renderAnimalesMini(lid,'animals-lim',(k)=>{animalSelLim=k;document.getElementById('lim-sel-info').textContent='✓ '+k+' — '+(LOTERIAS_DATA[lid].animales[k]||'');});
  animalSelLim=null; document.getElementById('lim-sel-info').textContent=''; cargarLimites();
}
function guardarLimite(){
  if(!animalSelLim){glMsg('Seleccione un animal','err');return;}
  let hora=document.getElementById('lim-hora').value;
  let monto=parseFloat(document.getElementById('lim-monto').value)||0;
  fetch('/api/guardar-limite',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({loteria:lotLimActual,numero:animalSelLim,hora:hora,monto_max:monto,bloqueado:monto===0})})
  .then(r=>r.json()).then(d=>{
    if(d.status==='ok'){glMsg(d.mensaje,'ok');cargarLimites();}
    else glMsg(d.error,'err');
  });
}
function cargarLimites(){
  let c=document.getElementById('lista-limites');
  c.innerHTML='<p style="color:var(--text2);font-size:.72rem">Cargando...</p>';
  fetch('/api/limites-actuales?loteria='+lotLimActual).then(r=>r.json()).then(d=>{
    if(!d.limites||Object.keys(d.limites).length===0){c.innerHTML='<p style="color:var(--text2);font-size:.72rem">Sin límites configurados</p>';return;}
    let html='';
    Object.values(d.limites).forEach(l=>{
      let cls=l.bloqueado?'bloq':'lim';
      let txt=l.bloqueado?'BLOQUEADO':`Límite: S/${l.monto_max}`;
      html+=`<div class="lim-item ${cls}">
        <div class="ln">${l.numero}</div>
        <div class="lh">${l.hora}</div>
        <div class="lm">${txt}</div>
        <button onclick="eliminarLimite('${l.numero}','${l.hora}')" style="margin-top:4px;width:100%;padding:3px;background:#1a0808;border:1px solid #6b1515;color:#e05050;font-size:.6rem;cursor:pointer;border-radius:2px">QUITAR</button>
      </div>`;
    });
    c.innerHTML=html;
  });
}
function eliminarLimite(numero,hora){
  fetch('/api/eliminar-limite',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({loteria:lotLimActual,numero:numero,hora:hora})})
  .then(r=>r.json()).then(d=>{if(d.status==='ok'){cargarLimites();glMsg('Límite eliminado','ok');}});
}

// ---- REPORTES ----
function generarReporte(){
  let fi=document.getElementById('rep-ini').value; let ff=document.getElementById('rep-fin').value;
  if(!fi||!ff){glMsg('Seleccione fechas','err');return;}
  fetch('/admin/estadisticas-rango',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:fi,fecha_fin:ff})})
  .then(r=>r.json()).then(d=>{
    document.getElementById('rep-out').style.display='block';
    document.getElementById('rv').textContent='S/'+d.totales.ventas.toFixed(2);
    document.getElementById('rp').textContent='S/'+d.totales.premios.toFixed(2);
    document.getElementById('rc').textContent='S/'+d.totales.comisiones.toFixed(2);
    document.getElementById('rb').textContent='S/'+d.totales.balance.toFixed(2);
    let html='';
    d.resumen_por_dia.forEach(r=>{
      html+=`<tr><td>${r.fecha}</td><td>${r.tickets}</td><td>S/${r.ventas}</td><td style="color:var(--red)">S/${r.premios}</td><td>S/${r.comisiones}</td><td style="color:${r.balance>=0?'var(--green)':'var(--red)'}">S/${r.balance}</td></tr>`;
    });
    document.getElementById('rep-tbody').innerHTML=html;
  });
  fetch('/admin/reporte-agencias-rango',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:fi,fecha_fin:ff})})
  .then(r=>r.json()).then(d=>{
    let html='<div style="overflow-x:auto"><table><thead><tr><th>Agencia</th><th>Usuario</th><th>Tickets</th><th>Ventas</th><th>Premios</th><th>Comisión</th><th>Balance</th></tr></thead><tbody>';
    d.agencias.forEach(a=>{
      html+=`<tr><td style="color:var(--gold)">${a.nombre}</td><td>${a.usuario}</td><td>${a.tickets}</td>
        <td>S/${a.ventas}</td><td style="color:var(--red)">S/${a.premios_teoricos}</td>
        <td>S/${a.comision}</td><td style="color:${a.balance>=0?'var(--green)':'var(--red)'}">S/${a.balance}</td></tr>`;
    });
    html+='</tbody></table></div>';
    document.getElementById('rep-ags').innerHTML=html;
  });
}
function exportarCSV(){
  let fi=document.getElementById('rep-ini').value; let ff=document.getElementById('rep-fin').value;
  if(!fi||!ff){glMsg('Seleccione fechas','err');return;}
  fetch('/admin/exportar-csv',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:fi,fecha_fin:ff})})
  .then(r=>r.blob()).then(b=>{
    let a=document.createElement('a'); a.href=URL.createObjectURL(b); a.download='reporte.csv'; a.click();
  });
}
function cargarAgsSel(){
  fetch('/admin/lista-agencias').then(r=>r.json()).then(d=>{
    let sel=document.getElementById('rep-ag-sel'); if(!sel)return;
    let val=sel.value; sel.innerHTML='<option value="">— Seleccione —</option>';
    d.forEach(a=>sel.innerHTML+=`<option value="${a.id}">${a.nombre_agencia} (${a.usuario})</option>`);
    if(val) sel.value=val;
    // Populate loteria select for report
    let lotSel=document.getElementById('rep-ag-lot');
    if(lotSel&&!lotSel.options.length){Object.entries(LOTERIAS_DATA).forEach(([k,v])=>{lotSel.innerHTML+=`<option value="${k}">${v.emoji} ${v.nombre}</option>`;});}
  });
}
function reporteAgenciaHoras(){
  let ag=document.getElementById('rep-ag-sel').value;
  let fi=document.getElementById('rep-ag-ini').value; let ff=document.getElementById('rep-ag-fin').value;
  let lot=document.getElementById('rep-ag-lot').value||'zoolo';
  if(!ag||!fi||!ff){glMsg('Complete todos los campos','err');return;}
  fetch('/admin/reporte-agencia-horas',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agencia_id:parseInt(ag),fecha_inicio:fi,fecha_fin:ff,loteria:lot})})
  .then(r=>r.json()).then(d=>{
    if(!d.status){glMsg(d.error,'err');return;}
    let lot2=LOTERIAS_DATA[lot]||LOTERIAS_DATA['zoolo'];
    let html=`<div style="color:var(--gold);font-family:'Oswald',sans-serif;font-size:.78rem;margin-bottom:8px">${d.agencia} (${d.usuario}) — Total: S/${d.total_general}</div>`;
    d.resumen.forEach(hr=>{
      html+=`<div class="sbox" style="margin-bottom:6px">
        <div class="srow"><span class="sl">Hora</span><span class="sv">${hr.hora}</span><span style="color:var(--green);font-family:'Oswald',sans-serif">S/${hr.total}</span></div>`;
      hr.jugadas.forEach(j=>{
        html+=`<div style="display:flex;justify-content:space-between;font-size:.75rem;padding:3px 0;border-bottom:1px solid #0a1020">
          <span style="color:var(--text2)">${j.seleccion} ${j.nombre}</span>
          <span style="color:var(--text)">S/${j.apostado} (${j.cnt})</span></div>`;
      });
      html+='</div>';
    });
    document.getElementById('rep-ag-out').innerHTML=html;
  });
}

// ---- AGENCIAS ----
function cargarAgs(){
  fetch('/admin/lista-agencias').then(r=>r.json()).then(d=>{
    let t=document.getElementById('tabla-ags'); t.innerHTML='';
    d.forEach(a=>{
      let comPct=(a.comision*100);
      let comColor=comPct===0?'#4a6090':(comPct>20?'#f87171':'#4ade80');
      let tope=a.tope_taquilla>0?`<span style="color:#fbbf24;font-family:'Oswald',sans-serif">S/${a.tope_taquilla}</span>`:`<span style="color:#22c55e;font-size:.75rem">SIN LÍMITE</span>`;
      t.innerHTML+=`<tr>
        <td>${a.id}</td>
        <td style="color:#a0c8f8;font-family:'Oswald',sans-serif">${a.usuario}</td>
        <td><b style="color:var(--gold)">${a.nombre_agencia}</b></td>
        <td><span style="color:${comColor};font-family:'Oswald',sans-serif;font-size:.95rem;font-weight:700">${comPct.toFixed(1)}%</span></td>
        <td>${tope}</td>
        <td><span style="color:${a.activa?'var(--green)':'var(--red)'}">● ${a.activa?'ACTIVA':'INACTIVA'}</span></td>
        <td style="display:flex;gap:4px">
          <button class="btn-edit" onclick="abrirEditAg(${a.id},'${a.nombre_agencia}',${comPct.toFixed(1)},${a.tope_taquilla||0})">✏️ Editar</button>
          <button class="btn-sec" onclick="toggleAg(${a.id},${a.activa})" style="font-size:.7rem">${a.activa?'Desactivar':'Activar'}</button>
          <button style="padding:5px 8px;background:#3a0808;border:1px solid #6b1515;color:#f87171;font-size:.68rem;cursor:pointer;border-radius:2px;font-family:'Oswald',sans-serif;font-weight:700" onclick="eliminarAg(${a.id},'${a.nombre_agencia}')">🗑 ELIMINAR</button>
        </td>
      </tr>`;
    });
  });
}
function abrirEditAg(id,nombre,com,tope){
  document.getElementById('edit-ag-id').value=id;
  document.getElementById('edit-ag-nombre-title').textContent=nombre;
  document.getElementById('edit-ag-pass').value='';
  document.getElementById('edit-ag-com').value=com;
  document.getElementById('edit-ag-com-actual').textContent=parseFloat(com).toFixed(1)+'%';
  document.getElementById('edit-ag-tope').value=tope||0;
  document.getElementById('edit-ag-box').style.display='block';
  document.getElementById('edit-ag-msg').innerHTML='';
  document.getElementById('edit-ag-box').scrollIntoView({behavior:'smooth'});
  document.getElementById('edit-ag-com').focus();
  // Live preview while typing
  document.getElementById('edit-ag-com').oninput=function(){
    document.getElementById('edit-ag-com-actual').textContent=(parseFloat(this.value)||0).toFixed(1)+'%';
  };
}
// ======================== COMISIONES POR LOTERÍA ========================
let comAgsData=[], comAgsSelSet=new Set();

function initTabComisiones(){
  fetch('/admin/lista-agencias').then(r=>r.json()).then(ags=>{
    comAgsData=ags;
    let c=document.getElementById('com-agencias'); c.innerHTML='';
    let fag=document.getElementById('com-filtro-ag');
    fag.innerHTML='<option value="">— Todas las agencias —</option>';
    ags.forEach(ag=>{
      let btn=document.createElement('button');
      btn.className='ltag'; btn.dataset.id=ag.id;
      btn.innerHTML=`${ag.nombre_agencia} <span style="color:#4a6090;font-size:.6rem">(${(ag.comision*100).toFixed(1)}% gral)</span>`;
      btn.style.border='2px solid #2a4a80';
      btn.onclick=()=>comToggleAg(ag.id,btn);
      c.appendChild(btn);
      fag.innerHTML+=`<option value="${ag.id}">${ag.nombre_agencia}</option>`;
    });
    renderComLoteriasGrid();
    cargarTablaComisiones();
  });
}

function renderComLoteriasGrid(){
  let g=document.getElementById('com-loterias-grid'); g.innerHTML='';
  Object.entries(LOTERIAS_DATA).forEach(([lid,lot])=>{
    let div=document.createElement('div');
    div.style.cssText='background:#0a1020;border:1px solid #1a2a50;border-radius:4px;padding:8px';
    div.innerHTML=`
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
        <span style="font-size:.9rem">${lot.emoji}</span>
        <span style="color:${lot.color};font-family:'Oswald',sans-serif;font-size:.78rem;font-weight:700">${lot.nombre}</span>
      </div>
      <div style="display:flex;align-items:center;gap:4px">
        <input type="number" id="com-pct-${lid}" placeholder="% (vacío=gral)" min="0" max="100" step="0.5"
          style="width:100%;padding:8px;background:#0a1828;border:2px solid #2a4080;border-radius:3px;color:#fbbf24;font-family:'Oswald',sans-serif;font-size:1rem;font-weight:700;text-align:center">
        <span style="color:#4a6090;font-size:.9rem">%</span>
      </div>`;
    g.appendChild(div);
  });
}

function comToggleAg(id,btn){
  if(comAgsSelSet.has(id)){comAgsSelSet.delete(id);btn.classList.remove('sel');btn.style.background='';btn.style.borderColor='#2a4a80';}
  else{comAgsSelSet.add(id);btn.classList.add('sel');btn.style.background='#0a2a5a';btn.style.borderColor='#00b4d8';}
}
function comSelAllAgs(){
  comAgsData.forEach(ag=>{
    comAgsSelSet.add(ag.id);
    let btn=document.querySelector(`#com-agencias button[data-id='${ag.id}']`);
    if(btn){btn.classList.add('sel');btn.style.background='#0a2a5a';btn.style.borderColor='#00b4d8';}
  });
}
function comDeselAllAgs(){
  comAgsSelSet.clear();
  document.querySelectorAll('#com-agencias button').forEach(b=>{b.classList.remove('sel');b.style.background='';b.style.borderColor='#2a4a80';});
}

async function guardarComisionesLot(){
  let m=document.getElementById('com-msg');
  if(!comAgsSelSet.size){m.innerHTML='<span style="color:#e05050">Seleccione al menos una agencia</span>';return;}
  let comisiones={};
  Object.keys(LOTERIAS_DATA).forEach(lid=>{
    let inp=document.getElementById('com-pct-'+lid);
    if(inp&&inp.value!==''){
      let v=parseFloat(inp.value);
      if(!isNaN(v)&&v>=0) comisiones[lid]=v/100;
    }
  });
  if(!Object.keys(comisiones).length){m.innerHTML='<span style="color:#e05050">Ingresa al menos un % para una lotería</span>';return;}
  m.innerHTML='<span style="color:#60a0d0">Guardando...</span>';
  let d=await fetch('/admin/comisiones-loteria/guardar',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({agencia_ids:[...comAgsSelSet],comisiones})}).then(r=>r.json());
  if(d.status==='ok'){
    m.innerHTML=`<span style="color:#4ade80">✅ ${d.mensaje}</span>`;
    glMsg('✅ '+d.mensaje,'ok'); cargarTablaComisiones();
  } else { m.innerHTML=`<span style="color:#e05050">❌ ${d.error}</span>`; }
}

async function borrarComisionesLot(){
  let agFil=document.getElementById('com-filtro-ag').value;
  if(!confirm('¿Borrar comisiones por lotería'+(agFil?' de esta agencia':' de todas las agencias')+'?'))return;
  let ids=agFil?[parseInt(agFil)]:comAgsData.map(a=>a.id);
  let count=0;
  for(let aid of ids){
    let rows=await fetch('/admin/comisiones-loteria/lista?agencia_id='+aid).then(r=>r.json());
    for(let row of (rows.comisiones||[])){
      await fetch('/admin/comisiones-loteria/eliminar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:row.id})});
      count++;
    }
  }
  glMsg(`✅ ${count} comisión(es) eliminadas`,'ok'); cargarTablaComisiones();
}

function cargarTablaComisiones(){
  let agFil=document.getElementById('com-filtro-ag')?document.getElementById('com-filtro-ag').value:'';
  let url='/admin/comisiones-loteria/lista'+(agFil?'?agencia_id='+agFil:'');
  let c=document.getElementById('com-tabla'); if(!c)return;
  c.innerHTML='<p style="color:#4a6090;font-size:.75rem;padding:8px">Cargando...</p>';
  fetch(url).then(r=>r.json()).then(d=>{
    if(d.error){c.innerHTML=`<p style="color:#e05050">${d.error}</p>`;return;}
    if(!d.comisiones||!d.comisiones.length){
      c.innerHTML='<p style="color:var(--text2);font-size:.75rem;padding:8px">Sin comisiones por lotería — se usa el % general de cada agencia</p>';return;
    }
    let html='<table><thead><tr><th>AGENCIA</th><th>LOTERÍA</th><th>% GENERAL</th><th>% ESPECÍFICO</th><th>❌</th></tr></thead><tbody>';
    d.comisiones.forEach(row=>{
      let lot=LOTERIAS_DATA[row.loteria]||{emoji:'',color:'#fff'};
      let diff=row.comision-row.com_general;
      let diffColor=diff>0?'#f87171':(diff<0?'#4ade80':'#fbbf24');
      html+=`<tr>
        <td style="color:var(--gold);font-size:.75rem">${row.agencia_nombre}</td>
        <td style="color:${lot.color||'#fff'};font-size:.72rem">${lot.emoji||''} ${row.loteria_nombre}</td>
        <td style="color:#4a6090;font-family:'Oswald',sans-serif">${row.com_general.toFixed(1)}%</td>
        <td style="font-family:'Oswald',sans-serif;font-weight:700">
          <span style="color:#fbbf24;font-size:1rem">${row.comision.toFixed(1)}%</span>
          <span style="color:${diffColor};font-size:.68rem;margin-left:4px">${diff>=0?'+':''}${diff.toFixed(1)}%</span>
        </td>
        <td><button onclick="eliminarComisionLot(${row.id})" style="padding:2px 6px;background:#1a0808;border:1px solid #6b1515;color:#e05050;font-size:.58rem;cursor:pointer;border-radius:2px">✕</button></td>
      </tr>`;
    });
    html+='</tbody></table>';
    c.innerHTML=html;
  });
}
function eliminarComisionLot(id){
  fetch('/admin/comisiones-loteria/eliminar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})})
  .then(r=>r.json()).then(d=>{if(d.status==='ok'){glMsg('Eliminado','ok');cargarTablaComisiones();}else glMsg(d.error,'err');});
}
function guardarEditAg(){
  let id=document.getElementById('edit-ag-id').value;
  let pass=document.getElementById('edit-ag-pass').value.trim();
  let com=document.getElementById('edit-ag-com').value;
  let tope=document.getElementById('edit-ag-tope').value;
  let payload={id:parseInt(id)};
  if(pass) payload.password=pass;
  if(com!=='') payload.comision=parseFloat(com);
  if(tope!=='') payload.tope_taquilla=parseFloat(tope);
  fetch('/admin/editar-agencia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
  .then(r=>r.json()).then(d=>{
    if(d.status==='ok'){showMsg('edit-ag-msg','✅ Cambios guardados','ok');cargarAgs();setTimeout(()=>{document.getElementById('edit-ag-box').style.display='none';},1500);}
    else showMsg('edit-ag-msg','❌ '+d.error,'err');
  });
}
function crearAg(){
  let u=document.getElementById('ag-u').value.trim(); let p=document.getElementById('ag-p').value.trim(); let n=document.getElementById('ag-n').value.trim();
  if(!u||!p||!n){showMsg('ag-msg','Complete todos los campos','err');return;}
  let form=new FormData(); form.append('usuario',u);form.append('password',p);form.append('nombre',n);
  fetch('/admin/crear-agencia',{method:'POST',body:form}).then(r=>r.json()).then(d=>{
    if(d.status==='ok'){showMsg('ag-msg','✅ '+d.mensaje,'ok');document.getElementById('ag-u').value='';document.getElementById('ag-p').value='';document.getElementById('ag-n').value='';cargarAgs();}
    else showMsg('ag-msg','❌ '+d.error,'err');
  });
}
function toggleAg(id,a){
  fetch('/admin/editar-agencia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,activa:!a})})
  .then(r=>r.json()).then(d=>{if(d.status==='ok')cargarAgs();else glMsg(d.error,'err');});
}
function eliminarAg(id,nombre){
  if(!confirm(`⚠️ ¿Eliminar agencia "${nombre}"?\n\nSolo se puede eliminar si no tiene tickets activos.\nEsta acción es irreversible.`))return;
  fetch('/admin/eliminar-agencia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})})
  .then(r=>r.json()).then(d=>{
    if(d.status==='ok'){glMsg('✅ '+d.mensaje,'ok');cargarAgs();}
    else glMsg('❌ '+d.error,'err');
  });
}

// ---- OPERACIONES ----
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
        let lot=LOTERIAS_DATA[j.loteria]||LOTERIAS_DATA['zoolo'];
        let rn=j.resultado?(j.resultado+' '+(j.resultado_nombre||'')):'PEND';
        jhtml+=`<div style="display:flex;align-items:center;gap:6px;padding:4px 6px;margin:2px 0;background:#060c1a;border-left:3px solid ${j.gano?'#22c55e':'#1a2a50'};border-radius:2px;font-size:.75rem">
          <span style="color:${lot.color};font-size:.65rem">${lot.emoji}</span>
          <span style="color:#00c8e8;font-family:'Oswald',sans-serif;font-size:.7rem;min-width:48px;font-weight:700">${(j.hora||'').replace(':00 ','').replace(' ','')}</span>
          <span style="flex:1;color:#c0d8f0">${j.tipo==='animal'?(j.seleccion+' '+(j.nombre_seleccion||'')):j.seleccion}</span>
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
        let lot=LOTERIAS_DATA[tr.loteria]||LOTERIAS_DATA['zoolo'];
        let salStr=tr.salieron&&tr.salieron.length?tr.salieron.join(', '):'Ninguno';
        thtml+=`<div style="padding:8px 10px;margin:3px 0;background:#0d0620;border-left:3px solid ${tr.gano?'#c084fc':'#3b0764'};border-radius:3px;font-size:.78rem">
          <div style="display:flex;justify-content:space-between;margin-bottom:4px">
            <span style="color:${lot.color};font-size:.7rem">${lot.emoji}</span>
            <span style="color:#e0a0ff;font-family:'Oswald',sans-serif">${tr.animal1}(${tr.nombre1}) · ${tr.animal2}(${tr.nombre2}) · ${tr.animal3}(${tr.nombre3})</span>
            <span style="color:#fbbf24;font-weight:700">S/${tr.monto}</span>
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
      ${premio>0&&!t.pagado&&!t.anulado?`<button onclick="pagarAdm(${t.id},${premio})" style="width:100%;padding:11px;background:#166534;color:#fff;border:2px solid #22c55e;border-radius:4px;font-weight:700;cursor:pointer;font-family:'Oswald',sans-serif;letter-spacing:2px;font-size:.85rem;margin-top:10px">💰 PAGAR S/${premio.toFixed(2)}</button>`:''}
      ${premio===0&&!t.pagado?`<div class="msg err" style="margin-top:8px">SIN PREMIO AÚN</div>`:''}
    </div>`;
  });
}
function pagarAdm(tid,m){
  if(!confirm(`¿Confirmar pago S/${m}?`))return;
  fetch('/api/pagar-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticket_id:tid})})
  .then(r=>r.json()).then(d=>{
    if(d.status==='ok'){glMsg('✅ Ticket pagado','ok');document.getElementById('op-res').innerHTML='';}
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

// ---- AUDITORÍA ----
function cargarAudit(){
  let fi=document.getElementById('aud-ini').value; let ff=document.getElementById('aud-fin').value;
  let filtro=document.getElementById('aud-filtro').value;
  fetch('/admin/audit-logs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:fi,fecha_fin:ff,filtro:filtro,limit:300})})
  .then(r=>r.json()).then(d=>{
    document.getElementById('aud-res').textContent=`${d.total} registros`;
    let html='';
    d.logs.forEach(l=>{
      html+=`<tr><td style="color:#4a6090">${l.id}</td>
        <td style="font-size:.7rem">${l.fecha}</td>
        <td style="color:var(--gold)">${l.agencia}</td>
        <td style="color:var(--teal);font-family:'Oswald',sans-serif">${l.accion}</td>
        <td style="font-size:.7rem">${l.detalle}</td>
        <td style="color:#4a6090;font-size:.7rem">${l.ip}</td></tr>`;
    });
    document.getElementById('aud-tbody').innerHTML=html||'<tr><td colspan="6" style="text-align:center;color:var(--text2);padding:20px">Sin registros</td></tr>';
  });
}

document.addEventListener('DOMContentLoaded',()=>{
  setHoy('ra-fecha'); setHoy('ra-fi');
  renderLotTabs('lot-tabs-res','zoolo',selLotRes);
  updateHorarioSelect('zoolo','ra-hora');
  renderAnimalesMini('zoolo','animals-mini-res',(k)=>{animalSelAdmin=k;document.getElementById('animal-sel-info').textContent='✓ '+k+' — '+(LOTERIAS_DATA['zoolo'].animales[k]||'');});
  renderLotTabs('lot-tabs-riesgo','zoolo',selLotRiesgo);
  renderLotTabs('lot-tabs-topes','zoolo',selLotTopes);
  updateHorarioSelect('zoolo','tope-hora-sel');
  renderAnimalesMini('zoolo','animals-topes',(k)=>{animalSelTope=k;document.getElementById('tope-sel-info').textContent='✓ '+k+' — '+(LOTERIAS_DATA['zoolo'].animales[k]||'');});
  let riesgoHorasSel=document.getElementById('riesgo-hora-sel');
  getHorarios('zoolo').forEach(h=>{let opt=document.createElement('option');opt.value=h;opt.textContent=h;riesgoHorasSel.appendChild(opt);});
  // Loteria selects for report
  let repAgLot=document.getElementById('rep-ag-lot');
  Object.entries(LOTERIAS_DATA).forEach(([k,v])=>{repAgLot.innerHTML+=`<option value="${k}">${v.emoji} ${v.nombre}</option>`;});
  let hoy=new Date().toISOString().split('T')[0];
  ['rep-ini','rep-fin','rep-ag-ini','rep-ag-fin','aud-ini','aud-fin'].forEach(id=>{let e=document.getElementById(id);if(e)e.value=hoy;});
  cargarDash(); cargarAgsSel();
});
</script>
</body></html>'''


SUPER_ADMIN_HTML = r'''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SUPER ADMIN — MULTI-LOTERÍA v4</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;600;700&family=Rajdhani:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#06090f;--panel:#0a0e18;--border:#1a2540;--gold:#f5a623;--teal:#00b4d8;--red:#e53e3e;--green:#22c55e;--purple:#a855f7;--text:#c8d8f0;--text2:#4a6090}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Rajdhani',sans-serif;min-height:100vh}
.topbar{background:#0d1428;border-bottom:3px solid #a855f7;padding:0 16px;height:40px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.brand{font-family:'Oswald',sans-serif;font-size:1rem;font-weight:700;color:#fff;letter-spacing:2px}
.brand em{color:#a855f7;font-style:normal}
.brand small{color:#4a6090;font-size:.6rem;letter-spacing:3px;margin-left:8px}
.btn-exit{background:#991b1b;color:#fff;border:2px solid #ef4444;padding:5px 12px;border-radius:3px;cursor:pointer;font-family:'Oswald',sans-serif;font-weight:700;font-size:.75rem;letter-spacing:1px}
.tabs{display:flex;background:#050810;border-bottom:2px solid #1a2a50;overflow-x:auto;position:sticky;top:40px;z-index:99}
.tab{padding:10px 14px;cursor:pointer;color:#4a6090;font-size:.7rem;font-family:'Oswald',sans-serif;letter-spacing:2px;border-bottom:3px solid transparent;transition:all .2s;white-space:nowrap;font-weight:600}
.tab:hover{color:#90b8e0;background:#060c1a}
.tab.active{color:#a855f7;border-bottom-color:#a855f7;background:#060e18}
.tc{display:none;padding:14px;max-width:960px;margin:auto}
.tc.active{display:block}
.fbox{background:#090f1e;border:2px solid #1a2a50;border-radius:5px;padding:15px;margin-bottom:12px}
.fbox h3{font-family:'Oswald',sans-serif;color:#a855f7;margin-bottom:12px;font-size:.82rem;letter-spacing:2px;border-bottom:1px solid #1a2a50;padding-bottom:8px}
.frow{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;align-items:center}
.frow input,.frow select{flex:1;min-width:100px;padding:9px 11px;background:#0a1828;border:2px solid #2a4a80;border-radius:3px;color:#fbbf24;font-family:'Rajdhani',sans-serif;font-size:.85rem;font-weight:600}
.frow input:focus,.frow select:focus{outline:none;border-color:#a855f7}
.btn-s{padding:9px 14px;background:#166534;color:#fff;border:2px solid #22c55e;border-radius:3px;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:1px;cursor:pointer;font-size:.75rem;white-space:nowrap}
.btn-d{padding:9px 14px;background:#991b1b;color:#fff;border:2px solid #ef4444;border-radius:3px;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:1px;cursor:pointer;font-size:.75rem}
.btn-sec{padding:7px 10px;background:#2a1a50;color:#c084fc;border:2px solid #5b21b6;border-radius:3px;cursor:pointer;font-size:.75rem;font-family:'Oswald',sans-serif;letter-spacing:1px;font-weight:700}
.btn-sec:hover{background:#4c1d95;border-color:#a855f7;color:#fff}
.sgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-bottom:16px}
.sc{background:#0d1828;border:2px solid #1a2a50;border-radius:4px;padding:12px;text-align:center}
.sc h3{color:#4a6090;font-size:.62rem;letter-spacing:2px;font-family:'Oswald',sans-serif;margin-bottom:5px}
.sc p{color:#fbbf24;font-size:1.25rem;font-weight:700;font-family:'Oswald',sans-serif}
.sc p.g{color:#4ade80}.sc p.r{color:#f87171}.sc p.p{color:#c084fc}
.msg{padding:9px 12px;border-radius:3px;margin:6px 0;font-size:.8rem;font-family:'Oswald',sans-serif;letter-spacing:1px;text-align:center;font-weight:700;border:2px solid}
.msg.ok{background:#166534;color:#fff;border-color:#22c55e}
.msg.err{background:#991b1b;color:#fff;border-color:#ef4444}
table{width:100%;border-collapse:collapse;font-size:.78rem}
th{background:#0d1828;color:#a855f7;padding:8px;text-align:left;border-bottom:2px solid #1a2a50;font-family:'Oswald',sans-serif;letter-spacing:1px;font-size:.7rem}
td{padding:6px 8px;border-bottom:1px solid #0a1020;color:var(--text)}
tr:hover td{background:#0d1828}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:.65rem;font-family:'Oswald',sans-serif;letter-spacing:1px}
.badge.on{background:#166534;color:#4ade80;border:1px solid #22c55e}
.badge.off{background:#991b1b;color:#fca5a5;border:1px solid #ef4444}
.glmsg{position:fixed;top:48px;left:50%;transform:translateX(-50%);z-index:999;min-width:240px;display:none}
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:#0a0e18}
::-webkit-scrollbar-thumb{background:#1a2a50;border-radius:2px}
</style></head><body>
<div class="topbar">
  <div class="brand">MULTI<em>LOT</em><small>SUPER ADMIN</small></div>
  <button class="btn-exit" onclick="location.href='/logout'">SALIR</button>
</div>
<div class="tabs">
  <div class="tab active" onclick="showTab('t-dash',this)">📊 DASHBOARD</div>
  <div class="tab" onclick="showTab('t-admins',this)">👥 ADMINISTRADORES</div>
</div>
<div class="glmsg msg" id="glmsg"></div>
<div class="tc active" id="t-dash">
  <div class="fbox">
    <h3>📊 RESUMEN GLOBAL DEL SISTEMA</h3>
    <div class="sgrid">
      <div class="sc"><h3>ADMINS</h3><p class="p" id="g-admins">--</p></div>
      <div class="sc"><h3>AGENCIAS</h3><p id="g-agencias">--</p></div>
      <div class="sc"><h3>TICKETS TOTALES</h3><p id="g-tickets">--</p></div>
      <div class="sc"><h3>VENTAS HOY</h3><p class="g" id="g-ventas">--</p></div>
    </div>
    <button class="btn-sec" onclick="cargarDash()">🔄 ACTUALIZAR</button>
  </div>
  <div class="fbox">
    <h3>📋 ACTIVIDAD POR ADMINISTRADOR</h3>
    <div id="tabla-admins-dash"></div>
  </div>
</div>
<div class="tc" id="t-admins">
  <div class="fbox">
    <h3>➕ CREAR NUEVO ADMINISTRADOR</h3>
    <div class="frow">
      <input type="text" id="sa-user" placeholder="Usuario (lowercase)" autocomplete="off">
      <input type="password" id="sa-pass" placeholder="Contraseña" autocomplete="off">
      <input type="text" id="sa-nombre" placeholder="Nombre / Empresa">
      <button class="btn-s" onclick="crearAdmin()">CREAR</button>
    </div>
    <div id="sa-msg"></div>
  </div>
  <div class="fbox">
    <h3>📋 ADMINISTRADORES</h3>
    <button class="btn-sec" onclick="cargarAdmins()" style="margin-bottom:10px">🔄 ACTUALIZAR</button>
    <div id="sa-lista" style="overflow-x:auto"></div>
  </div>
  <div class="fbox" id="sa-edit-box" style="display:none">
    <h3>🔑 CAMBIAR CONTRASEÑA</h3>
    <div class="frow">
      <input type="text" id="sa-edit-id" readonly style="max-width:60px;color:#4a6090">
      <input type="text" id="sa-edit-user" readonly style="max-width:120px;color:#a855f7">
      <input type="password" id="sa-edit-pass" placeholder="Nueva contraseña">
      <button class="btn-s" onclick="cambiarPass()">GUARDAR</button>
      <button class="btn-d" onclick="document.getElementById('sa-edit-box').style.display='none'">CANCELAR</button>
    </div>
    <div id="sa-edit-msg"></div>
  </div>
</div>
<script>
function showTab(id,el){
  document.querySelectorAll('.tc').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById(id).classList.add('active'); el.classList.add('active');
}
function glMsg(msg,tipo){
  let m=document.getElementById('glmsg');
  m.textContent=msg; m.className='glmsg msg '+tipo; m.style.display='block';
  clearTimeout(window._gmt); window._gmt=setTimeout(()=>m.style.display='none',3500);
}
async function apiPost(url,data){
  let r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  return r.json();
}
async function cargarDash(){
  let d=await fetch('/super-admin/reporte-global').then(r=>r.json());
  if(d.error){glMsg('Error: '+d.error,'err');return;}
  document.getElementById('g-admins').textContent=d.admins.length;
  document.getElementById('g-agencias').textContent=d.admins.reduce((a,b)=>a+b.num_agencias,0);
  document.getElementById('g-tickets').textContent=d.global.tickets;
  document.getElementById('g-ventas').textContent='S/'+parseFloat(d.global.ventas).toFixed(2);
  let html='<div style="overflow-x:auto"><table><thead><tr><th>ADMINISTRADOR</th><th>USUARIO</th><th>AGENCIAS</th><th>VENTAS HOY</th></tr></thead><tbody>';
  d.admins.forEach(a=>{
    html+=`<tr><td style="color:#c084fc;font-weight:700">${a.nombre_agencia}</td>
      <td style="color:#fbbf24;font-family:'Oswald',sans-serif">${a.usuario}</td>
      <td>${a.num_agencias}</td>
      <td style="color:#4ade80;font-weight:700">S/${parseFloat(a.ventas_hoy).toFixed(2)}</td></tr>`;
  });
  html+='</tbody></table></div>';
  document.getElementById('tabla-admins-dash').innerHTML=html;
}
async function cargarAdmins(){
  let ags=await fetch('/super-admin/lista-admins').then(r=>r.json());
  if(!ags.length){document.getElementById('sa-lista').innerHTML='<p style="color:var(--text2);font-size:.8rem;padding:10px">No hay administradores</p>';return;}
  let html='<table><thead><tr><th>ID</th><th>USUARIO</th><th>NOMBRE</th><th>AGENCIAS</th><th>VENTAS TOTAL</th><th>ESTADO</th><th>ACCIONES</th></tr></thead><tbody>';
  ags.forEach(a=>{
    html+=`<tr><td style="color:#4a6090">${a.id}</td>
      <td style="color:#a855f7;font-family:'Oswald',sans-serif;font-weight:700">${a.usuario}</td>
      <td>${a.nombre_agencia}</td><td>${a.num_agencias}</td>
      <td style="color:#4ade80">S/${parseFloat(a.total_ventas||0).toFixed(2)}</td>
      <td><span class="badge ${a.activa?'on':'off'}">${a.activa?'ACTIVO':'INACTIVO'}</span></td>
      <td style="display:flex;gap:4px;flex-wrap:wrap">
        <button onclick="editarAdmin(${a.id},'${a.usuario}')" style="padding:4px 8px;background:#2a1a50;border:1px solid #5b21b6;color:#c084fc;font-size:.65rem;cursor:pointer;border-radius:2px">PASS</button>
        <button onclick="toggleAdmin(${a.id})" style="padding:4px 8px;background:${a.activa?'#3a1010':'#0a2010'};border:1px solid ${a.activa?'#6b1515':'#166534'};color:${a.activa?'#f87171':'#4ade80'};font-size:.65rem;cursor:pointer;border-radius:2px">${a.activa?'DESACT':'ACTIVAR'}</button>
      </td></tr>`;
  });
  html+='</tbody></table>';
  document.getElementById('sa-lista').innerHTML=html;
}
async function crearAdmin(){
  let u=document.getElementById('sa-user').value.trim().toLowerCase();
  let p=document.getElementById('sa-pass').value.trim();
  let n=document.getElementById('sa-nombre').value.trim();
  let m=document.getElementById('sa-msg');
  if(!u||!p||!n){m.innerHTML='<div class="msg err">Complete todos los campos</div>';return;}
  let d=await apiPost('/super-admin/crear-admin',{usuario:u,password:p,nombre:n});
  if(d.status==='ok'){
    m.innerHTML='<div class="msg ok">✅ '+d.mensaje+'</div>';
    ['sa-user','sa-pass','sa-nombre'].forEach(id=>document.getElementById(id).value='');
    cargarAdmins(); cargarDash();
  } else m.innerHTML='<div class="msg err">❌ '+d.error+'</div>';
}
function editarAdmin(id,usuario){
  document.getElementById('sa-edit-id').value=id;
  document.getElementById('sa-edit-user').value=usuario;
  document.getElementById('sa-edit-pass').value='';
  document.getElementById('sa-edit-box').style.display='block';
  document.getElementById('sa-edit-msg').innerHTML='';
  document.getElementById('sa-edit-pass').focus();
}
async function cambiarPass(){
  let id=document.getElementById('sa-edit-id').value;
  let pass=document.getElementById('sa-edit-pass').value.trim();
  let m=document.getElementById('sa-edit-msg');
  if(!pass){m.innerHTML='<div class="msg err">Escribe la nueva contraseña</div>';return;}
  let d=await apiPost('/super-admin/cambiar-password',{admin_id:id,password:pass});
  if(d.status==='ok'){m.innerHTML='<div class="msg ok">✅ Actualizado</div>';glMsg('✅ Contraseña actualizada','ok');}
  else m.innerHTML='<div class="msg err">❌ '+d.error+'</div>';
}
async function toggleAdmin(id){
  let d=await apiPost('/super-admin/toggle-admin',{admin_id:id});
  if(d.status==='ok'){glMsg('Estado actualizado','ok');cargarAdmins();}
  else glMsg('Error: '+d.error,'err');
}
document.addEventListener('DOMContentLoaded',()=>{cargarDash();cargarAdmins();});
</script>
</body></html>'''

# ========================= MAIN =========================
if __name__ == '__main__':
    print("=" * 60)
    print("  SISTEMA MULTI-LOTERÍA v4.0")
    print("=" * 60)
    print(f"  DB: {DB_PATH}")
    init_db()
    print("  ✓ Multi-loterías simultáneas en jugadas y tripletas")
    print("  ✓ Taquillas pueden anular tickets (sorteo no cerrado)")
    print("  ✓ LOTTO INTER agregado")
    print("  ✓ SELVA PLUS (antes Selva Paraiso)")
    print("  ✓ LOTTO GRANJA PLUS (antes Granjita)")
    print("  ✓ Tripleta Guacharito x130, Guacharo x100, Granja x50")
    print("  Super Admin: yampiero1 / 15821462")
    print("  Admin Ejemplo: cuborubi / 15821462")
    print("  URL: http://localhost:10000")
    print("=" * 60)
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
