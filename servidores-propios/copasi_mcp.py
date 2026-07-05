#!/usr/bin/env python3
"""
copasi_mcp.py — Servidor MCP para simulación bioquímica/bioreactores con COPASI.

Requiere que los bindings de Python de COPASI (COPASI.py + _COPASI.so) sean
importables. Si no están en el PYTHONPATH del sistema, ajusta COPASI_BINDINGS_DIR
más abajo o exporta PYTHONPATH antes de lanzar el servidor.

Instalación:
    pip install mcp --break-system-packages

Uso en claude_desktop_config.json (ejemplo):
    {
      "mcpServers": {
        "copasi": {
          "command": "python3",
          "args": ["/home/astrid/mcp-ecosystem-chiloe/servidores-propios/copasi_mcp.py"],
          "env": {
            "PYTHONPATH": "/home/astrid/COPASI/build/copasi/bindings/python"
          }
        }
      }
    }
"""

import csv
import os
import sys
import traceback
from pathlib import Path

# --- Localizar los bindings de COPASI ------------------------------------
COPASI_BINDINGS_DIR = os.environ.get(
    "COPASI_BINDINGS_DIR",
    "/home/astrid/COPASI/build/copasi/bindings/python",
)
if COPASI_BINDINGS_DIR not in sys.path:
    sys.path.insert(0, COPASI_BINDINGS_DIR)

try:
    import COPASI
    COPASI_OK = True
    COPASI_IMPORT_ERROR = None
except Exception as e:  # noqa: BLE001
    COPASI_OK = False
    COPASI_IMPORT_ERROR = f"{e}\n{traceback.format_exc()}"

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("copasi")

# Directorio donde se guardan/leen modelos SBML por defecto
MODELS_DIR = Path(os.environ.get("COPASI_MODELS_DIR", "~/copasi_modelos")).expanduser()
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Directorio donde se guardan resultados de simulaciones (CSV)
RESULTS_DIR = Path(os.environ.get("COPASI_RESULTS_DIR", "~/copasi_resultados")).expanduser()
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def _check_copasi():
    if not COPASI_OK:
        raise RuntimeError(
            "No se pudo importar COPASI. Revisa COPASI_BINDINGS_DIR / PYTHONPATH.\n"
            f"Error original:\n{COPASI_IMPORT_ERROR}"
        )


def _resolve_model_path(model_name: str) -> Path:
    """Acepta ruta absoluta o nombre de archivo dentro de MODELS_DIR."""
    p = Path(model_name).expanduser()
    if p.is_absolute() and p.exists():
        return p
    candidate = MODELS_DIR / model_name
    if candidate.exists():
        return candidate
    if not candidate.suffix:
        candidate_xml = MODELS_DIR / f"{model_name}.xml"
        if candidate_xml.exists():
            return candidate_xml
    raise FileNotFoundError(
        f"No encontré el modelo '{model_name}' (busqué en {p} y {candidate})"
    )


# ---------------------------------------------------------------------------
# 1) Listar / inspeccionar modelos
# ---------------------------------------------------------------------------

@mcp.tool()
def listar_modelos() -> str:
    """Lista los archivos SBML (.xml) disponibles en el directorio de modelos COPASI."""
    archivos = sorted(p.name for p in MODELS_DIR.glob("*.xml"))
    if not archivos:
        return f"No hay modelos .xml en {MODELS_DIR}. Usa construir_modelo_simple para crear uno."
    return f"Modelos en {MODELS_DIR}:\n" + "\n".join(f"- {a}" for a in archivos)


@mcp.tool()
def info_modelo(modelo: str) -> str:
    """
    Muestra especies, compartimentos, parámetros globales y reacciones de un modelo SBML.

    Args:
        modelo: nombre de archivo (dentro de ~/copasi_modelos) o ruta absoluta a un .xml SBML
    """
    _check_copasi()
    path = _resolve_model_path(modelo)

    data_model = COPASI.CRootContainer.addDatamodel()
    if not data_model.importSBML(str(path)):
        return f"Error al importar SBML: {path}"

    model = data_model.getModel()

    lines = [f"Modelo: {model.getObjectName()}  ({path.name})", ""]

    lines.append("Compartimentos:")
    for i in range(model.getNumCompartments()):
        c = model.getCompartment(i)
        lines.append(f"  - {c.getObjectName()}: volumen={c.getInitialValue():g}")

    lines.append("\nEspecies:")
    for i in range(model.getNumMetabs()):
        s = model.getMetabolite(i)
        lines.append(
            f"  - {s.getObjectName()}: conc_inicial={s.getInitialConcentration():g} "
            f"(compartimento={s.getCompartment().getObjectName()})"
        )

    lines.append("\nParámetros globales:")
    for i in range(model.getNumModelValues()):
        mv = model.getModelValue(i)
        lines.append(f"  - {mv.getObjectName()} = {mv.getInitialValue():g}")

    lines.append("\nReacciones:")
    for i in range(model.getNumReactions()):
        r = model.getReaction(i)
        lines.append(f"  - {r.getObjectName()}: {r.getChemEqIterator}" if False else f"  - {r.getObjectName()}")

    COPASI.CRootContainer.removeDatamodel(data_model)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2) Simulación (time course)
# ---------------------------------------------------------------------------

@mcp.tool()
def simular(modelo: str, duracion: float = 100.0, pasos: int = 100, nombre_salida: str = "") -> str:
    """
    Corre una simulación determinística (time course) de un modelo SBML y guarda el resultado en CSV.

    Args:
        modelo: nombre o ruta del archivo SBML a simular
        duracion: tiempo total de simulación (unidades del modelo, típicamente horas o segundos)
        pasos: número de puntos de salida
        nombre_salida: nombre del CSV de salida (opcional; si se omite se genera uno automático)
    """
    _check_copasi()
    path = _resolve_model_path(modelo)

    data_model = COPASI.CRootContainer.addDatamodel()
    if not data_model.importSBML(str(path)):
        return f"Error al importar SBML: {path}"

    task = data_model.getTask("Time-Course")
    if task is None or not isinstance(task, COPASI.CTrajectoryTask):
        return "El modelo no tiene una tarea de Time-Course disponible."

    problem = task.getProblem()
    problem.setStepNumber(pasos)
    problem.setDuration(duracion)
    problem.setTimeSeriesRequested(True)
    task.setMethodType(COPASI.CTaskEnum.Method_deterministic)

    try:
        data_model.getModel().applyInitialValues()
        success = task.processWithOutputFlags(True, COPASI.CCopasiTask.ONLY_TIME_SERIES)
    except Exception as e:  # noqa: BLE001
        COPASI.CRootContainer.removeDatamodel(data_model)
        return f"Error durante la simulación: {e}"

    if not success:
        COPASI.CRootContainer.removeDatamodel(data_model)
        return "La simulación no se completó correctamente."

    time_series = task.getTimeSeries()
    n_vars = time_series.getNumVariables()
    n_steps = time_series.getRecordedSteps()

    titles = [time_series.getTitle(i) for i in range(n_vars)]

    out_name = nombre_salida or f"{path.stem}_sim.csv"
    if not out_name.endswith(".csv"):
        out_name += ".csv"
    out_path = RESULTS_DIR / out_name

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(titles)
        for step in range(n_steps):
            row = [time_series.getData(step, i) for i in range(n_vars)]
            writer.writerow(row)

    COPASI.CRootContainer.removeDatamodel(data_model)

    return (
        f"Simulación completa: {n_steps} pasos, {n_vars} variables.\n"
        f"Columnas: {', '.join(titles)}\n"
        f"Resultado guardado en: {out_path}"
    )


# ---------------------------------------------------------------------------
# 3) Parámetros
# ---------------------------------------------------------------------------

@mcp.tool()
def obtener_parametro(modelo: str, nombre_parametro: str) -> str:
    """
    Obtiene el valor de un parámetro global, especie (conc. inicial) o compartimento.

    Args:
        modelo: nombre o ruta del archivo SBML
        nombre_parametro: nombre exacto del parámetro/especie/compartimento
    """
    _check_copasi()
    path = _resolve_model_path(modelo)
    data_model = COPASI.CRootContainer.addDatamodel()
    if not data_model.importSBML(str(path)):
        return f"Error al importar SBML: {path}"

    model = data_model.getModel()
    resultado = None

    for i in range(model.getNumModelValues()):
        mv = model.getModelValue(i)
        if mv.getObjectName() == nombre_parametro:
            resultado = f"{nombre_parametro} = {mv.getInitialValue():g}"
            break

    if resultado is None:
        for i in range(model.getNumMetabs()):
            s = model.getMetabolite(i)
            if s.getObjectName() == nombre_parametro:
                resultado = f"{nombre_parametro} (conc. inicial) = {s.getInitialConcentration():g}"
                break

    COPASI.CRootContainer.removeDatamodel(data_model)
    return resultado or f"No encontré '{nombre_parametro}' en el modelo."


@mcp.tool()
def fijar_parametro(modelo: str, nombre_parametro: str, valor: float, guardar_como: str = "") -> str:
    """
    Cambia el valor de un parámetro global o la concentración inicial de una especie,
    y guarda el modelo modificado (por defecto sobrescribiendo el original).

    Args:
        modelo: nombre o ruta del archivo SBML
        nombre_parametro: nombre exacto del parámetro/especie
        valor: nuevo valor numérico
        guardar_como: nombre de archivo nuevo (opcional); si se omite, sobrescribe el modelo original
    """
    _check_copasi()
    path = _resolve_model_path(modelo)
    data_model = COPASI.CRootContainer.addDatamodel()
    if not data_model.importSBML(str(path)):
        return f"Error al importar SBML: {path}"

    model = data_model.getModel()
    encontrado = False

    for i in range(model.getNumModelValues()):
        mv = model.getModelValue(i)
        if mv.getObjectName() == nombre_parametro:
            mv.setInitialValue(valor)
            encontrado = True
            break

    if not encontrado:
        for i in range(model.getNumMetabs()):
            s = model.getMetabolite(i)
            if s.getObjectName() == nombre_parametro:
                s.setInitialConcentration(valor)
                encontrado = True
                break

    if not encontrado:
        COPASI.CRootContainer.removeDatamodel(data_model)
        return f"No encontré '{nombre_parametro}' en el modelo."

    model.applyInitialValues()
    out_name = guardar_como or path.name
    if not out_name.endswith(".xml"):
        out_name += ".xml"
    out_path = MODELS_DIR / out_name if not Path(out_name).is_absolute() else Path(out_name)
    data_model.saveModel(str(out_path), True)

    COPASI.CRootContainer.removeDatamodel(data_model)
    return f"'{nombre_parametro}' = {valor:g} guardado en {out_path}"


# ---------------------------------------------------------------------------
# 4) Construcción de modelos simples
# ---------------------------------------------------------------------------

@mcp.tool()
def construir_modelo_simple(
    nombre_modelo: str,
    especies: str,
    reacciones: str,
    volumen_compartimento: float = 1.0,
) -> str:
    """
    Construye un modelo cinético simple (un compartimento, cinéticas de masa-acción)
    y lo guarda como SBML en el directorio de modelos.

    Args:
        nombre_modelo: nombre del archivo a crear (sin .xml)
        especies: lista "nombre:conc_inicial" separada por comas, ej: "A:10, B:0, C:0"
        reacciones: lista de reacciones separadas por ';', formato "A -> B; k=0.5"
                     (soporta '->' irreversible; usa múltiples especies con '+', ej "A + B -> C; k=0.2")
        volumen_compartimento: volumen del compartimento único (unidades del modelo)
    """
    _check_copasi()

    data_model = COPASI.CRootContainer.addDatamodel()
    model = data_model.getModel()
    model.setObjectName(nombre_modelo)

    compartment = model.createCompartment("comp1", volumen_compartimento)

    especies_dict = {}
    for item in especies.split(","):
        item = item.strip()
        if not item:
            continue
        nombre, conc = item.split(":")
        nombre = nombre.strip()
        conc = float(conc.strip())
        metab = model.createMetabolite(nombre, compartment.getObjectName())
        metab.setInitialConcentration(conc)
        especies_dict[nombre] = metab

    reacciones_creadas = []
    for idx, r in enumerate(reacciones.split(";")):
        r = r.strip()
        if not r:
            continue
        if "," in r:
            eq_part, k_part = r.split(",", 1)
            k_part = k_part.strip()
        else:
            eq_part = r
            k_part = "k=0.1"
        eq_part = eq_part.strip()
        k_value = 0.1
        if "k=" in k_part:
            try:
                k_value = float(k_part.split("k=")[1].strip())
            except ValueError:
                pass

        reaction = model.createReaction(f"r{idx+1}")
        reaction.setChemEq(eq_part)
        # cinética de masa-acción por defecto
        fun = COPASI.CRootContainer.getFunctionList().findFunction("Mass action (irreversible)")
        reaction.setFunction(fun)
        reaction.setParameterValue("k1", k_value)
        reacciones_creadas.append(f"{eq_part}  (k={k_value:g})")

    model.compileIfNecessary()
    model.applyInitialValues()

    out_path = MODELS_DIR / f"{nombre_modelo}.xml"
    data_model.saveModel(str(out_path), True)
    COPASI.CRootContainer.removeDatamodel(data_model)

    return (
        f"Modelo '{nombre_modelo}' creado en {out_path}\n"
        f"Especies: {list(especies_dict.keys())}\n"
        f"Reacciones:\n  " + "\n  ".join(reacciones_creadas)
    )


# ---------------------------------------------------------------------------
# 5) Ajuste básico de un parámetro (grid search + SSE) contra datos experimentales
# ---------------------------------------------------------------------------

@mcp.tool()
def ajustar_parametro_simple(
    modelo: str,
    nombre_parametro: str,
    valor_min: float,
    valor_max: float,
    n_puntos: int,
    csv_experimental: str,
    columna_tiempo: str,
    columna_variable: str,
    duracion: float,
) -> str:
    """
    Ajuste simple de UN parámetro por grid search: prueba n_puntos valores entre
    valor_min y valor_max, simula el modelo para cada uno, y calcula el error
    cuadrático (SSE) contra datos experimentales en un CSV. Devuelve el mejor valor.

    Args:
        modelo: nombre o ruta del archivo SBML
        nombre_parametro: parámetro global o especie a variar
        valor_min: límite inferior del rango de búsqueda
        valor_max: límite superior del rango de búsqueda
        n_puntos: cuántos valores probar en el rango (ej. 10-20)
        csv_experimental: ruta a CSV con datos experimentales (con encabezado)
        columna_tiempo: nombre de la columna de tiempo en el CSV experimental
        columna_variable: nombre de la columna a comparar (debe coincidir con una
                           especie/variable del modelo simulado)
        duracion: duración de la simulación (debe cubrir el rango de tiempo experimental)
    """
    _check_copasi()
    path = _resolve_model_path(modelo)

    exp_path = Path(csv_experimental).expanduser()
    if not exp_path.exists():
        return f"No encontré el CSV experimental: {exp_path}"

    exp_t, exp_y = [], []
    with open(exp_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            exp_t.append(float(row[columna_tiempo]))
            exp_y.append(float(row[columna_variable]))

    if not exp_t:
        return "El CSV experimental no tiene filas."

    mejor_valor = None
    mejor_sse = float("inf")
    resultados = []

    for i in range(n_puntos):
        valor = valor_min + (valor_max - valor_min) * i / max(n_puntos - 1, 1)

        data_model = COPASI.CRootContainer.addDatamodel()
        if not data_model.importSBML(str(path)):
            COPASI.CRootContainer.removeDatamodel(data_model)
            return f"Error al importar SBML: {path}"

        model = data_model.getModel()
        encontrado = False
        for j in range(model.getNumModelValues()):
            mv = model.getModelValue(j)
            if mv.getObjectName() == nombre_parametro:
                mv.setInitialValue(valor)
                encontrado = True
                break
        if not encontrado:
            for j in range(model.getNumMetabs()):
                s = model.getMetabolite(j)
                if s.getObjectName() == nombre_parametro:
                    s.setInitialConcentration(valor)
                    encontrado = True
                    break
        if not encontrado:
            COPASI.CRootContainer.removeDatamodel(data_model)
            return f"No encontré '{nombre_parametro}' en el modelo."

        model.applyInitialValues()

        task = data_model.getTask("Time-Course")
        problem = task.getProblem()
        problem.setStepNumber(max(len(exp_t) * 5, 50))
        problem.setDuration(duracion)
        problem.setTimeSeriesRequested(True)
        task.setMethodType(COPASI.CTaskEnum.Method_deterministic)

        success = task.processWithOutputFlags(True, COPASI.CCopasiTask.ONLY_TIME_SERIES)
        if not success:
            COPASI.CRootContainer.removeDatamodel(data_model)
            continue

        ts = task.getTimeSeries()
        n_vars = ts.getNumVariables()
        titles = [ts.getTitle(k) for k in range(n_vars)]
        try:
            col_idx = titles.index(columna_variable)
            time_idx = titles.index("Time") if "Time" in titles else 0
        except ValueError:
            COPASI.CRootContainer.removeDatamodel(data_model)
            return f"La variable '{columna_variable}' no aparece en la salida simulada: {titles}"

        sim_t = [ts.getData(s, time_idx) for s in range(ts.getRecordedSteps())]
        sim_y = [ts.getData(s, col_idx) for s in range(ts.getRecordedSteps())]

        sse = 0.0
        for te, ye in zip(exp_t, exp_y):
            # interpolación lineal simple sobre la serie simulada
            yi = _interp(sim_t, sim_y, te)
            sse += (yi - ye) ** 2

        resultados.append((valor, sse))
        if sse < mejor_sse:
            mejor_sse = sse
            mejor_valor = valor

        COPASI.CRootContainer.removeDatamodel(data_model)

    tabla = "\n".join(f"  {v:.5g} -> SSE={s:.5g}" for v, s in resultados)
    return (
        f"Mejor valor encontrado para '{nombre_parametro}': {mejor_valor:.5g} "
        f"(SSE={mejor_sse:.5g})\n\nBúsqueda completa:\n{tabla}\n\n"
        "Nota: este es un grid search simple sobre 1 parámetro. Para ajuste multi-parámetro "
        "y algoritmos más robustos (evolución diferencial, etc.) se puede usar la tarea de "
        "Parameter Estimation nativa de COPASI — avísame si quieres que agregue esa versión."
    )


def _interp(xs, ys, x):
    """Interpolación lineal simple; extrapola con el valor del extremo más cercano."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if xs[i] >= x:
            x0, x1 = xs[i - 1], xs[i]
            y0, y1 = ys[i - 1], ys[i]
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return ys[-1]


# ---------------------------------------------------------------------------

@mcp.tool()
def estado_copasi() -> str:
    """Verifica si los bindings de COPASI se importaron correctamente."""
    if COPASI_OK:
        version = COPASI.CVersion.VERSION.getVersion()
        return f"COPASI OK — versión {version}. PYTHONPATH usado: {COPASI_BINDINGS_DIR}"
    return f"COPASI NO disponible.\n{COPASI_IMPORT_ERROR}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
