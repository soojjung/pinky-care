# PinkyCare — ROS2 워크스페이스

Pinky 로봇의 자율주행 노드. Nav2 기반 배송 미션 수행.

## 상태

**팀원 담당 · 별도 구현.** 이 폴더는 향후 ROS2 패키지들이 들어갈 자리 표시자.

## 예상 스택

- ROS2 Humble (또는 팀 결정 버전)
- Nav2
- 빌드 시스템: colcon

## 예상 폴더 구조 (표준 colcon 워크스페이스)

```
ros2_ws/
├── src/
│   └── pinky_delivery/           # 배송 미션 노드
│       ├── pinky_delivery/
│       │   ├── __init__.py
│       │   ├── delivery_node.py  # 백엔드 REST 클라이언트 + Nav2 액션 클라이언트
│       │   └── config/
│       ├── package.xml
│       └── setup.py
├── install/                      # colcon build 결과 (git ignored)
├── build/                        # colcon build 결과 (git ignored)
└── log/
```

## 백엔드 연동

로봇 상태를 백엔드에 알리는 방식은 `PATCH /deliveries/{id}/robot-status`. 상세는 API 명세 참고.

- `MOVING`: Nav2 목적지 이동 시작 시 호출
- `ARRIVED`: Nav2 goal reached 콜백에서 호출

## 관련 문서

- API 명세서: [`../docs/api-spec.md`](../docs/api-spec.md)
- 시스템 아키텍처: [`../README.md`](../README.md)
