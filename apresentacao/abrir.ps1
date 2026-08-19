# Abre a apresentacao do Botane no navegador padrao.
# Uso:  .\abrir.ps1          -> abre o arquivo direto (file://)
#       .\abrir.ps1 -Servir  -> sobe um servidor local em http://127.0.0.1:8899

param([switch]$Servir)

$pagina = Join-Path $PSScriptRoot 'index.html'

if ($Servir) {
    Write-Host "Servindo $PSScriptRoot em http://127.0.0.1:8899  (Ctrl+C para parar)"
    Start-Process 'http://127.0.0.1:8899/'
    python -m http.server 8899 --bind 127.0.0.1 --directory $PSScriptRoot
} else {
    Start-Process $pagina
}
