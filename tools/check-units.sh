#!/bin/sh
# Guards the frame illusion.
#
# Inside the phone (src/app) every length must be in px:
#   - rem resolves against the document root, so browser page-zoom would
#     rescale the app but not the frame around it;
#   - vw/vh/dvh resolve against the BROWSER viewport, so a 100dvh panel in a
#     568px frame would be 900px tall and break the illusion entirely.
# Container queries (cqh/cqw) are fine — those resolve against the frame.
set -e

HITS=$(grep -rnE '[0-9](rem|vw|vh|dvh|svh|lvh|dvw|svw)\b' src/app || true)

if [ -n "$HITS" ]; then
  echo "Browser-relative units found inside the phone viewport:"
  echo "$HITS"
  echo
  echo "Use px, or a container query unit (cqh/cqw)."
  exit 1
fi

echo "unit check passed: no browser-relative units under src/app"
