# Promove `main` para `producao` -- e isso POE NO AR (ver CLAUDE.md, secao Branches).
#
#   .\promover.ps1                  roda as duas baterias, confere tudo, pergunta e empurra
#   .\promover.ps1 -UsarLogs        aceita as baterias ja rodadas depois do ultimo commit
#   .\promover.ps1 -BackupFeito     declara que o backup do banco do ar ja foi tirado
#   .\promover.ps1 -Sim             nao pergunta antes do push (o resto continua cobrado)
#   .\promover.ps1 -Ensaio          confere tudo e para ANTES do push (nada vai ao ar)
#
# O roteiro de docs/deploy.md (secao 6), na ordem, e sem pular passo:
#   1. a VERSAO subiu em relacao ao que esta no ar
#   2. a bateria inteira (API + navegador) esta verde para ESTE commit
#   3. backup do banco ANTES do push, quando ha migracao nova
#   4. push de main e producao juntos (--atomic)
#   5. acompanha o /api/saude ate a versao virar e roda o verificar_deploy.py
#
# Nasceu em 14/10/2026: na promocao da 1.1.92 (com a migracao 111) o backup nao foi
# confirmado, e `main` ficou para tras no GitHub -- so `producao` foi empurrado.
#
# ATENCAO: producao so avanca por AVANCO RAPIDO de main (nunca recebeu commit proprio).
# Por isso nao ha checkout: o script empurra `main:producao` e nao toca nas alteracoes
# nao commitadas da arvore de trabalho.

param(
    [switch]$UsarLogs,
    [switch]$BackupFeito,
    [switch]$Sim,
    [switch]$Ensaio
)

$ErrorActionPreference = 'Stop'
$raiz = $PSScriptRoot
$no_ar = 'https://sistema.botanedeliecafe.com.br'
$log_api = Join-Path $raiz 'api\.bateria-api.txt'
$log_web = Join-Path $raiz 'web\.bateria-navegador.txt'

function Parar($texto) {
    Write-Host ""
    Write-Host "PAROU: $texto" -ForegroundColor Red
    exit 1
}

function Passo($texto) { Write-Host ""; Write-Host "== $texto" -ForegroundColor Cyan }

function Saude($base) {
    try { return Invoke-RestMethod -Uri "$base/saude" -TimeoutSec 15 } catch { return $null }
}

Set-Location $raiz

# ------------------------------------------------------------------ 0. git
Passo 'git'
$ramo = (git rev-parse --abbrev-ref HEAD).Trim()
if ($ramo -ne 'main') { Parar "o ramo atual e '$ramo'. Promova a partir de main." }
git fetch origin --quiet
if ($LASTEXITCODE -ne 0) { Parar 'git fetch falhou.' }
git merge-base --is-ancestor origin/producao main
if ($LASTEXITCODE -ne 0) {
    Parar 'origin/producao tem commit que main nao tem. Producao so recebe main -- investigue antes.'
}
$commit = (git rev-parse --short HEAD).Trim()
$novos = @(git log --oneline origin/producao..main)
if ($novos.Count -eq 0) { Parar 'nada a promover: producao ja esta em main.' }
Write-Host "commit $commit, $($novos.Count) commit(s) novos:"
$novos | ForEach-Object { Write-Host "   $_" }
$sujos = @(git status --porcelain --untracked-files=no)
if ($sujos.Count -gt 0) {
    Write-Host "aviso: ha alteracoes NAO commitadas (elas NAO vao ao ar, mas estavam na bateria):" -ForegroundColor Yellow
    $sujos | ForEach-Object { Write-Host "   $_" -ForegroundColor Yellow }
}

# ------------------------------------------------------------------ 1. versao
Passo 'versao'
$linha = (git show HEAD:api/main.py) | Select-String -Pattern '^VERSAO = "([0-9.]+)"' | Select-Object -First 1
if (-not $linha) { Parar 'nao achei VERSAO em api/main.py.' }
$versao = $linha.Matches[0].Groups[1].Value
$ar = Saude "$no_ar/api"
if (-not $ar) { Parar "o ar nao respondeu em $no_ar/api/saude." }
Write-Host "no ar: $($ar.versao) / $($ar.migracao)"
Write-Host "vai:   $versao"
if ([version]$versao -le [version]$ar.versao) {
    Parar "a VERSAO ($versao) nao passou da que esta no ar ($($ar.versao)). Suba o numero em api/main.py e commite."
}

# ------------------------------------------------------------------ 2. bateria
Passo 'bateria (API + navegador)'
$local = Saude 'http://127.0.0.1:9200'
if (-not $local) { Parar 'a API local (9200) nao respondeu. Suba com .\iniciar_local.ps1.' }
if ($local.versao -ne $versao) {
    Parar "a API local esta na $($local.versao), nao na ${versao}: reinicie-a antes, senao a bateria testa codigo velho."
}
$hora_commit = [datetimeoffset]::FromUnixTimeSeconds([int64](git log -1 --format=%ct)).LocalDateTime

if (-not $UsarLogs) {
    Write-Host 'API... (cerca de 7 minutos)'
    # ATENCAO: pelo cmd, e nao com `*>`: no PowerShell 5.1 o `*>` grava em UTF-16 e
    # embrulha cada linha de stderr num erro -- o registro sairia ilegivel para o passo abaixo.
    $env:PYTHONUTF8 = '1'
    Push-Location (Join-Path $raiz 'api')
    cmd /c "python tests/rodar_tudo.py > `"$log_api`" 2>&1"
    Pop-Location
    Write-Host 'navegador... (demorado)'
    Push-Location (Join-Path $raiz 'web')
    cmd /c "node scripts/verificar.mjs > `"$log_web`" 2>&1"
    Pop-Location
}

# ATENCAO: na API, "84/85 suites, ..., 0 falharam" tambem e vermelho -- a suite que
# quebrou antes do resumo nao conta checagem nenhuma. Por isso o par de numeros abaixo.
foreach ($par in @(@($log_api, '^(\d+)/\1 su.+, \d+ checagens ok, 0 falharam'),
                   @($log_web, '^\d+ passaram, 0 falharam'))) {
    $arquivo, $padrao = $par
    if (-not (Test-Path $arquivo)) { Parar "nao ha registro da bateria em $arquivo. Rode sem -UsarLogs." }
    if ((Get-Item $arquivo).LastWriteTime -lt $hora_commit) {
        Parar "$arquivo e mais velho que o ultimo commit -- a bateria nao testou este codigo."
    }
    # A linha de RESUMO, e nao a ultima: o navegador ainda escreve onde guardou as fotos.
    $linhas = Get-Content $arquivo -Encoding UTF8
    $fim = $linhas | Where-Object { $_ -match 'checagens ok|passaram,' } | Select-Object -Last 1
    if (-not $fim) { $fim = $linhas | Where-Object { $_.Trim() } | Select-Object -Last 1 }
    if ($fim -notmatch $padrao) { Parar "bateria NAO esta verde ($arquivo): $fim" }
    Write-Host "ok  $fim"
}

# ------------------------------------------------------------------ 3. backup
Passo 'migracoes e backup'
$migracoes = @(git diff --name-only --diff-filter=A origin/producao main -- api/db_scripts)
if ($migracoes.Count -eq 0) {
    Write-Host 'nenhuma migracao nova -- backup dispensado pelo roteiro.'
} else {
    Write-Host 'migracao(oes) nova(s) -- rodam no start e nao tem desfazer:' -ForegroundColor Yellow
    $migracoes | ForEach-Object { Write-Host "   $_" -ForegroundColor Yellow }
    $pg_dump = Get-Command pg_dump -ErrorAction SilentlyContinue
    if ($env:DATABASE_URL_PRODUCAO -and $pg_dump) {
        $pasta = Join-Path $raiz '.backup'
        New-Item -ItemType Directory -Force $pasta | Out-Null
        $destino = Join-Path $pasta ("producao-{0}-antes-da-{1}.dump" -f (Get-Date -Format 'yyyy-MM-dd-HHmm'), $versao)
        Write-Host "pg_dump -> $destino"
        & $pg_dump.Source --format=custom --no-owner --file=$destino $env:DATABASE_URL_PRODUCAO
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $destino) -or (Get-Item $destino).Length -lt 10240) {
            Parar 'o pg_dump falhou ou gerou arquivo vazio. Nada foi empurrado.'
        }
        Write-Host ("ok  backup de {0:N1} MB" -f ((Get-Item $destino).Length / 1MB))
    } elseif ($BackupFeito) {
        Write-Host 'backup declarado com -BackupFeito.'
    } else {
        Parar ("ha migracao nova e nenhum backup. Ou defina `$env:DATABASE_URL_PRODUCAO (e tenha o " +
               "pg_dump no PATH) para o script tirar, ou tire pelo painel da DigitalOcean " +
               "(Databases > Backups) e rode de novo com -BackupFeito.")
    }
}

# ------------------------------------------------------------------ 4. push
Passo 'push'
Write-Host "Vai ao ar: $($ar.versao) -> $versao ($($novos.Count) commit(s), $($migracoes.Count) migracao(oes))." -ForegroundColor Yellow
if ($Ensaio) {
    Write-Host 'ENSAIO: tudo conferido, nada foi empurrado.' -ForegroundColor Green
    exit 0
}
if (-not $Sim) {
    $resposta = Read-Host 'Digite PROMOVER para empurrar'
    if ($resposta -ne 'PROMOVER') { Parar 'cancelado. Nada foi empurrado.' }
}
# --atomic: main e producao sobem juntos ou nenhum sobe. Na 1.1.92 so producao subiu.
# O git escreve o progresso do push no stderr. No PowerShell 5.1 com a saida
# redirecionada (*>&1), isso vira erro e o 'Stop' derrubava o script logo depois
# de um push BEM-SUCEDIDO (1.1.96). Quem decide o sucesso e o $LASTEXITCODE.
$ErrorActionPreference = 'Continue'
git push --atomic origin main:main main:producao 2>&1 | ForEach-Object { Write-Host "$_" }
$codigo_push = $LASTEXITCODE
# A referencia local de producao acompanha (avanco rapido, sem checkout).
if ($codigo_push -eq 0) { git fetch . main:producao --quiet 2>&1 | ForEach-Object { Write-Host "$_" } }
$ErrorActionPreference = 'Stop'
if ($codigo_push -ne 0) { Parar 'o push falhou. Nada foi para o ar.' }

# ------------------------------------------------------------------ 5. conferir
Passo 'acompanhando o /api/saude (a migracao aparece antes da versao)'
$limite = (Get-Date).AddMinutes(12)
$visto = ''
while ((Get-Date) -lt $limite) {
    $s = Saude "$no_ar/api"
    if ($s) {
        $agora = "$($s.versao) / $($s.migracao)"
        if ($agora -ne $visto) { Write-Host ("{0:HH:mm:ss}  {1}" -f (Get-Date), $agora); $visto = $agora }
        if ($s.versao -eq $versao) { break }
    }
    Start-Sleep -Seconds 20
}
if (-not $s -or $s.versao -ne $versao) {
    Parar "em 12 minutos o ar nao virou para $versao. Olhe o painel da DigitalOcean (o start pode ter recusado subir)."
}
Write-Host "no ar: $versao" -ForegroundColor Green
python (Join-Path $raiz 'api\verificar_deploy.py') $no_ar
