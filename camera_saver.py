#!/usr/bin/python3
"""Salva fotos da câmera do drone (via ponte ROS 2) numa pasta acessível aos scripts da missão.

Adaptado do script original da equipe (que gravava em /mnt/c/Users/AeroRio/Desktop/dataset_drone):
  - pasta de saída vem de --dir ou da variável DRONE_PHOTOS_DIR
    (padrão /home/ardupilot/aerorio/photos, que é a pasta aerorio/photos do host montada pelo run.sh);
  - tópico vem de --topic; sem ele, espera e usa o primeiro tópico sensor_msgs/Image que aparecer,
    então funciona em qualquer mundo sem editar o script;
  - a numeração continua a partir do último frame_NNNNN.png existente, para não sobrescrever;
  - trata rgb8, bgr8, rgba8, bgra8 e mono8.

Roda com o Python do sistema (/usr/bin/python3), onde ficam rclpy, numpy e cv2 do ROS/apt.
Uso: camera_saver.py [--dir PASTA] [--topic TOPICO] [--interval SEGUNDOS]
"""
import argparse
import os
import re
import sys
import time

try:
    import rclpy
except ModuleNotFoundError:
    # Shell sem o ROS carregado (ex.: docker exec): reexecuta após "source setup.bash".
    if os.environ.get("CAMERA_SAVER_REEXEC"):
        sys.exit("rclpy não encontrado mesmo após carregar o ROS; verifique /opt/ros/" + os.environ.get("ROS_DISTRO", "jazzy"))
    os.environ["CAMERA_SAVER_REEXEC"] = "1"
    setup = os.path.expanduser("~/ros_env.sh")
    if not os.path.exists(setup):
        setup = f"/opt/ros/{os.environ.get('ROS_DISTRO', 'jazzy')}/setup.bash"
    os.execvp("bash", ["bash", "-c", f'source "{setup}" && exec /usr/bin/python3 "$0" "$@"', os.path.realpath(__file__), *sys.argv[1:]])

import cv2
import numpy as np
from rclpy.node import Node
from sensor_msgs.msg import Image

DEFAULT_DIR = os.environ.get("DRONE_PHOTOS_DIR", os.path.expanduser("~/aerorio/photos"))
IMAGE_TYPE = "sensor_msgs/msg/Image"
FRAME_RE = re.compile(r"^frame_(\d{5})\.png$")


class CameraSaver(Node):
    def __init__(self, save_dir: str, topic: str, interval: float):
        super().__init__("camera_saver")
        self.save_dir = save_dir
        self.interval = interval
        self.last_save_time = 0.0

        os.makedirs(self.save_dir, exist_ok=True)
        existing = [int(m.group(1)) for f in os.listdir(self.save_dir) if (m := FRAME_RE.match(f))]
        self.counter = max(existing, default=-1) + 1

        self.get_logger().info(f"salvando em {self.save_dir} a cada {interval:g}s (próximo: frame_{self.counter:05d}.png)")
        self.get_logger().info(f"tópico: {topic}")
        self.create_subscription(Image, topic, self.listener_callback, 10)

    def listener_callback(self, msg: Image):
        now = time.time()
        if now - self.last_save_time < self.interval:
            return

        buf = np.frombuffer(msg.data, dtype=np.uint8)
        enc = msg.encoding
        if enc == "mono8":
            img = buf.reshape(msg.height, msg.width)
        else:
            img = buf.reshape(msg.height, msg.width, -1)
            if enc == "rgb8":
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            elif enc == "rgba8":
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
            elif enc == "bgra8":
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            elif enc != "bgr8":
                self.get_logger().warning(f"encoding {enc} não tratado; gravando bytes como estão")

        filename = os.path.join(self.save_dir, f"frame_{self.counter:05d}.png")
        cv2.imwrite(filename, img)
        self.get_logger().info(f"salvo {filename}")
        self.counter += 1
        self.last_save_time = now


def wait_for_image_topic(node: Node, poll: float = 2.0) -> str:
    """Bloqueia até existir um tópico sensor_msgs/Image (publicado pela ponte ros_gz) e o devolve."""
    node.get_logger().info("aguardando um tópico sensor_msgs/Image (a ponte ROS 2 precisa estar rodando)...")
    while rclpy.ok():
        for name, types in node.get_topic_names_and_types():
            if IMAGE_TYPE in types:
                return name
        time.sleep(poll)
    raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default=DEFAULT_DIR, help=f"pasta de saída (padrão: {DEFAULT_DIR})")
    ap.add_argument("--topic", default=None, help="tópico da imagem (padrão: primeiro sensor_msgs/Image encontrado)")
    ap.add_argument("--interval", type=float, default=1.0, help="segundos entre fotos (padrão: 1.0)")
    args = ap.parse_args()

    rclpy.init()
    topic = args.topic
    if topic is None:
        probe = Node("camera_saver_probe")
        topic = wait_for_image_topic(probe)
        probe.destroy_node()

    node = CameraSaver(args.dir, topic, args.interval)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
