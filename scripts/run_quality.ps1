param([switch]$Diagnostics, [switch]$Constrained)
$ErrorActionPreference = 'Stop'
if ($Diagnostics -and $Constrained) { throw 'Choose either -Diagnostics or -Constrained.' }
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code ${LASTEXITCODE}: $Program" }
}
New-Item -ItemType Directory -Force -Path 'artifacts/benchmark-model-cache','data/outputs' | Out-Null
Invoke-Checked -Program docker -Arguments @('compose', '-f', 'docker-compose.benchmark.yml', 'build')
$runningWorker = & docker compose ps --status running -q worker
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect worker state.' }
try {
    # Free the resident worker model so benchmark measurements do not compete for VRAM.
    if ($runningWorker) { Invoke-Checked -Program docker -Arguments @('compose', 'stop', '--timeout', '960', 'worker') }
    $benchmarkArguments = @('compose', '-f', 'docker-compose.benchmark.yml', 'run', '--rm', 'benchmark')
    if ($Diagnostics) { $benchmarkArguments += @('python', '-m', 'scripts.quality_diagnostics') }
    if ($Constrained) { $benchmarkArguments += @('python', '-m', 'scripts.quality_suite', '--constrained') }
    Invoke-Checked -Program docker -Arguments $benchmarkArguments
}
finally {
    if ($runningWorker) { Invoke-Checked -Program docker -Arguments @('compose', 'start', 'worker') }
}
