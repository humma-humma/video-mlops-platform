import os, time
import pandas as pd
from config import *
from model_utils import load_model
from audio_utils import get_audio_transcript
from inference_utils import (
    create_messages, run_inference, save_results_to_csv, save_stats_to_json
)
from evaluation_utils import evaluate_with_stats

def main():
    start_time = time.time()

    processor, model, model_load_time = load_model(MODEL_NAME, DEVICE)

    res_dict, summary_times, category_times = {}, [], []

    video_ids = [v for v in os.listdir(VIDEO_FOLDER) if v.endswith(('.mp4'))]
    if SAMPLE_VIDEO:
        video_ids = video_ids[:SAMPLE_SIZE]
    print(f"Processing {len(video_ids)} videos...")

    for vid_file in video_ids:
        video_id = vid_file.split(".mp4")[0]
        video_path = os.path.join(VIDEO_FOLDER, vid_file)

        transcript = get_audio_transcript(video_id, video_path, AUDIO_FOLDER, AUDIO_TRANSCRIPT_FOLDER)

        # ---- Summary Generation ----
        summary_msg = create_messages(video_path, transcript, mode="summary")
        summary, t1 = run_inference(processor, model, summary_msg, mode="summary")
        summary_times.append(t1)

        # ---- Category Generation ----
        category_msg = create_messages(video_path, transcript, mode="category")
        category, t2 = run_inference(processor, model, category_msg, mode="category")
        category_times.append(t2)

        res_dict[video_id] = {"summary": summary, "category": category}

    total_time = time.time() - start_time

    response_df = save_results_to_csv(res_dict, CSV_PATH)

    ground_truth = pd.read_csv(GROUND_TRUTH_FILE)
    # response_df = pd.DataFrame.from_dict(res_dict, orient="index").reset_index()
    # response_df.rename(columns={"index": "video_id"}, inplace=True)

    ground_truth_video_ids = set(ground_truth['video_id'].astype(str).tolist())
    response_video_ids = set(response_df['video_id'].astype(str).tolist())
    common_video_ids = ground_truth_video_ids.intersection(response_video_ids)
    ground_truth = ground_truth[ground_truth['video_id'].astype(str).isin(common_video_ids)]
    response_df = response_df[response_df['video_id'].astype(str).isin(common_video_ids)]

    # Sort the dataframes by video_id to ensure alignment
    ground_truth = ground_truth.sort_values(by='video_id').reset_index(drop=True)
    response_df = response_df.sort_values(by='video_id').reset_index(drop=True)
    # assert video ids are aligned
    # print("Asserting video ID alignment between ground truth and response dataframes...")
    # assert all(ground_truth['video_id'].astype(str) == response_df['video_id'].astype(str))
    # ground_truth = ground_truth[ground_truth['video_id'].astype(str).isin(response_df['video_id'].astype(str))]
    print(f"Ground truth size: {len(ground_truth)}, Response size: {len(response_df)}")

    evaluation_results = evaluate_with_stats(ground_truth, response_df)

    save_stats_to_json(MODEL_NAME, model_load_time, total_time, summary_times, category_times, evaluation_results, STAT_JSON_PATH)

    print("✅ Inference completed.")

if __name__ == "__main__":
    main()
