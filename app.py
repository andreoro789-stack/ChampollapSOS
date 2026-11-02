from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import mysql.connector
from datetime import datetime, timedelta
import random
import os

# Importación condicional del detector NSFW
try:
    import opennsfw2 as nsfw
    NSFW_DISPONIBLE = True
except ImportError:
    NSFW_DISPONIBLE = False
    print("[AVISO] 'opennsfw2' no está instalado. Ejecute: pip install opennsfw2 Pillow")

app = Flask(__name__)
app.secret_key = 'champollap_segura_key_2026'
CORS(app)

# -------------------------------------------------------------
# CONFIGURACIÓN DE SUBIDA DE IMÁGENES Y AUDIOS
# -------------------------------------------------------------
UPLOAD_FOLDER_REPORTES = os.path.join('static', 'uploads', 'reportes')
UPLOAD_FOLDER_AUDIOS = os.path.join('static', 'uploads', 'audios')
ALLOWED_EXTENSIONS_IMG = {'png', 'jpg', 'jpeg', 'webp'}
ALLOWED_EXTENSIONS_AUDIO = {'webm', 'ogg', 'mp3', 'wav'}

os.makedirs(UPLOAD_FOLDER_REPORTES, exist_ok=True)
os.makedirs(UPLOAD_FOLDER_AUDIOS, exist_ok=True)

app.config['UPLOAD_FOLDER_REPORTES'] = UPLOAD_FOLDER_REPORTES
app.config['UPLOAD_FOLDER_AUDIOS'] = UPLOAD_FOLDER_AUDIOS
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024  # Máximo 12 MB combinado

def allowed_file_img(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS_IMG

def es_imagen_inapropiada(ruta_archivo):
    """Retorna True si la probabilidad de desnudez o pornografía supera el 70%."""
    if not NSFW_DISPONIBLE:
        return False
    try:
        probabilidad = nsfw.predict_image(ruta_archivo)
        print(f"[NSFW AUDIT] Probabilidad de contenido explícito: {probabilidad:.4f}")
        return probabilidad >= 0.70
    except Exception as e:
        print(f"[NSFW ERROR] Falla al evaluar imagen: {e}")
        return False

# Configuración de base de datos MySQL adaptable para Azure y Local
db_config = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASSWORD', 'root321'),
    'database': os.environ.get('DB_NAME', 'bd_incidentes_champollap'),
    'port': int(os.environ.get('DB_PORT', 3306)),
    'time_zone': '-06:00'
}

def get_db_connection():
    # Al incluir time_zone en db_config, mysql-connector aplica el desfase de Guatemala automáticamente
    return mysql.connector.connect(**db_config)

def inicializar_sistema():
    """Garantiza la existencia de roles, estados, catálogos, usuarios, comunicados y columnas."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. Roles
        cursor.execute("""
            INSERT INTO roles (id_rol, nombre_rol, descripcion) 
            VALUES (1, 'Administrador', 'Líder COCODE con permisos totales')
            ON DUPLICATE KEY UPDATE nombre_rol='Administrador';
        """)
        cursor.execute("""
            INSERT INTO roles (id_rol, nombre_rol, descripcion) 
            VALUES (2, 'Vecino', 'Residente comunitario')
            ON DUPLICATE KEY UPDATE nombre_rol='Vecino';
        """)

        # 2. Estados de reporte
        cursor.execute("""
            INSERT INTO estados_reporte (id_estado, nombre) 
            VALUES 
                (1, 'Pendiente'),
                (2, 'Aprobado'),
                (3, 'Atendido'),
                (4, 'Desestimado')
            ON DUPLICATE KEY UPDATE nombre=VALUES(nombre);
        """)

        # 3. Tipos de incidente base
        tipos_base = [
            (1, 'Accidente de Tránsito', 'Alta'),
            (2, 'Robo / Asalto', 'Alta'),
            (3, 'Actividad Sospechosa', 'Media'),
            (4, 'Emergencia Médica / Incendio', 'Critica'),
            (5, 'Problemas entre Vecinos', 'Baja')
        ]
        cursor.executemany("""
            INSERT INTO tipos_incidente (id_tipo, nombre, nivel_prioridad) 
            VALUES (%s, %s, %s) 
            ON DUPLICATE KEY UPDATE id_tipo=VALUES(id_tipo);
        """, tipos_base)

        # 4. Hashes independientes
        hash_admin = generate_password_hash('admin2026')
        hash_vecino = generate_password_hash('vecino123')

        # Administrador COCODE (Rol 1)
        cursor.execute("""
            INSERT INTO usuarios 
            (id_usuario, id_rol, nombres, apellidos, dpi, telefono, correo, direccion_champollap, contrasena_hash, estado_aprobacion, cuenta_suspendida) 
            VALUES (1, 1, 'Comité', 'COCODE', '1234567890123', '55554444', 'admin@champollap.gt', 'Sector Central, Champollap', %s, 'Aprobado', 0)
            ON DUPLICATE KEY UPDATE 
                contrasena_hash = VALUES(contrasena_hash),
                estado_aprobacion = 'Aprobado',
                cuenta_suspendida = 0;
        """, (hash_admin,))

        # Vecino Residente (Rol 2)
        cursor.execute("""
            INSERT INTO usuarios 
            (id_usuario, id_rol, nombres, apellidos, dpi, telefono, correo, direccion_champollap, contrasena_hash, estado_aprobacion, cuenta_suspendida) 
            VALUES (2, 2, 'Juan', 'Pérez', '9876543210987', '77778888', 'vecino@champollap.gt', 'Sector Las Manzanas, Champollap', %s, 'Aprobado', 0)
            ON DUPLICATE KEY UPDATE 
                contrasena_hash = VALUES(contrasena_hash),
                estado_aprobacion = 'Aprobado',
                cuenta_suspendida = 0;
        """, (hash_vecino,))

        # 5. Columnas multimedia en tabla reportes
        try:
            cursor.execute("ALTER TABLE reportes ADD COLUMN foto VARCHAR(255) NULL AFTER origen_ubicacion;")
        except mysql.connector.Error:
            pass

        try:
            cursor.execute("ALTER TABLE reportes ADD COLUMN audio VARCHAR(255) NULL AFTER foto;")
        except mysql.connector.Error:
            pass

        # 6. Tabla de Comunicados Oficiales
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comunicados (
                id_comunicado INT AUTO_INCREMENT PRIMARY KEY,
                id_usuario_admin INT NOT NULL,
                titulo VARCHAR(150) NOT NULL,
                contenido TEXT NOT NULL,
                categoria ENUM('Seguridad', 'Agua / Luz', 'Faena Comunal', 'General') DEFAULT 'General',
                fecha_publicacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (id_usuario_admin) REFERENCES usuarios(id_usuario)
            ) ENGINE=InnoDB;
        """)

        conn.commit()
        print("[OK] Base de datos 'bd_incidentes_champollap' sincronizada exitosamente.")
        print("     - Admin (admin@champollap.gt)   -> Clave: admin2026")
        print("     - Vecino (vecino@champollap.gt) -> Clave: vecino123")
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[AVISO] Advertencia de conexión a BD en inicio (la app continuará encendiendo): {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# -------------------------------------------------------------
# RUTAS PWA
# -------------------------------------------------------------

@app.route('/sw.js')
def service_worker():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json', mimetype='application/json')

# -------------------------------------------------------------
# DECORADORES DE ACCESO POR ROL
# -------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            return redirect(url_for('vista_login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            return redirect(url_for('vista_login'))
        if session['usuario'].get('id_rol') != 1:
            return redirect(url_for('vista_vecino'))
        return f(*args, **kwargs)
    return decorated_function

# -------------------------------------------------------------
# RUTAS DE VISTAS (PÁGINAS)
# -------------------------------------------------------------

@app.route('/')
@login_required
def index():
    if session['usuario']['id_rol'] == 1:
        return redirect(url_for('vista_admin'))
    return redirect(url_for('vista_vecino'))

@app.route('/admin')
@admin_required
def vista_admin():
    return render_template('admin_dashboard.html', usuario=session['usuario'])

@app.route('/vecino')
@login_required
def vista_vecino():
    return render_template('vecino_dashboard.html', usuario=session['usuario'])

@app.route('/login')
def vista_login():
    if 'usuario' in session:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/registro')
def vista_registro():
    if 'usuario' in session:
        return redirect(url_for('index'))
    return render_template('registro.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('vista_login'))

# -------------------------------------------------------------
# ENDPOINTS DE AUTENTICACIÓN
# -------------------------------------------------------------

@app.route('/api/login', methods=['POST'])
def api_login():
    conn = None
    cursor = None
    try:
        data = request.json or {}
        credencial = data.get('credencial', '').strip()
        password = data.get('password', '')

        if not credencial or not password:
            return jsonify({'exito': False, 'mensaje': 'Ingrese sus datos completos.'}), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT u.*, r.nombre_rol 
            FROM usuarios u
            INNER JOIN roles r ON u.id_rol = r.id_rol
            WHERE TRIM(u.correo) = %s OR TRIM(u.telefono) = %s OR TRIM(u.dpi) = %s
        """
        cursor.execute(query, (credencial, credencial, credencial))
        usuario = cursor.fetchone()

        if not usuario:
            return jsonify({'exito': False, 'mensaje': 'Usuario no registrado.'}), 404

        es_correcta = check_password_hash(usuario['contrasena_hash'], password)
        if not es_correcta:
            return jsonify({'exito': False, 'mensaje': 'Contraseña incorrecta.'}), 401

        if usuario.get('cuenta_suspendida') == 1:
            return jsonify({'exito': False, 'mensaje': 'Tu cuenta ha sido suspendida por emisión de reportes falsos o decisión comunitaria.'}), 403

        if usuario.get('estado_aprobacion') == 'Pendiente':
            return jsonify({'exito': False, 'mensaje': 'Tu cuenta está en revisión por el COCODE.'}), 403
        
        if usuario.get('estado_aprobacion') == 'Rechazado':
            return jsonify({'exito': False, 'mensaje': 'Tu solicitud de acceso fue rechazada.'}), 403

        session['usuario'] = {
            'id_usuario': usuario['id_usuario'],
            'nombres': usuario['nombres'],
            'apellidos': usuario['apellidos'],
            'id_rol': usuario['id_rol'],
            'rol': usuario['nombre_rol'],
            'dpi': usuario['dpi']
        }

        destino = '/admin' if usuario['id_rol'] == 1 else '/vecino'
        return jsonify({'exito': True, 'mensaje': 'Bienvenido al sistema.', 'redirect': destino}), 200

    except Exception as e:
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/registro', methods=['POST'])
def api_registro():
    conn = None
    cursor = None
    try:
        data = request.json or {}
        nombres = data.get('nombres', '').strip()
        apellidos = data.get('apellidos', '').strip()
        dpi = data.get('dpi', '').strip()
        telefono = data.get('telefono', '').strip()
        correo = data.get('correo', '').strip()
        direccion = data.get('direccion_champollap', '').strip()
        password = data.get('password', '')

        if not all([nombres, apellidos, dpi, telefono, correo, direccion, password]):
            return jsonify({'exito': False, 'mensaje': 'Todos los campos son obligatorios.'}), 400

        contrasena_hash = generate_password_hash(password)

        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
            INSERT INTO usuarios 
            (id_rol, nombres, apellidos, dpi, telefono, correo, direccion_champollap, contrasena_hash, estado_aprobacion) 
            VALUES (2, %s, %s, %s, %s, %s, %s, %s, 'Pendiente')
        """
        cursor.execute(query, (nombres, apellidos, dpi, telefono, correo, direccion, contrasena_hash))
        conn.commit()

        return jsonify({'exito': True, 'mensaje': 'Solicitud enviada exitosamente. El COCODE validará tu ingreso.'}), 201

    except mysql.connector.Error as err:
        if conn: conn.rollback()
        if err.errno == 1062:
            return jsonify({'exito': False, 'mensaje': 'El DPI, correo o teléfono ya están registrados.'}), 409
        return jsonify({'exito': False, 'mensaje': str(err)}), 500
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# -------------------------------------------------------------
# CRUD DE VECINOS Y APROBACIÓN DE REGISTROS (ADMINISTRADOR)
# -------------------------------------------------------------

@app.route('/api/admin/vecinos', methods=['GET'])
@admin_required
def listar_vecinos():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id_usuario, nombres, apellidos, dpi, telefono, correo, direccion_champollap, estado_aprobacion, fecha_registro
            FROM usuarios 
            WHERE id_rol = 2
            ORDER BY fecha_registro DESC
        """)
        vecinos = cursor.fetchall()
        return jsonify({'exito': True, 'data': vecinos}), 200
    except Exception as e:
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/admin/vecinos', methods=['POST'])
@admin_required
def crear_vecino_admin():
    conn = None
    cursor = None
    try:
        data = request.json or {}
        nombres = data.get('nombres', '').strip()
        apellidos = data.get('apellidos', '').strip()
        dpi = data.get('dpi', '').strip()
        telefono = data.get('telefono', '').strip()
        correo = data.get('correo', '').strip()
        direccion = data.get('direccion_champollap', '').strip()
        password = data.get('password', '').strip()
        id_admin = session.get('usuario', {}).get('id_usuario', 1)

        if not all([nombres, apellidos, dpi, telefono, correo, direccion, password]):
            return jsonify({'exito': False, 'mensaje': 'Todos los campos son obligatorios.'}), 400

        contrasena_hash = generate_password_hash(password)

        zona_gt = ZoneInfo("America/Guatemala")
        ahora_gt = datetime.now(zona_gt)

        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
            INSERT INTO usuarios 
            (id_rol, nombres, apellidos, dpi, telefono, correo, direccion_champollap, contrasena_hash, estado_aprobacion, aprobado_por, fecha_aprobacion) 
            VALUES (2, %s, %s, %s, %s, %s, %s, %s, 'Aprobado', %s, %s)
        """
        valores = (nombres, apellidos, dpi, telefono, correo, direccion, contrasena_hash, id_admin, ahora_gt)
        cursor.execute(query, valores)
        conn.commit()
        id_vecino = cursor.lastrowid

        return jsonify({'exito': True, 'mensaje': 'Vecino registrado y habilitado exitosamente.', 'id_usuario': id_vecino}), 201

    except mysql.connector.Error as err:
        if conn: conn.rollback()
        if err.errno == 1062:
            return jsonify({'exito': False, 'mensaje': 'El DPI, correo o teléfono ya pertenecen al padrón.'}), 409
        return jsonify({'exito': False, 'mensaje': f'Error en base de datos: {err.msg}'}), 500
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/admin/vecinos/<int:id_usuario>', methods=['GET'])
@admin_required
def obtener_vecino_individual(id_usuario):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id_usuario, nombres, apellidos, dpi, telefono, correo, direccion_champollap, estado_aprobacion 
            FROM usuarios 
            WHERE id_usuario = %s AND id_rol = 2
        """, (id_usuario,))
        vecino = cursor.fetchone()
        if not vecino:
            return jsonify({'exito': False, 'mensaje': 'Vecino no encontrado.'}), 404
        return jsonify({'exito': True, 'data': vecino}), 200
    except Exception as e:
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/admin/vecinos/<int:id_usuario>', methods=['PUT'])
@admin_required
def actualizar_vecino_admin(id_usuario):
    conn = None
    cursor = None
    try:
        data = request.json or {}
        nombres = data.get('nombres', '').strip()
        apellidos = data.get('apellidos', '').strip()
        dpi = data.get('dpi', '').strip()
        telefono = data.get('telefono', '').strip()
        correo = data.get('correo', '').strip()
        direccion = data.get('direccion_champollap', '').strip()
        estado = data.get('estado_aprobacion', 'Aprobado')
        nueva_password = data.get('password', '').strip()

        if not all([nombres, apellidos, dpi, telefono, correo, direccion]):
            return jsonify({'exito': False, 'mensaje': 'Campos obligatorios incompletos.'}), 400

        # Si el administrador lo pone como 'Aprobado', la cuenta suspendida pasa a 0 obligatoriamente
        susc_val = 0 if estado == 'Aprobado' else 1

        conn = get_db_connection()
        cursor = conn.cursor()

        if nueva_password:
            pass_hash = generate_password_hash(nueva_password)
            query = """
                UPDATE usuarios 
                SET nombres = %s, apellidos = %s, dpi = %s, telefono = %s, correo = %s, 
                    direccion_champollap = %s, estado_aprobacion = %s, cuenta_suspendida = %s, contrasena_hash = %s
                WHERE id_usuario = %s AND id_rol = 2
            """
            valores = (nombres, apellidos, dpi, telefono, correo, direccion, estado, susc_val, pass_hash, id_usuario)
        else:
            query = """
                UPDATE usuarios 
                SET nombres = %s, apellidos = %s, dpi = %s, telefono = %s, correo = %s, 
                    direccion_champollap = %s, estado_aprobacion = %s, cuenta_suspendida = %s
                WHERE id_usuario = %s AND id_rol = 2
            """
            valores = (nombres, apellidos, dpi, telefono, correo, direccion, estado, susc_val, id_usuario)

        cursor.execute(query, valores)
        conn.commit()
        return jsonify({'exito': True, 'mensaje': 'Datos del vecino actualizados y sincronizados exitosamente.'}), 200

    except mysql.connector.Error as err:
        if conn: conn.rollback()
        if err.errno == 1062:
            return jsonify({'exito': False, 'mensaje': 'DPI, teléfono o correo duplicado con otro usuario.'}), 409
        return jsonify({'exito': False, 'mensaje': str(err)}), 500
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/admin/vecinos/<int:id_usuario>/aprobar', methods=['PUT'])
@admin_required
def aprobar_solicitud_vecino(id_usuario):
    conn = None
    cursor = None
    try:
        data = request.json or {}
        nuevo_estado = data.get('estado', 'Aprobado')
        id_admin = session.get('usuario', {}).get('id_usuario', 1)

        zona_gt = ZoneInfo("America/Guatemala")
        ahora_gt = datetime.now(zona_gt)

        conn = get_db_connection()
        cursor = conn.cursor()

        # Forzar el desbloqueo absoluto (cuenta_suspendida = 0) si el estado es Aprobado
        if nuevo_estado == 'Aprobado':
            cursor.execute("""
                UPDATE usuarios 
                SET estado_aprobacion = 'Aprobado', cuenta_suspendida = 0, aprobado_por = %s, fecha_aprobacion = %s 
                WHERE id_usuario = %s AND id_rol = 2
            """, (id_admin, ahora_gt, id_usuario))
        else:
            cursor.execute("""
                UPDATE usuarios 
                SET estado_aprobacion = %s, cuenta_suspendida = 1, aprobado_por = %s, fecha_aprobacion = %s 
                WHERE id_usuario = %s AND id_rol = 2
            """, (nuevo_estado, id_admin, ahora_gt, id_usuario))

        conn.commit()
        return jsonify({'exito': True, 'mensaje': f'Vecino actualizado a {nuevo_estado} y desbloqueado correctamente.'}), 200
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/admin/vecinos/<int:id_usuario>', methods=['DELETE'])
@admin_required
def eliminar_vecino_admin(id_usuario):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM reportes WHERE id_usuario = %s", (id_usuario,))
        (reportes_asociados,) = cursor.fetchone()

        if reportes_asociados > 0:
            cursor.execute("""
                UPDATE usuarios 
                SET cuenta_suspendida = 1, estado_aprobacion = 'Rechazado' 
                WHERE id_usuario = %s AND id_rol = 2
            """, (id_usuario,))
            conn.commit()
            return jsonify({'exito': True, 'mensaje': 'El vecino posee reportes asociados. Su cuenta ha sido suspendida.'}), 200

        cursor.execute("DELETE FROM usuarios WHERE id_usuario = %s AND id_rol = 2", (id_usuario,))
        conn.commit()
        return jsonify({'exito': True, 'mensaje': 'Vecino eliminado del padrón comunitario.'}), 200

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# -------------------------------------------------------------
# REPORTES Y CATÁLOGOS CON EVIDENCIAS (FOTO Y AUDIO)
# -------------------------------------------------------------

@app.route('/api/catalogos', methods=['GET'])
def obtener_catalogos():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id_tipo, nombre, nivel_prioridad FROM tipos_incidente ORDER BY id_tipo ASC")
        tipos = cursor.fetchall()
        cursor.execute("SELECT id_estado, nombre FROM estados_reporte ORDER BY id_estado ASC")
        estados = cursor.fetchall()
        return jsonify({'exito': True, 'tipos': tipos, 'estados': estados}), 200
    except Exception as e:
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/reportes', methods=['GET'])
@login_required
def obtener_reportes():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT 
                r.id_reporte, 
                r.id_estado,
                r.codigo_seguimiento, 
                r.descripcion, 
                r.foto,
                r.audio,
                r.resolucion_admin,
                CAST(r.latitud AS FLOAT) as latitud, 
                CAST(r.longitud AS FLOAT) as longitud, 
                t.nombre AS tipo, 
                t.nivel_prioridad, 
                e.nombre AS estado, 
                r.fecha_hora_incidente,
                r.fecha_registro,
                CONCAT(u.nombres, ' ', u.apellidos) AS usuario_nombre
            FROM reportes r
            INNER JOIN tipos_incidente t ON r.id_tipo = t.id_tipo
            INNER JOIN estados_reporte e ON r.id_estado = e.id_estado
            INNER JOIN usuarios u ON r.id_usuario = u.id_usuario
            WHERE r.es_falso_reporte = 0
            ORDER BY r.fecha_registro DESC
        """
        cursor.execute(query)
        reportes = cursor.fetchall()
        return jsonify({'exito': True, 'data': reportes}), 200
    except Exception as e:
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/mis-reportes', methods=['GET'])
@login_required
def mis_reportes():
    conn = None
    cursor = None
    try:
        id_usuario = session['usuario']['id_usuario']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT 
                r.id_reporte, 
                r.codigo_seguimiento, 
                r.descripcion, 
                r.foto,
                r.audio,
                CAST(r.latitud AS FLOAT) as latitud, 
                CAST(r.longitud AS FLOAT) as longitud, 
                t.nombre AS tipo, 
                t.nivel_prioridad, 
                e.nombre AS estado, 
                r.fecha_hora_incidente,
                r.fecha_registro
            FROM reportes r
            INNER JOIN tipos_incidente t ON r.id_tipo = t.id_tipo
            INNER JOIN estados_reporte e ON r.id_estado = e.id_estado
            WHERE r.id_usuario = %s AND r.es_falso_reporte = 0
            ORDER BY r.fecha_registro DESC
        """
        cursor.execute(query, (id_usuario,))
        reportes = cursor.fetchall()
        return jsonify({'exito': True, 'data': reportes}), 200
    except Exception as e:
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/mis-datos', methods=['GET'])
@login_required
def mis_datos():
    conn = None
    cursor = None
    try:
        id_usuario = session['usuario']['id_usuario']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id_usuario, nombres, apellidos, correo, estado_aprobacion, cuenta_suspendida FROM usuarios WHERE id_usuario = %s", (id_usuario,))
        usuario = cursor.fetchone()
        return jsonify({'exito': True, 'usuario': usuario}), 200
    except Exception as e:
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/reportes', methods=['POST'])
@login_required
def crear_reporte():
    conn = None
    cursor = None
    archivo_foto_guardado = None
    archivo_audio_guardado = None
    try:
        # Forzar la conversión exacta desde UTC al huso horario de Guatemala
        zona_gt = ZoneInfo("America/Guatemala")
        ahora_gt = datetime.now(ZoneInfo("UTC")).astimezone(zona_gt)
        fecha_hora_gt = ahora_gt.strftime('%Y-%m-%d %H:%M:%S')
        fecha_input = fecha_hora_gt

        # Extracción de campos (soporta Multipart y JSON crudo)
        if request.content_type and 'multipart/form-data' in request.content_type:
            id_tipo = int(request.form.get('id_tipo', 1))
            descripcion = request.form.get('descripcion', '').strip()
            latitud = float(request.form.get('latitud', 14.9625))
            longitud = float(request.form.get('longitud', -91.7764))
            origen_ubicacion = request.form.get('origen_ubicacion', 'Marcacion_Manual')
        else:
            data = request.json or {}
            id_tipo = int(data.get('id_tipo', 1))
            descripcion = data.get('descripcion', '').strip()
            latitud = float(data.get('latitud', 14.9625))
            longitud = float(data.get('longitud', -91.7764))
            origen_ubicacion = data.get('origen_ubicacion', 'GPS_Automatico')

        id_usuario = session['usuario']['id_usuario']
        nombre_foto = None
        nombre_audio = None

        # 1. Procesamiento y Moderación de Imagen
        if 'foto' in request.files:
            file_f = request.files['foto']
            if file_f and file_f.filename != '':
                if not allowed_file_img(file_f.filename):
                    return jsonify({'exito': False, 'mensaje': 'Formato de imagen no permitido (use JPG, PNG o WEBP).'}), 400

                nombre_seguro_f = f"{ahora_gt.strftime('%Y%m%d_%H%M%S')}_{random.randint(100,999)}_{secure_filename(file_f.filename)}"
                ruta_f = os.path.join(app.config['UPLOAD_FOLDER_REPORTES'], nombre_seguro_f)
                file_f.save(ruta_f)
                archivo_foto_guardado = ruta_f

                if es_imagen_inapropiada(ruta_f):
                    os.remove(ruta_f)
                    return jsonify({'exito': False, 'mensaje': 'La imagen fue rechazada automáticamente por contener contenido explícito o inapropiado.'}), 400

                nombre_foto = nombre_seguro_f

        # 2. Procesamiento de Nota de Voz
        if 'audio' in request.files:
            file_a = request.files['audio']
            if file_a and file_a.filename != '':
                nombre_seguro_a = f"VOZ_{ahora_gt.strftime('%Y%m%d_%H%M%S')}_{random.randint(100,999)}.webm"
                ruta_a = os.path.join(app.config['UPLOAD_FOLDER_AUDIOS'], nombre_seguro_a)
                file_a.save(ruta_a)
                archivo_audio_guardado = ruta_a
                nombre_audio = nombre_seguro_a

        codigo_seguimiento = f"CH-{random.randint(1000, 9999)}"
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
            INSERT INTO reportes 
            (codigo_seguimiento, id_usuario, id_tipo, id_estado, descripcion, fecha_hora_incidente, latitud, longitud, origen_ubicacion, foto, audio) 
            VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s, %s, %s)
        """
        valores = (codigo_seguimiento, id_usuario, id_tipo, descripcion, fecha_input, latitud, longitud, origen_ubicacion, nombre_foto, nombre_audio)
        cursor.execute(query, valores)
        conn.commit()
        id_reporte = cursor.lastrowid

        return jsonify({
            'exito': True, 
            'mensaje': 'Reporte guardado exitosamente.', 
            'codigo_seguimiento': codigo_seguimiento, 
            'id_reporte': id_reporte
        }), 201

    except Exception as e:
        if conn: conn.rollback()
        if archivo_foto_guardado and os.path.exists(archivo_foto_guardado): os.remove(archivo_foto_guardado)
        if archivo_audio_guardado and os.path.exists(archivo_audio_guardado): os.remove(archivo_audio_guardado)
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# -------------------------------------------------------------
# AUDITORÍA DE REPORTES Y DETECCIÓN DE FALSOS (RN-03)
# -------------------------------------------------------------

@app.route('/api/admin/reportes/<int:id_reporte>/marcar-falso', methods=['POST'])
@admin_required
def marcar_falso_reporte(id_reporte):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id_usuario, codigo_seguimiento FROM reportes WHERE id_reporte = %s", (id_reporte,))
        reporte = cursor.fetchone()

        if not reporte:
            return jsonify({'exito': False, 'mensaje': 'Reporte no encontrado.'}), 404

        id_infractor = reporte['id_usuario']

        # 1. Marcar el reporte como falso y cambiar estado a Desestimado
        cursor.execute("""
            UPDATE reportes 
            SET es_falso_reporte = 1, id_estado = (SELECT id_estado FROM estados_reporte WHERE nombre = 'Desestimado' LIMIT 1)
            WHERE id_reporte = %s
        """, (id_reporte,))

        # 2. Aplicar la sanción RN-03 actualizando el estado de aprobación a 'Rechazado' (Suspendido)
        if id_infractor:
            cursor.execute("""
                UPDATE usuarios 
                SET estado_aprobacion = 'Rechazado', cuenta_suspendida = 1 
                WHERE id_usuario = %s
            """, (id_infractor,))

        conn.commit()

        return jsonify({
            'exito': True, 
            'mensaje': f"Reporte {reporte['codigo_seguimiento']} desestimado como FALSO. La cuenta del emisor ha sido suspendida."
        }), 200

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# -------------------------------------------------------------
# ALERTAS RÁPIDAS (BOTÓN S.O.S)
# -------------------------------------------------------------
@app.route('/api/alertas-rapidas', methods=['POST'])
@login_required
def alerta_rapida():
    conn = None
    cursor = None
    try:
        data = request.json or {}
        id_usuario = session['usuario']['id_usuario']
        
        # Forzar zona horaria de Guatemala para la alerta S.O.S
        zona_gt = ZoneInfo("America/Guatemala")
        ahora_gt = datetime.now(zona_gt).strftime('%Y-%m-%d %H:%M:%S')

        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
            INSERT INTO alertas_rapidas (id_usuario, latitud, longitud, estado, fecha_hora) 
            VALUES (%s, %s, %s, 'Activa', %s)
        """
        cursor.execute(query, (id_usuario, data.get('latitud', 14.9625), data.get('longitud', -91.7764), ahora_gt))
        conn.commit()
        id_alerta = cursor.lastrowid

        return jsonify({'exito': True, 'mensaje': 'Alerta S.O.S transmitida exitosamente.', 'id_alerta': id_alerta}), 201
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/admin/alertas-activas', methods=['GET'])
@admin_required
def obtener_alertas_activas():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT 
                a.id_alerta, 
                CAST(a.latitud AS FLOAT) as latitud, 
                CAST(a.longitud AS FLOAT) as longitud, 
                DATE_FORMAT(a.fecha_hora, '%Y-%m-%d %H:%i:%s') AS fecha_hora, 
                a.estado,
                u.id_usuario, 
                CONCAT(u.nombres, ' ', u.apellidos) AS vecino, 
                u.telefono, 
                u.direccion_champollap
            FROM alertas_rapidas a
            INNER JOIN usuarios u ON a.id_usuario = u.id_usuario
            WHERE a.estado = 'Activa' 
            ORDER BY a.fecha_hora DESC
        """
        cursor.execute(query)
        alertas = cursor.fetchall()
        return jsonify({'exito': True, 'alertas': alertas}), 200
    except Exception as e:
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/admin/alertas/<int:id_alerta>/atender', methods=['PUT'])
@admin_required
def atender_alerta(id_alerta):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE alertas_rapidas SET estado = 'Atendida' WHERE id_alerta = %s", (id_alerta,))
        conn.commit()
        return jsonify({'exito': True, 'mensaje': 'Alerta S.O.S marcada como atendida.'}), 200
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# -------------------------------------------------------------
# NOTIFICACIONES DEL VECINO
# -------------------------------------------------------------

@app.route('/api/mis-notificaciones', methods=['GET'])
@login_required
def mis_notificaciones():
    conn = None
    cursor = None
    try:
        id_usuario = session['usuario']['id_usuario']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT 
                r.id_reporte,
                r.codigo_seguimiento,
                r.es_falso_reporte,
                e.nombre AS estado,
                t.nombre AS tipo,
                r.fecha_registro
            FROM reportes r
            INNER JOIN estados_reporte e ON r.id_estado = e.id_estado
            INNER JOIN tipos_incidente t ON r.id_tipo = t.id_tipo
            WHERE r.id_usuario = %s
            ORDER BY r.fecha_registro DESC
            LIMIT 10
        """
        cursor.execute(query, (id_usuario,))
        reportes = cursor.fetchall()
        
        notificaciones = []
        for rep in reportes:
            estado_lower = rep['estado'].lower()
            if rep['es_falso_reporte'] == 1:
                notificaciones.append({
                    'id': f"falso_{rep['id_reporte']}",
                    'titulo': f"Reporte Desestimado ({rep['codigo_seguimiento']})",
                    'mensaje': f"Tu reporte de {rep['tipo']} fue catalogado como no verídico por el COCODE.",
                    'tipo': 'error',
                    'icono': 'ri-close-circle-fill text-red-500'
                })
            elif estado_lower == 'atendido':
                notificaciones.append({
                    'id': f"aten_{rep['id_reporte']}",
                    'titulo': f"¡Incidente Resuelto! ({rep['codigo_seguimiento']})",
                    'mensaje': f"El COCODE o las autoridades comunitarias han atendido la alerta de {rep['tipo']}.",
                    'tipo': 'exito',
                    'icono': 'ri-checkbox-circle-fill text-emerald-500'
                })
            elif estado_lower == 'aprobado':
                notificaciones.append({
                    'id': f"aprob_{rep['id_reporte']}",
                    'titulo': f"Reporte Aprobado ({rep['codigo_seguimiento']})",
                    'mensaje': f"Tu reporte {rep['codigo_seguimiento']} fue validado y publicado en el mapa vecinal.",
                    'tipo': 'info',
                    'icono': 'ri-shield-check-fill text-blue-500'
                })

        return jsonify({'exito': True, 'notificaciones': notificaciones}), 200
    except Exception as e:
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# -------------------------------------------------------------
# MURO DE COMUNICADOS DEL COCODE
# -------------------------------------------------------------

@app.route('/api/comunicados', methods=['GET'])
@login_required
def listar_comunicados():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id_comunicado, titulo, contenido, categoria, fecha_publicacion 
            FROM comunicados 
            ORDER BY fecha_publicacion DESC 
            LIMIT 6
        """)
        return jsonify({'exito': True, 'data': cursor.fetchall()}), 200
    except Exception as e:
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/admin/comunicados', methods=['POST'])
@admin_required
def crear_comunicado():
    conn = None
    cursor = None
    try:
        data = request.json or {}
        titulo = data.get('titulo', '').strip()
        contenido = data.get('contenido', '').strip()
        categoria = data.get('categoria', 'General')
        id_admin = session['usuario']['id_usuario']

        if not titulo or not contenido:
            return jsonify({'exito': False, 'mensaje': 'Título y contenido requeridos.'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO comunicados (id_usuario_admin, titulo, contenido, categoria) 
            VALUES (%s, %s, %s, %s)
        """, (id_admin, titulo, contenido, categoria))
        conn.commit()
        return jsonify({'exito': True, 'mensaje': 'Comunicado oficial publicado exitosamente.'}), 201
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/admin/reportes/<int:id_reporte>', methods=['DELETE'])
@admin_required
def eliminar_reporte_admin(id_reporte):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. Obtener los datos del reporte y sus archivos asociados
        cursor.execute("SELECT foto, audio, codigo_seguimiento FROM reportes WHERE id_reporte = %s", (id_reporte,))
        reporte = cursor.fetchone()

        if not reporte:
            return jsonify({'exito': False, 'mensaje': 'Reporte no encontrado.'}), 404

        # 2. Borrar archivos físicos de evidencias si existen en disco
        if reporte.get('foto'):
            ruta_foto = os.path.join(app.config['UPLOAD_FOLDER_REPORTES'], reporte['foto'])
            if os.path.exists(ruta_foto):
                os.remove(ruta_foto)

        if reporte.get('audio'):
            ruta_audio = os.path.join(app.config['UPLOAD_FOLDER_AUDIOS'], reporte['audio'])
            if os.path.exists(ruta_audio):
                os.remove(ruta_audio)

        # 3. Eliminar únicamente el registro del reporte de la base de datos
        cursor.execute("DELETE FROM reportes WHERE id_reporte = %s", (id_reporte,))
        conn.commit()

        return jsonify({
            'exito': True, 
            'mensaje': f"Reporte {reporte['codigo_seguimiento']} eliminado correctamente de la bitácora."
        }), 200

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'exito': False, 'mensaje': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

if __name__ == '__main__':
    puerto = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=puerto)