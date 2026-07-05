#!/usr/bin/env bash
# Instala GROMACS en Ubuntu/Debian.
# Uso: sudo bash install_gromacs.sh [version]
# Por defecto compila desde codigo fuente (recomendado: mejor rendimiento,
# permite elegir soporte GPU). Si preferis algo mas rapido y simple,
# mas abajo esta comentada la opcion via apt.

set -e

VERSION="${1:-2024.4}"
JOBS="$(nproc)"

echo "=== Instalando dependencias de compilacion ==="
apt-get update
apt-get install -y \
    build-essential \
    cmake \
    wget \
    libfftw3-dev \
    libopenmpi-dev \
    openmpi-bin \
    ninja-build \
    python3-dev

echo "=== Descargando GROMACS $VERSION ==="
cd /tmp
wget -q "https://ftp.gromacs.org/gromacs/gromacs-${VERSION}.tar.gz"
tar xf "gromacs-${VERSION}.tar.gz"
cd "gromacs-${VERSION}"

echo "=== Configurando build (CPU, con MPI opcional para thread-MPI) ==="
mkdir -p build && cd build
cmake .. \
    -DGMX_BUILD_OWN_FFTW=OFF \
    -DGMX_MPI=OFF \
    -DGMX_GPU=OFF \
    -DCMAKE_INSTALL_PREFIX=/usr/local/gromacs

echo "=== Compilando (esto puede tardar 15-40 min) ==="
make -j"${JOBS}"

echo "=== Instalando ==="
make install

echo "=== Listo. Agregando GROMACS al entorno ==="
echo 'source /usr/local/gromacs/bin/GMXRC' >> /etc/profile.d/gromacs.sh
source /usr/local/gromacs/bin/GMXRC

gmx --version

echo ""
echo "GROMACS instalado. Abri una terminal nueva (o corre 'source /usr/local/gromacs/bin/GMXRC')"
echo "para que el comando 'gmx' quede disponible en el PATH."

# ------------------------------------------------------------------
# Alternativa rapida (paquete precompilado de Ubuntu, version puede ser
# mas vieja que la oficial). Si preferis esto en vez de compilar:
#
#   sudo apt-get update
#   sudo apt-get install -y gromacs
#
# ------------------------------------------------------------------

# Para soporte GPU (NVIDIA/CUDA), agregar al cmake:
#   -DGMX_GPU=CUDA
# y tener instalado el CUDA toolkit antes de compilar.
