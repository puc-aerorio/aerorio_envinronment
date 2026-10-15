# Ambiente de desenvolvimento: ArduPilot SITL + Gazebo Harmonic + ardupilot_gazebo + uav_api + ROS 2 Jazzy
#
# Build:  docker build -t aerorio/sim .
# Run:    ./run.sh            (detecta GPU NVIDIA automaticamente; cai para Mesa/llvmpipe sem ela)
#
# Versões podem ser fixadas no build:
#   docker build --build-arg ARDUPILOT_REF=Copter-4.6 --build-arg ARDUPILOT_GAZEBO_REF=main -t aerorio/sim .
# O usuário do container é criado com HOST_UID/HOST_GID (padrão 1000) para escrever na pasta montada.

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

# 3b. ROS 2 Jazzy + ros_gz (ponte Gazebo -> ROS 2 para ler as imagens da câmera).
#     Jazzy é o par oficial do Gazebo Harmonic no Ubuntu 24.04.
RUN curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" \
       > /etc/apt/sources.list.d/ros2.list \
    && apt-get update && apt-get install -y \
    ros-jazzy-ros-base \
    ros-jazzy-ros-gz-bridge \
    ros-jazzy-ros-gz-image \
    ros-jazzy-cv-bridge \
    ros-jazzy-rqt-image-view \
    python3-colcon-common-extensions \
    && rm -rf /var/lib/apt/lists/*
ENV ROS_DISTRO=jazzy

# 4. Usuário sem root (os scripts do ArduPilot recusam rodar como root).
#    Criado com o uid/gid do usuário do host (run.sh passa HOST_UID/HOST_GID) para que o container
#    consiga escrever na pasta aerorio/ montada do host (fotos do camera_saver, logs, etc.).
#    O ubuntu:24.04 já traz um usuário "ubuntu" com uid 1000; ele é removido para liberar o uid.
ARG HOST_UID=1000
ARG HOST_GID=1000
RUN if getent passwd "${HOST_UID}" >/dev/null; then userdel -r "$(getent passwd "${HOST_UID}" | cut -d: -f1)"; fi \
    && if getent group "${HOST_GID}" >/dev/null; then groupdel "$(getent group "${HOST_GID}" | cut -d: -f1)" || true; fi \
    && groupadd -o -g "${HOST_GID}" ardupilot \
    && useradd -m -s /bin/bash -u "${HOST_UID}" -g "${HOST_GID}" ardupilot \
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

# 7b. Mundos e modelos customizados da equipe (simulation/gazebo -> ~/aerorio_gazebo).
#     normalize.sh remove lixo do Windows (*Zone.Identifier) e troca caminhos absolutos
#     (file:///home/grelhas/...) por URIs portáveis model://<nome>.
COPY --chown=ardupilot:ardupilot gazebo/ /home/ardupilot/aerorio_gazebo/
COPY --chown=ardupilot:ardupilot start_simulation.sh stop_simulation.sh camera_saver.py /home/ardupilot/
COPY --chown=ardupilot:ardupilot tmux.conf /home/ardupilot/.tmux.conf
# xclip: copiar do tmux para o clipboard do host (via X11). Instalado aqui, tarde, para não
# invalidar as camadas pesadas (ArduPilot/Gazebo) quando mudar.
RUN sudo apt-get update && sudo apt-get install -y --no-install-recommends xclip \
    && sudo rm -rf /var/lib/apt/lists/*

# 7c. Visual Studio Code (repositório da Microsoft). A janela abre no X11 do host como o Gazebo.
#     Configurações e extensões ficam em ~/.config/Code e ~/.vscode, que o run.sh monta como
#     volumes Docker nomeados para sobreviverem ao --rm do container.
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor \
        | sudo tee /usr/share/keyrings/packages.microsoft.gpg >/dev/null \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" \
        | sudo tee /etc/apt/sources.list.d/vscode.list >/dev/null \
    && sudo apt-get update && sudo apt-get install -y --no-install-recommends code libasound2t64 \
    && sudo rm -rf /var/lib/apt/lists/* \
    && mkdir -p /home/ardupilot/.config/Code /home/ardupilot/.vscode \
    && printf '%s\n' '#!/bin/sh' \
         '# O sandbox do Chromium precisa criar namespaces, bloqueado pelo seccomp padrão do Docker.' \
         'exec /usr/bin/code --no-sandbox "$@"' \
       | sudo tee /usr/local/bin/code >/dev/null \
    && sudo chmod +x /usr/local/bin/code
RUN chmod +x /home/ardupilot/aerorio_gazebo/normalize.sh /home/ardupilot/start_simulation.sh \
       /home/ardupilot/stop_simulation.sh /home/ardupilot/camera_saver.py \
    && /home/ardupilot/aerorio_gazebo/normalize.sh /home/ardupilot/aerorio_gazebo \
    && sudo ln -sf /home/ardupilot/start_simulation.sh /usr/local/bin/start_simulation.sh \
    && sudo ln -sf /home/ardupilot/stop_simulation.sh /usr/local/bin/stop_simulation.sh \
    && sudo ln -sf /home/ardupilot/camera_saver.py /usr/local/bin/camera_saver.py

# 8. Variáveis de ambiente (ENV para docker exec / shells não interativos; .bashrc para shells de login)
# DRONE_PHOTOS_DIR: onde camera_saver.py grava as fotos; aerorio/photos do host via o bind mount do run.sh.
ENV DRONE_PHOTOS_DIR=/home/ardupilot/aerorio/photos \
    GZ_SIM_SYSTEM_PLUGIN_PATH=/home/ardupilot/ardupilot_gazebo/build \
    GZ_SIM_RESOURCE_PATH=/home/ardupilot/aerorio_gazebo/models:/home/ardupilot/aerorio_gazebo/worlds:/home/ardupilot/ardupilot_gazebo/models:/home/ardupilot/ardupilot_gazebo/worlds \
    PATH=/home/ardupilot/venv-ardupilot/bin:/home/ardupilot/.local/bin:/home/ardupilot/ardupilot/Tools/autotest:${PATH}
# ros_env.sh: carrega o ROS 2 e corrige a colisão com o Gazebo do sistema. O setup.bash do ROS
# põe o "gz" do gz_tools_vendor na frente no PATH e define GZ_CONFIG_PATH só com os pacotes
# vendor (transport/msgs), o que esconde o "gz sim" do gz-harmonic. Usado pelo .bashrc,
# start_simulation.sh e camera_saver.py. O venv volta para a frente do PATH para que "python3"
# seja o do ArduPilot (pymavlink, uav_api); o rclpy continua importável nele via PYTHONPATH do ROS.
RUN { \
      echo 'source /opt/ros/jazzy/setup.bash'; \
      echo 'export GZ_CONFIG_PATH="/usr/share/gz${GZ_CONFIG_PATH:+:$GZ_CONFIG_PATH}"'; \
      echo 'export PATH="$HOME/venv-ardupilot/bin:/usr/local/bin:/usr/bin:$PATH"'; \
    } > /home/ardupilot/ros_env.sh \
    && { \
      echo 'export GZ_VERSION=harmonic'; \
      echo 'export GZ_SIM_SYSTEM_PLUGIN_PATH=$HOME/ardupilot_gazebo/build:$GZ_SIM_SYSTEM_PLUGIN_PATH'; \
      echo 'export GZ_SIM_RESOURCE_PATH=$HOME/aerorio_gazebo/models:$HOME/aerorio_gazebo/worlds:$HOME/ardupilot_gazebo/models:$HOME/ardupilot_gazebo/worlds'; \
      echo 'export PATH=$HOME/ardupilot/Tools/autotest:$PATH'; \
      echo 'source $HOME/ardupilot/Tools/completion/completion.bash'; \
      echo 'source $HOME/ros_env.sh'; \
    } >> ~/.bashrc

CMD ["/bin/bash"]
