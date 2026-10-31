CREATE DATABASE bd_incidentes_champollap 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_spanish_ci;

USE bd_incidentes_champollap;

-- 1. Roles del Sistema
CREATE TABLE roles (
    id_rol INT AUTO_INCREMENT PRIMARY KEY,
    nombre_rol VARCHAR(50) NOT NULL UNIQUE,
    descripcion VARCHAR(255) NULL
) ENGINE=InnoDB;

-- 2. Padrón Comunitario de Usuarios (Vecinos y Administradores COCODE)
CREATE TABLE usuarios (
    id_usuario INT AUTO_INCREMENT PRIMARY KEY,
    id_rol INT NOT NULL DEFAULT 2,
    nombres VARCHAR(100) NOT NULL,
    apellidos VARCHAR(100) NOT NULL,
    dpi VARCHAR(13) NOT NULL UNIQUE, 
    telefono VARCHAR(15) NOT NULL UNIQUE,
    correo VARCHAR(100) NOT NULL UNIQUE,
    direccion_champollap TEXT NOT NULL, 
    contrasena_hash VARCHAR(255) NOT NULL, 
    estado_aprobacion ENUM('Pendiente', 'Aprobado', 'Rechazado') DEFAULT 'Pendiente',
    aprobado_por INT NULL, 
    fecha_aprobacion DATETIME NULL,
    falsos_reportes_acumulados INT DEFAULT 0,
    cuenta_suspendida TINYINT(1) DEFAULT 0, 
    fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_rol) REFERENCES roles(id_rol),
    FOREIGN KEY (aprobado_por) REFERENCES usuarios(id_usuario)
) ENGINE=InnoDB;

-- 3. Tipos de Incidente
CREATE TABLE tipos_incidente (
    id_tipo INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE, 
    descripcion TEXT NULL,
    nivel_prioridad ENUM('Baja', 'Media', 'Alta', 'Critica') DEFAULT 'Media'
) ENGINE=InnoDB;

-- 4. Estados de Reporte (Alineados estrictamente con app.py)
CREATE TABLE estados_reporte (
    id_estado INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(30) NOT NULL UNIQUE 
) ENGINE=InnoDB;

-- 5. Tabla de Reportes Comunitarios
CREATE TABLE reportes (
    id_reporte INT AUTO_INCREMENT PRIMARY KEY,
    codigo_seguimiento VARCHAR(20) NOT NULL UNIQUE, 
    id_usuario INT NOT NULL, 
    id_tipo INT NOT NULL,
    id_estado INT NOT NULL DEFAULT 1, 
    descripcion TEXT NOT NULL,
    fecha_hora_incidente DATETIME NOT NULL,
    latitud DECIMAL(10, 8) NOT NULL,
    longitud DECIMAL(11, 8) NOT NULL,
    origen_ubicacion ENUM('GPS_Automatico', 'Marcacion_Manual', 'GPS_Predeterminado') NOT NULL,
    foto VARCHAR(255) NULL,
    es_falso_reporte TINYINT(1) DEFAULT 0, 
    fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario),
    FOREIGN KEY (id_tipo) REFERENCES tipos_incidente(id_tipo),
    FOREIGN KEY (id_estado) REFERENCES estados_reporte(id_estado)
) ENGINE=InnoDB;

-- 6. Botón de Pánico y Alertas Rápidas (S.O.S)
CREATE TABLE alertas_rapidas (
    id_alerta INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,
    latitud DECIMAL(10, 8) NOT NULL,
    longitud DECIMAL(11, 8) NOT NULL,
    estado ENUM('Activa', 'Atendida', 'Falsa_Alarma') DEFAULT 'Activa',
    fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
) ENGINE=InnoDB;

-- -------------------------------------------------------------
-- CARGA DE REGISTROS INICIALES Y CATÁLOGOS OFICIALES
-- -------------------------------------------------------------

-- Roles
INSERT INTO roles (id_rol, nombre_rol, descripcion) VALUES 
(1, 'Administrador', 'Líder COCODE con control administrativo total'),
(2, 'Vecino', 'Residente acreditado de Aldea Champollap');

-- Estados de reporte
INSERT INTO estados_reporte (id_estado, nombre) VALUES 
(1, 'Pendiente'),
(2, 'Aprobado'),
(3, 'Atendido'),
(4, 'Desestimado');

-- Tipos de incidentes
INSERT INTO tipos_incidente (id_tipo, nombre, nivel_prioridad) VALUES 
(1, 'Accidente de Tránsito', 'Alta'),
(2, 'Robo / Asalto', 'Alta'),
(3, 'Actividad Sospechosa', 'Media'),
(4, 'Emergencia Médica / Incendio', 'Critica'),
(5, 'Problemas entre Vecinos', 'Baja');

-- Usuarios semilla
-- Administrador: admin@champollap.gt  | Clave: admin2026
-- Vecino:        vecino@champollap.gt | Clave: vecino123
INSERT INTO usuarios 
(id_usuario, id_rol, nombres, apellidos, dpi, telefono, correo, direccion_champollap, contrasena_hash, estado_aprobacion, cuenta_suspendida) 
VALUES 
(1, 1, 'Comité', 'COCODE', '1234567890123', '55554444', 'admin@champollap.gt', 'Sector Central, Champollap', 'scrypt:32768:8:1$W763YJpP1f4r1PcL$35f3dfd9cb8a994784a929cfce7a69bcdd66432655bf968b59d99ba4266ba9a2b535d8ee75b69c76b92fdf21f7831ce2256b106368d184f45ecb37119ff7f2b1', 'Aprobado', 0),
(2, 2, 'Juan', 'Pérez', '9876543210987', '77778888', 'vecino@champollap.gt', 'Sector Las Manzanas, Champollap', 'scrypt:32768:8:1$W763YJpP1f4r1PcL$35f3dfd9cb8a994784a929cfce7a69bcdd66432655bf968b59d99ba4266ba9a2b535d8ee75b69c76b92fdf21f7831ce2256b106368d184f45ecb37119ff7f2b1', 'Aprobado', 0);

COMMIT;

ALTER TABLE reportes MODIFY COLUMN origen_ubicacion VARCHAR(50) NOT NULL;