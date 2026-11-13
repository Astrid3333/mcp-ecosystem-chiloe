#!/usr/bin/env python3
"""
Sincroniza repos GitHub de Astrid3333 como servidores MCP en el ecosistema.

Reglas que este script respeta (verificadas con MCP Inspector):
  - La config que opencode lee es `~/.config/opencode/opencode.json` con dialecto
    V1: `mcp.<nombre> = {type:"local", command:[...], cwd, enabled, timeout}`.
    `~/.config/opencode/mcp.json` NO lo lee opencode (el binario solo busca
    opencode.jsonc / opencode.json / config.json) y se mantenia como espejo.
  - Los clones de `~/github/` no tienen `.venv`; cada comando apunta al
    interprete y al directorio donde el servidor arranca de verdad.
  - Las entradas ya presentes en la config existente ganan: el generador solo
    agrega servidores faltantes, no pisa ajustes afinados a mano.
"""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

CONFIG_PATH = Path("/home/astrid/.config/opencode/opencode.json")
MIRROR_PATH = Path("/home/astrid/.config/opencode/mcp.json")
GITHUB_DIR = Path("/home/astrid/github")
CHILOE = Path("/home/astrid/Documents/OpenScience/projects/githu/mcp-ecosystem-chiloe")

# repo GitHub -> servidor MCP. `command`/`cwd` son los comandos que pasaron
# el handshake MCP (initialize + tools/list) en la auditoria con Inspector.
MCP_REPOS = {
    "octave-mcp": {
        "server_name": "octave",
        "command": [
            "/bin/bash", "-lc",
            f"cd {CHILOE}/servidores-propios && exec .venv/bin/python octave_mcp.py",
        ],
        "cwd": str(CHILOE / "servidores-propios"),
    },
    "solvespace-mcp": {
        "server_name": "solvespace",
        "command": ["/bin/bash", "-lc", "cd /home/astrid/solvespace-mcp && exec node src/index.js"],
        "cwd": "/home/astrid/solvespace-mcp",
    },
    "openscad-mcp": {
        "server_name": "openscad",
        "command": ["/bin/bash", "-lc", "cd /home/astrid/openscad-mcp && exec .venv/bin/python server.py"],
        "cwd": "/home/astrid/openscad-mcp",
    },
    "mcp-free-cad-": {
        "server_name": "freecad",
        "command": ["/bin/bash", "-lc", "cd /home/astrid/mcp-free-cad- && exec python3 freecad_mcp_server.py"],
        "cwd": "/home/astrid/mcp-free-cad-",
    },
    "mcp-ecosystem-chiloe": {
        "server_name": "ecosystem-chiloe",
        "command": ["/bin/bash", "-lc", f"cd {CHILOE} && exec .venv/bin/python server.py"],
        "cwd": str(CHILOE),
    },
    "structuresynth-mcp": {
        "server_name": "structuresynth",
        "command": [
            "/bin/bash", "-lc",
            "exec /home/astrid/Documents/OpenScience/sessions/2026-10-22-0227/structuresynth-mcp/.venv/bin/structuresynth-mcp",
        ],
    },
    "bend-mcp": {
        "server_name": "bend",
        "command": [
            "/bin/bash", "-lc",
            "exec /home/astrid/Documents/OpenScience/sessions/2026-10-15-1617/bend-mcp/.venv/bin/bend-mcp",
        ],
    },
    "motion-mcp": {
        "server_name": "motion",
        "command": [
            "/bin/bash", "-lc",
            "cd /home/astrid/github/motion-mcp && exec /home/astrid/motion-env/bin/python -m motion_mcp.server",
        ],
        "cwd": "/home/astrid/github/motion-mcp",
    },
    "kdenlive-mcp": {
        "server_name": "kdenlive",
        "command": [
            "/bin/bash", "-lc",
            "exec /home/astrid/Documents/OpenScience/sessions/2026-10-24-1841/kdenlive-mcp/bin/kdenlive-mcp",
        ],
    },
    "unreal-mcp-bridge": {
        "server_name": "unreal",
        "command": ["/bin/bash", "-lc", "cd /home/astrid/unreal-mcp/Python && exec .venv/bin/python unreal_mcp_server.py"],
        "cwd": "/home/astrid/unreal-mcp/Python",
    },
    "biosim-mcp": {
        "server_name": "biosim",
        "command": ["/bin/bash", "-lc", "cd /home/astrid/biosim-mcp && exec /usr/bin/python3 server.py"],
        "cwd": "/home/astrid/biosim-mcp",
    },
    "microbio-mcp": {
        "server_name": "microbio",
        "command": ["/bin/bash", "-lc", "cd /home/astrid/microbio-mcp && exec /home/astrid/microbio-env/bin/python3 server.py"],
        "cwd": "/home/astrid/microbio-mcp",
    },
    "physics-mcp": {
        "server_name": "physics",
        "command": ["/bin/bash", "-lc", "cd /home/astrid/physics-mcp && exec /home/astrid/physics-env/bin/python3 server.py"],
        "cwd": "/home/astrid/physics-mcp",
    },
    "psyche-mcp": {
        "server_name": "psyche",
        "command": ["/bin/bash", "-lc", "cd /home/astrid/psyche-mcp && exec /home/astrid/psyche-env/bin/python3 server.py"],
        "cwd": "/home/astrid/psyche-mcp",
        "timeout": 120000,
    },
    "plantas-mcp": {
        "server_name": "plantas",
        "command": ["/bin/bash", "-lc", "cd /home/astrid/github/plantas-mcp && exec /usr/bin/python3 server.py"],
        "cwd": "/home/astrid/github/plantas-mcp",
    },
    "quimica-mcp": {
        "server_name": "quimica",
        "command": [
            "/bin/bash", "-lc",
            "cd /home/astrid/github/quimica-mcp && exec /home/astrid/quimica-env/bin/python quimica_mcp.py",
        ],
        "cwd": "/home/astrid/github/quimica-mcp",
    },
}


def clone_or_update_repo(repo_name: str, target_dir: Path) -> bool:
    repo_url = f"https://github.com/Astrid3333/{repo_name}.git"
    git = shutil.which("git")
    if not git:
        return False
    if target_dir.exists():
        result = subprocess.run(
            [git, "-C", str(target_dir), "pull"], capture_output=True, text=True, timeout=60
        )
        return result.returncode == 0
    result = subprocess.run(
        [git, "clone", repo_url, str(target_dir)], capture_output=True, text=True, timeout=120
    )
    return result.returncode == 0


def generate_mcp_config() -> dict:
    """Entradas MCP en dialecto opencode V1."""
    servers = {}
    for info in MCP_REPOS.values():
        entry = {
            "type": "local",
            "command": list(info["command"]),
            "enabled": True,
        }
        if info.get("cwd"):
            entry["cwd"] = info["cwd"]
        if info.get("timeout"):
            entry["timeout"] = info["timeout"]
        servers[info["server_name"]] = entry
    return servers


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Sincroniza repos GitHub como servidores MCP")
    parser.add_argument("--no-clone", action="store_true", help="no clona ni actualiza repos")
    parser.add_argument("--dry-run", action="store_true", help="muestra el resultado sin escribir")
    args = parser.parse_args()

    if not args.no_clone:
        print("=== Sincronizando repos GitHub como servidores MCP ===")
        GITHUB_DIR.mkdir(parents=True, exist_ok=True)
        for repo_name in MCP_REPOS:
            repo_dir = GITHUB_DIR / repo_name
            status = "✅" if clone_or_update_repo(repo_name, repo_dir) else "⚠️"
            print(f"  {status} {repo_name}")

    generated = generate_mcp_config()
    existing = load_json(CONFIG_PATH)
    existing_mcp = existing.get("mcp", {})
    if isinstance(existing_mcp.get("servers"), dict):
        existing_mcp = existing_mcp["servers"]

    # Las entradas existentes ganan: el generador solo agrega lo que falta.
    merged = {**generated, **existing_mcp}
    added = sorted(set(generated) - set(existing_mcp))
    kept = sorted(set(generated) & set(existing_mcp))

    print(f"\nServidores definidos por el generador: {len(generated)}")
    print(f"Agregados (faltaban): {', '.join(added) if added else '(ninguno)'}")
    print(f"Respetados (ya estaban): {len(kept)}")
    print(f"Total en config: {len(merged)}")

    if args.dry_run:
        print("(dry-run: no se escribio nada)")
        return 0

    existing["mcp"] = merged
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"✅ Configuración MCP actualizada en {CONFIG_PATH}")

    # El espejo conserva los servidores que solo viven ahí, reparando los que
    # apuntan a rutas sin interprete (los clones de ~/github no tienen .venv).
    mirror = load_json(MIRROR_PATH)
    mirror_mcp = mirror.get("mcp", {})
    if isinstance(mirror_mcp.get("servers"), dict):
        mirror_mcp = mirror_mcp["servers"]
    extra = {k: v for k, v in mirror_mcp.items() if k not in merged}
    for name, entry in list(extra.items()):
        cmd = entry.get("command", [])
        if isinstance(cmd, str):
            cmd = [cmd]
        if any(str(part).startswith(".venv/bin/python") for part in cmd):
            extra[name] = {
                "type": "local",
                "command": ["/bin/bash", "-lc", f"cd {CHILOE} && exec .venv/bin/python server.py"],
                "cwd": str(CHILOE),
                "enabled": True,
            }
    mirror["mcp"] = {**merged, **extra}
    MIRROR_PATH.write_text(json.dumps(mirror, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"✅ Espejo actualizado en {MIRROR_PATH} ({len(extra)} entradas exclusivas conservadas)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
