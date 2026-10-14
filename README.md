# simulation

Imagem Docker de desenvolvimento com **ArduPilot SITL**, **Gazebo Harmonic**, o plugin
**ardupilot_gazebo** e o **uav_api**. Funciona com GPU NVIDIA (se o host tiver o NVIDIA
Container Toolkit) ou, sem ele, via Mesa: GPU integrada Intel/AMD por `/dev/dri`, ou llvmpipe (software) se não houver nenhuma.

> `aerostation` será adicionado à imagem quando o pacote estiver no PyPI. Até lá, rode-o no
> host; o container usa `--network host`, então `uav-api` em `:8000` e o SITL ficam acessíveis.

## Build e execução

```bash
cd simulation
./run.sh --build     # primeira vez (demora: baixa Gazebo, ArduPilot e compila o SITL)
./run.sh             # abre um shell; chamar de novo em outro terminal entra no mesmo container
```

`run.sh` adiciona `--gpus all` automaticamente quando `nvidia-smi` funciona **e** o Docker
tem o runtime `nvidia`. Caso contrário avisa e roda em Mesa (iGPU ou software). `./run.sh --cpu` força o modo
sem GPU.

A pasta `aerorio/` do host fica montada em `/home/ardupilot/aerorio` dentro do container.

## Habilitar a GPU NVIDIA (host)

O driver já está instalado, mas o Docker precisa do NVIDIA Container Toolkit:

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Verificação dentro do container: `nvidia-smi` e `glxinfo -B` (deve mostrar
`NVIDIA GeForce RTX ...` em vez de `llvmpipe`).

## Iniciar a simulação

Dentro do container, `start_simulation.sh [mundo]` abre uma sessão tmux `drone` com cinco painéis:
Gazebo, SITL (`sim_vehicle.py` com mapa e console), `uav-api` em `:8000`, a ponte ROS 2 da câmera
e o `camera_saver.py`, que grava as fotos.

```bash
./run.sh                       # no host
start_simulation.sh            # no container: mundo padrão iris_runway.sdf
start_simulation.sh missao1    # mundo customizado (ver seção abaixo)
```

- `Ctrl-b d` desanexa da sessão (tudo continua rodando); `start_simulation.sh` de novo reanexa.
- `stop_simulation.sh` encerra tudo: manda Ctrl-C aos painéis, mata o que sobrar (Gazebo, SITL,
  MAVProxy, uav-api, ponte ROS 2, camera_saver) e fecha a sessão tmux. Com `--purge` apaga
  também os arquivos que o SITL deixa em `~` (`eeprom.bin`, `logs/`, `terrain/`, `mav.*`).
- O SITL sobe com `sim_vehicle.py -N` (sem recompilar; o binário já vem pronto na imagem).
  Se você alterar o código do ArduPilot, compile uma vez com `sim_vehicle.py -v ArduCopter --no-mavproxy`
  ou `cd ~/ardupilot && ./waf copter`.
- Mundos `zephyr*` sobem `ArduPlane`; os demais, `ArduCopter` com o frame `gazebo-iris`.
- O `uav-api` 0.3+ trata `--simulated` como flag sem valor; para SITL externo o script
  não passa a flag e usa `--uav_connection <ip>:14550 --connection_type udpin`.

## Imagens da câmera via ROS 2

A imagem tem ROS 2 Jazzy (`ros-base`, `ros_gz_bridge`, `ros_gz_image`, `cv_bridge`,
`rqt_image_view`). O ROS é carregado por `~/ros_env.sh` (já no `.bashrc`), **não** pelo
`setup.bash` diretamente: o `setup.bash` sozinho põe o `gz` do pacote vendor do ROS na frente
e esconde o `gz sim` do Gazebo do sistema ("sim is not a valid command"). Se isso acontecer num
shell, rode `source ~/ros_env.sh`. O painel 3 do `start_simulation.sh` espera o Gazebo publicar tópicos
`.../sensor/<nome>/image`, descobre todos e sobe um `parameter_bridge` para cada um (mais o
`camera_info`). Para o Iris com gimbal o tópico é:

```
/world/<mundo>/model/iris_with_gimbal/model/gimbal/link/pitch_link/sensor/camera/image
```

`<mundo>` é o `<world name=...>` dentro do SDF, não o nome do arquivo (os mundos customizados
usam `iris_runway`). Para conferir:

```bash
ros2 topic list | grep image
ros2 topic hz /world/iris_runway/model/iris_with_gimbal/model/gimbal/link/pitch_link/sensor/camera/image
ros2 run rqt_image_view rqt_image_view
```

Leitura em Python (o `rclpy` fica importável no mesmo interpretador do `uav_api`):

```python
import rclpy, cv2
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

TOPIC = "/world/iris_runway/model/iris_with_gimbal/model/gimbal/link/pitch_link/sensor/camera/image"

class Camera(Node):
    def __init__(self):
        super().__init__("camera_reader")
        self.bridge = CvBridge()
        self.create_subscription(Image, TOPIC, self.on_image, 10)
    def on_image(self, msg):
        frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")   # numpy BGR, pronto para o OpenCV
        cv2.imwrite("/tmp/frame.jpg", frame)

rclpy.init(); rclpy.spin(Camera())
```

## Fotos da câmera (`camera_saver.py`)

O painel 4 roda `camera_saver.py`, que assina o primeiro tópico `sensor_msgs/Image` publicado
pela ponte e grava `frame_00000.png`, `frame_00001.png`, ... uma vez por segundo em
`$DRONE_PHOTOS_DIR` (padrão `/home/ardupilot/aerorio/photos`). Como o `run.sh` monta a pasta
`aerorio/` do host no container, as fotos aparecem em **`aerorio/photos/`** no host e nos
scripts de missão que rodam dentro do container, sem configurar nada.

- A numeração continua do último `frame_NNNNN.png` existente; apague a pasta para recomeçar.
- Opções: `camera_saver.py --dir PASTA --topic TOPICO --interval 0.5`.
- Rodar à mão: `camera_saver.py` (já está no PATH e usa o Python do sistema, onde ficam
  `rclpy`, `numpy` e `cv2`).

## Mundos e modelos customizados

A pasta `simulation/gazebo/` é copiada para `/home/ardupilot/aerorio_gazebo` na imagem e entra
**antes** da `ardupilot_gazebo` no `GZ_SIM_RESOURCE_PATH`: um modelo com o mesmo nome aqui
substitui o do upstream.

```
simulation/gazebo/
├── models/<nome>/model.sdf + model.config   # ex.: basepadronizada, gabaritohexagono25
├── worlds/<nome>.sdf                        # ex.: missao1.sdf, bouncing.sdf
└── normalize.sh
```

Para atualizar a partir do Drive ("Arquivos do Gazebo"): baixe a pasta, extraia `models/` e
`worlds/` aqui e rode `./gazebo/normalize.sh`. Ele apaga os `*Zone.Identifier` do Windows e
troca os caminhos absolutos da máquina de origem (`file:///home/grelhas/...`) por
`model://<nome>`. Depois, `./run.sh --build`.

Regras para novos arquivos: referencie modelos sempre como `<uri>model://<nome></uri>`, nunca
com caminho absoluto, e cada modelo precisa de `model.config` com `<name>` igual à pasta.

## Fechar o container

O container sobe com `--rm`, então ele é removido automaticamente ao encerrar. Há três jeitos:

```bash
# 1. No terminal principal (o primeiro ./run.sh): sair do shell encerra o container
exit            # ou Ctrl+D

# 2. De qualquer terminal do host: parar o container pelo nome
docker stop aerorio-sim

# 3. Terminais extras (./run.sh chamado enquanto o container já rodava) são apenas
#    `docker exec`; sair deles não derruba o container
```

Antes de sair, encerre a simulação com `stop_simulation.sh`, ou use `docker stop`, que envia
SIGTERM a tudo e remove o container.
Arquivos salvos fora de `/home/ardupilot/aerorio` (a pasta montada do host) são perdidos ao
fechar; o que estiver nessa pasta permanece no host.

## Fixar versões

```bash
docker build --build-arg ARDUPILOT_REF=Copter-4.6 --build-arg ARDUPILOT_GAZEBO_REF=main -t aerorio/sim .
```
