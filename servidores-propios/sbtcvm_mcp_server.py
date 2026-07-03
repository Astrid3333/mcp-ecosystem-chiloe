#!/usr/bin/env python3
"""
sbtcvm-mcp: servidor MCP para SBTCVM Gen2-9 (Simple Balanced Ternary Computer VM)

Envuelve la VM ternaria balanceada de 9-trit directamente vía import de Python
(sin subprocess ni parsing de terminal) exponiendo control de sesión, step/run,
lectura/escritura de memoria, registros y el ensamblador nativo (g2asm.py).

Requiere: SBTCVM Gen2-9 clonado localmente.
  git clone https://github.com/SBTCVM/SBTCVM-Gen2-9.git

Configura la ruta del repo con la variable de entorno SBTCVM_HOME, o edita
DEFAULT_SBTCVM_HOME abajo.
"""

import os
import sys
import subprocess
import itertools
from typing import Optional

from mcp.server.fastmcp import FastMCP

DEFAULT_SBTCVM_HOME = os.path.expanduser("~/sbtcvm")
SBTCVM_HOME = os.environ.get("SBTCVM_HOME", DEFAULT_SBTCVM_HOME)

if not os.path.isdir(os.path.join(SBTCVM_HOME, "vmsystem")):
    sys.stderr.write(
        f"[sbtcvm-mcp] ADVERTENCIA: no se encontro vmsystem/ en '{SBTCVM_HOME}'. "
        "Verifica SBTCVM_HOME o clona SBTCVM-Gen2-9 ahi.\n"
    )

sys.path.insert(0, SBTCVM_HOME)

mcp = FastMCP("sbtcvm")

_sessions = {}
_session_counter = itertools.count(1)


def _load_vm_modules():
    cwd = os.getcwd()
    try:
        os.chdir(SBTCVM_HOME)
        import vmsystem.MEM_G2x_9 as MEM
        import vmsystem.CPU_G2x_9 as CPU
        import vmsystem.IO_G2x_9 as IO
        import vmsystem.COMMON_IO_G2x_9 as devcommon
        import vmsystem.libbaltcalc as libbaltcalc
        return MEM, CPU, IO, devcommon, libbaltcalc
    finally:
        os.chdir(cwd)


def _get_session(session_id: str):
    sess = _sessions.get(session_id)
    if sess is None:
        raise ValueError(
            f"Sesion '{session_id}' no existe. Usa sbtcvm_boot primero."
        )
    return sess


def _reg_snapshot(cpusys, include_stacks: bool = False) -> dict:
    def bt(v):
        return {"bt": v.bt(), "dec": v.dec()}

    snap = {
        "execpoint": bt(cpusys.execpoint),
        "reg1": bt(cpusys.reg1),
        "reg2": bt(cpusys.reg2),
        "mempoint1": bt(cpusys.mempoint1),
        "mempoint2": bt(cpusys.mempoint2),
        "mempoint2_di": cpusys.mempoint2_di,
        "mempoint3": bt(cpusys.mempoint3),
        "mempoint3_di": cpusys.mempoint3_di,
        "fop1": bt(cpusys.fop1),
        "fop2": bt(cpusys.fop2),
        "fop3": bt(cpusys.fop3),
        "dataval": bt(cpusys.dataval),
        "instval": bt(cpusys.instval),
        "exceptflg": cpusys.exceptflg,
        "exceptcode": cpusys.exceptcode,
        "stack_depths": {
            "stack1": len(cpusys.stack1),
            "stack2": len(cpusys.stack2),
            "stack3": len(cpusys.stack3),
            "stack4": len(cpusys.stack4),
            "stack5": len(cpusys.stack5),
            "stack6": len(cpusys.stack6),
            "intstack": len(cpusys.intstack),
        },
    }
    if include_stacks:
        def dump(stack):
            return [bt(v) if hasattr(v, "bt") else v for v in stack]
        snap["stacks"] = {
            "stack1": dump(cpusys.stack1),
            "stack2": dump(cpusys.stack2),
            "stack3": dump(cpusys.stack3),
            "stack4": dump(cpusys.stack4),
            "stack5": dump(cpusys.stack5),
            "stack6": dump(cpusys.stack6),
        }
    return snap


@mcp.tool()
def sbtcvm_list_roms(filter: str = "") -> dict:
    """Lista las imagenes .trom (ROM ternaria compilada) disponibles en el
    repo SBTCVM (incluye demos, juegos y tests bundled). Usa 'filter' para
    buscar por substring en el nombre/ruta."""
    roms_dir = os.path.join(SBTCVM_HOME, "roms")
    found = []
    if os.path.isdir(roms_dir):
        for root, _dirs, files in os.walk(roms_dir):
            for f in files:
                if f.lower().endswith(".trom"):
                    rel = os.path.relpath(os.path.join(root, f), SBTCVM_HOME)
                    if filter.lower() in rel.lower():
                        found.append(rel)
    return {"sbtcvm_home": SBTCVM_HOME, "count": len(found), "roms": sorted(found)}


@mcp.tool()
def sbtcvm_boot(rom: str = "VDIBOOT") -> dict:
    """Arranca una nueva sesion de VM (CPU + memoria + IO, un solo nucleo,
    sin coprocesador) cargando la ROM indicada (nombre relativo a roms/, o
    'VDIBOOT' para el boot por defecto). Devuelve session_id y estado inicial."""
    MEM, CPU, IO, devcommon, _lb = _load_vm_modules()
    cwd = os.getcwd()
    try:
        os.chdir(SBTCVM_HOME)
        memsys = MEM.memory(rom)
        iosys = IO.io()
        devcommon.factorydevs(iosys)
        cpusys = CPU.cpu(memsys, iosys)
    finally:
        os.chdir(cwd)

    session_id = f"s{next(_session_counter)}"
    _sessions[session_id] = {
        "mem": memsys, "io": iosys, "cpu": cpusys,
        "rom": rom, "cycles_run": 0, "halted": False, "halt_info": None,
    }
    return {
        "session_id": session_id,
        "rom": rom,
        "designation": cpusys.designation,
        "registers": _reg_snapshot(cpusys),
    }


@mcp.tool()
def sbtcvm_step(session_id: str, cycles: int = 1) -> dict:
    """Ejecuta N ciclos de CPU en una sesion existente. Se detiene antes si
    la VM hace HALT o lanza una excepcion no capturada."""
    sess = _get_session(session_id)
    cpusys = sess["cpu"]
    executed = 0
    for _ in range(max(1, cycles)):
        if sess["halted"]:
            break
        retval = cpusys.cycle()
        executed += 1
        sess["cycles_run"] += 1
        if retval is not None:
            sess["halted"] = True
            sess["halt_info"] = {"code": retval[1], "message": retval[2]}
            break
    return {
        "session_id": session_id,
        "cycles_executed": executed,
        "total_cycles": sess["cycles_run"],
        "halted": sess["halted"],
        "halt_info": sess["halt_info"],
        "registers": _reg_snapshot(cpusys),
    }


@mcp.tool()
def sbtcvm_run(session_id: str, max_cycles: int = 5000) -> dict:
    """Corre la VM hasta que se detenga (HALT/excepcion) o hasta max_cycles,
    lo que ocurra primero. Util para ejecutar un programa completo de una vez."""
    sess = _get_session(session_id)
    cpusys = sess["cpu"]
    executed = 0
    while executed < max_cycles and not sess["halted"]:
        retval = cpusys.cycle()
        executed += 1
        sess["cycles_run"] += 1
        if retval is not None:
            sess["halted"] = True
            sess["halt_info"] = {"code": retval[1], "message": retval[2]}
            break
    return {
        "session_id": session_id,
        "cycles_executed": executed,
        "total_cycles": sess["cycles_run"],
        "halted": sess["halted"],
        "halt_info": sess["halt_info"],
        "stopped_reason": "halt" if sess["halted"] else "max_cycles_reached",
        "registers": _reg_snapshot(cpusys),
    }


@mcp.tool()
def sbtcvm_registers(session_id: str, include_stacks: bool = False) -> dict:
    """Devuelve el estado completo de registros de la CPU (execpoint, reg1/2,
    punteros de memoria, operandos, flags de excepcion) en balanced-ternario
    ('bt', ej. '--0+') y decimal. include_stacks=True vuelca el contenido
    completo de las 6 pilas de datos."""
    sess = _get_session(session_id)
    return {"session_id": session_id, **_reg_snapshot(sess["cpu"], include_stacks)}


@mcp.tool()
def sbtcvm_read_memory(session_id: str, address: int, count: int = 1, column: str = "both") -> dict:
    """Lee palabras de memoria desde 'address' (rango valido: -9841..9841,
    espacio de direcciones de 9 trits). column: 'inst', 'data' o 'both'."""
    sess = _get_session(session_id)
    memsys = sess["mem"]
    words = []
    for a in range(address, address + max(1, count)):
        entry = {"address": a}
        if column in ("inst", "both"):
            v = memsys.getinst(a)
            entry["inst"] = {"bt": v.bt(), "dec": v.dec()}
        if column in ("data", "both"):
            v = memsys.getdata(a)
            entry["data"] = {"bt": v.bt(), "dec": v.dec()}
        words.append(entry)
    return {"session_id": session_id, "words": words}


@mcp.tool()
def sbtcvm_write_memory(session_id: str, address: int, value: int, column: str = "data") -> dict:
    """Escribe un valor decimal en una direccion de memoria. column: 'inst' o 'data'."""
    sess = _get_session(session_id)
    memsys = sess["mem"]
    if column == "inst":
        memsys.setinst(address, value)
        new_val = memsys.getinst(address)
    else:
        memsys.setdata(address, value)
        new_val = memsys.getdata(address)
    return {
        "session_id": session_id, "address": address, "column": column,
        "new_value": {"bt": new_val.bt(), "dec": new_val.dec()},
    }


@mcp.tool()
def sbtcvm_reset(session_id: str, cocpu: bool = False) -> dict:
    """Soft-reset de la CPU de la sesion (limpia registros, pilas y punteros;
    no recarga la ROM ni borra la memoria de datos ya modificada)."""
    sess = _get_session(session_id)
    sess["cpu"].softreset(cocpu=1 if cocpu else 0)
    sess["halted"] = False
    sess["halt_info"] = None
    return {"session_id": session_id, "registers": _reg_snapshot(sess["cpu"])}


@mcp.tool()
def sbtcvm_assemble(source: str, syntax_only: bool = False) -> dict:
    """Compila un fuente .tasm (assembly SBTCVM) a .trom usando g2asm.py.
    'source' es una ruta relativa a SBTCVM_HOME (ej. 'roms/mi_prueba.tasm')
    o absoluta. Con syntax_only=True solo valida sin escribir el .trom."""
    g2asm = os.path.join(SBTCVM_HOME, "g2asm.py")
    args = [sys.executable, g2asm, "-s" if syntax_only else "-b", source]
    proc = subprocess.run(
        args, cwd=SBTCVM_HOME, capture_output=True, text=True, timeout=60
    )
    return {
        "source": source,
        "syntax_only": syntax_only,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


@mcp.tool()
def sbtcvm_convert(value: str) -> dict:
    """Convierte entre decimal y balanced-ternario. Acepta un entero decimal
    como string (ej. '42', '-7') o una cadena balanced-ternario usando
    '+', '-', '0' (ej. '+-0+'). Devuelve ambas representaciones."""
    _MEM, _CPU, _IO, _devcommon, libbaltcalc = _load_vm_modules()
    btint = libbaltcalc.btint
    v = value.strip()
    is_decimal = v.lstrip("-").isdigit()
    if is_decimal:
        b = btint(int(v))
    else:
        b = btint(v)
    return {"input": value, "decimal": b.dec(), "balanced_ternary": b.bt()}


if __name__ == "__main__":
    mcp.run()
