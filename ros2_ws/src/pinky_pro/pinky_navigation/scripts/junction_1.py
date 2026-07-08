"""Pinky Pro 병동 배송 로봇의 Nav2 목적지 이동 및 도착 후 감시 노드.

- 101/102/103호로 이동한 뒤 30초간 카메라 프레임을 백엔드로 업로드
- '복귀' 상태로 실행되면 간호실 좌표로 이동하고, LCD에 배송 결과 표정 출력
"""
# pip install ultralytics cvbridge
import argparse
import math
import sys
import time

import cv2
import rclpy
import requests  # 백엔드 API 전송
from cv_bridge import CvBridge
from nav2_msgs.action import NavigateToPose
from PIL import Image, ImageDraw, ImageFont, ImageSequence
from pinky_lcd.pinky_lcd import LCD
from rclpy.action import ActionClient
from rclpy.node import Node
from sensor_msgs.msg import Image as RosImage

BACKEND_URL = "http://localhost:8000"

# 실제 로봇에서 amcl_pose로 받아온 방별 목적지 좌표 (정규화 확인 완료)
ROOMS = {
    # 101, 102, 103호는 도착 후 +y축 방향(맵 위쪽)을 바라보도록 설정
    101: {'x': 0.63,  'y': 1.585, 'qz': 0.7071,  'qw': 0.7071,  'name': '101호'},
    102: {'x': 1.333, 'y': 1.585, 'qz': 0.7071,  'qw': 0.7071,  'name': '102호'},
    103: {'x': 1.807, 'y': 1.585, 'qz': 0.7071,  'qw': 0.7071,  'name': '103호'},

    # 복귀(간호실) 시에는 -y축 방향(맵 아래쪽)을 바라보도록 설정
    '복귀': {'x': 0.0, 'y': 0.0, 'qz': -0.7071, 'qw': 0.7071, 'name': '간호실'},
}

ARRIVAL_THRESHOLD = 0.2  # m

_LCD_WIDTH, _LCD_HEIGHT = 800, 480  # Pinky Pro 표준 해상도
_SUCCESS_STYLE = {
    "background": (255, 192, 203),
    "text": (255, 255, 255),
    "message": "배송 성공!",
    "gif": "/home/user/images/happy_face.gif",
}
_FAILURE_STYLE = {
    "background": (70, 130, 180),
    "text": (255, 255, 255),
    "message": "배송 실패!",
    "gif": "/home/user/images/sad_face.gif",
}


def _render_status_text(status_text, background, text_color):
    """상태 안내 문구를 가운데 정렬해 그린 PIL 이미지를 반환한다."""
    text_img = Image.new('RGB', (_LCD_WIDTH, _LCD_HEIGHT), color=background)
    draw = ImageDraw.Draw(text_img)
    try:
        font = ImageFont.truetype("NanumGothic.ttf", 50)
    except OSError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), status_text, font=font)
    x = (_LCD_WIDTH - (bbox[2] - bbox[0])) // 2
    y = (_LCD_HEIGHT - (bbox[3] - bbox[1])) // 2
    draw.text((x, y), status_text, fill=text_color, font=font)
    return text_img


class NavGoalNode(Node):  # pylint: disable=too-many-instance-attributes
    """Nav2로 목적지에 이동한 뒤 도착 처리와 후속 미션을 수행하는 ROS2 노드."""

    def __init__(self, room_number, delivery_id=None):
        super().__init__('nav_goal_and_check_node')
        self.delivery_id = delivery_id
        room = ROOMS[room_number]
        self.goal_x = room['x']
        self.goal_y = room['y']
        self.goal_qz = room['qz']
        self.goal_qw = room['qw']
        self.room_name = room['name']
        self.room_key = room_number

        self._action_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self._goal_handle = None
        self._arrived = False

        self.bridge = CvBridge()
        self.camera_sub = None
        self.yolo_start_time = None
        self.yolo_duration = 30.0  # yolo를 켜는 시간
        self.last_send_time = 0.0

        if room_number == '복귀' and self.delivery_id:
            self.show_emotion_face()

    def show_emotion_face(self):
        """백엔드에서 최종 배송 상태를 받아 LCD에 안내 문구와 표정 GIF를 재생한다."""
        try:
            res = requests.get(f"{BACKEND_URL}/deliveries/{self.delivery_id}").json()
            final_status = res.get("status")

            if final_status == "SUCCESS":
                self.get_logger().info("배송 성공")
                style = _SUCCESS_STYLE
            else:
                self.get_logger().info("배송 실패")
                style = _FAILURE_STYLE

            lcd = LCD()
            text_img = _render_status_text(style["message"], style["background"], style["text"])
            lcd.img_show(text_img)
            time.sleep(3.0)  # 3초간 대기하며 안내 문구 유지

            # 이어서 표정 GIF 재생
            gif = Image.open(style["gif"])
            for frame in ImageSequence.Iterator(gif):
                lcd.img_show(frame)
                time.sleep(0.1)
            lcd.clear()
            self.get_logger().info("간호실로 복귀합니다.")
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.get_logger().error(f"백엔드 전송 오류: {e}")

    def send_goal(self):
        """Nav2 액션 서버로 현재 room의 목적지 좌표를 전송한다."""
        self.get_logger().info(f'[{self.room_name}] Nav2 액션 서버를 기다리는 중...')
        self._action_client.wait_for_server()

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose.header.stamp = self.get_clock().now().to_msg()
        goal_msg.pose.header.frame_id = 'map'
        goal_msg.pose.pose.position.x = self.goal_x
        goal_msg.pose.pose.position.y = self.goal_y
        goal_msg.pose.pose.orientation.z = self.goal_qz
        goal_msg.pose.pose.orientation.w = self.goal_qw

        self.get_logger().info(
            f'{self.room_name} (x: {self.goal_x}, y: {self.goal_y})로 목적지를 전송했습니다. 로봇이 이동합니다...')
        send_goal_future = self._action_client.send_goal_async(
            goal_msg, feedback_callback=self.feedback_callback)
        send_goal_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        """Nav2가 goal을 수락했는지 확인하고 결과 대기 콜백을 건다."""
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error('목적지가 Nav2에 의해 거부되었습니다.')
            rclpy.shutdown()
            return

        self._goal_handle = goal_handle
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.get_result_callback)

    def feedback_callback(self, feedback_msg):
        """이동 중 실시간 거리 계산 → 임계값 이내면 도착 처리 후 YOLO 감시 시작."""
        if self._arrived:
            return

        current_pose = feedback_msg.feedback.current_pose.pose
        distance = math.hypot(self.goal_x - current_pose.position.x,
                              self.goal_y - current_pose.position.y)

        if distance <= ARRIVAL_THRESHOLD:
            self._arrived = True
            self.get_logger().info('======================================')
            self.get_logger().info(f'로봇이 {self.room_name}에 무사히 도착했습니다!')
            self.get_logger().info('======================================')

            if self._goal_handle is not None:
                self._goal_handle.cancel_goal_async()

            # 로봇 도착 시 백엔드 상태 전이 (ARRIVED) - 방 이동일 때만 전송
            if self.delivery_id and self.room_key != '복귀':
                try:
                    requests.patch(
                        f"{BACKEND_URL}/deliveries/{self.delivery_id}/robot-status",
                        json={"status": "ARRIVED"},
                    )
                except Exception as e:  # pylint: disable=broad-exception-caught
                    self.get_logger().error(f"백엔드 통신 실패 (ARRIVED): {e}")

            if self.room_key in [101, 102, 103]:
                self.get_logger().info(f'{self.yolo_duration}초간 실시간 객체 탐지를 시작합니다.')
                self.yolo_start_time = time.time()

                self.camera_sub = self.create_subscription(
                    RosImage,
                    '/image_raw',
                    self.camera_callback,
                    10,
                )

    def camera_callback(self, msg):
        """카메라 프레임을 초당 1장씩 JPEG로 인코딩해 백엔드에 업로드한다."""
        current_time = time.time()

        # 30초 경과 시 카메라 구독 해제 및 종료
        if current_time - self.yolo_start_time > self.yolo_duration:
            self.get_logger().info('[타임아웃] 30초 제한 시간이 종료되었습니다. 전송을 멈춥니다.')
            self.destroy_subscription(self.camera_sub)
            cv2.destroyAllWindows()
            rclpy.shutdown()  # 프로세스 완전 종료하여 자원 반환
            return

        # 초당 1프레임 체크 및 백엔드로 이미지 파일 업로드
        if current_time - self.last_send_time >= 1.0:
            self.last_send_time = current_time
            try:
                cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

                # 이미지 바이너리 인코딩
                _, img_encoded = cv2.imencode('.jpg', cv_image)
                img_bytes = img_encoded.tobytes()

                if self.delivery_id:
                    files = {'image': ('frame.jpg', img_bytes, 'image/jpeg')}
                    upload_url = f"{BACKEND_URL}/deliveries/{self.delivery_id}/image"
                    response = requests.post(upload_url, files=files)
                    self.get_logger().info(f"서버 업로드 성공 (Status: {response.status_code})")

            except Exception as e:  # pylint: disable=broad-exception-caught
                self.get_logger().error(f'이미지 처리 및 전송 중 오류: {e}')

    def get_result_callback(self, _future):
        """Nav2 액션이 종료됐을 때 정리 작업을 수행한다."""
        del _future
        self.get_logger().info('네비게이션 종료.')
        cv2.destroyAllWindows()
        rclpy.shutdown()


def main():
    """CLI 인자를 파싱해 NavGoalNode를 실행한다."""
    parser = argparse.ArgumentParser(description='목적지 입력 및 도착 확인 프로그램')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--room-number', type=int, choices=[101, 102, 103],
                       help='방 번호를 입력하세요')
    group.add_argument('--state', type=str, choices=['복귀'],
                       help='로봇 복귀를 원할 시 "복귀"를 입력해주세요')
    parser.add_argument('--delivery-id', type=str, default=None,
                        help='백엔드 배송 ID')
    args, _ = parser.parse_known_args(sys.argv[1:])

    rclpy.init()
    target_key = '복귀' if args.state == '복귀' else args.room_number
    node = NavGoalNode(target_key, delivery_id=args.delivery_id)
    node.send_goal()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()


if __name__ == '__main__':
    main()
