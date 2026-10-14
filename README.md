# simulation

Imagem Docker de desenvolvimento com **ArduPilot SITL**, **Gazebo Harmonic**, o plugin
**ardupilot_gazebo** e o **uav_api**. Funciona com GPU NVIDIA (se o host tiver o NVIDIA
Container Toolkit) ou com renderização por software (Mesa/llvmpipe).

> `aerostation` será adicionado à imagem quando o pacote estiver no PyPI. Até lá, rode-o no
> host; o container usa `--network host`, então `uav-api` em `:8000` e o SITL ficam acessíveis.

## Build e execução

```bash
cd simulation
./run.sh --build     # primeira vez (demora: baixa Gazebo, ArduPilot e compila o SITL)
./run.sh             # abre um shell; chamar de novo em outro terminal entra no mesmo container
```

`run.sh` adiciona `--gpus all` automaticamente quando `nvidia-smi` funciona **e** o Docker
tem o runtime `nvidia`. Caso contrário avisa e roda em Mesa. `./run.sh --cpu` força o modo
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

## Fluxo de simulação (três terminais, todos via `./run.sh`)

```bash
# Terminal 1: Gazebo com o mundo do Iris
gz sim -v4 -r iris_runway.sdf

# Terminal 2: SITL do ArduCopter ligado ao Gazebo
sim_vehicle.py -v ArduCopter -f gazebo-iris --model JSON --map --console

# Terminal 3: uav_api apontando para o SITL
uav-api --port 8000 --sysid 1
```

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

Antes de sair, pare o que estiver rodando dentro (Gazebo, `sim_vehicle.py`, `uav-api`) com
`Ctrl+C`, ou use `docker stop`, que envia SIGTERM a tudo e remove o container.
Arquivos salvos fora de `/home/ardupilot/aerorio` (a pasta montada do host) são perdidos ao
fechar; o que estiver nessa pasta permanece no host.

## Fixar versões

```bash
docker build --build-arg ARDUPILOT_REF=Copter-4.6 --build-arg ARDUPILOT_GAZEBO_REF=main -t aerorio/sim .
```
