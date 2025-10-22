# Laboratorio 2 – Gestión de Calificaciones (TCP) con/ sin hilos + microservicio NRC

## Participantes

- Lasso Sebastían
- Lugmaña Matias
- Toscano Jossue

## Objetivo

Se implementa un servicio TCP para gestionar calificaciones en archivos CSV con dos variantes: servidor secuencial y servidor concurrente (con hilos). La variante concurrente valida la materia (NRC) contra un microservicio TCP independiente.

## Estructura

```
calificaciones.csv
estudiantes.csv
nrcs.csv
nrcs_server.py
con_hilos/
  server.py
  client.py
sin_hilos/
  server.py
  client.py
```

## Requisitos

- Python 3.9+
- Puertos disponibles: 12345 (servidor de calificaciones), 12346 (microservicio NRC)
- SO: macOS/Linux/Windows

## Datos (CSV)

- `estudiantes.csv`
  ```csv
  ID_Estudiante,Nombre
  1,Ana
  2,Beto
  3,Carla
  4,Juanito
  5,Pedrito
  6,Lasso Sebastían
  7,Lugmaña Matias
  8,Toscano Jossue
  ```
- `calificaciones.csv`
  ```csv
  ID_Estudiante,Materia,Calificacion
  1,MAT101,10
  1,BD402,15
  6,MAT101,18
  6,BD402,16
  7,PRO201,17
  8,SOF301,19
  ```
- `nrcs.csv` (se autogenera si no existe)
  ```csv
  NRC,Materia
  MAT101,Matemáticas I
  PRO201,Programación II
  SOF301,Ingeniería de Software I
  BD402,Bases de Datos
  ```

Los servidores usan `estudiantes.csv` para resolver el nombre canónico; el servidor con hilos valida el NRC contra `nrcs_server.py`.

## Puertos

- Servidor de calificaciones: 127.0.0.1:12345
- Microservicio NRC: 127.0.0.1:12346

## Ejecución

Primero se asegura de tener corriendo el microservicio NRC.

### 1) Microservicio NRC

```zsh
cd "./Lab2_Distribuidas"
python3 nrcs_server.py
```

### 2A) Servidor secuencial (sin hilos)

```zsh
cd "./Lab2_Distribuidas/sin_hilos"
python3 server.py
```
En otra terminal:
```zsh
cd "./Lab2_Distribuidas/sin_hilos"
python3 client.py
```

### 2B) Servidor concurrente (con hilos + validación de NRC)

```zsh
cd "./Lab2_Distribuidas/con_hilos"
python3 server.py
```
En otra terminal:
```zsh
cd "./Lab2_Distribuidas/con_hilos"
python3 client.py
```

## Protocolo (línea por petición, JSON por respuesta)

- Secuencial: `AGREGAR|ID|Materia|Calificacion`, `BUSCAR|ID`, `ACTUALIZAR|ID|Materia|NuevaCal` o `ACTUALIZAR|ID|NuevaCal`, `LISTAR`, `ELIMINAR|ID|Materia` o `ELIMINAR|ID`.
- Concurrente: `AGREGAR|ID|Nombre|Materia(NRC)|Calificacion`, `BUSCAR|ID`, `ACTUALIZAR|ID|Materia|NuevaCal` o `ACTUALIZAR|ID|NuevaCal`, `LISTAR`, `ELIMINAR|ID|Materia` o `ELIMINAR|ID`.
- NRC: `BUSCAR_NRC|NRC` → `{status: ok|not_found|error, ...}`.

## Flujo mínimo (con hilos)

1) Ejecutar `nrcs_server.py` → `con_hilos/server.py` → `con_hilos/client.py`.
2) En el cliente: agregar una nota válida y luego listar/buscar.

### Pruebas rápidas (con hilos)

```text
AGREGAR|6|Lasso Sebastían|MAT101|18
AGREGAR|6|Lasso Sebastían|BD402|16
AGREGAR|7|Lugmaña Matias|PRO201|17
AGREGAR|8|Toscano Jossue|SOF301|19
BUSCAR|6
LISTAR
ACTUALIZAR|6|MAT101|19
ELIMINAR|6|BD402
```

### Pruebas rápidas (sin hilos)

```text
AGREGAR|6|MAT101|18
AGREGAR|6|BD402|16
BUSCAR|6
LISTAR
ACTUALIZAR|6|MAT101|19
ELIMINAR|6|BD402
```

## Notas de diseño

- `con_hilos/server.py` usa un hilo por conexión y `threading.Lock` para proteger el CSV.
- Se persiste `ID_Estudiante`, `Materia`, `Calificacion`; el nombre se resuelve desde `estudiantes.csv`.
- `nrcs_server.py` valida NRC y autogenera `nrcs.csv` si falta.

## Problemas comunes

- No conecta: verificar servidor en 127.0.0.1:12345 y microservicio en 127.0.0.1:12346 (para con hilos).
- Puerto en uso: cerrar procesos previos o cambiar puertos.
- `ID_Estudiante` no encontrado: agregarlo a `estudiantes.csv`.
- `NRC` no encontrado (con hilos): usar un NRC existente en `nrcs.csv`.

## Resetear datos

```zsh
rm -f "./Lab2_Distribuidas/calificaciones.csv" "./Lab2_Distribuidas/estudiantes.csv" "./Lab2_Distribuidas/nrcs.csv"
```
Luego se vuelve a ejecutar `nrcs_server.py` y los servidores según el modo elegido.

