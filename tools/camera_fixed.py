import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
import threading
from nav2_msgs.action import NavigateToPose
from sensor_msgs.msg import Image as RosImage
from pinky_interfaces.srv import Emotion
from cv_bridge import CvBridge
import cv2
import numpy as np 
import argparse
import sys
import math
import time
from action_msgs.msg import GoalStatus

# 웹 스트리밍하기
from flask import Flask, Response

ROOMS = {
    101: {'x': 0.03, 'y': 1.3, 'qz': 0.7915, 'qw': 0.6111, 'name': '간호실'},
    102: {'x': 0.63,  'y': 1.585, 'qz':  0.6992, 'qw': 0.7149, 'name': '102호'},
    103: {'x': 1.333, 'y': 1.585, 'qz':  0.7089, 'qw': 0.7053, 'name': '103호'},
    104: {'x': 1.807, 'y': 1.585, 'qz':  0.7055, 'qw': 0.7087, 'name': '104호'}}

ARRIVAL_THRESHOLD = 0.2  # m
CAMERA_CHECK_DURATION = 5.0  # 도착 후 PC에 카메라 미리보기를 띄워둘 시간(초)

# 우리 상태(NORMAL/SUCCESS/FAILURE) -> emotion_server가 아는 gif 이름
EMOTION_MAP = {
      'NORMAL': 'basic',
      'SUCCESS': 'happy',
      'FAILURE': 'sad',
  }


class NavGoalNode(Node):
    def __init__(self, room_number):
        super().__init__('nav_goal_and_check_node')
        room = ROOMS[room_number]
        self.goal_x = room['x']
        self.goal_y = room['y']
        self.goal_qz = room['qz']
        self.goal_qw = room['qw']
        self.room_name = room['name']

        self._action_client = ActionClient(self, NavigateToPose,'navigate_to_pose')
        self._goal_handle = None
        self._arrived = False

        self.bridge = CvBridge()
        self.yolo_start_time = None
        self.yolo_duration = 30.0

        # 카메라 미리보기용 최신 프레임 저장소 (PC 화면에 cv2.imshow로 띄우는 용도)
        self.latest_frame = None
        self.frame_lock = threading.Lock()

        # LCD 직접 제어 대신 emotion_server에 서비스로 요청만 보냄 (GPIO 충돌 방지)
        self.emotion_client = self.create_client(Emotion, 'set_emotion')
        if not self.emotion_client.wait_for_service(timeout_sec=3.0):
            self.get_logger().warn('emotion_server의 set_emotion 서비스가 아직 안 떠 있습니다. (emotion_server 먼저 실행했는지 확인)')

        self.current_emotion = 'NORMAL'
        self.set_emotion('NORMAL')  # 시작하자마자 basic 애니메이션으로 초기화

        # 카메라 구독
        self.camera_sub = self.create_subscription(
            RosImage, '/camera/image_raw', self.camera_callback, 10)

        self.is_returning = False
        self.is_checking_done = False

        # Flask 서버
        self.app = Flask(__name__)
        self.setup_flask_routes()
        # 외부(SSH 접속 대상 PC 등)에서 접속할 수 있도록 0.0.0.0 포트 5000으로 오픈
        self.flask_thread = threading.Thread(
            target=lambda: self.app.run(host='0.0.0.0', port=5000, threaded=True, use_reloader=False),
            daemon=True
        )
        self.flask_thread.start()
        self.get_logger().info("Flask 웹 스트리밍 서버가 포트 5000에서 시작되었습니다.")

    def setup_flask_routes(self):
        """Flask 라우팅 경로 정의"""
        @self.app.route('/video_feed')
        def video_feed():
            # 웹 브라우저에 MJPEG 스트림 형태로 리턴
            return Response(self.generate_frames(),
                            mimetype='multipart/x-mixed-replace; boundary=frame')

    def generate_frames(self):
        """최신 프레임을 인코딩하여 지속적으로 전송하는 제너레이터"""
        while rclpy.ok():
            # 목적지에 도착해서 검증 시작하기 전(yolo_start_time이 None일 때)에는
            # 웹 브라우저에 대기 화면(텍스트 이미지 등)을 보여줍니다.
            if self.yolo_start_time is None:
                # 검은색 배경에 "이동 중..." 안내 문구가 적힌 임시 이미지를 생성
                blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(blank_frame, "Moving to destination... Waiting for Arrival", 
                            (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                ret, buffer = cv2.imencode('.jpg', blank_frame)
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                time.sleep(0.1)
                continue

            # 목적지에 도착하여 검증이 시작되면(yolo_start_time이 활성화되면) 
            # 그때부터 실제 로봇의 시야를 실시간으로 송출합니다!
            with self.frame_lock:
                if self.latest_frame is None:
                    time.sleep(0.03)
                    continue
                frame = self.latest_frame.copy()

            # OpenCV 프레임을 JPEG 포맷으로 인코딩
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                continue
                
            frame_bytes = buffer.tobytes()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            time.sleep(0.03)


    def set_target_room(self, room_number):
        room = ROOMS[room_number]
        self.goal_x = room['x']
        self.goal_y = room['y']
        self.goal_qz = room['qz']
        self.goal_qw = room['qw']
        self.room_name = room['name']
        self._arrived = False
        self.is_checking_done = False

    def send_goal(self):
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
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error('목적지에 도달할 수 없습니다.')
            rclpy.shutdown()
            return

        self._goal_handle = goal_handle
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.get_result_callback)

    def feedback_callback(self, feedback_msg):
        if self._arrived:
            return

        current_pose = feedback_msg.feedback.current_pose.pose
        distance = math.hypot(self.goal_x - current_pose.position.x,
                               self.goal_y - current_pose.position.y)

        if distance <= ARRIVAL_THRESHOLD:
            self._arrived = True

            if self.is_returning:
                self.get_logger().info('====================================')
                self.get_logger().info('간호실에 최종 복귀 완료했습니다. 프로그램을 종료합니다.')
                self.get_logger().info('====================================')
                if self._goal_handle is not None:
                    self._goal_handle.cancel_goal_async()
                rclpy.shutdown()
                return

            self.get_logger().info('====================================')
            self.get_logger().info(f'로봇이 배달지({self.room_name})에 도착했습니다. 카메라 확인을 시작합니다.')
            self.get_logger().info('====================================')

            if self._goal_handle is not None:
                self._goal_handle.cancel_goal_async()

            self._start_arrival_camera_check()

    # ---- emotion_server 연동 ----
    def set_emotion(self, flag):
        """flag: 'NORMAL' | 'SUCCESS' | 'FAILURE' -> emotion_server에 서비스 콜"""
        self.current_emotion = flag
        emotion_name = EMOTION_MAP.get(flag, 'basic')

        if not self.emotion_client.service_is_ready():
            self.get_logger().warn('emotion_server 서비스가 준비되지 않아 요청을 건너뜁니다.')
            return

        req = Emotion.Request()
        req.emotion = emotion_name
        future = self.emotion_client.call_async(req)
        future.add_done_callback(self._emotion_response_callback)

        # SUCCESS/FAILURE는 화면 보여줄 시간(3초) 준 뒤 다음 동작으로 전환
        if flag in ('SUCCESS', 'FAILURE'):
            threading.Thread(target=self._after_emotion_delay, args=(flag,),daemon=True).start()

    def _emotion_response_callback(self, future):
        try:
            res = future.result()
            self.get_logger().info(f'emotion_server 응답: {res.response}')
        except Exception as e:
            self.get_logger().error(f'emotion_server 호출 실패: {e}')

    def _after_emotion_delay(self, flag):
        time.sleep(3.0)
        if flag == 'FAILURE':
            self._handle_failure_input()
        else:
            self._handle_success_return()

    # 기존 이름 유지하고 싶으면 이렇게 별칭으로 둬도 됨
    def show_emotion_and_feedback(self, flag):
        self.set_emotion(flag)

    def _handle_success_return(self):
        self.get_logger().info('성공 확인: 간호실로 복귀 동작을 수행합니다.')
        self.is_returning = True
        self.set_target_room(101)
        self.send_goal()

    def _handle_failure_input(self):
        pending = input("배달 오류가 생겼습니다! '복귀' 혹은 '대기'를 선택해주세요: ").strip()
        if pending in ['복귀', '대기']:
            if pending == '대기':
                print("5분간 대기를 시작합니다...")
                time.sleep(10)  # 테스트용, 실제는 300
            print("간호실로 복귀합니다.")
            self.is_returning = True
            self.set_target_room(101)
            self.send_goal()

    # ---- 카메라 확인 (도착 시 PC 화면에 5초 미리보기) ----
    def _start_arrival_camera_check(self):
        threading.Thread(target=self._run_arrival_camera_check, daemon=True).start()

    def _run_arrival_camera_check(self):
        window_name = 'Pinky Camera Check'
        self.get_logger().info(f'카메라 미리보기를 {CAMERA_CHECK_DURATION:.0f}초간 PC 화면에 띄웁니다...')

        start = time.time()
        shown_any_frame = False
        while time.time() - start < CAMERA_CHECK_DURATION:
            with self.frame_lock:
                frame = self.latest_frame

            if frame is not None:
                cv2.imshow(window_name, frame)
                shown_any_frame = True

            # cv2 창 이벤트 처리를 위해 waitKey를 반드시 호출해야 함
            cv2.waitKey(1)
            time.sleep(0.03)

        if shown_any_frame:
            cv2.destroyWindow(window_name)
        else:
            self.get_logger().warn('카메라 프레임을 한 번도 받지 못했습니다. /camera/image_raw 토픽을 확인해주세요.')

        self.get_logger().info('카메라 미리보기 종료. SUCCESS/FAILURE 검증을 시작합니다.')
        self.yolo_start_time = time.time()

    def camera_callback(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            with self.frame_lock:
                self.latest_frame = frame
        except Exception as e:
            self.get_logger().error(f'카메라 이미지 변환 실패: {e}')

        if self.yolo_start_time is None:
            return

        current_time = time.time()
        if current_time - self.yolo_start_time > self.yolo_duration:
            self.get_logger().info('[타임아웃] 30초 제한 시간이 종료되었습니다. 전송을 멈춤 처리합니다.')
            self.is_checking_done = True
            self.yolo_start_time = None
            self.set_emotion('FAILURE')
            return

    def run_manual_test(self):
        while rclpy.ok():
            if self.yolo_start_time is not None and not self.is_checking_done:
                remaining = self.yolo_duration - (time.time() -self.yolo_start_time)
                if remaining <= 0:
                    time.sleep(0.5)
                    continue

                state = input(f"\n[테스트] SUCCESS 혹은 FAILURE를 입력해주세요 (남은시간: {remaining:.1f}초): ").strip()

                if state == 'SUCCESS':
                    self.get_logger().info('전송 성공!')
                    self.is_checking_done = True
                    self.yolo_start_time = None
                    self.set_emotion('SUCCESS')

                elif state == 'FAILURE':
                    self.get_logger().info('전송 실패 ...')
                    self.is_checking_done = True
                    self.yolo_start_time = None
                    self.set_emotion('FAILURE')

            time.sleep(0.5)

    def get_result_callback(self, future):
        result = future.result()
        status = result.status
        self.get_logger().info(f'네비게이션 액션 주행 상태가 업데이트되었습니다. (status={status})')

        if self._arrived:
            return  # feedback_callback 쪽에서 이미 처리된 경우 중복 방지

        if status == GoalStatus.STATUS_SUCCEEDED:
            self._arrived = True

            if self.is_returning:
                self.get_logger().info('====================================')
                self.get_logger().info('간호실에 최종 복귀 완료했습니다. 프로그램을 종료합니다.')
                self.get_logger().info('====================================')
                rclpy.shutdown()
                return

            self.get_logger().info('====================================')
            self.get_logger().info(f'로봇이 배달지({self.room_name})에 도착했습니다. 카메라 확인을 시작합니다.')
            self.get_logger().info('====================================')
            self._start_arrival_camera_check()


def main():
    parser = argparse.ArgumentParser(description='목적지 입력 및 도착 확인  프로그램')
    parser.add_argument('--target', type=str, required=False,
                          help='방 번호(102, 103, 104) 를 입력하세요.')

    args, _ = parser.parse_known_args(sys.argv[1:])

    if args.target is None:
        while True:
            user_input = input("목적지를 입력하세요 (102, 103, 104 중 하나를 입력해주세요): ").strip()
            if user_input in ['102', '103', '104']:
                target_key = int(user_input)
                break
            print("잘못된 입력입니다. 다시 입력해주세요.")
    else:
        if args.target in ['102', '103', '104']:
            target_key = int(args.target)
        else:
            print("target은 102, 103, 104만 가능합니다.")
            sys.exit(1)

    rclpy.init()
    node = NavGoalNode(target_key)
    node.send_goal()

    spin_thread = threading.Thread(target=rclpy.spin, args=(node,),daemon=True)
    spin_thread.start()

    try:
        node.run_manual_test()
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()


if __name__ == '__main__':
    main()