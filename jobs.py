"""
jobs.py
Gestión simple de trabajos (jobs) en background para GROMACS y LAMMPS.

Guarda el estado de cada job en ~/.md_mcp/jobs.json para poder consultarlo
más tarde desde otra llamada MCP (cada llamada de herramienta es "sin estado",
así que persistimos en disco).
"""

import json
import os
import time
import subprocess
from pathlib import Path

JOBS_DIR = Path.home() / ".md_mcp"
JOBS_FILE = JOBS_DIR / "jobs.json"


def _ensure_store():
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    if not JOBS_FILE.exists():
        JOBS_FILE.write_text("{}")


def _load():
    _ensure_store()
    try:
        return json.loads(JOBS_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def _save(data):
    JOBS_FILE.write_text(json.dumps(data, indent=2))


def create_job(job_name: str, engine: str, cwd: str, log_path: str, cmd: str) -> str:
    """Registra un nuevo job (todavía no lanzado) y devuelve su job_id."""
    jobs = _load()
    job_id = f"{engine}_{job_name}_{int(time.time())}"
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
    """Lanza el proceso en background (nohup-style) y devuelve el PID."""
    jobs = _load()
    job = jobs[job_id]
    Path(job["cwd"]).mkdir(parents=True, exist_ok=True)
    log_file = open(job["log_path"], "w")
    proc = subprocess.Popen(
        job["cmd"],
        cwd=job["cwd"],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        shell=True,
        preexec_fn=os.setsid,  # para poder matar el grupo completo si hace falta
    )
    job["pid"] = proc.pid
    job["status"] = "running"
    _save(jobs)
    return proc.pid


def get_job(job_id: str):
    return _load().get(job_id)


def list_jobs():
    return list(_load().values())


def _pid_alive(pid):
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def refresh_status(job_id: str):
    """Revisa si el proceso sigue vivo y actualiza el estado guardado."""
    jobs = _load()
    job = jobs.get(job_id)
    if not job:
        return None
    if job["status"] == "running" and not _pid_alive(job["pid"]):
        job["status"] = "finished"
        job["finished_at"] = time.time()
        _save(jobs)
    return job


def tail_log(log_path: str, n_lines: int = 40) -> str:
    """Devuelve las últimas n_lines del log del job."""
    p = Path(log_path)
    if not p.exists():
        return ""
    lines = p.read_text(errors="ignore").splitlines()
    return "\n".join(lines[-n_lines:])
