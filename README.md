# aerorio_envinronment

Imagem Docker de desenvolvimento com **ArduPilot SITL**, **Gazebo Harmonic**, o plugin
**ardupilot_gazebo**, **ROS 2 Jazzy** (só para tirar as imagens da câmera do Gazebo), **uav_api**
e **VS Code**. Funciona com GPU NVIDIA (se o host tiver o NVIDIA Container Toolkit) ou, sem ele,
via Mesa (GPU integrada por `/dev/dri`, ou software).

> `aerostation` será adicionado à imagem quando o pacote estiver no PyPI. Até lá, rode-o no
> host; o container usa `--network host`, então `uav-api` em `:8000` e o SITL ficam acessíveis.

Estrutura do repositório:

```
.
├── Dockerfile                 # receita da imagem aerorio/sim
├── run.sh                     # constrói (--build) e abre o container no host
├── README.md
├── .dockerignore / .gitignore
├── tools/                     # arquivos do time, usados DENTRO do container (vira ~/tools)
│   ├── start_simulation.sh    # sobe Gazebo + SITL + uav-api + ponte + saver no tmux
│   ├── stop_simulation.sh     # derruba tudo (--purge limpa os arquivos do SITL)
│   ├── reset_drone.sh         # volta o drone ao início (reinicia só SITL + uav-api)
│   ├── camera_saver.py        # grava as fotos da câmera em workspace/photos/
│   ├── tmux.conf              # mouse e clipboard no tmux (vira ~/.tmux.conf)
│   ├── examples/exemplo_missao.py
│   └── gazebo/{models,worlds}/  # mundos e modelos da equipe (+ normalize.sh)
└── workspace/                 # SUA pasta de trabalho (vira ~/workspace)
    ├── tarefa/                # tarefa de entrada: kit/ fornecido e solucao/<seu_nome>/
    └── photos/                # fotos da câmera; criada em tempo de execução, ignorada pelo git
```

`tools/` é o que a equipe mantém (scripts, mundos, exemplos); `workspace/` é onde você cria os
seus scripts e pastas. As duas são montadas no container pelo `run.sh`.

## Guia rápido

Tudo abaixo roda no terminal do host, a menos que diga "no container".

### 1. Clonar e construir a imagem (uma vez)

```bash
git clone git@github.com:puc-aerorio/aerorio_envinronment.git
cd aerorio_envinronment
./run.sh --build     # demora: baixa Gazebo, ROS 2, ArduPilot, VS Code e compila o SITL
```

O clone pode ficar em qualquer pasta. A pasta `tools/` dele (scripts, mundos do Gazebo,
exemplos) é copiada para `~/tools` dentro da imagem.

Reconstrua (`./run.sh --build`) sempre que mudar o `Dockerfile` ou quiser que a imagem sozinha
(sem o `run.sh`) carregue suas mudanças em `tools/`.
As camadas pesadas ficam em cache, então só o que mudou é refeito.

### 2. Abrir o container

```bash
./run.sh             # abre um shell no container aerorio-sim
```

Chamar `./run.sh` de novo em outro terminal abre mais um shell no **mesmo** container.
`run.sh` monta duas pastas do clone, com o seu usuário: `tools/` por cima de `~/tools` e
`workspace/` em `~/workspace`. O que você editar ou gravar nelas (scripts, mundos, fotos) é o
mesmo arquivo no host, sem reconstruir a imagem. Crie os seus scripts em `~/workspace`.

### 3. Iniciar e parar a simulação

No container:

```bash
start_simulation.sh            # mundo padrão iris_runway.sdf
start_simulation.sh missao1    # um dos mundos customizados (tools/gazebo/worlds)
```

Abre uma sessão tmux `drone` com seis painéis: Gazebo, SITL (MAVProxy com mapa e console),
`uav-api` em `http://localhost:8000`, a ponte ROS 2 da câmera, o `camera_saver.py` (grava uma foto
por segundo em `~/workspace/photos`, ou seja, `workspace/photos/` no clone) e um **shell livre**, já
selecionado, para seus comandos.
Espere a API avisar `API is ready` antes de mandar comandos.

- Mouse: clique troca de painel, arraste a borda para redimensionar, roda rola o histórico.
- Copiar/colar: arrastar o texto copia para o clipboard do host; `Ctrl+Shift+V` ou botão do meio
  colam. Para selecionar pelo próprio terminal, arraste segurando `Shift`.
- `Ctrl-b d` desanexa (tudo continua rodando); `start_simulation.sh` de novo reanexa.

Para tentar a missão de novo (depois de mudar o código, por exemplo) sem esperar o Gazebo
carregar tudo outra vez, reinicie só o drone, no painel livre:

```bash
reset_drone.sh                 # drone de volta à pose inicial, SITL e uav-api novos
reset_drone.sh --purge         # idem, e apaga eeprom.bin/logs do SITL (parâmetros ao padrão)
```

Gazebo, ponte e `camera_saver.py` continuam rodando; o script só termina quando a uav-api
responde de novo, então `reset_drone.sh && python3 ~/workspace/missao.py` funciona.

Para parar:

```bash
stop_simulation.sh             # encerra Gazebo, SITL, uav-api, ponte e saver, fecha a sessão
stop_simulation.sh --purge     # idem, e apaga eeprom.bin, logs/, terrain/ e mav.* do SITL
```

### 4. Abrir o VS Code numa pasta

No container (qualquer painel ou shell):

```bash
code ~/workspace                   # a sua pasta (workspace/ do clone)
code ~/tools/examples              # os exemplos do time
```

A janela abre no seu desktop. O VS Code enxerga o Python do container (`pymavlink`, `uav_api`,
`cv2`), o ROS 2 e o ArduPilot. Extensões e configurações ficam guardadas em volumes Docker e
sobrevivem ao fechamento do container.

### 5. Rodar um script Python que usa a uav_api e as fotos

O script `tools/examples/exemplo_missao.py` arma, decola a 5 m, voa 10 m para o norte, lê a foto mais
recente gravada pelo `camera_saver.py`, mede o brilho e pousa. Com a simulação no ar, no painel
livre (ou em qualquer shell do container):

```bash
python3 ~/tools/examples/exemplo_missao.py
```

Para partir dele, copie-o para a sua pasta e edite a cópia:

```bash
cp ~/tools/examples/exemplo_missao.py ~/workspace/minha_missao.py
code ~/workspace/minha_missao.py
python3 ~/workspace/minha_missao.py
```

A receita que ele segue, para os seus próprios scripts:

```python
import glob, os, requests, cv2

API = "http://127.0.0.1:8000"                   # uav-api (painel 2)
FOTOS = os.path.expanduser("~/workspace/photos")  # onde o camera_saver.py grava

requests.get(f"{API}/command/arm").json()
requests.get(f"{API}/command/takeoff", params={"alt": 5}).json()
requests.post(f"{API}/movement/go_to_ned_wait", json={"x": 10, "y": 0, "z": -5}).json()

ultima = sorted(glob.glob(f"{FOTOS}/frame_*.png"))[-1]
img = cv2.imread(ultima)                        # numpy BGR, pronto para o OpenCV

requests.get(f"{API}/command/land")
```

A documentação interativa dos endpoints fica em `http://localhost:8000/docs` (também abre no
navegador do host). Scripts dentro de `~/workspace` são os mesmos arquivos de `workspace/` no
host, então edite no VS Code e rode no painel livre. Para usar outro projeto do host, acrescente um
`-v /caminho/no/host:/home/ardupilot/<nome>` ao `docker run` do `run.sh`.

### 6. Fechar o container

```bash
stop_simulation.sh   # no container, se a simulação estiver rodando
exit                 # (ou Ctrl+D) no shell principal, o do primeiro ./run.sh
```

Ou, de qualquer terminal do host, `docker stop aerorio-sim`. Shells extras abertos com
`./run.sh` são `docker exec`; sair deles não derruba o container. O container é removido ao
fechar (`--rm`): o que estiver fora de `~/workspace` e `~/tools` é perdido, o que estiver dentro
fica no clone.

## Referência

### Aceleração com GPU NVIDIA (host)

`run.sh` adiciona `--gpus all` automaticamente quando `nvidia-smi` funciona **e** o Docker tem
o runtime `nvidia`. Caso contrário avisa e roda em Mesa (iGPU via `/dev/dri` ou software).
`./run.sh --cpu` força o modo sem GPU. Para habilitar a GPU, instale o NVIDIA Container Toolkit:

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

### `run.sh`, `tools/`, `workspace/` e o usuário do container

O repositório tem três partes: na raiz, o que só o host usa (`Dockerfile`, `run.sh`, este README);
em `tools/`, o que a equipe mantém e roda dentro do container (scripts, `tmux.conf`, `gazebo/`,
`examples/`); em `workspace/`, a pasta de trabalho de cada um (tarefas, scripts próprios, fotos).
O `Dockerfile` copia só `tools/` para `/home/ardupilot/tools` (o `.dockerignore` deixa de fora
`workspace/` e `__pycache__`), põe os scripts no PATH como symlinks para lá e cria
`/home/ardupilot/workspace/photos` vazia. Assim a imagem funciona sozinha: `docker run -it --rm
aerorio/sim` em qualquer máquina já tem mundos, scripts e exemplos (sem edição ao vivo nem fotos
no host). `run.sh` monta a `tools/` do clone por cima desse mesmo caminho (a versão editada no
host é a que roda) e a `workspace/` do clone em `~/workspace`.

O usuário `ardupilot` do container é criado com o uid/gid de quem roda `./run.sh --build`
(`--build-arg HOST_UID/HOST_GID`), por isso os arquivos que o container grava em `~/workspace`
e `~/tools` pertencem ao seu usuário no host. Se outra pessoa usar a imagem com outro uid, reconstrua.
`run.sh` também compartilha o X11 (`DISPLAY` e `/tmp/.X11-unix`), usa `--network host` e monta
os volumes do VS Code.

### `start_simulation.sh` em detalhe

- O SITL sobe com `sim_vehicle.py -N` (sem recompilar; o binário já vem pronto na imagem).
  Se você alterar o código do ArduPilot, compile uma vez com `cd ~/ardupilot && ./waf copter`.
- Mundos `zephyr*` sobem `ArduPlane` (frame `gazebo-zephyr`); os demais, `ArduCopter` com o
  frame `gazebo-iris`.
- O script passa os `.parm` do frame com `--add-param-file` (ex.: `copter.parm` e `gazebo-iris.parm`).
  No ArduPilot master atual o `sim_vehicle.py` não passa mais `--defaults`; o binário procura os
  parâmetros pelo nome do `--model`, e com `--model JSON` nada é carregado: o copter sobe com
  `Frame: UNSUPPORTED` e não arma. Se rodar o `sim_vehicle.py` à mão, inclua
  `--add-param-file=$HOME/ardupilot/Tools/autotest/default_params/copter.parm --add-param-file=$HOME/ardupilot/Tools/autotest/default_params/gazebo-iris.parm`.
- O `uav-api` 0.3+ trata `--simulated` como flag sem valor; para SITL externo o script
  não passa a flag e usa `--uav_connection <ip>:14550 --connection_type udpin`. O painel
  tenta de novo a cada 5 s até o SITL responder.
- `/command/land` da uav_api bloqueia até pousar **e** desarmar; no Gazebo o desarme pode passar
  do limite de 30 s da API e a chamada volta HTTP 500 com o drone já no chão. O exemplo confere
  a altura por `/telemetry/ned` em vez de confiar no código de resposta.
- `stop_simulation.sh` manda Ctrl-C aos painéis, mata o que sobrar (Gazebo, SITL, MAVProxy,
  uav-api, ponte ROS 2, camera_saver) e fecha a sessão tmux. Sai com 1 se algo sobreviveu.
- `reset_drone.sh` reinicia só o SITL e a uav-api, nos mesmos painéis (o `start_simulation.sh`
  guarda os ids dos painéis, o mundo e o IP no ambiente da sessão tmux e expõe o comando do
  SITL como `--sitl MUNDO IP`). Os modelos usam o plugin do ArduPilot em `lock_step`: quando o
  SITL some, o plugin bloqueia a física do Gazebo esperando pacotes, o que parece "quebrar" a
  simulação. Com o mundo **pausado** ele não espera, então o script faz: para a uav-api →
  pausa → para o SITL → teleporta o drone para a pose do seu `<include>` no `.sdf` do mundo
  (serviço `/world/<mundo>/set_pose`) → despausa → sobe SITL e uav-api de novo. Não usa o
  "reset" do mundo de propósito: o gz-sim 8 não implementa o reset só dos modelos, e o reset
  completo zera o tempo de simulação, mas o plugin não zera o próprio relógio e ficaria parado
  até o tempo antigo passar. Ao reconectar, o Gazebo loga `ArduPilot controller has reset` (normal).
  Funciona também com o drone em voo (ele volta ao chão, parado, na origem).
- A configuração do tmux (mouse, clipboard via `xclip`) está em `tools/tmux.conf` → `~/.tmux.conf`.

### Fotos da câmera (`camera_saver.py`)

Assina o primeiro tópico `sensor_msgs/Image` publicado pela ponte ROS 2 e grava
`frame_00000.png`, `frame_00001.png`, ... uma vez por segundo em `$DRONE_PHOTOS_DIR`
(padrão `/home/ardupilot/workspace/photos`, ou seja, `workspace/photos/` no clone; a pasta está
no `.gitignore`). Resolução atual da câmera do gimbal: 1280x720.

- A numeração continua do último `frame_NNNNN.png` existente; apague a pasta para recomeçar.
- Opções: `camera_saver.py --dir PASTA --topic TOPICO --interval 0.5`.
- Rodar à mão: `camera_saver.py` (já está no PATH e usa o Python do sistema, onde ficam
  `rclpy`, `numpy` e `cv2`).

### Imagens da câmera via ROS 2 (para quem precisar do fluxo ao vivo)

A imagem tem ROS 2 Jazzy (`ros-base`, `ros_gz_bridge`, `ros_gz_image`, `cv_bridge`,
`rqt_image_view`). O ROS é carregado por `~/ros_env.sh` (já no `.bashrc`), **não** pelo
`setup.bash` diretamente: o `setup.bash` sozinho põe o `gz` do pacote vendor do ROS na frente
e esconde o `gz sim` do Gazebo do sistema ("sim is not a valid command"). Se isso acontecer num
shell, rode `source ~/ros_env.sh`. O painel da ponte espera o Gazebo publicar tópicos
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

Para assinar o tópico em Python, siga o `camera_saver.py`: ele converte `sensor_msgs/Image`
em numpy com `np.frombuffer(...).reshape(h, w, -1)` em vez do `cv_bridge`. O `cv_bridge` é
compilado contra o numpy 1.x do sistema e quebra com o numpy 2 do venv do ArduPilot (o `python3`
padrão dos shells); ele só funciona em `/usr/bin/python3`, que não tem `uav_api`.

### Mundos e modelos customizados

A pasta `tools/gazebo/` do repositório (`~/tools/gazebo` no container) entra **antes** da
`ardupilot_gazebo` no `GZ_SIM_RESOURCE_PATH`: um modelo com o mesmo nome aqui substitui o do upstream.

```
tools/gazebo/
├── models/<nome>/model.sdf + model.config   # ex.: basepadronizada, gabaritohexagono25
├── worlds/<nome>.sdf                        # ex.: missao1.sdf, bouncing.sdf
└── normalize.sh
```

Para atualizar a partir do Drive ("Arquivos do Gazebo"): baixe a pasta, extraia `models/` e
`worlds/` aqui e rode `./tools/gazebo/normalize.sh`. Ele apaga os `*Zone.Identifier` do Windows e
troca os caminhos absolutos da máquina de origem (`file:///home/grelhas/...`) por
`model://<nome>`. Com o clone montado pelo `run.sh` a mudança já vale no próximo
`start_simulation.sh`; reconstrua (`./run.sh --build`) para a imagem sozinha também ter os arquivos.

Regras para novos arquivos: referencie modelos sempre como `<uri>model://<nome></uri>`, nunca
com caminho absoluto, e cada modelo precisa de `model.config` com `<name>` igual à pasta.

### VS Code em detalhe

`code` é um wrapper em `/usr/local/bin` que passa `--no-sandbox` ao VS Code: o sandbox do
Chromium precisa criar namespaces, o que o perfil seccomp padrão do Docker bloqueia (sem a flag
ele aborta sem abrir janela). Configurações (`~/.config/Code`) e extensões (`~/.vscode`) ficam nos
volumes Docker `aerorio-sim-vscode-config` e `aerorio-sim-vscode-ext`, criados pelo `run.sh`.
Para zerar: `docker volume rm aerorio-sim-vscode-config aerorio-sim-vscode-ext`.

### Fixar versões

```bash
docker build --build-arg ARDUPILOT_REF=Copter-4.6 --build-arg ARDUPILOT_GAZEBO_REF=main -t aerorio/sim .
```

`run.sh --build` sempre usa `master`/`main`; para fixar, rode o `docker build` acima (com
`--build-arg HOST_UID=$(id -u) --build-arg HOST_GID=$(id -g)`) e depois `./run.sh`.
