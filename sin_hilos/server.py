"""
Servidor TCP secuencial (sin hilos) para gestionar calificaciones.

- Protocolo de texto por línea (\"\n\"): comandos
  AGREGAR|{id}|{nombre}|{materia}|{calificacion}
  BUSCAR|{id}
  ACTUALIZAR|{id}|{nueva_calificacion}
  LISTAR
  ELIMINAR|{id}

- Respuestas como JSON (dicts serializados) terminadas en \n.
- Persistencia en CSV con encabezados: ID_Estudiante,Nombre,Materia,Calificacion

Uso:
    python3 server.py

Requisitos: Python 3.9+, librerías estándar (socket, csv, json).
"""
from __future__ import annotations

import csv
import json
import os
import socket
import sys
from pathlib import Path
from typing import Dict, List, Optional

HOST = "127.0.0.1"  # localhost
PORT = 12345

# Ruta del CSV: laboratorio_2/calificaciones.csv
CSV_PATH = Path(__file__).resolve().parents[1] / "calificaciones.csv"
# Ahora persistimos solo ID, Materia, Calificacion (el Nombre se resuelve por join)
FIELDNAMES = ["ID_Estudiante", "Materia", "Calificacion"]
ESTUDIANTES_CSV = Path(__file__).resolve().parents[1] / "estudiantes.csv"
ESTUDIANTES_FIELDS = ["ID_Estudiante", "Nombre"]


def log(msg: str) -> None:
    """Imprime logs simples en stdout (se puede reemplazar por logging si se desea)."""
    print(f"[server] {msg}")


def ensure_csv_exists() -> None:
    """Crea el archivo CSV con encabezados si no existe."""
    if not CSV_PATH.exists():
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
        log(f"CSV creado en: {CSV_PATH}")


def ensure_estudiantes_csv_exists() -> None:
    """Crea estudiantes.csv con encabezados si no existe."""
    if not ESTUDIANTES_CSV.exists():
        ESTUDIANTES_CSV.parent.mkdir(parents=True, exist_ok=True)
        with ESTUDIANTES_CSV.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=ESTUDIANTES_FIELDS)
            writer.writeheader()
        log(f"CSV estudiantes creado en: {ESTUDIANTES_CSV}")


def load_records() -> List[Dict[str, str]]:
    """Carga todos los registros del CSV como lista de dicts (strings)."""
    ensure_csv_exists()
    with CSV_PATH.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def save_records(records: List[Dict[str, str]]) -> None:
    """Sobrescribe el CSV con la lista de registros dada."""
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(records)


def get_estudiante_nombre(student_id: str) -> Optional[str]:
    """Lee estudiantes.csv y devuelve el nombre del estudiante si existe, sino None."""
    ensure_estudiantes_csv_exists()
    with ESTUDIANTES_CSV.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("ID_Estudiante") == student_id:
                return row.get("Nombre") or ""
    return None


def load_estudiantes_map() -> Dict[str, str]:
    """Devuelve un mapa {ID_Estudiante -> Nombre} desde estudiantes.csv."""
    ensure_estudiantes_csv_exists()
    out: Dict[str, str] = {}
    with ESTUDIANTES_CSV.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row.get("ID_Estudiante")
            if sid:
                out[sid] = row.get("Nombre") or ""
    return out


def find_by_id(student_id: str) -> Optional[Dict[str, str]]:
    """Busca un registro por ID_Estudiante. Devuelve el dict o None si no existe."""
    for row in load_records():
        if row.get("ID_Estudiante") == student_id:
            return row
    return None


def handle_agregar(parts: List[str]) -> Dict:
    """AGREGAR|{id}|{materia}|{calificacion}"""
    if len(parts) != 4:
        return {"status": "error", "message": "Formato inválido para AGREGAR. Usa: AGREGAR|ID|Materia|Calificacion"}

    student_id, materia, calificacion = parts[1], parts[2], parts[3]

    # Validación simple de ID y calificación
    if not student_id:
        return {"status": "error", "message": "ID_Estudiante vacío"}

    # Validar existencia en estudiantes.csv y usar nombre canónico
    nombre_canonico = get_estudiante_nombre(student_id)
    if nombre_canonico is None:
        return {"status": "error", "message": "ID_Estudiante no encontrado en estudiantes.csv"}

    records = load_records()
    # Unicidad por par (ID_Estudiante, Materia)
    if any(r["ID_Estudiante"] == student_id and r.get("Materia") == materia for r in records):
        return {"status": "error", "message": "La nota para ese ID y Materia ya existe"}

    # Persistimos sin el campo Nombre
    new_row = {
        "ID_Estudiante": student_id,
        "Materia": materia,
        "Calificacion": calificacion,
    }
    records.append(new_row)
    save_records(records)
    log(f"AGREGADO: {new_row} (nombre canónico: {nombre_canonico})")
    # Responder incluyendo el nombre canónico para comodidad del cliente
    resp_data = dict(new_row)
    resp_data["Nombre"] = nombre_canonico
    return {"status": "ok", "data": resp_data}


def handle_buscar(parts: List[str]) -> Dict:
    """BUSCAR|{id}"""
    if len(parts) != 2:
        return {"status": "error", "message": "Formato inválido para BUSCAR"}
    student_id = parts[1]
    # Devolver todas las notas del estudiante
    rows = [r for r in load_records() if r.get("ID_Estudiante") == student_id]
    if not rows:
        return {"status": "not_found", "message": "No existe el ID"}
    est_map = load_estudiantes_map()
    nombre_canon = est_map.get(student_id)
    enriched: List[Dict[str, str]] = []
    for r in rows:
        rr = dict(r)
        if nombre_canon:
            rr["Nombre"] = nombre_canon
        enriched.append(rr)
    return {"status": "ok", "data": enriched}


def handle_actualizar(parts: List[str]) -> Dict:
    """ACTUALIZAR|{id}|{nueva_calificacion} o ACTUALIZAR|{id}|{materia}|{nueva_calificacion}

    - Si se especifica materia, actualiza solo esa nota.
    - Si no se especifica, y hay exactamente 1 nota para el ID, actualiza esa.
      Si hay 0 → not_found; si hay >1 → error pidiendo materia.
    """
    if len(parts) not in (3, 4):
        return {"status": "error", "message": "Formato inválido para ACTUALIZAR (use ID|nueva o ID|Materia|nueva)"}

    student_id = parts[1]
    if len(parts) == 4:
        materia, nueva_cal = parts[2], parts[3]
        records = load_records()
        updated = False
        for r in records:
            if r["ID_Estudiante"] == student_id and r.get("Materia") == materia:
                r["Calificacion"] = nueva_cal
                updated = True
                break
        if not updated:
            return {"status": "not_found", "message": "No existe nota para ese ID y Materia"}
        save_records(records)
        log(f"ACTUALIZADO: ID={student_id}, Materia={materia}, nueva_cal={nueva_cal}")
        return {"status": "ok", "data": {"ID_Estudiante": student_id, "Materia": materia, "Calificacion": nueva_cal}}
    else:
        nueva_cal = parts[2]
        records = load_records()
        notas_id = [r for r in records if r.get("ID_Estudiante") == student_id]
        if not notas_id:
            return {"status": "not_found", "message": "No existe el ID"}
        if len(notas_id) > 1:
            return {"status": "error", "message": "El ID tiene varias notas; use ACTUALIZAR|ID|Materia|nueva"}
        materia = notas_id[0].get("Materia")
        for r in records:
            if r["ID_Estudiante"] == student_id and r.get("Materia") == materia:
                r["Calificacion"] = nueva_cal
                break
        save_records(records)
        log(f"ACTUALIZADO: ID={student_id}, Materia={materia}, nueva_cal={nueva_cal}")
        return {"status": "ok", "data": {"ID_Estudiante": student_id, "Materia": materia, "Calificacion": nueva_cal}}


def handle_listar(parts: List[str]) -> Dict:
    """LISTAR"""
    if len(parts) != 1:
        return {"status": "error", "message": "Formato inválido para LISTAR"}
    rows = load_records()
    # Join con estudiantes.csv para devolver nombre canónico
    est_map = load_estudiantes_map()
    enriched: List[Dict[str, str]] = []
    for r in rows:
        rr = dict(r)
        sid = rr.get("ID_Estudiante", "")
        nombre_canon = est_map.get(sid)
        if nombre_canon:
            rr["Nombre"] = nombre_canon
        enriched.append(rr)
    return {"status": "ok", "data": enriched}


def handle_eliminar(parts: List[str]) -> Dict:
    """ELIMINAR|{id}|{materia}

    Comportamiento:
    - Si se proveen ID y Materia, elimina solo esa nota específica.
    - Si solo se provee ID y hay exactamente 1 nota para ese ID, elimina esa única nota.
      Si hay 0 notas → not_found; si hay >1 notas → error pidiendo especificar materia.
    """
    if len(parts) not in (2, 3):
        return {"status": "error", "message": "Formato inválido para ELIMINAR (use ID o ID|Materia)"}

    student_id = parts[1]
    materia = parts[2] if len(parts) == 3 else None
    records = load_records()

    if materia:
        # Eliminar solo la nota específica
        new_records = [r for r in records if not (r.get("ID_Estudiante") == student_id and r.get("Materia") == materia)]
        if len(new_records) == len(records):
            return {"status": "not_found", "message": "No existe nota para ese ID y Materia"}
        save_records(new_records)
        log(f"ELIMINADO: ID={student_id}, Materia={materia}")
        return {"status": "ok", "data": {"ID_Estudiante": student_id, "Materia": materia}}
    else:
        # Sin materia: decidir según cuántas notas tiene el ID
        notas_id = [r for r in records if r.get("ID_Estudiante") == student_id]
        if not notas_id:
            return {"status": "not_found", "message": "No existe el ID"}
        if len(notas_id) > 1:
            return {"status": "error", "message": "El ID tiene varias notas; especifique Materia (ELIMINAR|ID|Materia)"}
        # Tiene exactamente una nota: elimínala
        unica_materia = notas_id[0].get("Materia")
        new_records = [r for r in records if not (r.get("ID_Estudiante") == student_id and r.get("Materia") == unica_materia)]
        save_records(new_records)
        log(f"ELIMINADO: ID={student_id}, Materia={unica_materia}")
        return {"status": "ok", "data": {"ID_Estudiante": student_id, "Materia": unica_materia}}


def process_command(line: str) -> Dict:
    """Procesa una línea de comando y devuelve la respuesta (dict)."""
    line = line.strip()
    parts = line.split("|") if line else []
    if not parts:
        return {"status": "error", "message": "Comando vacío"}

    cmd = parts[0].upper()
    if cmd == "AGREGAR":
        return handle_agregar(parts)
    if cmd == "BUSCAR":
        return handle_buscar(parts)
    if cmd == "ACTUALIZAR":
        return handle_actualizar(parts)
    if cmd == "LISTAR":
        return handle_listar(parts)
    if cmd == "ELIMINAR":
        return handle_eliminar(parts)

    return {"status": "error", "message": f"Comando desconocido: {cmd}"}


def recv_line(conn: socket.socket) -> Optional[str]:
    """Lee desde el socket hasta encontrar un '\n' o cierre de conexión.
    Devuelve la línea (incluye datos antes de '\n') o None si no hay datos.
    """
    buffer = bytearray()
    while True:
        chunk = conn.recv(1024)
        if not chunk:
            break
        buffer.extend(chunk)
        if b"\n" in chunk:
            break
    if not buffer:
        return None
    # Consideramos solo hasta el primer salto de línea
    line = buffer.split(b"\n", 1)[0].decode("utf-8", errors="replace")
    return line


def serve_forever() -> None:
    """Inicia el servidor TCP secuencial y atiende clientes de a uno por vez."""
    ensure_csv_exists()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        log(f"Servidor escuchando en {HOST}:{PORT} (secuencial)")

        while True:
            conn, addr = s.accept()
            with conn:
                log(f"Conexión de {addr}")
                try:
                    line = recv_line(conn)
                    if line is None:
                        log("Cliente cerró sin enviar datos")
                        continue
                    log(f"Comando recibido: {line}")
                    resp = process_command(line)
                except Exception as e:
                    resp = {"status": "error", "message": f"Excepción: {e}"}

                # Enviamos JSON + \n
                payload = json.dumps(resp, ensure_ascii=False)
                try:
                    conn.sendall((payload + "\n").encode("utf-8"))
                except Exception as e:
                    log(f"Error enviando respuesta: {e}")
                log(f"Respuesta enviada: {resp}")


if __name__ == "__main__":
    try:
        serve_forever()
    except KeyboardInterrupt:
        log("Servidor detenido por el usuario (Ctrl+C)")
        sys.exit(0)
