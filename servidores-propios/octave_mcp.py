#!/usr/bin/env python3
import subprocess, json, sys

def run_octave(code):
    result = subprocess.run(
        ["octave", "--no-gui", "--eval", code],
        capture_output=True, text=True, timeout=30
    )
    return result.stdout + result.stderr

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        req_id = req.get("id")
        method = req.get("method", "")
        if req_id is None:
            continue
        if method == "initialize":
            resp = {"jsonrpc":"2.0","id":req_id,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"octave-mcp","version":"1.0"}}}
        elif method == "tools/list":
            resp = {"jsonrpc":"2.0","id":req_id,"result":{"tools":[{"name":"run_octave","description":"Ejecuta codigo GNU Octave","inputSchema":{"type":"object","properties":{"code":{"type":"string"}},"required":["code"]}}]}}
        elif method == "tools/call":
            code = req["params"]["arguments"]["code"]
            output = run_octave(code)
            resp = {"jsonrpc":"2.0","id":req_id,"result":{"content":[{"type":"text","text":output or "(sin salida)"}]}}
        else:
            resp = {"jsonrpc":"2.0","id":req_id,"result":{}}
        print(json.dumps(resp), flush=True)
    except Exception as e:
        print(json.dumps({"jsonrpc":"2.0","id":None,"error":{"code":-32603,"message":str(e)}}), flush=True)
