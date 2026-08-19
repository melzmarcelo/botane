# Sobe o Botane local: Postgres (servico), API na 9200 e web na 3100.
#
#   .\iniciar_local.ps1              sobe os dois em janelas separadas
#   .\iniciar_local.ps1 -SoApi       so a API
#   .\iniciar_local.ps1 -Verificar   sobe, roda os testes e derruba

param([switch]$SoApi, [switch]$SoWeb, [switch]$Verificar)

$raiz = $PSScriptRoot
$api = Join-Path $raiz 'api'
$web = Join-Path $raiz 'web'

# --- Postgres ---
$servico = Get-Service -Name 'postgresql-x64-18' -ErrorAction SilentlyContinue
if ($servico -and $servico.Status -ne 'Running') {
    Write-Host 'Iniciando o PostgreSQL...'
    Start-Service $servico.Name
}
if (-not $servico) {
    Write-Host 'AVISO: servico postgresql-x64-18 nao encontrado. O banco precisa estar de pe.' -ForegroundColor Yellow
}

function Start-Api {
    Write-Host 'API   -> http://localhost:9200/docs'
    Start-Process powershell -ArgumentList @(
        '-NoExit', '-Command',
        "Set-Location '$api'; python -m uvicorn main:app --port 9200 --reload"
    )
}

function Start-Web {
    if (-not (Test-Path (Join-Path $web 'node_modules'))) {
        Write-Host 'Instalando dependencias do front (primeira vez)...'
        Push-Location $web; npm install; Pop-Location
    }
    Write-Host 'Web   -> http://localhost:3100'
    Start-Process powershell -ArgumentList @(
        '-NoExit', '-Command', "Set-Location '$web'; npm run dev"
    )
}

if ($Verificar) {
    Write-Host 'Rodando os testes (API e web precisam estar de pe).'
    Push-Location $api;  python tests/smoke_fundacao.py;  $a = $LASTEXITCODE; Pop-Location
    Push-Location $web;  node scripts/verificar.mjs;      $b = $LASTEXITCODE; Pop-Location
    if ($a -eq 0 -and $b -eq 0) { Write-Host 'Tudo verde.' -ForegroundColor Green }
    else { Write-Host 'Houve falha nos testes.' -ForegroundColor Red }
    exit ([int]($a -ne 0 -or $b -ne 0))
}

if ($SoWeb) { Start-Web; exit }
if ($SoApi) { Start-Api; exit }

Start-Api
Start-Sleep -Seconds 3
Start-Web

Write-Host ''
Write-Host 'Primeiro acesso: admin@botane.com.br / botane123 (o sistema pede a troca).'
