#!/usr/bin/env bash
# get-fonts.sh — download the six self-hosted faces into assets/fonts/.
#
# Run once, from the repository root:
#
#     ./assets/fonts/get-fonts.sh
#
# Needs npm on the PATH (only to fetch the packages; nothing is installed and
# no node_modules is created). If you would rather not use npm, the same files
# can be downloaded by hand — see README.md.
#
# Both the `latin` and `latin-ext` subsets are fetched: venues include Tōkyō,
# Kraków, Xi'An and Reykjavík, whose accents live in latin-ext.

set -euo pipefail

DEST="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fetch() {          # fetch <npm-package> <file-in-package> <destination-name>
  local pkg="$1" src="$2" out="$3"
  if [ ! -d "$WORK/$pkg" ]; then
    ( cd "$WORK" && npm pack "@fontsource/$pkg" --silent >/dev/null )
    mkdir -p "$WORK/$pkg"
    tar xzf "$WORK"/fontsource-"$pkg"-*.tgz -C "$WORK/$pkg" --strip-components=1
  fi
  if [ -f "$WORK/$pkg/files/$src" ]; then
    cp "$WORK/$pkg/files/$src" "$DEST/$out"
    printf '  %-34s %s\n' "$out" "$(du -h "$DEST/$out" | cut -f1)"
  else
    printf '  MISSING: %s in @fontsource/%s\n' "$src" "$pkg" >&2
  fi
}

echo "Fetching fonts into $DEST"

# Spectral — conference names and full titles
fetch spectral spectral-latin-400-normal.woff2      spectral-regular.woff2
fetch spectral spectral-latin-ext-400-normal.woff2  spectral-regular-ext.woff2
fetch spectral spectral-latin-400-italic.woff2      spectral-italic.woff2
fetch spectral spectral-latin-ext-400-italic.woff2  spectral-italic-ext.woff2
fetch spectral spectral-latin-600-normal.woff2      spectral-semibold.woff2
fetch spectral spectral-latin-ext-600-normal.woff2  spectral-semibold-ext.woff2

# Source Sans 3 — the interface
fetch source-sans-3 source-sans-3-latin-400-normal.woff2     source-sans-3-regular.woff2
fetch source-sans-3 source-sans-3-latin-ext-400-normal.woff2 source-sans-3-regular-ext.woff2
fetch source-sans-3 source-sans-3-latin-600-normal.woff2     source-sans-3-semibold.woff2
fetch source-sans-3 source-sans-3-latin-ext-600-normal.woff2 source-sans-3-semibold-ext.woff2

# IBM Plex Mono — every piece of data
fetch ibm-plex-mono ibm-plex-mono-latin-400-normal.woff2     ibm-plex-mono-regular.woff2
fetch ibm-plex-mono ibm-plex-mono-latin-ext-400-normal.woff2 ibm-plex-mono-regular-ext.woff2
fetch ibm-plex-mono ibm-plex-mono-latin-600-normal.woff2     ibm-plex-mono-semibold.woff2
fetch ibm-plex-mono ibm-plex-mono-latin-ext-600-normal.woff2 ibm-plex-mono-semibold-ext.woff2

echo
echo "Done. Total: $(du -sh "$DEST" | cut -f1)"
echo "These files are committed to the repository — they are part of the site."
