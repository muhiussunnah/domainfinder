# Saves your DataForSEO API login and password as Windows user environment variables
# (DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD), after checking them against the API.
# Get them at https://app.dataforseo.com/api-access (API password, not your website password).
#
# Run it yourself in PowerShell:
#   powershell -ExecutionPolicy Bypass -File setup_credentials.ps1

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$login = Read-Host "DataForSEO API login (email)"
$secure = Read-Host "DataForSEO API password" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }

if (-not $login -or -not $password) {
    Write-Host "Nothing entered, nothing saved."
    exit 1
}

$token = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("${login}:${password}"))
try {
    $r = Invoke-RestMethod -Uri "https://api.dataforseo.com/v3/appendix/user_data" -Method Get `
        -Headers @{ Authorization = "Basic $token" }
    if ($r.status_code -ne 20000) { throw $r.status_message }
    $balance = $null
    try { $balance = $r.tasks[0].result[0].money.balance } catch {}
    if ($null -ne $balance) { Write-Host "Credentials work. Balance: $balance USD" }
    else { Write-Host "Credentials work." }
}
catch {
    Write-Host "DataForSEO rejected these credentials, nothing saved: $_"
    exit 1
}

[Environment]::SetEnvironmentVariable("DATAFORSEO_LOGIN", $login, "User")
[Environment]::SetEnvironmentVariable("DATAFORSEO_PASSWORD", $password, "User")
Write-Host "Saved. Fully quit Claude (also from the system tray) and open it again so it sees them."
