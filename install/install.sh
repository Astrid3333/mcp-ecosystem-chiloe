#!/usr/bin/env bash
#
# install.sh - Instala GROMACS y/o LAMMPS en Ubuntu/Debian.
#
# Uso:
#   ./install.sh gromacs
#   ./install.sh lammps
#   ./install.sh both
#
# Requiere sudo y conexión a internet. Pensado para Ubuntu 22.04/24.04.

set -e

ENGINE="${1:-both}"

echo ">> Actualizando índices de paquetes..."
sudo apt-get update -y

echo ">> Instalando dependencias de compilación comunes..."
sudo apt-get install -y build-essential cmake git wget \
    libfftw3-dev libopenmpi-dev openmpi-bin \
    libblas-dev liblapack-dev

install_gromacs() {
    if command -v gmx >/dev/null 2>&1; then
        echo ">> GROMACS ya está instalado: $(gmx --version | head -n1)"
        return
    fi
    echo ">> Instalando GROMACS vía apt (paquete precompilado)..."
    if sudo apt-get install -y gromacs; then
        echo ">> GROMACS instalado correctamente."
    else
        echo ">> El paquete apt no está disponible, compilando desde fuente..."
        cd /tmp
        wget -q https://ftp.gromacs.org/gromacs/gromacs-2024.3.tar.gz
        tar xf gromacs-2024.3.tar.gz
        cd gromacs-2024.3
        mkdir -p build && cd build
        cmake .. -DGMX_BUILD_OWN_FFTW=ON -DREGRESSIONTEST_DOWNLOAD=OFF
        make -j"$(nproc)"
        sudo make install
        echo "source /usr/local/gromacs/bin/GMXRC" >> "$HOME/.bashrc"
        echo ">> GROMACS compilado e instalado en /usr/local/gromacs"
    fi
}

install_lammps() {
    if command -v lmp >/dev/null 2>&1; then
        echo ">> LAMMPS ya está instalado: $(lmp -help | head -n1)"
        return
    fi
    echo ">> Intentando instalar LAMMPS vía apt..."
    if sudo apt-get install -y lammps; then
        # el binario en Ubuntu suele llamarse lmp o lammps
        if ! command -v lmp >/dev/null 2>&1 && command -v lammps >/dev/null 2>&1; then
            sudo ln -sf "$(command -v lammps)" /usr/local/bin/lmp
        fi
        echo ">> LAMMPS instalado correctamente."
    else
        echo ">> El paquete apt no está disponible, compilando desde fuente..."
        cd /tmp
        git clone --depth 1 -b stable https://github.com/lammps/lammps.git
        cd lammps
        mkdir -p build && cd build
        cmake ../cmake -DBUILD_MPI=yes
        make -j"$(nproc)"
        sudo make install
        echo ">> LAMMPS compilado e instalado (binario: lmp)."
    fi
}

case "$ENGINE" in
    gromacs) install_gromacs ;;
    lammps)  install_lammps ;;
    both)    install_gromacs; install_lammps ;;
    *) echo "Uso: $0 [gromacs|lammps|both]"; exit 1 ;;
esac

echo ">> Listo. Verificá con: gmx --version   y/o   lmp -help"
