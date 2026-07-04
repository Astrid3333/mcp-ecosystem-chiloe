# Servidores MCP Propios — Castro, Chiloé


## solvespace-mcp
- Ubicación: ~/solvespace-mcp/ | Lenguaje: Node.js
- Controla SolveSpace vía CLI para CAD paramétrico 2D/3D
- Env: SOLVESPACE_CLI=/usr/bin/solvespace-cli, SOLVESPACE_WORKDIR=~/solvespace-projects
- Replicar: cd ~/solvespace-mcp && npm install


## analisis-suelos (mcp_suelos)
- Ubicación: ~/mcp_suelos/ | Lenguaje: Python 3
- Suelos volcánicos/trumaos Chiloé 42°S, alta pluviometría
- Herramientas: triángulo textural USDA, retención agua, materia orgánica, pelillo/agroecología
- Replicar: pip install -r ~/mcp_suelos/requirements.txt


## octave-mcp
- Ubicación: ~/octave-mcp/ | Lenguaje: Python 3 wrapper sobre GNU Octave
- Integración numérica de atractores caóticos: Lorenz, Dequan-Li, Halvorsen, Aizawa, Mackey-Glass
- Usado en TritOS y visualizaciones Blender
- Replicar: sudo apt install octave


## gazebo-mcp
- Ubicación: ~/gazebo-mcp/ (gazebo_core.py + gazebo_entities.py) | Lenguaje: Python 3 (FastMCP)
- Control de simulaciones Gazebo Harmonic desde Claude Desktop vía CLI `gz`
- gazebo_core: versión de Gazebo, lanzar/detener simulaciones (mundos .sdf, modo headless)
- gazebo_entities: listar entidades/modelos, manejo de sensores, conversión Euler↔cuaternión (orientación de cuerpos rígidos)
- Uso: simulación física para prótesis (transtibial canina / transradial humana)
- Dependencias: gz (Gazebo Harmonic), fastmcp (pip install fastmcp)
- Replicar: cd ~/gazebo-mcp && pip install fastmcp


## krita-mcp
- Ubicación: ~/krita-mcp/ | Lenguaje: Python 3
- Control de Krita para pintura digital y diseño gráfico desde Claude


## bolsa-mcp
- Ubicación: ~/bolsa-mcp/ | Virtualenv: ~/bolsa-env/ | Lenguaje: Python 3
- Análisis bursátil — usado en tesis inversión plataformas fungales (rFC, quitosano, beta-glucanos)
- Replicar: python -m venv ~/bolsa-env && ~/bolsa-env/bin/pip install -r ~/bolsa-mcp/requirements.txt

## contabilidad-mcp
- Ubicación: ~/contabilidad-mcp/ | Lenguaje: Python 3 (FastMCP)
- Contabilidad de partida doble (double-entry) genérica e internacional
- Cuentas, asientos, libro mayor, P&L, balance general, IVA, exportación QIF
- Repo: https://github.com/Astrid3333/contabilidad-mcp
- Replicar: cd ~/contabilidad-mcp && pip install fastmcp

## neuron-mcp
- Ubicación: ~/neuron-mcp/ (servidores-propios/neuron_mcp.py) | Lenguaje: Python 3 (FastMCP + NEURON/HOC)
- Simulación de neuronas biofísicas: secciones (soma/dendrita/axón), canales Hodgkin-Huxley y pasivos, current clamp, registro de potencial de membrana
- Dependencias: neuron, numpy, mcp (pip)
- Replicar: python3 -m venv ~/neuron-env && source ~/neuron-env/bin/activate && pip install mcp neuron numpy


## brian2-mcp
- Ubicación: ~/brian2-mcp/ (servidores-propios/brian2_mcp.py) | Lenguaje: Python 3 (FastMCP + Brian2)
- Redes de neuronas spiking: grupos con modelo configurable, sinapsis, monitores de spikes y de estado, corrida de red completa
- Dependencias: brian2, numpy, mcp (pip)
- Replicar: python3 -m venv ~/brian2-env && source ~/brian2-env/bin/activate && pip install mcp brian2 numpy
