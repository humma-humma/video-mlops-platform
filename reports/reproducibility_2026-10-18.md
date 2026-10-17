# Local reproducibility check — 2026-10-18

Scope: current `portfolio-main` workspace on Windows, using the existing project `.venv`, Node.js and Docker CLI. The README and service timeline changes were present during this check. This report is a local check, not a fresh-clone or real-GPU acceptance.

The video model revision and CPU model artifact are identified, but service-test dependency ranges and some container image tags are mutable. Passing checks establish functional behavior in the tested environment, not identical dependency bytes on every future installation.

| Check | Result |
| --- | --- |
| Dataset manifest verification | **PASS** — `python -m scripts.verify_manifest`; manifest SHA-256 `fa6422f1f519e63fe0c3a8c9c25295640e21af9513f1111265c16e9e2b27dfc2`. |
| Video demo and operations UI behavior | **PASS** — five `demo_ui.test.cjs` and two `operations_ui.test.cjs` checks. These are Node behavior tests, not a new browser review. |
| Focused Python contracts | **PASS** — 11 tests across `test_text_model.py`, `test_service_config.py` and `test_dataset_manifest.py`. |
| Compose configuration | **PASS** — both base + CI and base + GPU overrides parsed with `docker compose ... config --quiet`. |
| README, timeline and report local links | **PASS** — 35 README links, 26 timeline links and four report links checked; no missing local targets. |
| Diff whitespace | **PASS** — `git diff --check`. |
| Full Python suite | **INCONCLUSIVE IN THIS SESSION** — 103 passed, one optional test skipped and 60 test setups errored because pytest could not create its temporary `.lock` under the Windows temp path (`PermissionError`). A retry with a new workspace-local `--basetemp` also met an access-denied error on that generated directory. These are filesystem permissions in the agent session, not observed assertion failures. |
| Live Compose and inference smoke | **NOT RUN** — `docker info` was denied access to `//./pipe/dockerDesktopLinuxEngine`. No live job or GPU claim is based on this check. |

The earlier [GitHub Actions run for the two-deployment version](https://github.com/humma-humma/video-mlops-platform/actions/runs/39071741619) passed on the remote runner, according to the recorded delivery result. Its CPU/UI and fake-worker S3Mock checks are separate from this local check and from the [real GPU acceptance](gpu_service_smoke_current.json).

To complete a fresh local acceptance from an unrestricted project PowerShell, run the [README checks](../README.md#reproduce-the-checks), then the CPU and GPU smoke commands against the intended Compose mode. The full [local acceptance script](../scripts/verify_local.ps1) can also rebuild and change the stack; review its prerequisites before using it with existing named volumes.
