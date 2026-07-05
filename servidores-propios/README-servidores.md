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

## biosim-mcp
- Ubicación: ~/biosim-mcp/ (repo propio, github.com/Astrid3333/biosim-mcp) | Lenguaje: Python 3 (FastMCP + COPASI)
- Simulación de sistemas bioquímicos: carga de modelos COPASI/SBML, resumen del modelo, time course, estado estacionario, análisis de sensibilidad, edición de parámetros
- Dependencias: COPASI (compilado desde fuente), python-copasi bindings, mcp (pip)
- Replicar: ver build de COPASI en notas propias (bison 3.x / raptor RDF)

## psyche-mcp
- Ubicación: ~/psyche-mcp/ | Lenguaje: Python 3 (FastMCP + girth + factor_analyzer)
- Psicometría IRT: creación de bancos de ítems, curva de información de Fisher, calibración (2PL/3PL via MML), scoring de respondentes por máxima verosimilitud, simulación de test adaptativo (CAT), validación de estructura factorial (EFA)
- Dependencias: mcp, numpy, scipy, girth, factor-analyzer, pandas (venv propio en ~/psyche-env)

## physics-mcp
- Ubicación: ~/physics-mcp/ | Lenguaje: Python 3 (FastMCP + numpy/scipy)
- Física clásica y microfísica: osciladores amortiguados, sistemas N-cuerpos, campos eléctricos/magnéticos (Coulomb, Biot-Savart), ecuación de Schrödinger 1D (pozo/oscilador armónico), tunelamiento cuántico, decaimiento de partículas, cinemática relativista
- Dependencias: mcp, numpy, scipy (venv propio en ~/physics-env)

## microbio-mcp
- Ubicación: ~/microbio-mcp/ | Lenguaje: Python 3 (FastMCP + numpy/scipy)
- Virología y bacteriología: ajuste y simulación de curvas de crecimiento bacteriano (logística/Gompertz), modelos epidemiológicos SIR/SEIR, estimación de R0, dinámica de infección viral intracelular
- Dependencias: mcp, numpy, scipy (venv propio en ~/microbio-env)
