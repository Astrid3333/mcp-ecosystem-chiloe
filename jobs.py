"""
jobs.py
Gestión simple de trabajos (jobs) en background para GROMACS y LAMMPS.

Guarda el estado de cada trabajo en ~/.md_mcp/jobs.json para poder consultarlo
más tarde desde otra llamada MCP (cada llamada de herramienta es "sin estado",
así que persistimos en disco).
"""

import json
import os
import shlex
import time
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

JOBS_DIR = Path.home() / ".md_mcp"
JOBS_FILE = JOBS_DIR / "jobs.json"


def _ensure_store() -> None:
    """Crea el directorio y archivo de jobs si no existen."""
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    if not JOBS_FILE.exists():
        JOBS_FILE.write_text("{}")


def _load() -> Dict[str, Any]:
    """Carga todos los trabajos desde el archivo JSON.

    Returns:
        Diccionario con los trabajos indexados por job_id.
        Devuelve diccionario vacío si el archivo no existe o está corrupto.
    """
    _ensure_store()
    try:
        raw = JOBS_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: Dict[str, Any]) -> None:
    """Guarda todos los trabajos en el archivo JSON.

    Args:
        data: Diccionario con los trabajos a persistir.
    """
    JOBS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def create_job(
    job_name: str,
    engine: str,
    cwd: str,
    log_path: str,
    cmd: str,
) -> str:
    """Registra un nuevo trabajo (todavía no lanzado) y devuelve su job_id.

    Args:
        job_name: Nombre legible del trabajo.
        engine: Motor de simulación (ej: "gromacs", "lammps").
        cwd: Directorio de trabajo donde se ejecutará el comando.
        log_path: Ruta al archivo de registro (log) de salida.
        cmd: Comando de shell a ejecutar.

    Returns:
        Identificador único del trabajo (job_id).
    """
    jobs = _load()
    job_id = f"{engine}_{job_name}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    jobs[job_id] = {
        "job_id": job_id,
        "job_name": job_name,
        "engine": engine,
        "cwd": str(cwd),
        "log_path": str(log_path),
        "cmd": cmd,
        "pid": None,
        "status": "created",
        "created_at": time.time(),
        "finished_at": None,
    }
    _save(jobs)
    return job_id


def start_job(job_id: str) -> int:
    """Lanza el proceso en background (estilo nohup) y devuelve su PID.

    Args:
        job_id: Identificador del trabajo previamente creado.

    Returns:
        ID de proceso (PID) del trabajo lanzado.

    Raises:
        KeyError: Si el job_id no existe.
        FileNotFoundError: Si el comando no se puede ejecutar.
    """
    jobs = _load()
    if job_id not in jobs:
        raise KeyError(f"Trabajo '{job_id}' no encontrado")
    job = jobs[job_id]
    Path(job["cwd"]).mkdir(parents=True, exist_ok=True)
    log_file = open(job["log_path"], "w", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            shlex.split(job["cmd"]),
            cwd=job["cwd"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            shell=False,
            preexec_fn=os.setsid,  # para poder matar el grupo completo si hace falta
        )
    except Exception:
        log_file.close()
        raise
    job["pid"] = proc.pid
    job["status"] = "running"
    _save(jobs)
    return proc.pid


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Devuelve los datos de un trabajo por su ID.

    Args:
        job_id: Identificador del trabajo.

    Returns:
        Diccionario con los datos del trabajo, o None si no existe.
    """
    return _load().get(job_id)


def list_jobs() -> List[Dict[str, Any]]:
    """Devuelve la lista de todos los trabajos registrados.

    Returns:
        Lista de diccionarios, uno por cada trabajo.
    """
    return list(_load().values())


def _pid_alive(pid: Optional[int]) -> bool:
    """Verifica si un proceso sigue vivo.

    Args:
        pid: ID de proceso a comprobar.

    Returns:
        True si el proceso existe, False en caso contrario o si pid es None.
    """
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def refresh_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Revisa si el proceso sigue vivo y actualiza su estado guardado.

    Args:
        job_id: Identificador del trabajo.

    Returns:
        Diccionario actualizado del trabajo, o None si no existe.
    """
    jobs = _load()
    job = jobs.get(job_id)
    if not job:
        return None
    if job["status"] == "running" and not _pid_alive(job.get("pid")):
        job["status"] = "finished"
        job["finished_at"] = time.time()
        _save(jobs)
    return job


def tail_log(log_path: str, n_lines: int = 40) -> str:
    """Devuelve las últimas n líneas del archivo de registro de un trabajo.

    Args:
        log_path: Ruta al archivo de log.
        n_lines: Número de líneas a devolver desde el final (default 40).

    Returns:
        Texto con las últimas líneas del log, o cadena vacía si el archivo
        no existe.
    """
    p = Path(log_path)
    if not p.exists():
        return ""
    lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    return "\n".join(lines[-n_lines:])
