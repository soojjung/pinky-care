"""Pinky Pro 병동 배송 로봇의 Nav2 목적지 이동 및 도착 후 감시 노드.

- 102/103/104호로 이동한 뒤 30초간 카메라 프레임을 백엔드로 업로드
- 업로드가 끝나면 배송 상태를 폴링해 SUCCESS/FAILED 확정 시 표정 표시 후
  간호실(101호)로 자율 복귀 (백엔드가 subprocess를 띄우던 v1 방식은 삭제됨)
- '복귀' 상태로 실행되면 간호실 좌표로 이동하고, 배송 결과 표정 출력
  (수동 호출용 백엔드 없이도 사용 가능한 진입점)

표정 표시는 LCD 를 직접 제어하지 않고 로봇의 emotion_server(set_emotion 서비스)에
요청만 보낸다. (nav_goal_and_check_node.py 와 동일 방식 — GPIO 충돌 방지)
"""
# pip install requests cvbridge
import argparse
import math
import os
import sys
import time

import cv2
import rclpy
import requests  # 백엔드 API 전송
from cv_bridge import CvBridge
from nav2_msgs.action import NavigateToPose
from pinky_interfaces.srv import Emotion  # 로봇 emotion_server 서비스
from rclpy.action import ActionClient
from rclpy.node import Node
from sensor_msgs.msg import Image as RosImage

# 배포 시 시연자 노트북 IP로 환경변수 지정:
#   BACKEND_URL=http://192.168.x.x:8000 python3 junction_1.py ...
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

# 배송 결과 폴링 파라미터
POLL_INTERVAL_SEC = 1.0     # 상태 조회 주기 (백엔드 부담 무시할 수준)
MAX_POLL_SEC = 600          # 안전장치: 10분 넘게 terminal이 안 오면 강제 실패 처리

# 실제 로봇 SLAM 맵에서 amcl_pose로 검증한 방별 목적지 좌표.
# (nav_goal_and_check_node.py 와 동일 좌표계 — 로봇팀 실측값)
ROOMS = {
    # 배송 병실 102/103/104호
    102: {'x': 0.63,  'y': 1.585, 'qz': 0.6992, 'qw': 0.7149, 'name': '102호'},
    103: {'x': 1.333, 'y': 1.585, 'qz': 0.7089, 'qw': 0.7053, 'name': '103호'},
    104: {'x': 1.807, 'y': 1.585, 'qz': 0.7055, 'qw': 0.7087, 'name': '104호'},

    # 복귀 지점 = 101호(간호실). 실측 좌표·자세 사용.
    '복귀': {'x': 0.03, 'y': 1.3, 'qz': 0.7915, 'qw': 0.6111, 'name': '간호실'},
}

ARRIVAL_THRESHOLD = 0.2  # m

_EMOTION_DISPLAY_SEC = 3.0  # 복귀 전 표정을 보여줄 시간

# 배송 결과 → emotion_server 가 아는 gif 이름
_EMOTION_MAP = {
    'NORMAL': 'basic',
    'SUCCESS': 'happy',
    'FAILURE': 'sad',
}


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

        # 결과 폴링 상태 (30초 창 종료 후 세팅됨)
        self._poll_timer = None
        self._poll_started_at = None

        # LCD 직접 제어 대신 emotion_server 에 서비스로 표정 요청 (GPIO 충돌 방지)
        self.emotion_client = self.create_client(Emotion, 'set_emotion')
        if not self.emotion_client.wait_for_service(timeout_sec=3.0):
            self.get_logger().warn(
                'emotion_server 의 set_emotion 서비스가 아직 안 떠 있습니다. '
                '(emotion_server 를 먼저 실행했는지 확인)'
            )

        if room_number == '복귀' and self.delivery_id:
            self.show_emotion_face()

    def show_emotion_face(self):
        """(수동 호출용) 백엔드에서 최종 상태를 받아 표정을 표시한다.

        v2에선 배송 종료 후 로봇이 폴링으로 스스로 결정하므로 이 함수는
        ``--state 복귀`` 진입점에서만 쓰인다.
        """
        try:
            res = requests.get(f"{BACKEND_URL}/deliveries/{self.delivery_id}").json()
            final_status = res.get("status")
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.get_logger().error(f"백엔드 상태 조회 실패: {e}")
            return

        flag = "SUCCESS" if final_status == "SUCCESS" else "FAILURE"
        self.get_logger().info(f"상태={final_status} → 표정 {flag}")
        self.set_emotion(flag)

    def set_emotion(self, flag):
        """emotion_server 에 표정 요청을 보낸다. flag: 'NORMAL'|'SUCCESS'|'FAILURE'.

        서비스 응답을 기다리지 않고 요청만 비동기로 보낸다(emotion_server 가
        LCD 표시를 전담). 서비스가 안 떠 있으면 로그만 남기고 넘어간다.
        """
        emotion_name = _EMOTION_MAP.get(flag, 'basic')
        if not self.emotion_client.service_is_ready():
            self.get_logger().warn('emotion_server 미준비 — 표정 요청 건너뜀')
            return
        req = Emotion.Request()
        req.emotion = emotion_name
        self.emotion_client.call_async(req)
        self.get_logger().info(f"emotion_server 표정 요청: {emotion_name}")

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

            if self.room_key in [102, 103, 104]:
                self.get_logger().info(f'{self.yolo_duration}초간 실시간 객체 탐지를 시작합니다.')
                self.yolo_start_time = time.time()

                self.camera_sub = self.create_subscription(
                    RosImage,
                    '/camera/image_raw',   # 로봇 실제 카메라 토픽 (camera.py 와 동일)
                    self.camera_callback,
                    10,
                )

    def camera_callback(self, msg):
        """카메라 프레임을 초당 1장씩 JPEG로 인코딩해 백엔드에 업로드한다.

        30초 창이 끝나면 프로세스를 죽이지 않고 결과 폴링으로 넘어간다.
        """
        current_time = time.time()

        # 30초 경과 시 카메라 구독 해제 후 폴링 진입
        if current_time - self.yolo_start_time > self.yolo_duration:
            self.get_logger().info('[30초 창 종료] 카메라 업로드 중단, 배송 결과 폴링 시작.')
            self._end_camera_window()
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

    def _end_camera_window(self):
        """30초 창 종료 처리 — 카메라 정리 후 백엔드 상태 폴링 진입."""
        if self.camera_sub is not None:
            self.destroy_subscription(self.camera_sub)
            self.camera_sub = None
        cv2.destroyAllWindows()

        if self.delivery_id is None:
            # 배송 id 없으면 어차피 폴링해도 알 수 없으니 그냥 종료
            self.get_logger().warn("delivery_id 없음 — 폴링 없이 종료")
            rclpy.shutdown()
            return

        self._poll_started_at = time.time()
        self._poll_timer = self.create_timer(POLL_INTERVAL_SEC, self._poll_tick)
        self.get_logger().info(
            f"[폴링] {POLL_INTERVAL_SEC:.0f}초 간격으로 배송 상태 확인 (최대 {MAX_POLL_SEC}s)"
        )

    def _poll_tick(self):
        """1초마다 배송 상태를 확인해 후속 조치를 결정한다.

        - SUCCESS/FAILED → 폴링 취소 + LCD 표정 + 간호실 복귀 Nav2 goal
        - AWAITING_NURSE → 간호사 결정 대기, 계속 폴링
        - VERIFYING/기타 non-terminal → 그대로 폴링 지속
        - 통신 실패 → 로그만 남기고 다음 tick에서 재시도
        - MAX_POLL_SEC 초과 → 실패 처리 후 강제 복귀 (배터리 · 안전 이유)
        """
        try:
            res = requests.get(
                f"{BACKEND_URL}/deliveries/{self.delivery_id}", timeout=3
            ).json()
            status = res.get("status")
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.get_logger().warn(f"상태 조회 실패, 재시도: {e}")
            return

        elapsed = time.time() - self._poll_started_at
        self.get_logger().info(f"[폴링] status={status} · elapsed={elapsed:.0f}s")

        if status == "SUCCESS":
            self._finish_polling_and_return("SUCCESS")
            return
        if status == "FAILED":
            self._finish_polling_and_return("FAILURE")
            return

        # AWAITING_NURSE, VERIFYING 등은 계속 대기하되 안전장치 확인
        if elapsed > MAX_POLL_SEC:
            self.get_logger().error(
                f"폴링 상한({MAX_POLL_SEC}s) 초과 — 실패 처리로 강제 복귀"
            )
            self._finish_polling_and_return("FAILURE")

    def _finish_polling_and_return(self, flag):
        """폴링 종료 → 표정 표시 → 간호실 복귀. flag: 'SUCCESS'|'FAILURE'."""
        if self._poll_timer is not None:
            self._poll_timer.cancel()
            self._poll_timer = None

        self.set_emotion(flag)
        time.sleep(_EMOTION_DISPLAY_SEC)  # 표정 보여줄 시간
        self._send_return_goal()

    def _send_return_goal(self):
        """간호실(101호) 좌표로 Nav2 goal 을 새로 전송한다."""
        return_coords = ROOMS['복귀']
        self.goal_x = return_coords['x']
        self.goal_y = return_coords['y']
        self.goal_qz = return_coords['qz']
        self.goal_qw = return_coords['qw']
        self.room_name = return_coords['name']
        self.room_key = '복귀'
        self._arrived = False       # feedback_callback 재사용을 위해 리셋
        self._goal_handle = None
        self.send_goal()

    def get_result_callback(self, _future):
        """Nav2 액션이 종료됐을 때 정리 작업을 수행한다.

        방 도착일 때는 카메라 감시가 이어지므로 shutdown 하지 않고,
        복귀 도착일 때만 프로세스를 종료한다.
        """
        del _future
        self.get_logger().info('네비게이션 종료.')
        cv2.destroyAllWindows()
        if self.room_key == '복귀':
            rclpy.shutdown()


def main():
    """CLI 인자를 파싱해 NavGoalNode를 실행한다."""
    parser = argparse.ArgumentParser(description='목적지 입력 및 도착 확인 프로그램')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--room-number', type=int, choices=[102, 103, 104],
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
