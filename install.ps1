# Installs the expired-domain-finder skill for Claude Code on Windows.
#   powershell -ExecutionPolicy Bypass -File install.ps1
$src = Join-Path $PSScriptRoot "expired-domain-finder"
$dst = Join-Path $HOME ".claude\skills\expired-domain-finder"
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item -Path (Join-Path $src "*") -Destination $dst -Recurse -Force
Write-Host "Skill installed to $dst"

python -m pip install --user --quiet wordninja
if ($?) { Write-Host "wordninja installed (better domain-name matching)." }
else { Write-Host "Could not install wordninja; the skill still works, with rougher name matching." }

Write-Host ""
Write-Host "Next: save your DataForSEO API credentials (optional, enables the paid checks):"
Write-Host "  powershell -ExecutionPolicy Bypass -File `"$dst\scripts\setup_credentials.ps1`""
Write-Host "Then restart Claude and ask: find expired domains for the camping niche"
