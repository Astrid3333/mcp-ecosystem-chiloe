"""
templates.py
Generadores de archivos de entrada para GROMACS (.mdp) y LAMMPS (.in).
Son plantillas razonables por defecto, pensadas para editarse a mano
después si hace falta mayor control.
"""


def gromacs_mdp_template(sim_type: str, nsteps: int, dt: float, temperature: float,
                          extra_params: dict | None = None) -> str:
    sim_type = sim_type.lower()
    extra_params = extra_params or {}

    common = f"""; Generado automáticamente - tipo: {sim_type}
nsteps                  = {nsteps}
dt                      = {dt}
nstxout                 = 500
nstvout                 = 500
nstenergy               = 500
nstlog                  = 500
continuation            = yes
constraint_algorithm    = lincs
constraints             = h-bonds
cutoff-scheme           = Verlet
coulombtype             = PME
rcoulomb                = 1.0
rvdw                    = 1.0
pbc                     = xyz
"""

    if sim_type == "em":
        block = """integrator              = steep
emtol                   = 1000.0
emstep                  = 0.01
"""
    elif sim_type == "nvt":
        block = f"""integrator              = md
tcoupl                  = V-rescale
tc-grps                 = System
tau_t                   = 0.1
ref_t                   = {temperature}
pcoupl                  = no
gen_vel                 = yes
gen_temp                = {temperature}
gen_seed                = -1
"""
    elif sim_type == "npt":
        block = f"""integrator              = md
tcoupl                  = V-rescale
tc-grps                 = System
tau_t                   = 0.1
ref_t                   = {temperature}
pcoupl                  = C-rescale
pcoupltype              = isotropic
tau_p                   = 2.0
ref_p                   = 1.0
compressibility         = 4.5e-5
gen_vel                 = no
"""
    else:  # md de producción
        block = f"""integrator              = md
tcoupl                  = V-rescale
tc-grps                 = System
tau_t                   = 0.1
ref_t                   = {temperature}
pcoupl                  = C-rescale
pcoupltype              = isotropic
tau_p                   = 2.0
ref_p                   = 1.0
compressibility         = 4.5e-5
gen_vel                 = no
"""

    extra_lines = "\n".join(f"{k} = {v}" for k, v in extra_params.items())
    return common + block + ("\n; parámetros extra\n" + extra_lines if extra_lines else "")


def lammps_input_template(sim_type: str, nsteps: int, timestep: float, temperature: float,
                           extra_lines: list[str] | None = None) -> str:
    sim_type = sim_type.lower()
    extra_lines = extra_lines or []

    header = f"""# Generado automáticamente - tipo: {sim_type}
units           lj
atom_style      atomic
boundary        p p p

# --- Reemplazá esta sección por tu propia geometría / lectura de datos ---
# read_data      data.system
# ---------------------------------------------------------------------

timestep        {timestep}
"""

    if sim_type == "min":
        block = """
minimize        1.0e-4 1.0e-6 1000 10000
"""
    elif sim_type == "nve":
        block = f"""
velocity        all create {temperature} 12345
fix             1 all nve
thermo          100
run             {nsteps}
"""
    elif sim_type == "nvt":
        block = f"""
velocity        all create {temperature} 12345
fix             1 all nvt temp {temperature} {temperature} 0.1
thermo          100
run             {nsteps}
"""
    elif sim_type == "npt":
        block = f"""
velocity        all create {temperature} 12345
fix             1 all npt temp {temperature} {temperature} 0.1 iso 1.0 1.0 1.0
thermo          100
run             {nsteps}
"""
    else:
        block = f"""
fix             1 all nve
thermo          100
run             {nsteps}
"""

    extra = "\n".join(extra_lines)
    return header + block + ("\n# líneas extra\n" + extra if extra else "")
