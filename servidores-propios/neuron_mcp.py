from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from neuron import h

h.load_file("stdrun.hoc")

mcp = FastMCP("neuron-mcp")

_STATE: dict[str, Any] = {
    "sections": {},
    "stims": {},
    "recordings": {},
    "t_vec": None,
}


def _require_section(name: str):
    if name not in _STATE["sections"]:
        raise RuntimeError(
            f"No existe la seccion '{name}'. Usa 'create_section' primero. "
            f"Secciones disponibles: {list(_STATE['sections'].keys())}"
        )
    return _STATE["sections"][name]


@mcp.tool()
def create_section(
    name: str = "soma",
    length_um: float = 20.0,
    diam_um: float = 20.0,
    nseg: int = 1,
) -> dict[str, Any]:
    """Crea un compartimento (seccion) de neurona, por ejemplo un soma o un
    tramo de dendrita/axon."""
    sec = h.Section(name=name)
    sec.L = length_um
    sec.diam = diam_um
    sec.nseg = nseg
    _STATE["sections"][name] = sec
    return {
        "status": "ok",
        "section": name,
        "length_um": length_um,
        "diam_um": diam_um,
        "nseg": nseg,
    }


@mcp.tool()
def connect_sections(child: str, parent: str, parent_end: float = 1.0) -> dict[str, Any]:
    """Conecta dos secciones para formar una morfologia (ej. dendrita al soma)."""
    child_sec = _require_section(child)
    parent_sec = _require_section(parent)
    child_sec.connect(parent_sec(parent_end), 0)
    return {"status": "ok", "child": child, "parent": parent, "parent_end": parent_end}


@mcp.tool()
def insert_hh_channels(
    section: str = "soma",
    gnabar: float = 0.12,
    gkbar: float = 0.036,
    gl: float = 0.0003,
    el: float = -54.3,
) -> dict[str, Any]:
    """Inserta canales ionicos tipo Hodgkin-Huxley (Na+, K+, fuga) en una
    seccion, dandole capacidad de disparar potenciales de accion."""
    sec = _require_section(section)
    sec.insert("hh")
    for seg in sec:
        seg.hh.gnabar = gnabar
        seg.hh.gkbar = gkbar
        seg.hh.gl = gl
        seg.hh.el = el
    return {
        "status": "ok",
        "section": section,
        "gnabar": gnabar,
        "gkbar": gkbar,
        "gl": gl,
        "el": el,
    }


@mcp.tool()
def insert_passive(section: str = "soma", g_pas: float = 0.001, e_pas: float = -65.0) -> dict[str, Any]:
    """Inserta un canal pasivo (fuga simple) en una seccion."""
    sec = _require_section(section)
    sec.insert("pas")
    for seg in sec:
        seg.pas.g = g_pas
        seg.pas.e = e_pas
    return {"status": "ok", "section": section, "g_pas": g_pas, "e_pas": e_pas}


@mcp.tool()
def add_current_clamp(
    section: str = "soma",
    position: float = 0.5,
    delay_ms: float = 5.0,
    duration_ms: float = 1.0,
    amplitude_nA: float = 0.1,
    stim_name: str = "stim1",
) -> dict[str, Any]:
    """Agrega un electrodo de corriente (current clamp) para estimular una
    seccion e inducir potenciales de accion."""
    sec = _require_section(section)
    stim = h.IClamp(sec(position))
    stim.delay = delay_ms
    stim.dur = duration_ms
    stim.amp = amplitude_nA
    _STATE["stims"][stim_name] = stim
    return {
        "status": "ok",
        "stim_name": stim_name,
        "section": section,
        "delay_ms": delay_ms,
        "duration_ms": duration_ms,
        "amplitude_nA": amplitude_nA,
    }


@mcp.tool()
def run_simulation(
    duration_ms: float = 25.0,
    dt_ms: float = 0.025,
    record_sections: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Corre la simulacion y graba el potencial de membrana de una o mas
    secciones a lo largo del tiempo."""
    if not _STATE["sections"]:
        raise RuntimeError("No hay ninguna seccion creada. Usa 'create_section' primero.")

    sections_to_record = record_sections or list(_STATE["sections"].keys())

    t_vec = h.Vector().record(h._ref_t)
    v_vecs = {}
    for name in sections_to_record:
        sec = _require_section(name)
        v_vecs[name] = h.Vector().record(sec(0.5)._ref_v)

    h.dt = dt_ms
    h.tstop = duration_ms
    h.v_init = -65.0
    h.finitialize(h.v_init)
    h.run()

    _STATE["t_vec"] = t_vec
    _STATE["recordings"] = v_vecs

    return {
        "status": "ok",
        "duration_ms": duration_ms,
        "dt_ms": dt_ms,
        "recorded_sections": sections_to_record,
        "n_samples": len(t_vec),
    }


@mcp.tool()
def get_membrane_potential(section: str = "soma", max_points: int = 500) -> dict[str, Any]:
    """Devuelve la serie de tiempo del potencial de membrana grabado para una
    seccion, luego de correr 'run_simulation'."""
    if _STATE["t_vec"] is None or section not in _STATE["recordings"]:
        raise RuntimeError(
            "No hay resultados grabados para esa seccion. Corre 'run_simulation' "
            "primero e incluye esta seccion en 'record_sections'."
        )

    t = list(_STATE["t_vec"])
    v = list(_STATE["recordings"][section])

    n = len(t)
    if n > max_points:
        step = max(1, n // max_points)
        t = t[::step]
        v = v[::step]

    return {
        "section": section,
        "time_ms": t,
        "voltage_mV": v,
        "n_points": len(t),
    }


@mcp.tool()
def list_sections() -> dict[str, Any]:
    """Lista las secciones creadas hasta ahora en el modelo."""
    info = []
    for name, sec in _STATE["sections"].items():
        info.append({
            "name": name,
            "length_um": sec.L,
            "diam_um": sec.diam,
            "nseg": sec.nseg,
            "mechanisms": [mech.name() for seg in sec for mech in seg],
        })
    return {"sections": info}


@mcp.tool()
def reset_model() -> dict[str, Any]:
    """Borra todas las secciones, estimulos y grabaciones."""
    _STATE["sections"] = {}
    _STATE["stims"] = {}
    _STATE["recordings"] = {}
    _STATE["t_vec"] = None
    return {"status": "ok", "message": "Modelo reiniciado"}


if __name__ == "__main__":
    mcp.run()
