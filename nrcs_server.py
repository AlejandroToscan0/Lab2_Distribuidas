"""
Microservicio TCP de NRC (catálogo de materias por NRC).

- Puerto: 127.0.0.1:12346
- Protocolo por línea ("\n") con comando:
    BUSCAR_NRC|{nrc}
- Respuestas como JSON por línea:
    {"status": "ok", "data": {"NRC": "MAT101", "Materia": "Matemáticas I"}}
    {"status": "not_found"}
    {"status": "error", "message": "..."}

Lee el archivo CSV `laboratorio_2/nrcs.csv` con columnas: NRC,Materia.
Crea el CSV con semillas si no existe.

Uso:
    python3 nrcs_server.py

Requisitos: Python 3.9+, librerías estándar (socket, csv, json).
"""
from __future__ import annotations

import csv
import json
import socket
import sys
from pathlib import Path
from typing import Dict, Optional

HOST = "127.0.0.1"
PORT = 12346

BASE_DIR = Path(__file__).resolve().parent
NRCS_CSV = BASE_DIR / "nrcs.csv"
FIELDNAMES = ["NRC", "Materia"]


SEEDS = [
    {"NRC": "MAT101", "Materia": "Matemáticas I"},
    {"NRC": "PRO201", "Materia": "Programación II"},
    {"NRC": "SOF301", "Materia": "Ingeniería de Software I"},
    {"NRC": "BD102", "Materia": "Bases de Datos"},
]


def log(msg: str) -> None:
    print(f"[nrcs] {msg}")


def ensure_nrcs_csv_exists() -> None:
    """Crea nrcs.csv con semillas si no existe."""
    if not NRCS_CSV.exists():
        NRCS_CSV.parent.mkdir(parents=True, exist_ok=True)
        with NRCS_CSV.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(SEEDS)
        log(f"CSV NRC creado en: {NRCS_CSV}")


def load_nrc_map() -> Dict[str, Dict[str, str]]:
    """Carga el CSV como mapa NRC -> registro {NRC, Materia}."""
    ensure_nrcs_csv_exists()
    out: Dict[str, Dict[str, str]] = {}
    with NRCS_CSV.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            nrc = row.get("NRC")
            if nrc:
                out[nrc] = {"NRC": row.get("NRC", ""), "Materia": row.get("Materia", "")}
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


def process(line: str) -> Dict:
    line = line.strip()
    parts = line.split("|") if line else []
    if not parts:
        return {"status": "error", "message": "Comando vacío"}

    cmd = parts[0].upper()
    if cmd != "BUSCAR_NRC" or len(parts) != 2:
        return {"status": "error", "message": "Formato: BUSCAR_NRC|{nrc}"}

    nrc = parts[1]
    nrc_map = load_nrc_map()
    data = nrc_map.get(nrc)
    if data:
        return {"status": "ok", "data": data}
    return {"status": "not_found"}


def serve_forever() -> None:
    ensure_nrcs_csv_exists()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        log(f"Microservicio NRC en {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            with conn:
                log(f"Conexión de {addr}")
                try:
                    line = recv_line(conn)
                    if line is None:
                        continue
                    log(f"Cmd: {line}")
                    resp = process(line)
                except Exception as e:
                    resp = {"status": "error", "message": f"Excepción: {e}"}
                payload = json.dumps(resp, ensure_ascii=False)
                try:
                    conn.sendall((payload + "\n").encode("utf-8"))
                except Exception as e:
                    log(f"Error enviando respuesta: {e}")


if __name__ == "__main__":
    try:
        serve_forever()
    except KeyboardInterrupt:
        log("NRC server detenido por el usuario")
        sys.exit(0)
