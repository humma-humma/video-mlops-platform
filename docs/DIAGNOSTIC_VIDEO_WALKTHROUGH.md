# Recorded-evidence walkthrough

[Play the 40-second MP4](../assets/portfolio/diagnostic_walkthrough.mp4). Five captioned slides show: the read-only evidence boundary; a cited model-artifact finding; abstention on an unavailable result; an earlier worker-recovery timeline; and an unapplied build-gate proposal. Each slide names its source report. The video contains no narration or live browser footage. It is meant for reviewers who need a quick orientation before following the case index, not as a substitute for the linked evidence.

The source is [the renderer](../scripts/render_diagnostic_walkthrough.py) and the [generated slides](../assets/portfolio/diagnostic_walkthrough_slides). Re-render on Windows with Python 3.12, Pillow, FFmpeg and Segoe UI installed:

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.replay_model_artifact_proposal
python -m scripts.render_diagnostic_walkthrough
ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 assets/portfolio/diagnostic_walkthrough.mp4
```

The renderer checks key report fields before creating the video. Its text is a concise interpretation of the committed local evidence. The live UI and GPU job flow remain documented in [the separate browser walkthrough script](WALKTHROUGH_SCRIPT.md); that browser recording is not claimed here.
