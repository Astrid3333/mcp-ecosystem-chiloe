#!/usr/bin/env python3
"""
Gazebo Entities MCP Server
Manejo de entidades, modelos y sensores en Gazebo
"""
import subprocess
import os
from fastmcp import FastMCP

mcp = FastMCP("gazebo-entities")

def run_gz(args: list, timeout: int = 10) -> dict:
    try:
        result = subprocess.run(
            ["gz"] + args,
            capture_output=True, text=True, timeout=timeout
        )
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
            "ok": result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timeout después de {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def gz_list_entities() -> str:
    """Lista los modelos/entidades en la simulación activa"""
    r = run_gz(["topic", "-e", "-t", "/world/default/pose/info", "-n", "1"])
    if r["ok"] and r["stdout"]:
        return r["stdout"]
    r2 = run_gz(["model", "--list"])
    return r2.get("stdout") or r2.get("stderr") or "No hay simulación activa"


@mcp.tool()
def gz_spawn_model(model_name: str, model_type: str = "box",
                   x: float = 0.0, y: float = 0.0, z: float = 1.0) -> str:
    """
    Inserta un modelo en la simulación.
    model_type: box, sphere, cylinder
    x, y, z: posición inicial
    """
    sdf = f"""<?xml version="1.0" ?>
<sdf version="1.8">
  <model name="{model_name}">
    <pose>{x} {y} {z} 0 0 0</pose>
    <link name="link">
      <collision name="col">
        <geometry><{model_type}><size>1 1 1</size></{model_type}></geometry>
      </collision>
      <visual name="vis">
        <geometry><{model_type}><size>1 1 1</size></{model_type}></geometry>
      </visual>
    </link>
  </model>
</sdf>"""
    sdf_path = f"/tmp/{model_name}.sdf"
    with open(sdf_path, "w") as f:
        f.write(sdf)
    r = run_gz(["service", "-s", "/world/default/create",
                "--reqtype", "gz.msgs.EntityFactory",
                "--reptype", "gz.msgs.Boolean",
                "--timeout", "2000",
                "--req", f'sdf_filename: "{sdf_path}", name: "{model_name}"'])
    return r.get("stdout") or r.get("stderr") or r.get("error", "")


@mcp.tool()
def gz_get_pose(model_name: str) -> str:
    """Obtiene la posición y orientación de un modelo"""
    r = run_gz(["model", "-m", model_name, "--pose"])
    return r.get("stdout") or r.get("stderr") or r.get("error", "")


@mcp.tool()
def gz_set_pose(model_name: str, x: float, y: float, z: float,
                roll: float = 0.0, pitch: float = 0.0, yaw: float = 0.0) -> str:
    """
    Mueve un modelo a una nueva posición en tiempo real.
    x, y, z: posición en metros
    roll, pitch, yaw: orientación en radianes
    """
    req = f'entity: {{name: "{model_name}" type: MODEL}} pose: {{position: {{x: {x} y: {y} z: {z}}} orientation: {{x: 0 y: 0 z: 0 w: 1}}}}'
    r = run_gz(["service", "-s", "/world/default/set_pose",
                "--reqtype", "gz.msgs.Pose",
                "--reptype", "gz.msgs.Boolean",
                "--timeout", "2000",
                "--req", req])
    return r.get("stdout") or r.get("stderr") or r.get("error", "")


@mcp.tool()
def gz_topic_list() -> str:
    """Lista todos los topics activos en la simulación"""
    r = run_gz(["topic", "--list"])
    return r.get("stdout") or r.get("stderr") or "Sin simulación activa"


@mcp.tool()
def gz_apply_force(model_name: str, link_name: str = "link",
                   fx: float = 0.0, fy: float = 0.0, fz: float = 10.0,
                   duration_ms: int = 1000) -> str:
    """
    Aplica una fuerza a un link de un modelo.
    fx, fy, fz: componentes de la fuerza en Newtons
    duration_ms: duración en milisegundos
    """
    req = (f'body_name: "{model_name}/{link_name}" '
           f'wrench: {{force: {{x: {fx} y: {fy} z: {fz}}} torque: {{x: 0 y: 0 z: 0}}}} '
           f'duration: {{sec: 0 nsec: {duration_ms * 1000000}}}')
    r = run_gz(["service", "-s", "/world/default/wrench",
                "--reqtype", "gz.msgs.EntityWrench",
                "--reptype", "gz.msgs.Boolean",
                "--timeout", "2000",
                "--req", req])
    return r.get("stdout") or r.get("stderr") or r.get("error", "")


@mcp.tool()
def gz_read_sensor(topic: str, n_msgs: int = 1) -> str:
    """
    Lee datos de un sensor via topic.
    topic: ej. /imu, /lidar, /camera/image
    Usa gz_topic_list() para ver topics disponibles.
    """
    r = run_gz(["topic", "-e", "-t", topic, "-n", str(n_msgs)], timeout=5)
    return r.get("stdout") or r.get("stderr") or r.get("error", "Sin datos en ese topic")


@mcp.tool()
def gz_fuel_download(owner: str, model: str, dest_dir: str = "") -> str:
    """
    Descarga un modelo desde Fuel (repositorio oficial de Gazebo).
    owner: propietario ej. 'OpenRobotics'
    model: nombre ej. 'Turtlebot3 Burger'
    """
    if not dest_dir:
        dest_dir = os.path.expanduser("~/gazebo-mcp/models")
    os.makedirs(dest_dir, exist_ok=True)
    url = f"https://fuel.gazebosim.org/1.0/{owner}/models/{model}"
    r = run_gz(["fuel", "download", "-u", url, "-p", dest_dir], timeout=60)
    if r["ok"]:
        return f"Modelo descargado en: {dest_dir}/{model}"
    return r.get("stderr") or r.get("error", "Error al descargar")


@mcp.tool()
def gz_spawn_fuel_model(model_name: str, fuel_uri: str,
                        x: float = 0.0, y: float = 0.0, z: float = 0.0) -> str:
    """
    Inserta un modelo de Fuel directamente en la simulación.
    fuel_uri: ej. 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/Turtlebot3 Burger'
    """
    req = f'sdf_filename: "{fuel_uri}" name: "{model_name}" pose: {{position: {{x: {x} y: {y} z: {z}}}}}'
    r = run_gz(["service", "-s", "/world/default/create",
                "--reqtype", "gz.msgs.EntityFactory",
                "--reptype", "gz.msgs.Boolean",
                "--timeout", "5000",
                "--req", req])
    return r.get("stdout") or r.get("stderr") or r.get("error", "")


if __name__ == "__main__":
    mcp.run()
