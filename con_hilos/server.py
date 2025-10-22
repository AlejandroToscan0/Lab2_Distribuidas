"""
Servidor TCP concurrente (con hilos) para gestionar calificaciones con validación de NRC.

- Puerto: 127.0.0.1:12345
- Protocolo de texto por línea con comandos:
  AGREGAR|{id}|{nombre}|{materia}|{calificacion}
  BUSCAR|{id}
  ACTUALIZAR|{id}|{nueva_calificacion}
  LISTAR
  ELIMINAR|{id}

- Respuestas como JSON por línea.
- Persistencia en laboratorio_2/calificaciones.csv (encabezados: ID_Estudiante,Nombre,Materia,Calificacion).
- Validación de Materia (NRC) al AGREGAR consultando al microservicio NRC (127.0.0.1:12346):
    BUSCAR_NRC|{nrc} → {status: "ok", data: {...}} o {status: "not_found"}
- Protección de acceso al CSV mediante threading.Lock.

Uso:
    python3 server.py

Requisitos: Python 3.9+, librerías estándar (socket, csv, json, threading).
"""
from __future__ import annotations

import csv
import json
import socket
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional

HOST = "127.0.0.1"
PORT = 12345

# Microservicio NRC
NRC_HOST = "127.0.0.1"
NRC_PORT = 12346

# CSV de calificaciones
CSV_PATH = (Path(__file__).resolve().parents[1] / "calificaciones.csv").resolve()
# Persistimos solo ID, Materia y Calificacion; Nombre se resuelve por join con estudiantes.csv
FIELDNAMES = ["ID_Estudiante", "Materia", "Calificacion"]
ESTUDIANTES_CSV = (Path(__file__).resolve().parents[1] / "estudiantes.csv").resolve()
ESTUDIANTES_FIELDS = ["ID_Estudiante", "Nombre"]

# Lock global para proteger acceso R/W al CSV
CSV_LOCK = threading.Lock()


def log(msg: str) -> None:
    print(f"[server-hilos] {msg}")


def ensure_csv_exists() -> None:
    if not CSV_PATH.exists():
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
        log(f"CSV creado en: {CSV_PATH}")


def ensure_estudiantes_csv_exists() -> None:
    if not ESTUDIANTES_CSV.exists():
        ESTUDIANTES_CSV.parent.mkdir(parents=True, exist_ok=True)
        with ESTUDIANTES_CSV.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=ESTUDIANTES_FIELDS)
            writer.writeheader()
        log(f"CSV estudiantes creado en: {ESTUDIANTES_CSV}")


def load_records() -> List[Dict[str, str]]:
    with CSV_PATH.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def save_records(records: List[Dict[str, str]]) -> None:
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(records)


def get_estudiante_nombre(student_id: str) -> Optional[str]:
    """Lee estudiantes.csv y devuelve el nombre si el ID existe, sino None."""
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


def recv_line(conn: socket.socket) -> Optional[str]:
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
    return buffer.split(b"\n", 1)[0].decode("utf-8", errors="replace")


def consultar_nrc(nrc: str) -> Dict:
    """Consulta al microservicio NRC. Devuelve dict JSON decodificado.
    Posibles resultados: {status: "ok", data: {...}} | {status: "not_found"}
    En caso de error de red, retorna {status: "error", "message": "..."}.
    """
    try:
        with socket.create_connection((NRC_HOST, NRC_PORT), timeout=3) as s:
            s.sendall((f"BUSCAR_NRC|{nrc}\n").encode("utf-8"))
            data = b""
            while True:
                chunk = s.recv(1024)
                if not chunk:
                    break
                data += chunk
                if b"\n" in chunk:
                    break
    except Exception as e:
        return {"status": "error", "message": f"NRC service error: {e}"}

    if not data:
        return {"status": "error", "message": "NRC service sin respuesta"}

    line = data.split(b"\n", 1)[0].decode("utf-8", errors="replace")
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {"status": "error", "message": f"NRC JSON inválido: {line}"}


# Handlers de comandos

def handle_agregar(parts: List[str]) -> Dict:
    if len(parts) != 5:
        return {"status": "error", "message": "Formato inválido para AGREGAR"}

    student_id, nombre, materia, calificacion = parts[1], parts[2], parts[3], parts[4]

    # Validar NRC con microservicio ANTES de tomar el lock para minimizar bloqueo
    nrc_resp = consultar_nrc(materia)
    if nrc_resp.get("status") == "error":
        return {"status": "error", "message": f"Fallo validación NRC: {nrc_resp.get('message')}"}
    if nrc_resp.get("status") == "not_found":
        return {"status": "error", "message": f"NRC no encontrado: {materia}"}

    # Validar existencia de estudiante por fuera del lock (lectura independiente)
    nombre_canonico = get_estudiante_nombre(student_id)
    if nombre_canonico is None:
        return {"status": "error", "message": "ID_Estudiante no encontrado en estudiantes.csv"}

    with CSV_LOCK:
        ensure_csv_exists()
        records = load_records()
        # Unicidad por par (ID_Estudiante, Materia)
        if any(r["ID_Estudiante"] == student_id and r.get("Materia") == materia for r in records):
            return {"status": "error", "message": "La nota para ese ID y Materia ya existe"}
        new_row = {
            "ID_Estudiante": student_id,
            "Materia": materia,
            "Calificacion": calificacion,
        }
        records.append(new_row)
        save_records(records)
        log(f"AGREGADO: {new_row} (nombre canónico: {nombre_canonico})")
        resp_data = dict(new_row)
        resp_data["Nombre"] = nombre_canonico
        return {"status": "ok", "data": resp_data}


def handle_buscar(parts: List[str]) -> Dict:
    if len(parts) != 2:
        return {"status": "error", "message": "Formato inválido para BUSCAR"}
    student_id = parts[1]
    with CSV_LOCK:
        ensure_csv_exists()
        rows = [dict(r) for r in load_records() if r.get("ID_Estudiante") == student_id]
    if not rows:
        return {"status": "not_found", "message": "No existe el ID"}
    # Enriquecer todas con nombre canónico
    est_map = load_estudiantes_map()
    nombre_canon = est_map.get(student_id)
    if nombre_canon:
        for rr in rows:
            rr["Nombre"] = nombre_canon
    return {"status": "ok", "data": rows}


def handle_actualizar(parts: List[str]) -> Dict:
    if len(parts) not in (3, 4):
        return {"status": "error", "message": "Formato inválido para ACTUALIZAR (use ID|nueva o ID|Materia|nueva)"}
    student_id = parts[1]
    if len(parts) == 4:
        materia, nueva_cal = parts[2], parts[3]
        with CSV_LOCK:
            ensure_csv_exists()
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
        with CSV_LOCK:
            ensure_csv_exists()
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
    if len(parts) != 1:
        return {"status": "error", "message": "Formato inválido para LISTAR"}
    with CSV_LOCK:
        ensure_csv_exists()
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
    if len(parts) not in (2, 3):
        return {"status": "error", "message": "Formato inválido para ELIMINAR (use ID o ID|Materia)"}
    student_id = parts[1]
    materia = parts[2] if len(parts) == 3 else None
    with CSV_LOCK:
        ensure_csv_exists()
        records = load_records()
        if materia:
            new_records = [r for r in records if not (r.get("ID_Estudiante") == student_id and r.get("Materia") == materia)]
            if len(new_records) == len(records):
                return {"status": "not_found", "message": "No existe nota para ese ID y Materia"}
            save_records(new_records)
        else:
            notas_id = [r for r in records if r.get("ID_Estudiante") == student_id]
            if not notas_id:
                return {"status": "not_found", "message": "No existe el ID"}
            if len(notas_id) > 1:
                return {"status": "error", "message": "El ID tiene varias notas; especifique Materia (ELIMINAR|ID|Materia)"}
            unica_materia = notas_id[0].get("Materia")
            new_records = [r for r in records if not (r.get("ID_Estudiante") == student_id and r.get("Materia") == unica_materia)]
            save_records(new_records)
    if materia:
        log(f"ELIMINADO: ID={student_id}, Materia={materia}")
        return {"status": "ok", "data": {"ID_Estudiante": student_id, "Materia": materia}}
    else:
        log(f"ELIMINADO: ID={student_id}, Materia={unica_materia}")
        return {"status": "ok", "data": {"ID_Estudiante": student_id, "Materia": unica_materia}}


def process_command(line: str) -> Dict:
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


def handle_client(conn: socket.socket, addr) -> None:
    with conn:
        log(f"Conexión de {addr}")
        try:
            line = recv_line(conn)
            if line is None:
                return
            log(f"Cmd: {line}")
            resp = process_command(line)
        except Exception as e:
            resp = {"status": "error", "message": f"Excepción: {e}"}
        payload = json.dumps(resp, ensure_ascii=False)
        try:
            conn.sendall((payload + "\n").encode("utf-8"))
        except Exception as e:
            log(f"Error enviando respuesta: {e}")


def serve_forever() -> None:
    ensure_csv_exists()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        log(f"Servidor concurrente en {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()


if __name__ == "__main__":
    try:
        serve_forever()
    except KeyboardInterrupt:
        log("Servidor detenido por el usuario")
        sys.exit(0)
