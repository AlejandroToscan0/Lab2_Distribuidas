"""
Cliente CLI para el servidor TCP secuencial de calificaciones.

- Muestra un menú en consola para enviar comandos:
    AGREGAR|{id}|{materia}|{calificacion}
    BUSCAR|{id}
    ACTUALIZAR|{id}|{materia}|{nueva_calificacion}
    LISTAR
    ELIMINAR|{id}|{materia}

- Las respuestas del servidor son JSON por línea y se muestran de forma legible.

Uso:
        python3 client.py

Asegúrate de tener el servidor corriendo en 127.0.0.1:12345.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Dict, Optional

HOST = "127.0.0.1"
PORT = 12345
ESTUDIANTES_CSV = Path(__file__).resolve().parents[1] / "estudiantes.csv"


def load_estudiantes_map() -> Dict[str, str]:
    """Carga estudiantes.csv y devuelve un mapa {ID -> Nombre}."""
    mapping: Dict[str, str] = {}
    try:
        with ESTUDIANTES_CSV.open("r", encoding="utf-8") as f:
            # saltar encabezado
            header = f.readline()
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",", 1)
                if len(parts) == 2:
                    sid, nombre = parts[0].strip(), parts[1].strip()
                    if sid and sid != "ID_Estudiante":
                        mapping[sid] = nombre
    except FileNotFoundError:
        print("[client] Advertencia: estudiantes.csv no encontrado. Asegúrate de crearlo y poblarlo.")
    return mapping


def send_command(cmd: str) -> Optional[dict]:
    """Envía un comando por socket y devuelve la respuesta parseada como dict.
    Retorna None si ocurre algún error de conexión o parseo.
    """
    try:
        with socket.create_connection((HOST, PORT), timeout=5) as s:
            s.sendall((cmd + "\n").encode("utf-8"))
            # Leemos hasta el primer '\n'
            data = b""
            while True:
                chunk = s.recv(1024)
                if not chunk:
                    break
                data += chunk
                if b"\n" in chunk:
                    break
    except (ConnectionRefusedError, TimeoutError) as e:
        print(f"[client] No se pudo conectar al servidor: {e}")
        return None
    except Exception as e:
        print(f"[client] Error de comunicación: {e}")
        return None

    if not data:
        print("[client] Respuesta vacía del servidor")
        return None

    line = data.split(b"\n", 1)[0].decode("utf-8", errors="replace")
    try:
        return json.loads(line)
    except json.JSONDecodeError as e:
        print(f"[client] Respuesta no es JSON válido: {line}")
        return None


def menu() -> None:
    """Muestra el menú interactivo del cliente y procesa entradas del usuario."""
    while True:
        print("\n=== Menú Calificaciones (secuencial) ===")
        print("1) AGREGAR")
        print("2) BUSCAR")
        print("3) ACTUALIZAR")
        print("4) LISTAR TODAS LAS NOTAS")
        print("5) ELIMINAR")
        print("0) SALIR")

        opcion = input("Selecciona una opción: ").strip()

        if opcion == "1":
            student_id = input("ID estudiante: ").strip()
            est_map = load_estudiantes_map()
            nombre_canon = est_map.get(student_id)
            if not nombre_canon:
                print("[client] ID no existe en estudiantes.csv. Agrega el estudiante primero.")
                continue
            print(f"[client] Estudiante: {student_id} → {nombre_canon}")
            materia = input("Materia (NRC): ").strip()
            calificacion = input("Calificación: ").strip()
            # Solo enviar ID, materia y calificación
            cmd = f"AGREGAR|{student_id}|{materia}|{calificacion}"
        elif opcion == "2":
            student_id = input("ID estudiante a buscar: ").strip()
            cmd = f"BUSCAR|{student_id}"
        elif opcion == "3":
            student_id = input("ID estudiante a actualizar: ").strip()
            materia = input("Materia (NRC) a actualizar: ").strip()
            nueva_cal = input("Nueva calificación: ").strip()
            if materia:
                cmd = f"ACTUALIZAR|{student_id}|{materia}|{nueva_cal}"
            else:
                cmd = f"ACTUALIZAR|{student_id}|{nueva_cal}"
        elif opcion == "4":
            cmd = "LISTAR"
        elif opcion == "5":
            student_id = input("ID estudiante a eliminar: ").strip()
            materia = input("Materia (NRC) de la nota a eliminar: ").strip()
            if materia:
                cmd = f"ELIMINAR|{student_id}|{materia}"
            else:
                cmd = f"ELIMINAR|{student_id}"
        elif opcion == "0":
            print("Hasta luego.")
            break
        else:
            print("Opción inválida.")
            continue

        resp = send_command(cmd)
        if resp is None:
            continue
        print("\n--- Respuesta ---")
        # Pretty print del dict JSON
        print(json.dumps(resp, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    menu()
