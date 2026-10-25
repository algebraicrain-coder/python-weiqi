#!/bin/zsh
# 双击启动 python-weiqi 网页版（macOS）
# 可选环境变量：
#   WEIQI_WEB_PORT=8090   指定端口（默认 8080）
#   WEIQI_NO_OPEN=1       只启动服务，不自动打开浏览器

cd "$(dirname "$0")/.." || exit 1
PORT="${WEIQI_WEB_PORT:-8080}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "找不到 python3，请先安装 Python 3。"
  read -r "?按回车退出..."
  exit 1
fi

if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "端口 $PORT 已被占用。"
  echo "可以用 WEIQI_WEB_PORT=8090 换一个端口，例如："
  echo "  WEIQI_WEB_PORT=8090 ./scripts/run_web.command"
  read -r "?按回车退出..."
  exit 1
fi

python3 main.py web --host 127.0.0.1 --port "$PORT" --no-open &
SERVER_PID=$!

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
}
trap 'cleanup; exit 130' INT TERM
trap cleanup EXIT

ready=0
for _ in {1..60}; do
  if curl -fsS "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    break
  fi
  sleep 0.1
done

if [[ "$ready" -ne 1 ]]; then
  echo "服务启动失败，请查看上面的错误信息。"
  wait "$SERVER_PID" 2>/dev/null
  read -r "?按回车退出..."
  exit 1
fi

URL="http://127.0.0.1:$PORT/"
if [[ "${WEIQI_NO_OPEN:-0}" == "1" ]]; then
  echo "服务已启动：$URL"
else
  open -a "Google Chrome" "$URL" 2>/dev/null || open "$URL" 2>/dev/null || echo "请手动打开：$URL"
fi
echo "按 Ctrl+C 或关闭此窗口停止服务。"

wait "$SERVER_PID"
