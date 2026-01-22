import itertools
import time

import pandas as pd
from tqdm import tqdm

from src.audio_utils import get_audio_transcript
from src.config import ConfigClass
from src.evaluation_utils import evaluate_with_stats
from src.inference_utils import (
    create_messages,
    run_inference,
    save_results_to_csv,
    save_stats_to_json,
)
from src.model_utils import load_model


def main(cfg: ConfigClass) -> None:
    start_time = time.perf_counter()

    processor, model, model_load_time = load_model(cfg.model_name, cfg.device)

    video_id_iter = cfg.video_folder.glob("*.mp4")
    if cfg.num_video_samples > 0:
        video_ids = itertools.islice(video_id_iter, cfg.num_video_samples)
    video_ids = tuple(video_id_iter)
    print(f"Processing {len(video_ids)} videos...")

    res_dict, summary_times, category_times = {}, [], []
    for video_path in tqdm(video_ids, desc="Processing videos"):
        video_id = video_path.stem

        transcript = get_audio_transcript(
            video_id,
            video_path,
            cfg.audio_folder,
            cfg.audio_transcript_folder,
        )

        # ---- Summary Generation ----
        summary_msg = create_messages(video_path, transcript, mode="summary")
        summary, t1 = run_inference(processor, model, summary_msg, mode="summary")
        summary_times.append(t1)

        # ---- Category Generation ----
        category_msg = create_messages(video_path, transcript, mode="category")
        category, t2 = run_inference(processor, model, category_msg, mode="category")
        category_times.append(t2)

        res_dict[video_id] = {"summary": summary, "category": category}

    total_time = time.perf_counter() - start_time

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

    evaluation_results = evaluate_with_stats(ground_truth, response_df)

    output_json_stat_path = cfg.statistics_folder / f"{cfg.file_name}_stats.json"

    save_stats_to_json(
        cfg.model_name,
        model_load_time,
        total_time,
        summary_times,
        category_times,
        evaluation_results,
        output_json_stat_path,
    )

    print("✅ Inference completed.")


if __name__ == "__main__":
    from argparse_dataclass import ArgumentParser

    parser = ArgumentParser(ConfigClass, description="Run VLM Inference")
    cfg = parser.parse_args()
    main(cfg)
