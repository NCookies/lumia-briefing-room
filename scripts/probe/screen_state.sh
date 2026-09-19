#!/usr/bin/env bash
# 일회성 조사 도구: 세그먼트별 첫 프레임을 작은 해상도로 뽑는다.
# 화면 전체 상태(회색 오버레이 등) 통계용. 원본은 읽기만 한다.
# usage: screen_state.sh <session_dir> <first> <last> <step> <out_dir> <ffmpeg>
set -euo pipefail
S="$1"; FIRST="$2"; LAST="$3"; STEP="$4"; OUT="$5"; FFMPEG="$6"
mkdir -p "$OUT"
for n in $(seq "$FIRST" "$STEP" "$LAST"); do
  p=$(printf '%05d' "$n")
  src="$S/chunk-stream0-${p}.m4s"
  [ -f "$src" ] || { echo "skip $p"; continue; }
  tmp="$OUT/.s_${p}.mp4"
  cat "$S/init-stream0.m4s" "$src" > "$tmp"
  "$FFMPEG" -hide_banner -v error -y -i "$tmp" -frames:v 1 -vf "scale=384:216" "$OUT/s_${p}.png" || echo "fail $p"
  rm -f "$tmp"
done
ls "$OUT" | grep -c '\.png$'
