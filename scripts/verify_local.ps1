param(
    [switch]$SkipGpu,
    [string]$Video = 'data/inputs/videos/7203774185322188037.mp4',
    [string]$Transcript = 'data/inputs/audio_transcripts/7203774185322188037.txt'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Project .venv is missing.' }
if (-not (Test-Path -LiteralPath $Video)) { throw "Video is missing: $Video" }
if (-not $SkipGpu -and -not (Test-Path -LiteralPath $Transcript)) { throw "Transcript is missing: $Transcript" }

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code ${LASTEXITCODE}: $Program" }
}

Invoke-Checked -Program docker -Arguments @('info', '--format', '{{.ServerVersion}}')
# Preserve a database snapshot before applying migrations to an existing stack.
$postgresId = & docker compose ps -q postgres
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the Compose stack.' }
if ($postgresId) {
    $backupRoot = Join-Path $projectRoot 'artifacts/backups'
    New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
    $backupName = 'video-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.dump'
    Invoke-Checked -Program docker -Arguments @('compose', 'exec', '-T', 'postgres', 'pg_dump', '-U', 'video', '-d', 'video', '-Fc', '-f', '/tmp/video-before-upgrade.dump')
    Invoke-Checked -Program docker -Arguments @('compose', 'cp', 'postgres:/tmp/video-before-upgrade.dump', (Join-Path $backupRoot $backupName))
}
Invoke-Checked -Program $python -Arguments @('-m', 'pip', 'install', '-r', 'requirements-service-test.txt')
Invoke-Checked -Program $python -Arguments @('-m', 'pytest', '-q')
Invoke-Checked -Program $python -Arguments @('-m', 'scripts.verify_manifest')
Invoke-Checked -Program docker -Arguments @('compose', 'up', '-d', '--build', '--wait', '--wait-timeout', '180')
Invoke-Checked -Program $python -Arguments @('-m', 'scripts.service_smoke', '--video', $Video, '--restart-worker', '--check-failure', '--check-storage')
$checks = @('cpu_tests_and_migrations', 'manifest_integrity', 'fake_service', 's3_storage', 'restart_persistence', 'durable_failure')
if (-not $SkipGpu) {
    Invoke-Checked -Program docker -Arguments @('compose', '-f', 'docker-compose.yml', '-f', 'docker-compose.gpu.yml', 'up', '-d', '--build', '--wait', '--wait-timeout', '180')
    Invoke-Checked -Program $python -Arguments @('-m', 'scripts.gpu_service_smoke', '--video', $Video, '--transcript', $Transcript)
    $checks += @('real_gpu_service', 'warm_model_reuse')
}
$report = @{ verified_at = (Get-Date).ToUniversalTime().ToString('o'); checks = $checks; gpu_checked = (-not $SkipGpu) }
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath 'reports/local_acceptance.json' -Encoding utf8
Write-Output 'PASS local acceptance. Evidence: reports/local_acceptance.json'
