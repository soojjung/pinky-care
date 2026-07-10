"""라즈베리파이 CSI 카메라(pinkylib.Camera) → ROS2 /camera/image_raw 발행 노드.

핑키 로봇에는 카메라를 ROS 토픽으로 내보내는 노드가 없다. bringup 은 라이다·
모터·배터리만 띄우고, pinkylib.Camera 는 순수 드라이버(Picamera2)라 ROS 발행을
안 한다. 그래서 junction_1.py 가 구독하는 `/camera/image_raw` 가 항상 비어 있었다.

이 노드가 그 빈자리를 채운다: pinkylib.Camera 로 프레임을 읽어 sensor_msgs/Image
(bgr8) 로 초당 여러 장 발행한다. junction_1.py 는 이 토픽을 받아 백엔드로 업로드하고,
백엔드가 YOLO 로 성공/실패를 판정한다.

cv_bridge 는 쓰지 않는다. 로봇의 cv_bridge C++ 확장(boost)이 깨져 있어
(libmysqlclient.so.21 invalid ELF header) cv2_to_imgmsg 가 ImportError 로 터진다.
대신 numpy 프레임을 sensor_msgs/Image 로 직접 구성한다 — 의존성도 더 가볍다.

로봇에서 상시 실행 (bringup 과 별도 터미널):

    python3 camera_publisher.py

주의: 카메라는 한 프로세스만 점유할 수 있다. Jupyter 노트북 등에서 Camera 를
잡고 있으면 "카메라가 사용 중" 에러가 난다 — 그 커널을 먼저 종료할 것.
"""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image as RosImage

from pinkylib import Camera

# junction_1.py 가 구독하는 토픽과 반드시 동일해야 한다.
TOPIC = "/camera/image_raw"
WIDTH, HEIGHT = 640, 480
PUBLISH_HZ = 15.0  # 백엔드는 초당 1장만 쓰지만, 미리보기·지연을 위해 넉넉히 발행


class CameraPublisher(Node):
    """pinkylib.Camera 프레임을 /camera/image_raw 로 흘려보내는 노드."""

    def __init__(self):
        super().__init__("camera_publisher")
        self.publisher = self.create_publisher(RosImage, TOPIC, 10)

        self.get_logger().info("카메라 초기화 중...")
        self.camera = Camera()
        self.camera.start(width=WIDTH, height=HEIGHT)
        self.get_logger().info(
            f"카메라 시작됨 ({WIDTH}x{HEIGHT}) → {TOPIC} 로 {PUBLISH_HZ:.0f}Hz 발행"
        )

        self.timer = self.create_timer(1.0 / PUBLISH_HZ, self._tick)

    def _tick(self):
        try:
            frame = self.camera.get_frame()  # BGR, 180° 회전 완료된 numpy 프레임 (HxWx3, uint8)
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.get_logger().error(f"프레임 획득 실패: {e}")
            return

        # cv_bridge 없이 sensor_msgs/Image 직접 구성 (bgr8)
        msg = RosImage()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "camera"
        msg.height = int(frame.shape[0])
        msg.width = int(frame.shape[1])
        msg.encoding = "bgr8"
        msg.is_bigendian = 0
        msg.step = int(frame.shape[1]) * 3  # 한 행의 바이트 수 (width * 3채널)
        msg.data = frame.tobytes()
        self.publisher.publish(msg)


def main():
    rclpy.init()
    node = CameraPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
