#!/usr/bin/env bash
# Instala LAMMPS en Ubuntu/Debian.
# Uso: sudo bash install_lammps.sh
#
# Por defecto compila desde codigo fuente con CMake (recomendado: permite
# elegir los "packages" que necesites, ej. MOLECULE, KSPACE, GPU, etc).
# Mas abajo esta comentada la opcion rapida via apt.

set -e

JOBS="$(nproc)"

echo "=== Instalando dependencias de compilacion ==="
apt-get update
apt-get install -y \
    build-essential \
    cmake \
    git \
    libopenmpi-dev \
    openmpi-bin \
    libfftw3-dev \
    ninja-build

echo "=== Clonando LAMMPS (rama stable) ==="
cd /tmp
if [ ! -d lammps ]; then
    git clone -b stable --depth 1 https://github.com/lammps/lammps.git
fi
cd lammps

echo "=== Configurando build ==="
mkdir -p build && cd build
cmake ../cmake \
    -D CMAKE_INSTALL_PREFIX=/usr/local \
    -D BUILD_MPI=yes \
    -D PKG_MOLECULE=yes \
    -D PKG_KSPACE=yes \
    -D PKG_RIGID=yes \
    -D PKG_EXTRA-DUMP=yes

echo "=== Compilando (esto puede tardar 15-40 min) ==="
cmake --build . -j"${JOBS}"

echo "=== Instalando (crea el binario 'lmp') ==="
cmake --install .

lmp -h | head -n 5

echo ""
echo "LAMMPS instalado. El binario se llama 'lmp' y deberia estar en /usr/local/bin/lmp"

# ------------------------------------------------------------------
# Alternativa rapida (paquete precompilado de Ubuntu, sin control fino
# de los packages incluidos):
#
#   sudo apt-get update
#   sudo apt-get install -y lammps
#
# ------------------------------------------------------------------

# Para agregar mas paquetes (ej. GPU, MANYBODY, REAXFF), agregar flags
# -D PKG_<NOMBRE>=yes al cmake antes de compilar. Lista completa:
# https://docs.lammps.org/Packages_list.html
