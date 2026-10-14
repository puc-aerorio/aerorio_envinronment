# Ambiente de desenvolvimento: ArduPilot SITL + Gazebo Harmonic + ardupilot_gazebo + uav_api
#
# Build:  docker build -t aerorio/sim .
# Run:    ./run.sh            (detecta GPU NVIDIA automaticamente; cai para Mesa/llvmpipe sem ela)
#
# Versões podem ser fixadas no build:
#   docker build --build-arg ARDUPILOT_REF=Copter-4.6 --build-arg ARDUPILOT_GAZEBO_REF=main -t aerorio/sim .

FROM ubuntu:24.04

ARG ARDUPILOT_REF=master
ARG ARDUPILOT_GAZEBO_REF=main

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=America/Sao_Paulo \
    LANG=C.UTF-8

# 1. Dependências básicas do sistema, OpenGL (GLVND) e X11.
#    libglvnd/libgl1/libegl1 permitem que o NVIDIA Container Toolkit injete o driver em runtime;
#    sem ele, as mesmas bibliotecas resolvem para o Mesa (llvmpipe) e o Gazebo continua renderizando.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata ca-certificates lsb-release curl gnupg git wget sudo \
    build-essential cmake pkg-config \
    python3 python3-dev python3-pip python3-setuptools python3-wheel python3-venv \
    libglvnd0 libglvnd-dev libgl1 libglx0 libegl1 libgles2 libgl1-mesa-dri mesa-utils \
    libx11-6 libxext6 libxrender1 libxi6 libxrandr2 libxcursor1 libxinerama1 libxkbcommon-x11-0 \
    libfontconfig1 libdbus-1-3 \
    x11-apps xauth tmux nano vim-tiny less \
    && rm -rf /var/lib/apt/lists/*

# Variáveis lidas pelo NVIDIA Container Toolkit quando o container roda com --gpus.
# Sem o toolkit (ou sem GPU) são simplesmente ignoradas.
ENV NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=all \
    QT_X11_NO_MITSHM=1

# 2. Repositório do Gazebo (OSRF). A chave já vem em formato binário, sem --dearmor.
RUN curl -fsSL https://packages.osrfoundation.org/gazebo.gpg -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" \
       > /etc/apt/sources.list.d/gazebo-stable.list

# 3. Gazebo Harmonic e dependências do plugin ardupilot_gazebo
RUN apt-get update && apt-get install -y \
    gz-harmonic \
    libgz-sim8-dev \
    rapidjson-dev \
    libopencv-dev \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-libav \
    gstreamer1.0-gl \
    && rm -rf /var/lib/apt/lists/*

# 4. Usuário sem root (os scripts do ArduPilot recusam rodar como root)
RUN useradd -m -s /bin/bash ardupilot \
    && echo "ardupilot ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers \
    && usermod -aG video,dialout ardupilot
USER ardupilot
WORKDIR /home/ardupilot
ENV USER=ardupilot \
    HOME=/home/ardupilot

# 5. ArduPilot (SITL)
#    Mesmas flags do Dockerfile oficial do ArduPilot: pula extras que não interessam para SITL.
#    DO_AP_STM_ENV=0 evita baixar o toolchain ARM (~1 GB), que só serve para firmware de placa.
ENV SKIP_AP_EXT_ENV=1 \
    SKIP_AP_COV_ENV=1 \
    SKIP_AP_GIT_CHECK=1 \
    DO_AP_STM_ENV=0
RUN git clone --branch "${ARDUPILOT_REF}" --recurse-submodules \
        https://github.com/ArduPilot/ardupilot.git /home/ardupilot/ardupilot \
    && cd /home/ardupilot/ardupilot \
    && Tools/environment_install/install-prereqs-ubuntu.sh -y \
    && sudo rm -rf /var/lib/apt/lists/*

# Pré-compila o SITL do ArduCopter para o primeiro sim_vehicle.py ser rápido.
# No Ubuntu 24.04 o install-prereqs cria o venv ~/venv-ardupilot (PEP 668); usamos ele se existir.
RUN bash -c 'set -e; \
    [ -f ~/.ardupilot_env ] && source ~/.ardupilot_env; \
    [ -f ~/venv-ardupilot/bin/activate ] && source ~/venv-ardupilot/bin/activate; \
    cd ~/ardupilot && ./waf configure --board sitl && ./waf copter'

# 6. uav_api (PyPI). Instalado no mesmo interpretador Python do ArduPilot/MAVProxy.
#    (aerostation será adicionado quando o pacote estiver no PyPI.)
RUN bash -c 'set -e; \
    if [ -f ~/venv-ardupilot/bin/activate ]; then \
        ~/venv-ardupilot/bin/pip install --no-cache-dir uav_api; \
    else \
        pip3 install --user --no-cache-dir --break-system-packages uav_api; \
    fi'

# 7. Plugin ardupilot_gazebo
ENV GZ_VERSION=harmonic
RUN git clone --branch "${ARDUPILOT_GAZEBO_REF}" \
        https://github.com/ArduPilot/ardupilot_gazebo.git /home/ardupilot/ardupilot_gazebo \
    && cd /home/ardupilot/ardupilot_gazebo \
    && mkdir build && cd build \
    && cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    && make -j"$(nproc)"

# 8. Variáveis de ambiente (ENV para docker exec / shells não interativos; .bashrc para shells de login)
ENV GZ_SIM_SYSTEM_PLUGIN_PATH=/home/ardupilot/ardupilot_gazebo/build \
    GZ_SIM_RESOURCE_PATH=/home/ardupilot/ardupilot_gazebo/models:/home/ardupilot/ardupilot_gazebo/worlds \
    PATH=/home/ardupilot/venv-ardupilot/bin:/home/ardupilot/.local/bin:/home/ardupilot/ardupilot/Tools/autotest:${PATH}
RUN { \
      echo 'export GZ_VERSION=harmonic'; \
      echo 'export GZ_SIM_SYSTEM_PLUGIN_PATH=$HOME/ardupilot_gazebo/build:$GZ_SIM_SYSTEM_PLUGIN_PATH'; \
      echo 'export GZ_SIM_RESOURCE_PATH=$HOME/ardupilot_gazebo/models:$HOME/ardupilot_gazebo/worlds:$GZ_SIM_RESOURCE_PATH'; \
      echo 'export PATH=$HOME/ardupilot/Tools/autotest:$PATH'; \
      echo 'source $HOME/ardupilot/Tools/completion/completion.bash'; \
    } >> ~/.bashrc

CMD ["/bin/bash"]
