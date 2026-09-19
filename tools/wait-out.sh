#!/bin/sh
# Waits for a background task's output file to contain a marker, or times out.
F="$1"; MARK="$2"; LIMIT="${3:-200}"
N=0
until grep -qE "$MARK" "$F" 2>/dev/null || [ "$N" -ge "$LIMIT" ]; do
  sleep 3; N=$((N+3))
done
cat "$F"
