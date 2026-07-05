"""
server.py
Servidor MCP (Model Context Protocol) que expone herramientas para manejar
simulaciones de GROMACS y LAMMPS desde Claude: lanzar jobs, consultar estado,
parsear resultados y generar archivos de entrada.

Requiere que 'gmx' (GROMACS) y/o 'lmp' (LAMMPS) esten instalados y en el PATH
del sistema donde corre este servidor (ver install/ para instalarlos).

Uso:
    python3 server.py
(normalmente no se corre a mano; Claude Desktop/Claude Code lo lanza segun
la config del MCP, ver README.md)
"""

import shutil
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import jobs
import parsers
import templates

mcp = FastMCP("md-simulation")

WORKDIR = Path.home() / "md_mcp_runs"
WORKDIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------

@mcp.tool()
def check_installation() -> dict:
    """Verifica si GROMACS (gmx) y LAMMPS (lmp) estan instalados y disponibles en el PATH."""
    gmx_path = shutil.which("gmx")
    lmp_path = shutil.which("lmp") or shutil.which("lammps")

    result = {
        "gromacs_installed": gmx_path is not None,
        "gromacs_path": gmx_path,
        "lammps_installed": lmp_path is not None,
        "lammps_path": lmp_path,
    }

    if gmx_path:
        try:
            v = subprocess.run([gmx_path, "--version"], capture_output=True, text=True, timeout=10)
            result["gromacs_version_raw"] = v.stdout.splitlines()[0] if v.stdout else v.stderr.splitlines()[0]
        except Exception as e:
            result["gromacs_version_raw"] = f"error al consultar version: {e}"

    if lmp_path:
        try:
            v = subprocess.run([lmp_path, "-h"], capture_output=True, text=True, timeout=10)
            first_line = (v.stdout or v.stderr).splitlines()[0] if (v.stdout or v.stderr) else ""
            result["lammps_version_raw"] = first_line
        except Exception as e:
            result["lammps_version_raw"] = f"error al consultar version: {e}"

    if not gmx_path or not lmp_path:
        result["hint"] = (
            "Corre los scripts en install/install_gromacs.sh y/o "
            "install/install_lammps.sh en la maquina donde corre este servidor."
        )

    return result


# ---------------------------------------------------------------------
# Generacion de archivos de entrada
# ---------------------------------------------------------------------

@mcp.tool()
def generate_mdp(job_name: str, sim_type: str = "npt", nsteps: int = 50000,
                  dt: float = 0.002, temperature: float = 300.0,
                  extra_params: dict | None = None) -> dict:
    """
    Genera un archivo .mdp de GROMACS para un job.

    sim_type: 'em' (minimizacion), 'nvt', 'npt' o 'md' (produccion).
    Devuelve la ruta del archivo generado.
    """
    job_dir = WORKDIR / job_name
    job_dir.mkdir(parents=True, exist_ok=True)
    mdp_path = job_dir / f"{sim_type}.mdp"
    content = templates.gromacs_mdp_template(sim_type, nsteps, dt, temperature, extra_params)
    mdp_path.write_text(content)
    return {"mdp_path": str(mdp_path), "content_preview": content[:500]}


@mcp.tool()
def generate_lammps_input(job_name: str, sim_type: str = "nve", nsteps: int = 100000,
                           timestep: float = 0.001, temperature: float = 300.0,
                           extra_lines: list[str] | None = None) -> dict:
    """
    Genera un archivo .in de LAMMPS para un job.

    sim_type: 'min', 'nve', 'nvt' o 'npt'.
    Devuelve la ruta del archivo generado. Ojo: hay que editar la seccion
    de lectura de geometria (read_data) antes de correrlo.
    """
    job_dir = WORKDIR / job_name
    job_dir.mkdir(parents=True, exist_ok=True)
    in_path = job_dir / f"{sim_type}.in"
    content = templates.lammps_input_template(sim_type, nsteps, timestep, temperature, extra_lines)
    in_path.write_text(content)
    return {"input_path": str(in_path), "content_preview": content[:500]}


# ---------------------------------------------------------------------
# Lanzar simulaciones
# ---------------------------------------------------------------------

@mcp.tool()
def run_gromacs(job_name: str, mdp_path: str, gro_path: str, top_path: str,
                 output_dir: str | None = None, n_threads: int = 0) -> dict:
    """
    Lanza una simulacion de GROMACS en background: corre 'gmx grompp' para
    preparar el .tpr y luego 'gmx mdrun' para ejecutarla.

    mdp_path, gro_path, top_path: rutas a los archivos .mdp, .gro y .top.
    output_dir: carpeta donde correr el job (por defecto ~/md_mcp_runs/<job_name>).
    n_threads: 0 deja que GROMACS elija automaticamente.
    Devuelve un job_id para consultar estado despues con job_status().
    """
    if shutil.which("gmx") is None:
        return {"error": "gmx no esta instalado o no esta en el PATH. Corre install/install_gromacs.sh"}

    cwd = Path(output_dir) if output_dir else WORKDIR / job_name
    cwd.mkdir(parents=True, exist_ok=True)
    log_path = cwd / "mdrun.log"

    nt_flag = f"-nt {n_threads}" if n_threads and n_threads > 0 else ""
    cmd = (
        f"gmx grompp -f {mdp_path} -c {gro_path} -p {top_path} -o topol.tpr -maxwarn 5 "
        f"&& gmx mdrun -deffnm topol {nt_flag}"
    )

    job_id = jobs.create_job(job_name, "gromacs", str(cwd), str(log_path), cmd)
    pid = jobs.start_job(job_id)
    return {"job_id": job_id, "pid": pid, "cwd": str(cwd), "log_path": str(log_path)}


@mcp.tool()
def run_lammps(job_name: str, input_path: str, output_dir: str | None = None,
               n_procs: int = 1) -> dict:
    """
    Lanza una simulacion de LAMMPS en background (via 'lmp -in <input>' o 'mpirun -np N lmp ...').

    input_path: ruta al archivo .in de LAMMPS.
    output_dir: carpeta donde correr el job (por defecto ~/md_mcp_runs/<job_name>).
    n_procs: numero de procesos MPI (1 = sin mpirun).
    Devuelve un job_id para consultar estado despues con job_status().
    """
    lmp_bin = shutil.which("lmp") or shutil.which("lammps")
    if lmp_bin is None:
        return {"error": "lmp no esta instalado o no esta en el PATH. Corre install/install_lammps.sh"}

    cwd = Path(output_dir) if output_dir else WORKDIR / job_name
    cwd.mkdir(parents=True, exist_ok=True)
    log_path = cwd / "lammps_run.log"

    if n_procs and n_procs > 1:
        cmd = f"mpirun -np {n_procs} {lmp_bin} -in {input_path}"
    else:
        cmd = f"{lmp_bin} -in {input_path}"

    job_id = jobs.create_job(job_name, "lammps", str(cwd), str(log_path), cmd)
    pid = jobs.start_job(job_id)
    return {"job_id": job_id, "pid": pid, "cwd": str(cwd), "log_path": str(log_path)}


# ---------------------------------------------------------------------
# Estado y resultados
# ---------------------------------------------------------------------

@mcp.tool()
def job_status(job_id: str, log_tail_lines: int = 30) -> dict:
    """Consulta el estado de un job (created/running/finished) y muestra el final del log."""
    job = jobs.refresh_status(job_id)
    if job is None:
        return {"error": f"No se encontro el job_id: {job_id}"}
    job = dict(job)
    job["log_tail"] = jobs.tail_log(job["log_path"], log_tail_lines)
    return job


@mcp.tool()
def list_all_jobs() -> list:
    """Lista todos los jobs conocidos (de GROMACS y LAMMPS) con su estado actual."""
    all_jobs = jobs.list_jobs()
    for j in all_jobs:
        jobs.refresh_status(j["job_id"])
    return jobs.list_jobs()


@mcp.tool()
def parse_results(job_id: str) -> dict:
    """
    Parsea el log de un job finalizado (o en curso) y devuelve un resumen:
    para GROMACS, bloques de energia y performance; para LAMMPS, la tabla
    de thermo (paso, energia, temperatura, etc).
    """
    job = jobs.get_job(job_id)
    if job is None:
        return {"error": f"No se encontro el job_id: {job_id}"}

    if job["engine"] == "gromacs":
        return parsers.parse_gromacs_log(job["log_path"])
    elif job["engine"] == "lammps":
        return parsers.parse_lammps_log(job["log_path"])
    else:
        return {"error": f"Motor desconocido: {job['engine']}"}


if __name__ == "__main__":
    mcp.run()
