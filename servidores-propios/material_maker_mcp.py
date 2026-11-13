"""Servidor MCP para Material Maker (https://github.com/RodZill4/material-maker).

Material Maker es un motor de materiales procedurales escrito en Godot (MIT).
Este servidor expone su modelo de datos (grafos de nodos `.ptex`) y su motor de
render headless (`--export-material`) para que un asistente pueda:

  * consultar el catalogo de nodos y sus parametros,
  * construir/inspeccionar grafos de materiales en formato `.ptex`,
  * renderizar mapas PBR (albedo/normal/ORM/height) sin interfaz grafica,
  * listar targets de export (Godot, Blender, Unity, Unreal, GLTF).

El render headless requiere un driver Vulkan funcional. En maquinas sin GPU
usable se debe forzar Mesa lavapipe:
    VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore", message=".*incomplete definition.*")

from mcp.server.fastmcp import FastMCP

MM_HOME = Path(os.environ.get("MATERIAL_MAKER_HOME", Path.home() / "Applications" / "material_maker"))
MM_BIN = MM_HOME / "material_maker.x86_64"
MM_NODES = MM_HOME / "nodes"
MM_LIBRARY = MM_HOME / "library"
MM_EXAMPLES = MM_HOME / "examples"

WORKSPACE = Path(
    os.environ.get("MATERIAL_MAKER_WORKSPACE", Path.home() / "Documents" / "OpenScience" / "materials")
).expanduser()

LAVAPIPE = "/usr/share/vulkan/icd.d/lvp_icd.json"

EXPORT_TARGETS = [
    "Blender",
    "GLTF/Plane",
    "Godot/Godot 3 Spatial",
    "Godot/Godot 4 ORM",
    "Godot/Godot 4 Standard",
    "Unity/3D",
    "Unity/HDRP",
    "Unity/URP",
    "Unreal/Unreal Engine 4",
    "Unreal/Unreal Engine 5",
]

# Puertos de entrada del nodo 'material' (orden real en nodes/material.mmg).
MATERIAL_PORTS = {
    0: ("albedo_tex", "rgb"),
    1: ("metallic_tex", "f"),
    2: ("roughness_tex", "f"),
    3: ("emission_tex", "rgb"),
    4: ("normal_tex", "rgb"),
    5: ("ao_tex", "f"),
    6: ("depth_tex", "f"),
    7: ("opacity_tex", "f"),
    8: ("sss_tex", "f"),
}

mcp = FastMCP("material-maker-mcp")


class MaterialMakerError(RuntimeError):
    """Error legible de Material Maker."""


def _require_install() -> Path:
    if not MM_BIN.exists():
        raise MaterialMakerError(
            f"Material Maker no esta instalado en {MM_HOME}. "
            f"Descargalo de https://github.com/RodZill4/material-maker/releases "
            f"y descomprimelo en {MM_HOME}."
        )
    return MM_BIN


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _node_catalog() -> dict[str, dict[str, Any]]:
    """Indice de nodos disponibles: nombre -> metadata del .mmg."""
    catalog: dict[str, dict[str, Any]] = {}
    if not MM_NODES.is_dir():
        return catalog
    for mmg in sorted(MM_NODES.glob("*.mmg")):
        try:
            data = _load_json(mmg)
        except (json.JSONDecodeError, OSError):
            continue
        shader_model = data.get("shader_model") or {}
        is_graph = "nodes" in data and "connections" in data
        catalog[mmg.stem] = {
            "type": data.get("type"),
            "description": shader_model.get("shortdesc") or data.get("shortdesc"),
            "long_description": shader_model.get("longdesc") or data.get("longdesc"),
            "inputs": shader_model.get("inputs") or [],
            "outputs": shader_model.get("outputs") or [],
            "parameters": shader_model.get("parameters") or [],
            "defaults": data.get("parameters") or {},
            "es_grafo": is_graph,
            "nodos_internos": [
                {"name": n.get("name"), "type": n.get("type")}
                for n in (data.get("nodes") or [])
            ] if is_graph else [],
        }
    return catalog


def _param_schema(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Normaliza la declaracion de parametros de un nodo a un esquema util."""
    schema: list[dict[str, Any]] = []
    for param in node.get("parameters") or []:
        if not isinstance(param, dict) or "name" not in param:
            continue
        schema.append(
            {
                "name": param["name"],
                "label": param.get("label"),
                "type": param.get("type"),
                "default": param.get("default"),
                "min": param.get("min"),
                "max": param.get("max"),
                "step": param.get("step"),
                "first": param.get("first"),
                "last": param.get("last"),
            }
        )
    return schema


def _normalize_param_value(value: Any) -> Any:
    """Deshace la normalizacion que aplican algunos clientes MCP a los argumentos.

    Se observaron dos formas al invocar desde un cliente que valida contra el JSON Schema:
    - los arrays envueltos como ``{"item": [...]}``;
    - los numeros enviados como cadenas (``"0.85"``).

    Ambos llegan intactos al servidor y el exportador los vuelca literales al shader, donde
    ``"0.85"`` o un array envuelto producen un material invalido.
    """
    if isinstance(value, dict):
        if set(value.keys()) == {"item"}:
            return _normalize_param_value(value["item"])
        return {k: _normalize_param_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_param_value(v) for v in value]
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                return float(text) if ("." in text or "e" in text.lower()) else int(text)
            except ValueError:
                return value
    return value


def _normalize_gradient_points(points: list[dict] | None) -> list[dict]:
    """Normaliza los puntos de gradiente al formato nativo del nodo colorize.

    Acepta el formato nativo ``{"r","g","b","a","pos"}`` y el alias habitual
    ``{"color": [r,g,b,a], "position": p}``.
    """
    normalized: list[dict] = []
    for point in points or []:
        if not isinstance(point, dict):
            raise MaterialMakerError(f"Punto de gradiente invalido: {point!r}")
        point = {k: _normalize_param_value(v) for k, v in point.items()}
        if any(k in point for k in ("r", "g", "b")):
            normalized.append(
                {
                    "r": float(point.get("r", 0.0)),
                    "g": float(point.get("g", 0.0)),
                    "b": float(point.get("b", 0.0)),
                    "a": float(point.get("a", 1.0)),
                    "pos": float(point.get("pos", point.get("position", 0.0))),
                }
            )
            continue
        color = point.get("color")
        if isinstance(color, dict):
            color = color.get("item", color)
        if not isinstance(color, (list, tuple)):
            raise MaterialMakerError(
                f"Punto de gradiente sin color valido: {point!r}. "
                "Usa {'r','g','b','a','pos'} o {'color': [r,g,b,a], 'position': p}."
            )
        values = [float(v) for v in color]
        values += [1.0] * (4 - len(values))
        normalized.append(
            {
                "r": values[0],
                "g": values[1],
                "b": values[2],
                "a": values[3],
                "pos": float(point.get("position", point.get("pos", 0.0))),
            }
        )
    return normalized


def _coerce_float_params(nodos: list[dict], catalog: dict[str, dict[str, Any]]) -> None:
    """Convierte a float los parametros declarados como float que llegan como int.

    El exportador de Godot escribe el valor literal en el shader: un entero produce
    ``METALLIC = (0)*orm_tex.b`` y el compilador de Godot rechaza ``int * float``
    ('Invalid arguments to operator'). En JSON es natural escribir ``metallic: 0``.
    """
    for node in nodos:
        if not isinstance(node, dict):
            continue
        meta = catalog.get(node.get("type") or "")
        if not meta:
            continue
        declared = {
            p["name"]: p.get("type")
            for p in _param_schema(meta)
            if p.get("name")
        }
        params = node.get("parameters")
        if not isinstance(params, dict):
            continue
        for name, value in list(params.items()):
            if declared.get(name) == "float" and isinstance(value, int) and not isinstance(value, bool):
                params[name] = float(value)


def _render_env() -> dict[str, str]:
    env = dict(os.environ)
    has_gpu = any(
        Path(p).exists()
        for p in [
            "/usr/share/vulkan/icd.d/nvidia_icd.json",
            "/usr/share/vulkan/icd.d/intel_icd.json",
            "/usr/share/vulkan/icd.d/radeon_icd.json",
            "/usr/share/vulkan/icd.d/amd_icd.json",
        ]
    )
    if not has_gpu and Path(LAVAPIPE).exists():
        env["VK_ICD_FILENAMES"] = LAVAPIPE
    return env


def _ensure_display(env: dict[str, str]) -> tuple[dict[str, str], subprocess.Popen | None]:
    """Material Maker necesita un DisplayServer: con Vulkan no basta con --headless.

    Godot aborta ('Unable to create DisplayServer') si no encuentra X11/Wayland, y
    el driver dummy de --headless revienta alhornear texturas. Se resuelve en este
    orden: Xvfb propio (hermetico), despues el socket X11 de la sesion del usuario.

    Returns:
        (entorno, proceso Xvfb) donde el proceso es None si no hubo que iniciar uno.
    """
    env = dict(env)
    if not env.get("XDG_RUNTIME_DIR"):
        runtime = Path(f"/run/user/{os.getuid()}")
        if runtime.is_dir():
            env["XDG_RUNTIME_DIR"] = str(runtime)

    current = env.get("DISPLAY") or ""
    if current and Path("/tmp/.X11-unix").is_dir():
        return env, None

    xvfb = shutil.which("Xvfb")
    if xvfb:
        for display_num in range(99, 120):
            lock = Path(f"/tmp/.X{display_num}-lock")
            if lock.exists():
                continue
            proc = subprocess.Popen(
                [xvfb, f":{display_num}", "-screen", "0", "1280x1024x24", "-nolisten", "tcp"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(40):
                if Path(f"/tmp/.X11-unix/X{display_num}").exists():
                    env["DISPLAY"] = f":{display_num}"
                    return env, proc
                if proc.poll() is not None:
                    break
                time.sleep(0.25)
            if proc.poll() is None:
                proc.terminate()
            continue

    x11_dir = Path("/tmp/.X11-unix")
    if x11_dir.is_dir():
        for sock in sorted(x11_dir.glob("X*")):
            if sock.name[1:].isdigit():
                env["DISPLAY"] = f":{sock.name[1:]}"
                return env, None

    raise MaterialMakerError(
        "Material Maker requiere un servidor grafico para renderizar: no se encontro "
        "DISPLAY ni un socket X11 en /tmp/.X11-unix. Opciones: (a) ejecutar el servidor "
        "MCP dentro de la sesion grafica, (b) instalar Xvfb (sudo apt install xvfb), "
        "o (c) usar el target 'Godot/Godot 4 ORM' sin render, solo inspeccion de grafos."
    )


@mcp.tool()
def listar_ejemplos() -> dict:
    """Lista los materiales de ejemplo incluidos con Material Maker (archivos .ptex)."""
    _require_install()
    if not MM_EXAMPLES.is_dir():
        return {"examples": [], "total": 0}
    examples = sorted(p.stem for p in MM_EXAMPLES.glob("*.ptex"))
    return {"examples": examples, "total": len(examples), "directorio": str(MM_EXAMPLES)}


@mcp.tool()
def listar_nodos(filtro: str = "", limite: int = 100) -> dict:
    """Lista los nodos del catalogo de Material Maker, opcionalmente filtrados por nombre.

    Args:
        filtro: subcadena case-insensitive sobre el nombre o la descripcion del nodo.
        limite: maximo de nodos devueltos (1..398).
    """
    catalog = _node_catalog()
    if not catalog:
        raise MaterialMakerError(f"No se pudo leer el catalogo de nodos en {MM_NODES}")
    needle = (filtro or "").strip().lower()
    matches = []
    for name, node in catalog.items():
        if needle and needle not in name.lower() and needle not in (node.get("description") or "").lower():
            continue
        matches.append(
            {
                "nombre": name,
                "tipo": node["type"],
                "descripcion": node.get("description"),
                "entradas": [i.get("name") for i in node.get("inputs") or []],
                "salidas": [o.get("type") for o in node.get("outputs") or []],
                "num_parametros": len(node.get("parameters") or []),
            }
        )
    matches.sort(key=lambda n: n["nombre"])
    total = len(matches)
    limit = max(1, min(int(limite), 398))
    return {"total": total, "devueltos": matches[:limit], "catalogo_completo": len(catalog)}


@mcp.tool()
def describir_nodo(nombre: str) -> dict:
    """Devuelve la ficha completa de un nodo: parametros con rangos, entradas y salidas.

    Args:
        nombre: nombre interno del nodo, por ejemplo "perlin", "bricks" o "colorize".
    """
    catalog = _node_catalog()
    key = (nombre or "").strip()
    if key not in catalog:
        close = [n for n in catalog if key.lower() in n.lower()][:12]
        raise MaterialMakerError(f"Nodo desconocido: '{nombre}'. Sugerencias: {close}")
    node = catalog[key]
    result = {
        "nombre": key,
        "tipo": node["type"],
        "descripcion": node.get("description"),
        "descripcion_larga": node.get("long_description"),
        "entradas": [
            {
                "nombre": i.get("name"),
                "tipo": i.get("type"),
                "etiqueta": i.get("label"),
                "descripcion": i.get("shortdesc"),
                "por_defecto": i.get("default"),
            }
            for i in node.get("inputs") or []
        ],
        "salidas": [
            {"tipo": o.get("type"), "etiqueta": o.get("shortdesc"), "descripcion": o.get("longdesc")}
            for o in node.get("outputs") or []
        ],
        "parametros": _param_schema(node),
        "valores_por_defecto": node.get("defaults") or {},
    }
    if node.get("es_grafo"):
        result["es_nodo_compuesto"] = True
        result["nodos_internos"] = node.get("nodos_internos") or []
    if key == "material":
        result["puertos_entrada"] = {
            str(port): {"nombre": n, "tipo": t} for port, (n, t) in MATERIAL_PORTS.items()
        }
    return result


@mcp.tool()
def listar_targets_export() -> dict:
    """Lista los targets de exportacion soportados (Godot, Blender, Unity, Unreal, GLTF)."""
    return {"targets": EXPORT_TARGETS, "total": len(EXPORT_TARGETS)}


@mcp.tool()
def inspeccionar_material(ruta: str) -> dict:
    """Inspecciona un archivo .ptex: nodos, conexiones y parametros.

    Args:
        ruta: ruta absoluta o relativa al workspace de materiales.
    """
    path = _resolve(ruta)
    data = _load_json(path)
    nodes = data.get("nodes") or []
    connections = data.get("connections") or []
    return {
        "ruta": str(path),
        "nombre": data.get("name"),
        "etiqueta": data.get("label"),
        "num_nodos": len(nodes),
        "num_conexiones": len(connections),
        "nodos": [
            {
                "nombre": n.get("name"),
                "tipo": n.get("type"),
                "posicion": n.get("node_position"),
                "parametros": n.get("parameters") or {},
            }
            for n in nodes
        ],
        "conexiones": connections,
    }


@mcp.tool()
def crear_material(
    nombre: str,
    nodos: list[dict],
    conexiones: list[dict],
    ruta_salida: str = "",
    parametros: dict | None = None,
    etiqueta: str = "",
) -> dict:
    """Crea un grafo de material .ptex a partir de nodos y conexiones.

    Args:
        nombre: nombre del material (sin extension .ptex).
        nodos: lista de nodos; cada uno {"name": str, "type": str, "parameters": dict}.
        conexiones: lista de conexiones {"from": str, "from_port": int, "to": str, "to_port": int}.
        ruta_salida: carpeta destino; por defecto el workspace de materiales.
        parametros: parametros globales del grafo (opcional).
        etiqueta: etiqueta descriptiva del grafo (opcional).
    """
    _require_install()
    if not nodos:
        raise MaterialMakerError("'nodos' no puede estar vacio: un material necesita al menos un nodo.")

    catalog = _node_catalog()
    malformed = [n for n in nodos if not isinstance(n, dict) or "type" not in n]
    if malformed:
        raise MaterialMakerError(
            "Formato de nodo invalido: cada elemento de 'nodos' debe ser un dict con las claves "
            f"'name', 'type' y 'parameters' (formato .ptex). Recibido: {malformed[0]!r}"
        )
    names = [n.get("name") for n in nodos]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise MaterialMakerError(f"Nombres de nodo duplicados: {sorted(duplicates)}")

    unknown_types = sorted({n.get("type") for n in nodos if n.get("type") not in catalog})
    if unknown_types:
        raise MaterialMakerError(
            f"Tipos de nodo inexistentes en el catalogo: {unknown_types}. "
            f"Consulta listar_nodos para descubrir los nombres correctos."
        )

    for node in nodos:
        if isinstance(node, dict) and isinstance(node.get("parameters"), dict):
            node["parameters"] = {
                k: _normalize_param_value(v) for k, v in node["parameters"].items()
            }
    _coerce_float_params(nodos, catalog)

    node_names = set(names)
    for conn in conexiones:
        for side in ("from", "to"):
            ref = conn.get(side)
            if ref not in node_names:
                raise MaterialMakerError(
                    f"Conexion invalida: {side}='{ref}' no corresponde a ningun nodo del grafo."
                )
        for side in ("from_port", "to_port"):
            if not isinstance(conn.get(side), int):
                raise MaterialMakerError(f"'{side}' debe ser un entero, recibio {conn.get(side)!r}")

    data = {
        "connections": [
            {
                "from": c["from"],
                "from_port": int(c["from_port"]),
                "to": c["to"],
                "to_port": int(c["to_port"]),
            }
            for c in conexiones
        ],
        "label": etiqueta or nombre,
        "name": nombre,
        "node_position": {"x": 0, "y": 0},
        "nodes": [
            {
                "name": n["name"],
                "node_position": n.get("node_position") or {"x": 0, "y": 0},
                "parameters": n.get("parameters") or {},
                "type": n["type"],
            }
            for n in nodos
        ],
        "parameters": parametros or {},
        "type": "material",
    }

    out_dir = Path(ruta_salida).expanduser() if ruta_salida else WORKSPACE
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{nombre}.ptex"
    out_path.write_text(json.dumps(data, indent=1), encoding="utf-8")

    return {
        "ruta": str(out_path),
        "num_nodos": len(data["nodes"]),
        "num_conexiones": len(data["connections"]),
        "validado_contra_catalogo": True,
    }


@mcp.tool()
def plantilla_material(
    nombre: str,
    nodo_base: str = "bricks",
    parametros_base: dict | None = None,
    gradiente: list[dict] | None = None,
    con_normal: bool = True,
    con_altura: bool = True,
    con_ao: bool = True,
    parametros_material: dict | None = None,
    ruta_salida: str = "",
) -> dict:
    """Construye un grafo PBR completo a partir de un nodo procedural base.

    Genera el grafo canonico: <base> -> colorize -> Material[albedo],
    <base> -> normal_map -> Material[normal] y <base> -> Material[depth].

    Args:
        nombre: nombre del material (sin extension .ptex).
        nodo_base: nodo procedural de partida, por ejemplo "bricks", "perlin" o "noise".
        parametros_base: parametros del nodo base (ver describir_nodo).
        gradiente: puntos de color para el nodo colorize; por defecto rampa blanco-negro.
        con_normal: incluir el nodo normal_map (mapa de normales).
        con_altura: conectar la altura al puerto depth del material (heightmap).
        con_ao: conectar el albedo al puerto de oclusion ambiental. Es necesario para
            que el exportador genere el mapa ORM (AO/roughness/metallic); sin esta
            conexion el target Godot no emite el archivo _orm.png.
        parametros_material: parametros del nodo material (roughness, metallic, ...).
        ruta_salida: carpeta destino; por defecto el workspace de materiales.
    """
    catalog = _node_catalog()
    if nodo_base not in catalog:
        close = [n for n in catalog if nodo_base.lower() in n.lower()][:12]
        raise MaterialMakerError(f"Nodo base desconocido '{nodo_base}'. Sugerencias: {close}")

    if not gradiente:
        gradiente = [
            {"a": 1, "b": 0, "g": 0, "pos": 0, "r": 0},
            {"a": 1, "b": 1, "g": 1, "pos": 1, "r": 1},
        ]
    puntos_gradiente = _normalize_gradient_points(gradiente)

    nodos: list[dict] = [
        {"name": nodo_base, "type": nodo_base, "parameters": parametros_base or {}},
        {
            "name": "colorize",
            "type": "colorize",
            "parameters": {
                "gradient": {"points": puntos_gradiente, "interpolation": 1, "type": "Gradient"}
            },
        },
        {"name": "Material", "type": "material", "parameters": parametros_material or {}},
    ]
    conexiones: list[dict] = [
        {"from": nodo_base, "from_port": 0, "to": "colorize", "to_port": 0},
        {"from": "colorize", "from_port": 0, "to": "Material", "to_port": 0},
    ]

    if con_normal:
        nodos.append({"name": "normal_map", "type": "normal_map", "parameters": {}})
        conexiones.append({"from": nodo_base, "from_port": 0, "to": "normal_map", "to_port": 0})
        conexiones.append({"from": "normal_map", "from_port": 0, "to": "Material", "to_port": 4})

    if con_altura:
        conexiones.append({"from": nodo_base, "from_port": 0, "to": "Material", "to_port": 6})

    if con_ao:
        conexiones.append({"from": nodo_base, "from_port": 0, "to": "Material", "to_port": 5})

    resultado = crear_material(
        nombre=nombre,
        nodos=nodos,
        conexiones=conexiones,
        ruta_salida=ruta_salida,
        etiqueta=f"plantilla PBR ({nodo_base})",
    )
    resultado["nodos"] = [n["name"] for n in nodos]
    resultado["puertos"] = {str(p): MATERIAL_PORTS[p][0] for p in (0, 4, 5, 6) if True}
    return resultado


@mcp.tool()
def render_material(
    ruta: str,
    target: str = "Godot/Godot 4 Standard",
    tamano: int = 1024,
    salida: str = "",
    timeout_s: int = 600,
) -> dict:
    """Renderiza un material .ptex a mapas PBR usando el motor de Material Maker en headless.

    Args:
        ruta: ruta del archivo .ptex a renderizar.
        target: target de exportacion (ver listar_targets_export).
        tamano: resolucion en pixeles de los mapas generados.
        salida: carpeta de salida; por defecto <workspace>/render/<nombre>.
        timeout_s: tiempo maximo de espera en segundos.
    """
    bin_path = _require_install()
    src = _resolve(ruta)
    if target not in EXPORT_TARGETS:
        raise MaterialMakerError(f"Target desconocido '{target}'. Disponibles: {EXPORT_TARGETS}")

    size = int(tamano)
    if size < 16 or size > 8192:
        raise MaterialMakerError("'tamano' debe estar entre 16 y 8192.")

    try:
        graph = json.loads(src.read_text())
    except json.JSONDecodeError as exc:
        raise MaterialMakerError(f"El archivo '{src.name}' no es un .ptex valido: {exc}") from exc
    node_types = {n.get("type") for n in graph.get("nodes", [])}
    if "material" not in node_types:
        raise MaterialMakerError(
            f"El grafo '{src.name}' no contiene un nodo de tipo 'material' (el nodo que recibe los mapas "
            "PBR), por eso el export no produce ningun archivo. Usa plantilla_material o conecta un nodo "
            "'Material' a tu grafo. Tipos presentes: " + (", ".join(sorted(t for t in node_types if t)) or "ninguno")
        )

    out_dir = Path(salida).expanduser() if salida else WORKSPACE / "render" / src.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(bin_path),
        "--rendering-driver",
        "vulkan",
        "--export-material",
        "--target",
        target,
        "-o",
        str(out_dir),
        "--size",
        str(size),
        str(src),
    ]
    return _run_export(cmd, out_dir, int(timeout_s), target, size)


def _run_export(
    cmd: list[str], out_dir: Path, timeout_s: int, target: str, size: int
) -> dict:
    """Ejecuta el export headless y fuerza el cierre cuando el motor no termina solo.

    Material Maker 1.8 deja el proceso vivo despues de exportar (el hilo de
    Vulkan/lavapipe no se une al salir el bucle principal), aunque la exportacion
    ya haya terminado. Se detecta el final real por el marcador 'Done' del log y
    se termina el proceso de forma controlada.
    """
    log_path = Path(tempfile.gettempdir()) / f"mm_export_{os.getpid()}_{int(time.time())}.log"
    start = time.time()
    env, xvfb_proc = _ensure_display(_render_env())
    stdout_buf = log_path.open("w", encoding="utf-8")

    # stdbuf fuerza buffering por linea: sin el, stdout de Godot queda en un
    # bloque de 4 KB y el marcador 'Done' no se ve hasta el cierre del proceso.
    full_cmd = (["stdbuf", "-oL", "-eL"] if shutil.which("stdbuf") else []) + cmd

    proc = subprocess.Popen(
        full_cmd,
        cwd=str(MM_HOME),
        env=env,
        stdout=stdout_buf,
        stderr=subprocess.STDOUT,
        text=True,
    )

    done_markers = ("Done", "Files succesfully exported")
    exported = False
    hung = False
    try:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if proc.poll() is not None:
                exported = True
                break
            try:
                log_text = log_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                log_text = ""
            if any(marker in log_text for marker in done_markers):
                exported = True
                break
            time.sleep(0.25)

        if not exported:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            raise MaterialMakerError(
                f"El render no termino en {timeout_s}s.\n"
                f"Log:\n{log_text[-2000:]}"
            )

        # El motor ya exporto; le damos un margen corto y cerramos si sigue vivo.
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            hung = True
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
    finally:
        stdout_buf.close()
        if xvfb_proc is not None and xvfb_proc.poll() is None:
            xvfb_proc.terminate()
            try:
                xvfb_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                xvfb_proc.kill()

    elapsed = round(time.time() - start, 2)
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    files = sorted(p for p in out_dir.iterdir() if p.is_file() and p.stat().st_size > 0)

    if not files:
        raise MaterialMakerError(
            f"El export termino sin generar archivos.\nLog:\n{log_text[-2000:]}"
        )

    return {
        "ok": True,
        "codigo_salida": proc.returncode,
        "duracion_s": elapsed,
        "target": target,
        "resolucion": size,
        "directorio": str(out_dir),
        "archivos": [
            {
                "nombre": p.name,
                "bytes": p.stat().st_size,
                "tipo": "imagen" if p.suffix.lower() == ".png" else "material",
            }
            for p in files
        ],
        "motor_no_cerro": hung,
        "log": log_text[-2000:],
    }


@mcp.tool()
def render_ejemplo(
    nombre_ejemplo: str,
    target: str = "Godot/Godot 4 Standard",
    tamano: int = 1024,
    salida: str = "",
    timeout_s: int = 600,
) -> dict:
    """Renderiza un material de ejemplo incluido con Material Maker.

    Args:
        nombre_ejemplo: nombre del ejemplo sin extension (ver listar_ejemplos).
        target: target de exportacion.
        tamano: resolucion en pixeles.
        salida: carpeta de salida; por defecto <workspace>/render/<nombre>.
        timeout_s: tiempo maximo de espera.
    """
    src = MM_EXAMPLES / f"{nombre_ejemplo}.ptex"
    if not src.exists():
        disponibles = sorted(p.stem for p in MM_EXAMPLES.glob("*.ptex"))[:20]
        raise MaterialMakerError(f"Ejemplo '{nombre_ejemplo}' no encontrado. Disponibles: {disponibles}")
    return render_material(str(src), target=target, tamano=tamano, salida=salida, timeout_s=timeout_s)


@mcp.tool()
def combinar_materiales(
    material_a: str,
    material_b: str,
    nombre_salida: str,
    blend_type: int = 0,
    cantidad: float = 0.5,
    salida: str = "",
) -> dict:
    """Combina dos materiales .ptex en uno nuevo usando un nodo 'blend' intermedio.

    Args:
        material_a: ruta del primer .ptex (se conecta al puerto 0 del blend).
        material_b: ruta del segundo .ptex (se conecta al puerto 1 del blend).
        nombre_salida: nombre del material resultante (sin extension).
        blend_type: tipo de mezcla (0=overwrite, 1=add, 2=subtract, 3=multiply, ...).
        cantidad: peso de la mezcla, 0..1.
        salida: carpeta destino; por defecto el workspace de materiales.
    """
    path_a = _resolve(material_a)
    path_b = _resolve(material_b)
    data_a = _load_json(path_a)
    data_b = _load_json(path_b)

    def _material_node(graph: dict, suffix: str) -> dict:
        for n in graph.get("nodes") or []:
            if n.get("type") == "material":
                return {
                    "name": f"material_{suffix}",
                    "type": "material",
                    "parameters": n.get("parameters") or {},
                }
        raise MaterialMakerError(f"El grafo {path_a.name} no contiene un nodo de tipo 'material'.")

    nodes = [
        _material_node(data_a, "a"),
        _material_node(data_b, "b"),
        {"name": "blend", "type": "blend", "parameters": {"amount": cantidad, "blend_type": int(blend_type)}},
    ]
    connections = [
        {"from": "material_a", "from_port": 0, "to": "blend", "to_port": 0},
        {"from": "material_b", "from_port": 1, "to": "blend", "to_port": 1},
    ]
    return crear_material(
        nombre=nombre_salida,
        nodos=nodes,
        conexiones=connections,
        ruta_salida=salida,
        etiqueta=f"blend({path_a.stem}, {path_b.stem})",
    )


@mcp.tool()
def instalar_material_maker(destino: str = "") -> dict:
    """Comprueba (o instala) Material Maker. Sin argumentos instala la release oficial en ~/Applications.

    Args:
        destino: carpeta de instalacion; por defecto ~/Applications/material_maker.
    """
    target_dir = Path(destino).expanduser() if destino else MM_HOME
    if (target_dir / "material_maker.x86_64").exists():
        version = _probe_version(target_dir)
        return {
            "instalado": True,
            "directorio": str(target_dir),
            "version": version,
            "accion": "ya instalado, no se hizo nada",
        }

    url = "https://github.com/RodZill4/material-maker/releases/download/1.8/material_maker_1_8_linux.tar.gz"
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir="/tmp/opencode") as tmp:
        archive = Path(tmp) / "mm.tar.gz"
        proc = subprocess.run(
            ["curl", "-fsSL", "-o", str(archive), url], capture_output=True, text=True, timeout=900
        )
        if proc.returncode != 0:
            raise MaterialMakerError(f"Fallo la descarga: {proc.stderr.strip()[-500:]}")
        subprocess.run(["tar", "xzf", str(archive), "-C", str(tmp)], check=True, timeout=600)
        extracted = Path(tmp) / "material_maker_1_8_linux"
        if not extracted.is_dir():
            raise MaterialMakerError("El archivo descargado no tiene la estructura esperada.")
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.move(str(extracted), str(target_dir))

    binary = target_dir / "material_maker.x86_64"
    binary.chmod(0o755)
    return {
        "instalado": True,
        "directorio": str(target_dir),
        "version": _probe_version(target_dir),
        "accion": "descargado e instalado desde la release oficial 1.8",
    }


def _probe_version(install_dir: Path) -> str:
    try:
        proc = subprocess.run(
            [str(install_dir / "material_maker.x86_64"), "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(install_dir),
        )
        return (proc.stdout or proc.stderr or "").strip().splitlines()[0] if (proc.stdout or proc.stderr) else ""
    except (subprocess.TimeoutExpired, OSError, IndexError):
        return ""


def _resolve(ruta: str) -> Path:
    if not ruta:
        raise MaterialMakerError("'ruta' es obligatoria.")
    path = Path(ruta).expanduser()
    if not path.is_absolute():
        candidate = WORKSPACE / path
        path = candidate if candidate.exists() else path.resolve()
    if not path.exists():
        raise MaterialMakerError(f"No existe el archivo: {path}")
    return path


if __name__ == "__main__":
    mcp.run()
