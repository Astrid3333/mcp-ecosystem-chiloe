#!/usr/bin/env python3
"""
Gazebo Harmonic MCP Server
Control de simulaciones Gazebo desde Claude Desktop
"""
import subprocess
import json
import os
import signal
from fastmcp import FastMCP

mcp = FastMCP("gazebo-mcp")

GZ_SIM_PROCESS = None

def run_gz(args: list, timeout: int = 10) -> dict:
    """Ejecuta un comando gz y retorna resultado"""
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
def gz_version() -> str:
    """Retorna la versión de Gazebo instalada"""
    r = run_gz(["sim", "--version"])
    return r.get("stdout") or r.get("error")


@mcp.tool()
def gz_launch(world_file: str = "empty.sdf", headless: bool = True) -> str:
    """
    Lanza una simulación Gazebo.
    world_file: ruta al .sdf o nombre de mundo estándar (empty.sdf, shapes.sdf, etc.)
    headless: True para correr sin ventana gráfica
    """
    global GZ_SIM_PROCESS
    if GZ_SIM_PROCESS and GZ_SIM_PROCESS.poll() is None:
        return "Ya hay una simulación corriendo. Usa gz_stop() primero."
    
    cmd = ["gz", "sim", world_file, "-r"]
    if headless:
        cmd.append("-s")  # solo servidor, sin GUI
    
    try:
        GZ_SIM_PROCESS = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "DISPLAY": ":0"}
        )
        import time; time.sleep(2)
        if GZ_SIM_PROCESS.poll() is None:
            return f"Simulación iniciada (PID {GZ_SIM_PROCESS.pid}) — mundo: {world_file}"
        else:
            stderr = GZ_SIM_PROCESS.stderr.read().decode()
            return f"Error al iniciar: {stderr}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def gz_stop() -> str:
    """Detiene la simulación en curso"""
    global GZ_SIM_PROCESS
    if GZ_SIM_PROCESS and GZ_SIM_PROCESS.poll() is None:
        GZ_SIM_PROCESS.terminate()
        GZ_SIM_PROCESS.wait(timeout=5)
        return f"Simulación detenida (PID {GZ_SIM_PROCESS.pid})"
    # También mata cualquier proceso gz suelto
    subprocess.run(["pkill", "-f", "gz sim"], capture_output=True)
    return "No había simulación activa (limpieza realizada)"


@mcp.tool()
def gz_pause() -> str:
    """Pausa la simulación en curso"""
    r = run_gz(["service", "-s", "/world/default/control",
                "--reqtype", "gz.msgs.WorldControl",
                "--reptype", "gz.msgs.Boolean",
                "--timeout", "2000",
                "--req", "pause: true"])
    return r.get("stdout") or r.get("stderr") or r.get("error", "")


@mcp.tool()
def gz_resume() -> str:
    """Reanuda la simulación pausada"""
    r = run_gz(["service", "-s", "/world/default/control",
                "--reqtype", "gz.msgs.WorldControl",
                "--reptype", "gz.msgs.Boolean",
                "--timeout", "2000",
                "--req", "pause: false"])
    return r.get("stdout") or r.get("stderr") or r.get("error", "")


@mcp.tool()
def gz_list_entities() -> str:
    """Lista los modelos/entidades en la simulación activa"""
    r = run_gz(["topic", "-e", "-t", "/world/default/pose/info", "-n", "1"])
    if r["ok"] and r["stdout"]:
        return r["stdout"]
    # alternativa
    r2 = run_gz(["model", "--list"])
    return r2.get("stdout") or r2.get("stderr") or "No hay simulación activa o sin entidades"


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
def gz_topic_list() -> str:
    """Lista todos los topics activos en la simulación"""
    r = run_gz(["topic", "--list"])
    return r.get("stdout") or r.get("stderr") or "Sin simulación activa"


@mcp.tool()
def gz_create_world(world_name: str = "chiloe", 
                    description: str = "Mundo vacío") -> str:
    """
    Genera un archivo .sdf de mundo vacío listo para usar.
    Guarda en ~/gazebo-mcp/worlds/
    """
    worlds_dir = os.path.expanduser("~/gazebo-mcp/worlds")
    os.makedirs(worlds_dir, exist_ok=True)
    
    sdf_content = f"""<?xml version="1.0" ?>
<sdf version="1.8">
  <world name="{world_name}">
    <!-- {description} -->
    <physics name="1ms" type="ignored">
      <max_step_size>0.001</max_step_size>
      <real_time_factor>1.0</real_time_factor>
    </physics>
    <plugin filename="gz-sim-physics-system"
            name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-scene-broadcaster-system"
            name="gz::sim::systems::SceneBroadcaster"/>
    <light type="directional" name="sun">
      <cast_shadows>true</cast_shadows>
      <pose>0 0 10 0 0 0</pose>
      <diffuse>0.8 0.8 0.8 1</diffuse>
      <specular>0.2 0.2 0.2 1</specular>
    </light>
    <model name="ground_plane">
      <static>true</static>
      <link name="link">
        <collision name="collision">
          <geometry><plane><normal>0 0 1</normal></plane></geometry>
        </collision>
        <visual name="visual">
          <geometry><plane><normal>0 0 1</normal><size>100 100</size></plane></geometry>
        </visual>
      </link>
    </model>
  </world>
</sdf>"""
    
    path = os.path.join(worlds_dir, f"{world_name}.sdf")
    with open(path, "w") as f:
        f.write(sdf_content)
    return f"Mundo creado en: {path}"


@mcp.tool()
def gz_status() -> str:
    """Estado actual del servidor Gazebo"""
    global GZ_SIM_PROCESS
    if GZ_SIM_PROCESS and GZ_SIM_PROCESS.poll() is None:
        estado = f"Simulación activa (PID {GZ_SIM_PROCESS.pid})"
    else:
        estado = "Sin simulación activa"
    
    topics = run_gz(["topic", "--list"])
    n_topics = len(topics.get("stdout", "").splitlines()) if topics["ok"] else 0
    
    return f"{estado}\nTopics activos: {n_topics}"



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
def gz_apply_force(model_name: str, link_name: str = "link",
                   fx: float = 0.0, fy: float = 0.0, fz: float = 10.0,
                   duration_ms: int = 1000) -> str:
    """
    Aplica una fuerza a un link de un modelo.
    fx, fy, fz: componentes de la fuerza en Newtons
    duration_ms: duración en milisegundos
    """
    req = (f'body_name: "{model_name}/{link_name}" '
           f'header: {{stamp: {{sec: 0}} frame_id: ""}} '
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
    owner: propietario del modelo ej. 'OpenRobotics'
    model: nombre del modelo ej. 'Turtlebot3 Burger'
    dest_dir: directorio destino (default: ~/gazebo-mcp/models/)
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
