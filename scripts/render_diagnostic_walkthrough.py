"""Render a short, clearly labeled walkthrough from committed incident evidence."""

import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "portfolio"
SLIDES = OUT / "diagnostic_walkthrough_slides"
FONT = Path("C:/Windows/Fonts/segoeui.ttf")
FONT_BOLD = Path("C:/Windows/Fonts/segoeuib.ttf")


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def font(size, bold=False):
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT), size)


def slide(number, title, kicker, lines, source):
    image = Image.new("RGB", (1280, 720), "#0d1421")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((48, 44, 1232, 676), radius=24, fill="#182538", outline="#30455f", width=2)
    draw.text((78, 69), "VIDEO-MLOPS  /  DIAGNOSTIC WORKBENCH", font=font(21, True), fill="#74b2ff")
    draw.text((78, 119), title, font=font(43, True), fill="#f5f8ff")
    draw.text((79, 183), kicker, font=font(24), fill="#aac1df")
    y = 254
    for label, value in lines:
        draw.rounded_rectangle((78, y, 1200, y + 78), radius=12, fill="#21334a")
        draw.text((100, y + 9), label.upper(), font=font(17, True), fill="#85b9ff")
        draw.text((100, y + 37), value, font=font(25), fill="#ffffff")
        y += 93
    draw.text((79, 628), source, font=font(17), fill="#a5b9d2")
    draw.text((1116, 628), f"{number} / 5", font=font(18, True), fill="#a5b9d2")
    path = SLIDES / f"{number:02d}.png"
    image.save(path)
    return path


def main():
    if not FONT.exists() or not FONT_BOLD.exists():
        raise RuntimeError("Segoe UI fonts required for this Windows renderer")
    SLIDES.mkdir(parents=True, exist_ok=True)
    model = read("reports/diagnostics/model-artifact-live/evaluation.json")
    restoration = read("reports/diagnostics/model-artifact-live/run_state.json")
    loss = read("reports/diagnostics/result-loss-live/evaluation.json")
    loss_state = read("reports/diagnostics/result-loss-live/run_state.json")
    recovery = read("reports/recovery_demo.json")
    replay = read("reports/diagnostics/proposals/model_artifact_replay.json")
    if not (model["correct_diagnoses"] == 1 and restoration["artifact_restored_exactly"]
            and loss["correct_abstentions"] == 1 and loss_state["object_restored_exactly"]):
        raise RuntimeError("Walkthrough evidence is incomplete")
    pages = [
        slide(1, "Evidence before diagnosis", "Recorded local evidence · October 2026 · no live service required", [
            ("Boundary", "Read-only export → redacted bundle → offline diagnosis"),
            ("What to inspect", "Attempts, failure stages, citations, missing evidence"),
            ("Claim", "One-host acceptance checks, not production RCA accuracy"),
        ], "docs/DIAGNOSTIC_WORKBENCH.md"),
        slide(2, "A supported finding", "Controlled CPU model-artifact loss", [
            ("Worker attempt", "FAILED · model_artifact_unavailable"),
            ("Cited diagnosis", "Status + attempt error code · 1/1 development check"),
            ("Recovery", "Exact artifact restored; next CPU job succeeded"),
        ], "reports/diagnostics/model-artifact-live/incident.json"),
        slide(3, "When evidence is insufficient", "Controlled loss of one successful job's result object", [
            ("Observed", "Job stayed SUCCEEDED; result read returned HTTP 503"),
            ("Decision", "Abstain · bundle cannot prove which storage fault occurred"),
            ("Recovery", "Exact result bytes restored; API read returned HTTP 200"),
        ], "reports/diagnostics/result-loss-live/incident.json"),
        slide(4, "Persistence and recovery", "Earlier controlled active GPU-worker interruption", [
            ("Durable history", "First attempt timed out; explicit retry succeeded"),
            ("Evidence", "Worker event and timed-out attempt are both required"),
            ("Limit", "A local kill is not a production availability estimate"),
        ], "reports/recovery_demo.json"),
        slide(5, "A proposal stays reviewable", "Offline build-gate replay · no deployment changed", [
            ("Patch", "Check packaged CPU model hash during image build"),
            ("Replay", "Healthy accepted; missing artifact rejected"),
            ("Next", "Human review, isolated image build, then release gate"),
        ], "reports/diagnostics/proposals/model_artifact_replay.json"),
    ]
    if (recovery["final_status"] != "SUCCEEDED"
            or [attempt["status"] for attempt in recovery["attempts"]] != ["FAILED", "SUCCEEDED"]
            or replay["scenarios"]["missing_artifact"]["candidate_gate"]["accepted"]):
        raise RuntimeError("Recovery or proposal evidence changed")
    manifest = SLIDES / "slides.txt"
    with manifest.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("".join(f"file '{path.name}'\nduration 8\n" for path in pages)
                     + f"file '{pages[-1].name}'\n")
    target = OUT / "diagnostic_walkthrough.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(manifest), "-t", "40", "-vf", "fps=25,format=yuv420p", "-c:v", "libx264",
                    "-movflags", "+faststart", str(target)], check=True, timeout=180)
    print(f"Rendered evidence walkthrough: {target}")


if __name__ == "__main__":
    main()
