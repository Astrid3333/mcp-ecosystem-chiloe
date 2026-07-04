from __future__ import annotations

from typing import Any, Optional

import numpy as np
from brian2 import (
    NeuronGroup,
    Synapses,
    SpikeMonitor,
    StateMonitor,
    Network,
    start_scope,
    ms,
    mV,
    Hz,
    run,
)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("brian2-mcp")

_STATE: dict[str, Any] = {
    "groups": {},
    "synapses": {},
    "monitors": {},
    "network": None,
}


def _require_group(name: str) -> NeuronGroup:
    if name not in _STATE["groups"]:
        raise RuntimeError(
            f"No existe el grupo de neuronas '{name}'. Usa 'create_neuron_group' "
            f"primero. Grupos disponibles: {list(_STATE['groups'].keys())}"
        )
    return _STATE["groups"][name]


def _rebuild_network() -> None:
    objs = (
        list(_STATE["groups"].values())
        + list(_STATE["synapses"].values())
        + list(_STATE["monitors"].values())
    )
    _STATE["network"] = Network(*objs)


@mcp.tool()
def create_neuron_group(
    name: str,
    n_neurons: int = 10,
    model: str = "dv/dt = (1.0 - v) / tau : 1",
    threshold: str = "v > 0.8",
    reset: str = "v = 0",
    refractory_ms: float = 2.0,
    tau_ms: float = 10.0,
    method: str = "exact",
) -> dict[str, Any]:
    """Crea un grupo de neuronas con un modelo de disparo (spiking)."""
    start_scope()
    tau = tau_ms * ms

    group = NeuronGroup(
        n_neurons,
        model,
        threshold=threshold,
        reset=reset,
        refractory=refractory_ms * ms,
        method=method,
        namespace={"tau": tau},
    )
    group.v = 0.0

    _STATE["groups"][name] = group
    _rebuild_network()

    return {
        "status": "ok",
        "group": name,
        "n_neurons": n_neurons,
        "model": model,
        "threshold": threshold,
        "reset": reset,
        "refractory_ms": refractory_ms,
        "tau_ms": tau_ms,
    }


@mcp.tool()
def create_synapses(
    name: str,
    source_group: str,
    target_group: str,
    on_pre: str = "v_post += 0.2",
    connect_probability: float = 0.1,
) -> dict[str, Any]:
    """Crea sinapsis entre dos grupos de neuronas."""
    source = _require_group(source_group)
    target = _require_group(target_group)

    syn = Synapses(source, target, on_pre=on_pre)
    syn.connect(p=connect_probability)

    _STATE["synapses"][name] = syn
    _rebuild_network()

    return {
        "status": "ok",
        "synapses": name,
        "source_group": source_group,
        "target_group": target_group,
        "on_pre": on_pre,
        "connect_probability": connect_probability,
        "n_connections": len(syn),
    }


@mcp.tool()
def add_spike_monitor(name: str, group: str) -> dict[str, Any]:
    """Agrega un monitor que registra los tiempos de disparo (spikes)."""
    grp = _require_group(group)
    monitor = SpikeMonitor(grp)
    _STATE["monitors"][name] = monitor
    _rebuild_network()
    return {"status": "ok", "monitor": name, "group": group, "type": "spike"}


@mcp.tool()
def add_state_monitor(name: str, group: str, variable: str = "v") -> dict[str, Any]:
    """Agrega un monitor que registra una variable de estado en el tiempo."""
    grp = _require_group(group)
    monitor = StateMonitor(grp, variable, record=True)
    _STATE["monitors"][name] = monitor
    _rebuild_network()
    return {"status": "ok", "monitor": name, "group": group, "variable": variable, "type": "state"}


@mcp.tool()
def run_simulation(duration_ms: float = 100.0) -> dict[str, Any]:
    """Corre la simulacion de la red completa."""
    if _STATE["network"] is None or not _STATE["groups"]:
        raise RuntimeError(
            "No hay ninguna red construida todavia. Usa 'create_neuron_group' primero."
        )
    _STATE["network"].run(duration_ms * ms)
    return {"status": "ok", "duration_ms": duration_ms}


@mcp.tool()
def get_spike_data(monitor: str, max_spikes: int = 2000) -> dict[str, Any]:
    """Devuelve tiempos e indices de disparo de un monitor spike."""
    if monitor not in _STATE["monitors"]:
        raise RuntimeError(f"No existe el monitor '{monitor}'.")

    mon = _STATE["monitors"][monitor]
    if not isinstance(mon, SpikeMonitor):
        raise RuntimeError(f"El monitor '{monitor}' no es un SpikeMonitor.")

    times = np.array(mon.t / ms)
    indices = np.array(mon.i)

    if len(times) > max_spikes:
        times = times[:max_spikes]
        indices = indices[:max_spikes]

    return {
        "monitor": monitor,
        "spike_times_ms": times.tolist(),
        "neuron_indices": indices.tolist(),
        "n_spikes_total": int(len(mon.t)),
        "n_spikes_returned": len(times),
    }


@mcp.tool()
def get_state_data(monitor: str, neuron_index: int = 0, max_points: int = 500) -> dict[str, Any]:
    """Devuelve la serie de tiempo de una variable grabada por un monitor de estado."""
    if monitor not in _STATE["monitors"]:
        raise RuntimeError(f"No existe el monitor '{monitor}'.")

    mon = _STATE["monitors"][monitor]
    if not isinstance(mon, StateMonitor):
        raise RuntimeError(f"El monitor '{monitor}' no es un StateMonitor.")

    t = np.array(mon.t / ms)
    variable_name = mon.record_variables[0]
    values = np.array(getattr(mon, variable_name)[neuron_index])

    n = len(t)
    if n > max_points:
        step = max(1, n // max_points)
        t = t[::step]
        values = values[::step]

    return {
        "monitor": monitor,
        "neuron_index": neuron_index,
        "variable": variable_name,
        "time_ms": t.tolist(),
        "values": values.tolist(),
        "n_points": len(t),
    }


@mcp.tool()
def list_network() -> dict[str, Any]:
    """Lista grupos, sinapsis y monitores actuales de la red."""
    return {
        "groups": {name: {"n_neurons": len(grp)} for name, grp in _STATE["groups"].items()},
        "synapses": {name: {"n_connections": len(syn)} for name, syn in _STATE["synapses"].items()},
        "monitors": {name: type(mon).__name__ for name, mon in _STATE["monitors"].items()},
    }


@mcp.tool()
def reset_network() -> dict[str, Any]:
    """Borra toda la red para empezar de cero."""
    _STATE["groups"] = {}
    _STATE["synapses"] = {}
    _STATE["monitors"] = {}
    _STATE["network"] = None
    return {"status": "ok", "message": "Red reiniciada"}


if __name__ == "__main__":
    mcp.run()
