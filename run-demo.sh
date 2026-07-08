#!/usr/bin/env bash
# PinkyCare 데모 런처 — 노트북에서 백엔드(:8000) + 프론트(:5173)를 한 번에 실행.
#
#   ./run-demo.sh
#
# 로봇(라즈베리파이)의 mission_dispatcher.py 는 다른 머신이라 여기서 못 띄운다.
# 대신 아래에 로봇에서 칠 명령을 노트북 IP까지 채워서 출력한다.
#
# (선택) 로봇을 SSH 로 붙일 수 있으면 디스패처까지 자동 실행:
#   ROBOT_SSH=pinky@192.168.4.1 ./run-demo.sh
#   ROBOT_DISPATCHER=/home/pinky/.../mission_dispatcher.py  # 경로 다르면 지정
#
# Ctrl+C 한 번으로 띄운 프로세스를 모두 정리한다.
set -uo pipefail  # -e 는 쓰지 않음: 서버 하나가 죽어도 정리 로직까지 도달해야 함

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"

# 로봇 AP(192.168.4.x)에서 받은 노트북 IP 자동 감지 (없으면 첫 번째 사설 IP)
LAN_IP="$(ip -4 addr show 2>/dev/null | grep -oP 'inet \K192\.168\.4\.[0-9]+' | head -1)"
[ -z "$LAN_IP" ] && LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[ -z "$LAN_IP" ] && LAN_IP="127.0.0.1"
BACKEND_URL="http://$LAN_IP:8000"

pids=()
# 자식 트리를 잎(자손)부터 뿌리까지 재귀적으로 종료 (vite→node, npm→sh→node 등 포함)
kill_tree() {
  local pid="$1" child
  for child in $(pgrep -P "$pid" 2>/dev/null); do
    kill_tree "$child"
  done
  kill -TERM "$pid" 2>/dev/null || true
}
cleanup() {
  echo ""
  echo "[run-demo] 종료 중... 프로세스 트리 정리"
  for pid in "${pids[@]:-}"; do
    [ -n "$pid" ] && kill_tree "$pid"
  done
  wait 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

# 명령을 백그라운드로 띄우고 자식 PID 기록 (cleanup 에서 트리째 종료)
launch() {  # launch <설명> <디렉터리> <명령...>
  local desc="$1" dir="$2"; shift 2
  ( cd "$dir" && exec "$@" ) &
  pids+=("$!")
}

# ── 사전 점검 ──
if [ ! -x "$BACKEND_DIR/.venv/bin/uvicorn" ]; then
  echo "[run-demo] 백엔드 venv 가 없습니다. 최초 1회 셋업:"
  echo "  cd $BACKEND_DIR && python3 -m venv .venv && .venv/bin/pip install -e '.[test]'"
  exit 1
fi
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "[run-demo] 프론트 의존성 설치 (최초 1회)..."
  ( cd "$FRONTEND_DIR" && npm install )
fi

# ── ① 백엔드 (0.0.0.0 바인딩: 로봇이 붙을 수 있게 / PYTHONPATH 비워 ROS 간섭 차단) ──
echo "[run-demo] ① 백엔드 → $BACKEND_URL  (로봇이 볼 주소)"
launch "backend" "$BACKEND_DIR" \
  env -u PYTHONPATH .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

# ── ② 프론트 ──
echo "[run-demo] ② 프론트 → http://localhost:5173  (LAN: http://$LAN_IP:5173)"
launch "frontend" "$FRONTEND_DIR" npm run dev -- --host

# ── ③ 로봇 디스패처 ──
if [ -n "${ROBOT_SSH:-}" ]; then
  DISP_PATH="${ROBOT_DISPATCHER:-mission_dispatcher.py}"
  echo "[run-demo] ③ 로봇 디스패처 → ssh $ROBOT_SSH ($DISP_PATH)"
  ( exec ssh -tt "$ROBOT_SSH" "BACKEND_URL=$BACKEND_URL python3 $DISP_PATH" ) &
  pids+=("$!")
else
  echo ""
  echo "[run-demo] ③ 로봇(라즈베리파이)에서 아래를 직접 실행하세요:"
  echo "    BACKEND_URL=$BACKEND_URL python3 mission_dispatcher.py"
  echo "    (SSH 자동실행 원하면:  ROBOT_SSH=pinky@192.168.4.1 ./run-demo.sh)"
fi

echo ""
echo "[run-demo] 실행 완료. 종료하려면 Ctrl+C."
wait
