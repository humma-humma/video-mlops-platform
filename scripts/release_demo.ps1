param(
    [string]$Video = 'data/inputs/videos/7203774185322188037.mp4'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot '.venv/Scripts/python.exe'
$baseCompose = @('compose', '-f', 'docker-compose.yml', '-f', 'docker-compose.gpu.yml')
$rollbackCompose = $baseCompose + @('-f', 'docker-compose.release.yml')
$runId = Get-Date -Format 'yyyyMMddHHmmss'
$savedReleaseId = $env:VIDEO_RELEASE_ID
$savedApiImage = $env:VIDEO_RELEASE_API_IMAGE
$savedDispatcherImage = $env:VIDEO_RELEASE_DISPATCHER_IMAGE
$savedWorkerImage = $env:VIDEO_RELEASE_WORKER_IMAGE

function Invoke-Checked {
    param([string]$Program, [string[]]$CommandArgs)
    & $Program @CommandArgs
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}

function Get-RunningImage {
    param([string]$Service)
    $container = & docker @baseCompose ps -q $Service
    if ($LASTEXITCODE -ne 0) { throw "Cannot access Docker Compose while inspecting $Service" }
    if (-not $container) { throw "No running $Service container" }
    $imageId = & docker inspect --format '{{.Image}}' $container
    if ($LASTEXITCODE -ne 0 -or -not $imageId) { throw "Cannot inspect $Service image" }
    return $imageId.Trim()
}

function Wait-Ready {
    $deadline = (Get-Date).AddMinutes(3)
    while ((Get-Date) -lt $deadline) {
        try {
            $ready = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health/ready' -TimeoutSec 5
            if ($ready.status -eq 'ok') { return }
        } catch { }
        Start-Sleep -Seconds 2
    }
    throw 'Service did not become ready within 3 minutes'
}

function Assert-Idle {
    $metrics = (Invoke-WebRequest -Uri 'http://127.0.0.1:8000/metrics' -UseBasicParsing -TimeoutSec 10).Content
    if ($metrics -notmatch '(?m)^video_jobs_outstanding 0$') {
        throw 'Outstanding GPU jobs exist; wait for them before switching images'
    }
}

if (-not (Test-Path -LiteralPath $python)) { throw 'Project Python environment is missing' }
if (-not (Test-Path -LiteralPath $Video)) { throw "Video is missing: $Video" }
if (-not (Test-Path -LiteralPath 'reports/gpu_service_smoke_current.json')) {
    throw 'Run the current-image GPU smoke before the release exercise'
}
$baselineJob = (Get-Content 'reports/gpu_service_smoke_current.json' -Raw | ConvertFrom-Json).runs[0].job_id
Assert-Idle
$live = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health/live' -TimeoutSec 10
if ($null -ne $live.release_id) { throw 'Expected the verified previous image without release metadata' }

$baseline = @{}
foreach ($service in @('api', 'dispatcher', 'worker')) {
    $imageId = Get-RunningImage $service
    $tag = "video-mlops-demo/${service}:baseline-${runId}"
    Invoke-Checked docker @('image', 'tag', $imageId, $tag)
    $baseline[$service] = @{ image_id = $imageId; tag = $tag }
}
$candidateId = "candidate-$runId"
$candidateReport = "reports/release_candidate_${runId}.json"
$rollbackReport = "reports/release_rollback_${runId}.json"
$candidate = @{}
$candidateDeployed = $false
$errorDuringCandidate = $null
try {
    $env:VIDEO_RELEASE_ID = $candidateId
    Invoke-Checked docker ($baseCompose + @('build', 'api', 'dispatcher', 'worker'))
    Assert-Idle
    $candidateDeployed = $true
    Invoke-Checked docker ($baseCompose + @('up', '-d', '--no-deps', '--no-build', '--force-recreate', 'api', 'dispatcher', 'worker'))
    Wait-Ready
    foreach ($service in @('api', 'dispatcher', 'worker')) {
        $imageId = Get-RunningImage $service
        $tag = "video-mlops-demo/${service}:candidate-${runId}"
        Invoke-Checked docker @('image', 'tag', $imageId, $tag)
        $candidate[$service] = @{ image_id = $imageId; tag = $tag }
    }
    Invoke-Checked $python @('-m', 'scripts.release_probe', '--video', $Video,
        '--expected-release', $candidateId, '--preserve', $baselineJob, '--output', $candidateReport)
} catch {
    $errorDuringCandidate = $_
}

if ($candidateDeployed) {
    try {
        Assert-Idle
        $env:VIDEO_RELEASE_API_IMAGE = $baseline.api.tag
        $env:VIDEO_RELEASE_DISPATCHER_IMAGE = $baseline.dispatcher.tag
        $env:VIDEO_RELEASE_WORKER_IMAGE = $baseline.worker.tag
        $env:VIDEO_RELEASE_ID = 'baseline'
        Invoke-Checked docker ($rollbackCompose + @('up', '-d', '--no-deps', '--no-build', '--force-recreate', 'api', 'dispatcher', 'worker'))
        Wait-Ready
        foreach ($service in @('api', 'dispatcher', 'worker')) {
            if ((Get-RunningImage $service) -ne $baseline[$service].image_id) {
                throw "Rollback image mismatch for $service"
            }
        }
        if (-not $errorDuringCandidate) {
            $candidateJob = (Get-Content $candidateReport -Raw | ConvertFrom-Json).new_job_id
            Invoke-Checked $python @('-m', 'scripts.release_probe', '--video', $Video,
                '--legacy-release', '--preserve', $baselineJob, '--preserve', $candidateJob,
                '--output', $rollbackReport)
            $before = (Get-Content $candidateReport -Raw | ConvertFrom-Json).preserved[0].result_hash
            $rollbackProbe = Get-Content $rollbackReport -Raw | ConvertFrom-Json
            $after = $rollbackProbe.preserved[0].result_hash
            if ($before -ne $after) { throw 'Baseline persisted result changed across rollout/rollback' }
            $candidateResultHash = (Get-Content $candidateReport -Raw | ConvertFrom-Json).new_result_hash
            if ($candidateResultHash -ne $rollbackProbe.preserved[1].result_hash) {
                throw 'Candidate persisted result changed during rollback'
            }
        }
        foreach ($service in @('api', 'dispatcher', 'worker')) {
            Invoke-Checked docker @('image', 'tag', $baseline[$service].image_id,
                "efficient-training-of-llms-${service}:latest")
        }
    } catch {
        Write-Warning "Rollback verification failed: $_"
        throw
    } finally {
        $env:VIDEO_RELEASE_ID = $savedReleaseId
        $env:VIDEO_RELEASE_API_IMAGE = $savedApiImage
        $env:VIDEO_RELEASE_DISPATCHER_IMAGE = $savedDispatcherImage
        $env:VIDEO_RELEASE_WORKER_IMAGE = $savedWorkerImage
    }
} else {
    $env:VIDEO_RELEASE_ID = $savedReleaseId
}
if ($errorDuringCandidate) { throw $errorDuringCandidate }
$report = @{
    schema_version = '1'; exercised_at = (Get-Date).ToUniversalTime().ToString('o')
    purpose = 'local operational service release and compatible rollback'
    baseline = $baseline; candidate = $candidate; baseline_job_id = $baselineJob
    candidate_probe = $candidateReport; rollback_probe = $rollbackReport
    source_commit = (& git rev-parse HEAD); source_dirty = [bool](& git status --porcelain)
    passed = $true
    limits = @('This is an operational service exercise, not model-quality promotion.',
        'Local image IDs identify content; tags are mutable and no remote registry deployment occurred.')
}
$reportPath = "reports/release_demo_${runId}.json"
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding utf8
Write-Output "PASS local release and rollback. Evidence: $reportPath"
