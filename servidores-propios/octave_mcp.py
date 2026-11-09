#!/usr/bin/env python3
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from octave_runner import run_octave
from lyapunov_tool import compute_lyapunov_exponent, LYAPUNOV_TOOL_SCHEMA
from stiff_ode_tool import integrate_stiff_ode, STIFF_ODE_TOOL_SCHEMA
from bifurcation_tool import compute_bifurcation_diagram, BIFURCATION_TOOL_SCHEMA
from hilbert_tool import compute_hilbert_transform, HILBERT_TOOL_SCHEMA
from formulas_tool import (
    evaluate_formula,
    solve_equation,
    differentiate,
    integrate_symbolic,
    formula_library,
    EVALUATE_FORMULA_SCHEMA,
    SOLVE_EQUATION_SCHEMA,
    DIFFERENTIATE_SCHEMA,
    INTEGRATE_SCHEMA,
    FORMULA_LIBRARY_SCHEMA,
)
from goertzel_tool import (
    goertzel,
    goertzel_scan,
    GOERTZEL_TOOL_SCHEMA,
)
from ancestral_octave_tool import ancestral_octave, ANCESTRAL_OCTAVE_TOOL_SCHEMA
from middle_square_weyl_tool import middle_square_weyl, MIDDLE_SQUARE_WEYL_TOOL_SCHEMA


TOOLS = [
    {
        "name": "run_octave",
        "description": "Ejecuta codigo GNU Octave",
        "inputSchema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    },
    LYAPUNOV_TOOL_SCHEMA,
    STIFF_ODE_TOOL_SCHEMA,
    BIFURCATION_TOOL_SCHEMA,
    HILBERT_TOOL_SCHEMA,
    EVALUATE_FORMULA_SCHEMA,
    SOLVE_EQUATION_SCHEMA,
    DIFFERENTIATE_SCHEMA,
    INTEGRATE_SCHEMA,
    FORMULA_LIBRARY_SCHEMA,
    GOERTZEL_TOOL_SCHEMA,
    ANCESTRAL_OCTAVE_TOOL_SCHEMA,
    MIDDLE_SQUARE_WEYL_TOOL_SCHEMA,
]


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req_id = None
    try:
        req = json.loads(line)
        req_id = req.get("id")
        method = req.get("method", "")
        if req_id is None:
            continue

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "octave-mcp", "version": "1.3"},
                },
            }

        elif method == "tools/list":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

        elif method == "tools/call":
            tool_name = req["params"]["name"]
            args = req["params"].get("arguments", {})

            if tool_name == "run_octave":
                output = run_octave(args["code"])
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": output or "(sin salida)"}]},
                }

            elif tool_name == "compute_lyapunov_exponent":
                result = compute_lyapunov_exponent(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "integrate_stiff_ode":
                result = integrate_stiff_ode(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "compute_bifurcation_diagram":
                result = compute_bifurcation_diagram(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "compute_hilbert_transform":
                result = compute_hilbert_transform(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "evaluate_formula":
                result = evaluate_formula(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "solve_equation":
                result = solve_equation(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "differentiate":
                result = differentiate(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "integrate_symbolic":
                result = integrate_symbolic(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "formula_library":
                result = formula_library(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "goertzel":
                result = goertzel(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "goertzel_scan":
                result = goertzel_scan(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "ancestral_octave":
                result = ancestral_octave(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "middle_square_weyl":
                result = middle_square_weyl(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            else:
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32601, "message": f"Tool desconocido: {tool_name}"},
                }

        else:
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}

        print(json.dumps(resp), flush=True)

    except Exception as e:
        print(json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(e)}}), flush=True)
