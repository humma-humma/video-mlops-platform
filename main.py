from dataclasses import asdict
import time

from src.config import InferenceConfig
from src.pipeline import (
    prepare_videos,
    run_batch_inference,
    run_isolated_inference,
    select_video_paths,
)


def validate_inputs(cfg: InferenceConfig) -> tuple:
    if not cfg.video_folder.is_dir():
        raise FileNotFoundError(f"Video folder does not exist: {cfg.video_folder}")
    if not cfg.ground_truth_file.is_file():
        raise FileNotFoundError(f"Ground truth file does not exist: {cfg.ground_truth_file}")

    video_ids = select_video_paths(cfg.video_folder, cfg.num_video_samples)
    if not video_ids:
        raise FileNotFoundError(f"No .mp4 files found in {cfg.video_folder}")
    return video_ids


def main(cfg: InferenceConfig) -> None:
    video_ids = validate_inputs(cfg)

    import pandas as pd

    from src.audio_utils import get_audio_transcript
    from src.evaluation_utils import evaluate_with_stats
    from src.inference_utils import (
        create_messages,
        run_inference,
        save_results_to_csv,
        save_stats_to_json,
    )
    from src.model_utils import load_model

    print(f"🚀 Starting inference...\n{cfg}")
    start_time = time.perf_counter()

    pipe, model_load_time = load_model(cfg)

    print(f"🚀 Processing {len(video_ids)} videos...")

    prepared_videos, input_preparation_time = prepare_videos(
        video_ids,
        transcript_loader=lambda video_id, video_path: get_audio_transcript(
            video_id,
            video_path,
            cfg.audio_folder,
            cfg.audio_transcript_folder,
            device_id=cfg.whisper_device_id,
        ),
        message_factory=lambda video_path, transcript, mode: create_messages(
            video_path, transcript, mode=mode
        ),
    )

    def inference(messages, mode):
        return run_inference(pipe, messages, mode=mode)

    if cfg.inference_strategy == "batch_two_pass":
        predictions = run_batch_inference(prepared_videos, inference=inference)
    else:
        predictions = run_isolated_inference(
            prepared_videos,
            inference=inference,
            strategy=cfg.inference_strategy,
        )
    summary_time = predictions.summary_time
    category_time = predictions.category_time
    combined_time = predictions.combined_time
    print(
        f"✅ Inference completed: summary={summary_time:.2f}s, "
        f"category={category_time:.2f}s, combined={combined_time:.2f}s, "
        f"failures={len(predictions.failures)}"
    )
    res_dict = predictions.as_result_dict()

    output_csv_path = cfg.csv_folder / f"{cfg.file_name}.csv"
    response_df = save_results_to_csv(res_dict, output_csv_path)

    ground_truth = pd.read_csv(cfg.ground_truth_file)
    # response_df = pd.DataFrame.from_dict(res_dict, orient="index").reset_index()
    # response_df.rename(columns={"index": "video_id"}, inplace=True)

    ground_truth_video_ids = set(ground_truth["video_id"].astype(str).tolist())
    response_video_ids = set(response_df["video_id"].astype(str).tolist())
    common_video_ids = ground_truth_video_ids.intersection(response_video_ids)
    ground_truth = ground_truth[
        ground_truth["video_id"].astype(str).isin(common_video_ids)
    ]
    response_df = response_df[
        response_df["video_id"].astype(str).isin(common_video_ids)
    ]

    # Sort the dataframes by video_id to ensure alignment
    ground_truth = ground_truth.sort_values(by="video_id").reset_index(drop=True)
    response_df = response_df.sort_values(by="video_id").reset_index(drop=True)
    # assert video ids are aligned
    # print("Asserting video ID alignment between ground truth and response dataframes...")
    # assert all(ground_truth['video_id'].astype(str) == response_df['video_id'].astype(str))
    # ground_truth = ground_truth[ground_truth['video_id'].astype(str).isin(response_df['video_id'].astype(str))]
    print(f"Ground truth size: {len(ground_truth)}, Response size: {len(response_df)}")

    evaluation_start = time.perf_counter()
    if ground_truth.empty or response_df.empty:
        evaluation_results = {
            "status": "skipped",
            "reason": "No successful predictions matched ground truth",
        }
    else:
        evaluation_results = evaluate_with_stats(ground_truth, response_df)
    evaluation_time = time.perf_counter() - evaluation_start
    total_time = time.perf_counter() - start_time

    output_json_stat_path = cfg.statistics_folder / f"{cfg.file_name}_stats.json"

    save_stats_to_json(
        cfg.model_name,
        model_load_time,
        total_time,
        summary_time,
        category_time,
        len(video_ids),
        evaluation_results,
        output_json_stat_path,
        stage_timings={
            "input_preparation": input_preparation_time,
            "summary_inference": summary_time,
            "category_inference": category_time,
            "combined_inference": combined_time,
            "evaluation": evaluation_time,
        },
        combined_time=combined_time,
        inference_strategy=predictions.strategy,
        per_video_timings=[
            {
                "video_id": prediction.video_id,
                "summary_time": prediction.summary_time,
                "category_time": prediction.category_time,
                "combined_time": prediction.combined_time,
            }
            for prediction in predictions.predictions
        ],
        failures=[asdict(failure) for failure in predictions.failures],
    )

    print("✅ Inference completed.")


if __name__ == "__main__":
    from argparse_dataclass import ArgumentParser

    parser = ArgumentParser(InferenceConfig, description="Run VLM Inference")
    cfg = parser.parse_args()
    main(cfg)
