# md-mcp-server

Servidor MCP (Model Context Protocol) que le da a Claude herramientas para
manejar simulaciones de **GROMACS** y **LAMMPS**: lanzar jobs en background,
consultar su estado, parsear resultados y generar archivos de entrada
(`.mdp` / `.in`).

> Corre en tu propia máquina Linux. Claude se conecta a este servidor local
> vía MCP para poder invocar `gmx` y `lmp` por vos.

## Estructura

```
md-mcp-server/
├── server.py                          # servidor MCP (las herramientas)
├── jobs.py                            # registro de jobs en background
├── templates.py                       # plantillas .mdp / .in
├── parsers.py                         # parseo de logs de resultados
├── requirements.txt
├── claude_desktop_config.example.json
└── install/
    ├── install_gromacs.sh
    └── install_lammps.sh
```

## 1. Instalar GROMACS y LAMMPS

Estos scripts compilan desde código fuente (CPU only por defecto). Tardan
15-40 min cada uno según tu CPU.

```bash
cd md-mcp-server/install
sudo bash install_gromacs.sh 2024.4
sudo bash install_lammps.sh
```

Cada script tiene, comentada al final, la alternativa rápida vía `apt`
(paquete precompilado, más simple pero con versión potencialmente más vieja):

```bash
sudo apt-get install -y gromacs lammps
```

Verificá que quedaron en el PATH:

```bash
gmx --version
lmp -h
```

## 2. Instalar el servidor MCP

```bash
cd md-mcp-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Conectar el servidor a Claude

Copiá `claude_desktop_config.example.json` a la config de Claude Desktop
(normalmente en `~/.config/Claude/claude_desktop_config.json` en Linux) y
reemplazá las rutas por las absolutas de tu instalación:

```json
{
  "mcpServers": {
    "md-simulation": {
      "command": "/home/tu_usuario/md-mcp-server/.venv/bin/python",
      "args": ["/home/tu_usuario/md-mcp-server/server.py"]
    }
  }
}
```

Si ya tenías otros servidores MCP configurados, agregá la entrada
`"md-simulation"` dentro del `"mcpServers"` existente en lugar de
reemplazar el archivo entero.

Reiniciá Claude Desktop. Las herramientas nuevas deberían aparecer:
`check_installation`, `generate_mdp`, `generate_lammps_input`,
`run_gromacs`, `run_lammps`, `job_status`, `list_all_jobs`, `parse_results`.

## 4. Probar

Pedile a Claude, por ejemplo:

> "Revisá si GROMACS y LAMMPS están instalados"
> "Generame un .mdp de NPT a 310 K por 100000 pasos"
> "Lanzá la simulación de LAMMPS con este input y avisame cuando termine"

## 5. Subir este repo a GitHub

```bash
cd md-mcp-server
git init
git add .
git commit -m "Servidor MCP para GROMACS y LAMMPS"
```

Creá el repo vacío en GitHub (desde la web, sin README ni licencia), después:

```bash
git remote add origin https://github.com/TU_USUARIO/md-mcp-server.git
git branch -M main
git push -u origin main
```

## Notas y límites

- Los jobs corren en **background** (no bloquean a Claude); consultá el
  progreso con `job_status` o `list_all_jobs`.
- El estado de los jobs se guarda en `~/.md_mcp/jobs.json`.
- Los resultados de las corridas quedan en `~/md_mcp_runs/<job_name>/` por
  defecto (podés cambiarlo con `output_dir`).
- `parse_results` es un parseo heurístico pensado para un resumen rápido;
  para análisis serios seguí usando `gmx energy`, `gmx rms`, etc. a mano.
- Para GPU (CUDA) hay que recompilar GROMACS/LAMMPS con los flags
  correspondientes — están comentados dentro de cada script de instalación.
