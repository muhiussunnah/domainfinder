#!/usr/bin/env sh
# Installs the expired-domain-finder skill for Claude Code on macOS / Linux.
set -e
src="$(cd "$(dirname "$0")" && pwd)/expired-domain-finder"
dst="$HOME/.claude/skills/expired-domain-finder"
mkdir -p "$dst"
cp -R "$src/." "$dst/"
echo "Skill installed to $dst"
python3 -m pip install --user --quiet wordninja && echo "wordninja installed (better domain-name matching)." \
  || echo "Could not install wordninja; the skill still works, with rougher name matching."
echo
echo "Next: add your DataForSEO API credentials to your shell profile (optional, enables the paid checks):"
echo "  export DATAFORSEO_LOGIN='you@example.com'"
echo "  export DATAFORSEO_PASSWORD='your-api-password'"
