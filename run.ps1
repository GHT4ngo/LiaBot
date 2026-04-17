Set-Location $PSScriptRoot

Write-Host ''
Write-Host '  =============================================' -ForegroundColor Cyan
Write-Host '  LiaBot - LIA-sokning for Data Engineering' -ForegroundColor Cyan
Write-Host '  =============================================' -ForegroundColor Cyan
Write-Host ''

# --- Stoppa processer som lyssnar på port 8002 och 8003 ---
$killedAny = $false
foreach ($port in @(8002, 8003)) {
    $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($listeners) {
        $pidsToKill = $listeners.OwningProcess | Sort-Object -Unique
        foreach ($procId in $pidsToKill) {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            $killedAny = $true
        }
    }
}
if ($killedAny) {
    Write-Host '  [0/3] Gamla processer stoppade' -ForegroundColor Yellow
    Start-Sleep -Seconds 2
} else {
    Write-Host '  [0/3] Inga gamla processer att stoppa' -ForegroundColor DarkGray
}

# --- Ollama ---
$ollamaRunning = Get-Process -Name 'ollama' -ErrorAction SilentlyContinue
if (-not $ollamaRunning) {
    Write-Host '  [1/3] Startar Ollama...' -ForegroundColor Yellow
    $ollamaPath = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
    Start-Process -FilePath $ollamaPath -ArgumentList 'serve' -WindowStyle Minimized
    Start-Sleep -Seconds 3
    Write-Host '  [1/3] Ollama startad' -ForegroundColor Green
} else {
    Write-Host '  [1/3] Ollama koer redan' -ForegroundColor Green
}

# --- Launcher (port 8003) ---
Write-Host '  [2/3] Startar Launcher (port 8003)...' -ForegroundColor Yellow
$launcher = Start-Process -FilePath 'python' -ArgumentList 'launcher.py' -PassThru -NoNewWindow
Start-Sleep -Seconds 1
Write-Host "  [2/3] Launcher startad (PID $($launcher.Id))" -ForegroundColor Green

# --- FastAPI (port 8002) ---
Write-Host '  [2/3] Startar API (port 8002)...' -ForegroundColor Yellow
$api = Start-Process -FilePath 'python' -ArgumentList 'api.py' -PassThru -NoNewWindow
Start-Sleep -Seconds 2

$check = Get-NetTCPConnection -LocalPort 8002 -State Listen -ErrorAction SilentlyContinue
if ($check) {
    Write-Host "  [2/3] API startad (PID $($api.Id))" -ForegroundColor Green
} else {
    Write-Host '  [2/3] API verkar inte ha startat - kolla felmeddelanden ovan' -ForegroundColor Red
}

# --- Oppna appen ---
Write-Host '  [3/3] Oppnar LiaBot i webblaesaren...' -ForegroundColor Yellow
Start-Process 'https://lia-tracker.lovable.app/'
Write-Host '  [3/3] Klart!' -ForegroundColor Green

Write-Host ''
Write-Host '  API koer pa: http://localhost:8002' -ForegroundColor Cyan
Write-Host '  Docs:        http://localhost:8002/docs' -ForegroundColor Cyan
Write-Host ''
Write-Host '  LiaBot koer i bakgrunden. Stang detta fonster nar du vill.' -ForegroundColor DarkGray
Write-Host ''
