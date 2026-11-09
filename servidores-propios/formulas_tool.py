"""
formulas_tool.py

Módulo para octave-mcp: fórmulas matemáticas y científicas.
Backend sympy (en proceso, sin subprocess) — rápido y determinista.

Herramientas:
  - evaluate_formula: evaluación numérica de expresiones con variables.
  - solve_equation:   raíces de f(x)=0 (simbólicas + numéricas).
  - differentiate:    derivada simbólica (orden n).
  - integrate_symbolic: integral indefinida o definida.
  - formula_library:  catálogo de fórmulas por dominio (física, química,
                      biología, matemáticas, clima/recursos) con listado,
                      detalle y aplicación con valores dados.

INTEGRACIÓN EN octave_mcp.py (mismo patrón que lyapunov_tool):

    from formulas_tool import (
        evaluate_formula, solve_equation, differentiate,
        integrate_symbolic, formula_library,
        EVALUATE_FORMULA_SCHEMA, SOLVE_EQUATION_SCHEMA,
        DIFFERENTIATE_SCHEMA, INTEGRATE_SCHEMA, FORMULA_LIBRARY_SCHEMA,
    )
    # + agregar schemas a TOOLS y dispatch por nombre en tools/call.

SEGURIDAD: whitelist de caracteres + rechazo de `__`/import/`;` antes de
pasar la expresión a sympy (no es un sandbox perfecto, pero bloquea el
vector de inyección clásico de sympify).
"""

import re

import sympy
from sympy import (
    E,
    I,
    diff,
    exp,
    integrate,
    log,
    oo,
    parse_expr,
    pi,
    solve,
    sqrt,
)
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    standard_transformations,
)

_TRANSFORMATIONS = (
    standard_transformations
    + (convert_xor, implicit_multiplication_application)
)

_SAFE_EXPR = re.compile(r"^[a-zA-Z0-9_\.\+\-\*/\(\)\[\]\s,:^%]+$")
_MAX_EXPR_LEN = 2000

# Nombres siempre disponibles en expresiones (constantes / unidades simbólicas).
_BASE_LOCALS = {
    "pi": pi,
    "e": E,
    "E": E,
    "I": I,
    "oo": oo,
    "inf": oo,
    "sqrt": sqrt,
    "exp": exp,
    "log": log,
    "ln": log,
    "sin": sympy.sin,
    "cos": sympy.cos,
    "tan": sympy.tan,
    "abs": sympy.Abs,
    "Abs": sympy.Abs,
}


# ---------------------------------------------------------------------------
# Catálogo de fórmulas
# ---------------------------------------------------------------------------
# Cada entrada: formula (sympy-parseable, ^ = potencia), vars (nombre ->
# descripción+unidad), dominio, nota.
FORMULA_CATALOG = {
    # --- Matemáticas ---
    "cuadratica": {
        "domain": "matematicas",
        "formula": "(-b + sqrt(b^2 - 4*a*c)) / (2*a)",
        "vars": {"a": "coef. cuadrático", "b": "coef. lineal", "c": "término indep."},
        "note": "Raíz positiva de ax²+bx+c=0 (discriminante b²-4ac ≥ 0).",
    },
    "interes_compuesto": {
        "domain": "matematicas",
        "formula": "P * (1 + r/n)^(n*t)",
        "vars": {"P": "capital inicial", "r": "tasa anual (decimal)", "n": "capitalizaciones/año", "t": "años"},
        "note": "Crecimiento exponencial discreto.",
    },
    "decaimiento_exponencial": {
        "domain": "matematicas",
        "formula": "N0 * exp(-lambda*t)",
        "vars": {"N0": "cantidad inicial", "lambda": "constante de decaimiento", "t": "tiempo"},
        "note": "Valioso para recursos y radiactividad.",
    },
    "logistica": {
        "domain": "matematicas",
        "formula": "K / (1 + ((K - N0)/N0) * exp(-r*t))",
        "vars": {"K": "capacidad de carga", "N0": "población inicial", "r": "tasa de crecimiento", "t": "tiempo"},
        "note": "Crecimiento con techo (poblaciones, adopción, recursos).",
    },
    "gaussiana": {
        "domain": "matematicas",
        "formula": "A * exp(-(x - mu)^2 / (2*sigma^2))",
        "vars": {"A": "amplitud", "mu": "media", "sigma": "desv. estándar", "x": "variable"},
        "note": "Distribución normal (campana de Gauss).",
    },
    # --- Física ---
    "energia_cinetica": {
        "domain": "fisica",
        "formula": "0.5 * m * v^2",
        "vars": {"m": "masa [kg]", "v": "velocidad [m/s]"},
        "note": "Ec = ½mv² (no relativista).",
    },
    "energia_potencial": {
        "domain": "fisica",
        "formula": "m * g * h",
        "vars": {"m": "masa [kg]", "g": "gravedad [m/s²]", "h": "altura [m]"},
        "note": "Ep = mgh cerca de la superficie terrestre (g≈9.81).",
    },
    "segunda_ley_newton": {
        "domain": "fisica",
        "formula": "m * a",
        "vars": {"m": "masa [kg]", "a": "aceleración [m/s²]"},
        "note": "F = ma.",
    },
    "ley_ohm": {
        "domain": "fisica",
        "formula": "I * R",
        "vars": {"I": "corriente [A]", "R": "resistencia [Ω]"},
        "note": "V = IR.",
    },
    "potencia_electrica": {
        "domain": "fisica",
        "formula": "V * I",
        "vars": {"V": "voltaje [V]", "I": "corriente [A]"},
        "note": "P = VI (DC; sin factor de potencia).",
    },
    "presion": {
        "domain": "fisica",
        "formula": "F / A",
        "vars": {"F": "fuerza [N]", "A": "área [m²]"},
        "note": "P = F/A [Pa].",
    },
    "gas_ideal": {
        "domain": "fisica",
        "formula": "n * R * T / V",
        "vars": {"n": "moles [mol]", "T": "temperatura [K]", "V": "volumen [m³]"},
        "note": "P = nRT/V; R = 8.314 J/(mol·K) (ingresar T en Kelvin).",
    },
    "foton": {
        "domain": "fisica",
        "formula": "h * f",
        "vars": {"h": "const. Planck = 6.626e-34 [J·s]", "f": "frecuencia [Hz]"},
        "note": "E = hf (fórmula de Planck-Einstein).",
    },
    "onda": {
        "domain": "fisica",
        "formula": "f * lambda",
        "vars": {"f": "frecuencia [Hz]", "lambda": "long. de onda [m]"},
        "note": "v = f·λ.",
    },
    # --- Química ---
    "molaridad": {
        "domain": "quimica",
        "formula": "n / V",
        "vars": {"n": "moles de soluto [mol]", "V": "volumen de solución [L]"},
        "note": "C = n/V [M = mol/L].",
    },
    "ph": {
        "domain": "quimica",
        "formula": "-log(H, 10)",
        "vars": {"H": "concentración [H⁺] [mol/L]"},
        "note": "pH = -log₁₀[H⁺]. Usar log(x, 10) o log10; sympy: log(H)/log(10).",
    },
    "arrhenius": {
        "domain": "quimica",
        "formula": "A * exp(-Ea / (R * T))",
        "vars": {"A": "factor preexponencial", "Ea": "energía de activación [J/mol]", "R": "8.314", "T": "temperatura [K]"},
        "note": "k = A·e^(−Ea/RT).",
    },
    # --- Biología ---
    "michaelis_menten": {
        "domain": "biologia",
        "formula": "Vmax * S / (Km + S)",
        "vars": {"Vmax": "velocidad máxima", "S": "concentración [S]", "Km": "constante de Michaelis"},
        "note": "v = Vmax·[S]/(Km+[S]).",
    },
    # --- Clima / recursos (útil para COLAPSO: 2084) ---
    "vida_media": {
        "domain": "recursos",
        "formula": "N0 * 0.5^(t / t_half)",
        "vars": {"N0": "cantidad inicial", "t_half": "vida media", "t": "tiempo"},
        "note": "N(t) = N0 · ½^(t/t½).",
    },
    "tasa_extraccion_sostenible": {
        "domain": "recursos",
        "formula": "r * K",
        "vars": {"r": "tasa intrínseca de renovación", "K": "capacidad de carga del recurso"},
        "note": "Máx. extracción renovable (modelo logístico en el punto K/2 ≈ rK/4 si r es fraccional; aquí extracción = r·K como cota superior simple).",
    },
}

_DOMAINS = sorted({f["domain"] for f in FORMULA_CATALOG.values()})


# ---------------------------------------------------------------------------
# Utilidades seguras
# ---------------------------------------------------------------------------
def _safe_parse(expr: str, extra_locals: dict | None = None) -> sympy.Expr:
    expr = (expr or "").strip()
    if not expr:
        raise ValueError("Expresión vacía.")
    if len(expr) > _MAX_EXPR_LEN:
        raise ValueError(f"Expresión demasiado larga (máx {_MAX_EXPR_LEN}).")
    if "__" in expr or ";" in expr or "import" in expr:
        raise ValueError("Expresión contiene constructos no permitidos.")
    if not _SAFE_EXPR.match(expr):
        raise ValueError(
            "Caracteres no permitidos. Solo letras, dígitos, operadores "
            "matemáticos y paréntesis."
        )
    local_dict = dict(_BASE_LOCALS)
    if extra_locals:
        # Variables de usuario como Symbols sympy (nombres simples).
        for k, v in extra_locals.items():
            if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", str(k)):
                raise ValueError(f"Nombre de variable inválido: {k!r}")
            local_dict[k] = sympy.Symbol(k)
            local_dict[k].value = v  # type: ignore[attr-defined]
    return parse_expr(expr, local_dict=local_dict, transformations=_TRANSFORMATIONS)


def _to_float(val) -> float | complex | None:
    try:
        v = complex(val.evalf())
        if abs(v.imag) < 1e-15:
            return float(v.real)
        return v
    except Exception:
        return None


def _jsonable(expr) -> str | float | list:
    if expr is None:
        return None
    if isinstance(expr, (list, tuple)):
        return [_jsonable(e) for e in expr]
    f = _to_float(expr)
    if f is not None:
        return f
    return str(expr)


# ---------------------------------------------------------------------------
# Herramientas
# ---------------------------------------------------------------------------
def evaluate_formula(expression: str, variables: dict | None = None) -> dict:
    """
    Evalúa una expresión matemática con variables opcionales.

    Args:
        expression: expresión sympy (usar ^ para potencia, nombres simples).
        variables: {nombre: valor numérico} a sustituir.

    Returns:
        dict con result (numérico o simbólico), expression, variables.
    """
    try:
        if variables:
            for k in variables:
                if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", str(k)):
                    raise ValueError(f"Nombre de variable inválido: {k!r}")
            # Parsear variables como símbolos y sustituir.
            expr = _safe_parse(expression)
            subs = {sympy.Symbol(k): sympy.nsimplify(v) for k, v in variables.items()}
            result = expr.subs(subs)
            result = result.evalf()
        else:
            expr = _safe_parse(expression)
            result = expr.evalf()
        return {
            "ok": True,
            "expression": expression,
            "variables": variables or {},
            "result": _jsonable(result),
            "result_latex": sympy.latex(result),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "expression": expression}


def solve_equation(equation: str, variable: str = "x") -> dict:
    """
    Resuelve equation = 0 para `variable`.

    Args:
        equation: expresión igualada a cero (ej: "x^2 - 4").
        variable: incógnita (por defecto "x").

    Returns:
        dict con solutions (lista) y numeric cuando aplica.
    """
    try:
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", variable):
            raise ValueError(f"Variable inválida: {variable!r}")
        var = sympy.Symbol(variable)
        expr = _safe_parse(equation)
        sols = solve(expr, var)
        numeric = []
        for s in sols:
            f = _to_float(s)
            numeric.append(f if f is not None else str(s))
        return {
            "ok": True,
            "equation": f"{equation} = 0",
            "variable": variable,
            "solutions": [_jsonable(s) for s in sols],
            "solutions_numeric": numeric,
            "n_solutions": len(sols),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "equation": equation}


def differentiate(expression: str, variable: str = "x", order: int = 1) -> dict:
    """
    Derivada simbólica de `expression` respecto a `variable` (orden n).

    Args:
        expression: expresión a derivar.
        variable: variable de derivación.
        order: orden de derivada (>=1).

    Returns:
        dict con derivative (str) y numeric si es constante.
    """
    try:
        if order < 1 or order > 10:
            raise ValueError("order debe estar entre 1 y 10.")
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", variable):
            raise ValueError(f"Variable inválida: {variable!r}")
        var = sympy.Symbol(variable)
        expr = _safe_parse(expression)
        d = diff(expr, var, order)
        return {
            "ok": True,
            "expression": expression,
            "variable": variable,
            "order": order,
            "derivative": str(d),
            "derivative_latex": sympy.latex(d),
            "numeric_at_0": _jsonable(d.subs(var, 0)),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "expression": expression}


def integrate_symbolic(
    expression: str,
    variable: str = "x",
    lower: float | None = None,
    upper: float | None = None,
) -> dict:
    """
    Integral indefinida (sin límites) o definida [lower, upper].

    Args:
        expression: integrando.
        variable: variable de integración.
        lower/upper: límites; si ambos se dan, integral definida.

    Returns:
        dict con integral (str) y value si es numérica.
    """
    try:
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", variable):
            raise ValueError(f"Variable inválida: {variable!r}")
        var = sympy.Symbol(variable)
        expr = _safe_parse(expression)
        if lower is not None and upper is not None:
            res = integrate(expr, (var, lower, upper))
            kind = "definite"
        else:
            res = integrate(expr, var)
            kind = "indefinite"
        return {
            "ok": True,
            "expression": expression,
            "variable": variable,
            "kind": kind,
            "bounds": [lower, upper] if kind == "definite" else None,
            "integral": str(res),
            "integral_latex": sympy.latex(res),
            "numeric": _jsonable(res) if kind == "definite" else None,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "expression": expression}


def formula_library(
    action: str = "list",
    name: str | None = None,
    domain: str | None = None,
    values: dict | None = None,
) -> dict:
    """
    Catálogo de fórmulas científicas.

    Actions:
        list: lista fórmulas (filtro opcional por domain).
        get:  detalle de una fórmula por nombre.
        apply: aplica la fórmula con `values` (sustitución numérica).
    """
    try:
        if action == "list":
            items = []
            for fname, fdata in FORMULA_CATALOG.items():
                if domain and fdata["domain"] != domain:
                    continue
                items.append(
                    {
                        "name": fname,
                        "domain": fdata["domain"],
                        "formula": fdata["formula"],
                        "vars": fdata["vars"],
                    }
                )
            return {
                "ok": True,
                "action": "list",
                "domains": _DOMAINS,
                "count": len(items),
                "formulas": items,
            }

        if action in ("get", "apply"):
            if not name:
                raise ValueError("action='get'/'apply' requiere `name`.")
            if name not in FORMULA_CATALOG:
                raise ValueError(
                    f"Fórmula desconocida: {name!r}. "
                    f"Disponibles: {sorted(FORMULA_CATALOG)}"
                )
            fdata = FORMULA_CATALOG[name]
            if action == "get":
                return {"ok": True, "action": "get", "name": name, **fdata}

            # apply
            if not values:
                raise ValueError("action='apply' requiere `values`.")
            missing = [v for v in fdata["vars"] if v not in values]
            if missing:
                raise ValueError(f"Faltan variables: {missing}")
            r = evaluate_formula(fdata["formula"], variables=values)
            r["action"] = "apply"
            r["name"] = name
            r["formula"] = fdata["formula"]
            return r

        raise ValueError("action debe ser 'list', 'get' o 'apply'.")
    except Exception as exc:
        return {"ok": False, "error": str(exc), "action": action}


# ---------------------------------------------------------------------------
# Schemas MCP (patrón types.Tool / allowlist)
# ---------------------------------------------------------------------------
EVALUATE_FORMULA_SCHEMA = {
    "name": "evaluate_formula",
    "description": (
        "Evalúa una expresión matemática con variables opcionales. "
        "Usar ^ para potencias (ej: 0.5*m*v^2). Devuelve valor numérico y LaTeX."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "Expresión sympy, ej: '0.5*m*v^2'."},
            "variables": {"type": "object", "description": "{nombre: valor}, ej: {'m': 2, 'v': 3}."},
        },
        "required": ["expression"],
    },
}

SOLVE_EQUATION_SCHEMA = {
    "name": "solve_equation",
    "description": "Resuelve f(x)=0 y devuelve las raíces simbólicas y numéricas.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "equation": {"type": "string", "description": "Expresión igualada a cero, ej: 'x^2 - 4'."},
            "variable": {"type": "string", "default": "x"},
        },
        "required": ["equation"],
    },
}

DIFFERENTIATE_SCHEMA = {
    "name": "differentiate",
    "description": "Derivada simbólica de una expresión respecto a una variable (orden n).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "expression": {"type": "string"},
            "variable": {"type": "string", "default": "x"},
            "order": {"type": "integer", "default": 1, "minimum": 1, "maximum": 10},
        },
        "required": ["expression"],
    },
}

INTEGRATE_SCHEMA = {
    "name": "integrate_symbolic",
    "description": "Integral indefinida o definida de una expresión.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "expression": {"type": "string"},
            "variable": {"type": "string", "default": "x"},
            "lower": {"type": "number", "description": "Límite inferior (definida)."},
            "upper": {"type": "number", "description": "Límite superior (definida)."},
        },
        "required": ["expression"],
    },
}

FORMULA_LIBRARY_SCHEMA = {
    "name": "formula_library",
    "description": (
        "Catálogo de fórmulas científicas (física, química, biología, "
        "matemáticas, recursos/clima). action=list|get|apply."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "get", "apply"], "default": "list"},
            "name": {"type": "string", "description": "Nombre de la fórmula (get/apply)."},
            "domain": {"type": "string", "description": "Filtro de dominio (list)."},
            "values": {"type": "object", "description": "{var: valor} para apply."},
        },
        "required": [],
    },
}


if __name__ == "__main__":
    # Smoke test standalone
    print("eval:", evaluate_formula("0.5*m*v^2", {"m": 2, "v": 3}))
    print("solve:", solve_equation("x^2 - 4"))
    print("diff:", differentiate("x^3 + 2*x"))
    print("int:", integrate_symbolic("x^2", lower=0, upper=1))
    print("lib:", formula_library("apply", name="energia_cinetica", values={"m": 2, "v": 3}))
