# 🌿 MCP Ecosystem — Chiloé / Astrid

Ecosistema completo de servidores MCP configurado en Claude Desktop para Linux Mint 22.3.

| Nombre | Tipo | Descripción |
|--------|------|-------------|
| solvespace | 🔨 Propio | CAD paramétrico con SolveSpace CLI |
| analisis-suelos | 🔨 Propio | Análisis de suelos para Chiloé (42°S) |
| krita | 🔨 Propio | Control de Krita (pintura digital) |
| octave | 🔨 Propio | Cálculo numérico con GNU Octave |
| bolsa-mcp | 🔨 Propio | Servidor de datos bursátiles |
| gazebo | 🔨 Propio | Simulación física Gazebo Harmonic (prótesis) |
| contabilidad | 🔨 Propio | Contabilidad de partida doble — SQLite, QIF |
| neuron-mcp | 🔨 Propio | Simulación de neuronas biofísicas (NEURON, Hodgkin-Huxley) |
| brian2-mcp | 🔨 Propio | Redes de neuronas spiking (Brian2) |
| biosim-mcp | 🔨 Propio | Simulación bioquímica (COPASI: steady state, sensibilidad) |
| psyche-mcp | 🔨 Propio | Psicometría IRT (calibración, scoring, tests adaptativos, EFA) |
| physics-mcp | 🔨 Propio | Física y microfísica (mecánica, EM, Schrödinger 1D, relatividad) |
| microbio-mcp | 🔨 Propio | Virología y bacteriología (crecimiento bacteriano, SIR/SEIR, infección viral) |
| blender | 📦 Tercero | Blender 3D via uvx |
| freecad | 📦 Tercero | FreeCAD via script local |
| qgis | 📦 Tercero | QGIS — análisis geoespacial |
| gdal | 📦 Tercero | GDAL — geodata raster/vectorial |
| inkscape | 📦 Tercero | Inkscape via inkmcp |
| materials-project | 📦 Tercero | Materials Project API |
| filesystem | 📦 Tercero | Acceso al sistema de archivos |
| fetch | 📦 Tercero | Fetch web |
| firecrawl-mcp | 📦 Tercero | Web scraping con Firecrawl |
| github | 📦 Tercero | Integración GitHub |
| mcp-registry | 📦 Tercero | Registro de MCPs |

Ver `claude_desktop_config.template.json` para la configuración completa.
Ver `servidores-propios/README-servidores.md` para documentación de los servidores propios.

## Instalación rápida

```bash
git clone https://github.com/Astrid3333/mcp-ecosystem-chiloe.git
cp claude_desktop_config.template.json ~/.config/Claude/claude_desktop_config.json
# Editar y poner las API keys reales
```

## Contexto

Construido en Castro, Chiloé, Región de Los Lagos, Chile.
Proyectos: TritOS (LIG en Nothofagus dombeyi), atractores caóticos, QGIS riesgo hídrico,
prótesis (transtibial canina / transradial humana), pelillo (Gracilaria chilensis).
