#!/usr/bin/env bash
# 일회성 조사 도구. Steam 백그라운드 녹화 세션에서 init + chunk 구간을
# 작업 폴더로 복사해 단일 fMP4로 이어붙인다. 원본은 읽기만 한다.
#
# usage: merge_m4s.sh <session_dir> <stream_id> <first_num> <last_num> <out_dir>
#   ex)  merge_m4s.sh "/h/steam video/video/bg_1049590_20260919_130747" 0 1000 1009 /tmp/work
set -euo pipefail

SESSION="$1"; STREAM="$2"; FIRST="$3"; LAST="$4"; OUT="$5"
mkdir -p "$OUT"

INIT="$SESSION/init-stream${STREAM}.m4s"
[ -f "$INIT" ] || { echo "no init segment: $INIT" >&2; exit 1; }

# 1) 원본 -> 작업 폴더 복사 (원본 미수정)
cp -n "$INIT" "$OUT/"
for n in $(seq -f '%05g' "$FIRST" "$LAST"); do
  src="$SESSION/chunk-stream${STREAM}-${n}.m4s"
  [ -f "$src" ] || { echo "missing chunk: $src" >&2; exit 1; }
  cp -n "$src" "$OUT/"
done

# 2) 단순 바이트 결합
MERGED="$OUT/merged-stream${STREAM}-${FIRST}-${LAST}.mp4"
cat "$OUT/init-stream${STREAM}.m4s" > "$MERGED"
for n in $(seq -f '%05g' "$FIRST" "$LAST"); do
  cat "$OUT/chunk-stream${STREAM}-${n}.m4s" >> "$MERGED"
done

echo "$MERGED"
ls -l "$MERGED"
