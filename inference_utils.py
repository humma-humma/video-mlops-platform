import os, time, numpy as np, pandas as pd, json, torch

def create_messages(video_path: str, transcript: str, mode: str = "summary"):
    """Create system messages for summary or category inference."""
    if mode == "summary":
        text = (
            f"Describe this video in detail. Use the audio transcript to get more context. Audio Transcript: {transcript}"
        )
    else:
        text = (
            "You are a video classification expert. Watch the video carefully and assign it to exactly one of the following categories:\n\n"
            "1. News\n"
            "2. Politics\n"
            "3. Music, Singing, & Dancing\n"
            "4. Comedy\n"
            "5. Sports\n"
            "6. Film & Animation\n"
            "7. Pets & Animals\n"
            "8. Entertainment & Shows\n"
            "9. Gaming\n"
            "10. Science & Technology\n"
            "11. Autos & Vehicles\n"
            "12. Education\n"
            "13. Outfit, Style, & Howto\n"
            "14. Nonprofits & Activism\n"
            "15. Travel & Events\n"
            "16. People & Blogs\n"
            "17. Food\n"
            "18. Relationship\n"
            "19. Family\n"
            "20. Beauty Care\n"
            "21. Daily Life\n"
            "22. Drama\n"
            "23. Lipsync\n"
            "24. Fitness & Health\n"
            "25. Society\n\n"
            "Use both the visuals and the audio transcript to determine the most relevant single category. "
            "Consider what the video is *primarily* about, not minor elements or background music. "
            "Do not include explanations or reasoning — respond with only the category name.\n\n"
            f"Audio Transcript: {transcript}"
        )

    return [
        {
            "role": "user",
            "content": [
                {"type": "video", "path": video_path},
                {"type": "text", "text": text},
            ],
        }
    ]


def create_messages_old(video_path: str, transcript: str, mode: str = "summary"):
    """Create system messages for summary or category inference."""
    if mode == "summary":
        text = f"Describe this video in detail. Use the audio transcript to get more context. Audio Transcript: {transcript}"
    else:
        text = (
            # "Analyze the video and categorize it into one of the following categories: "
            # "'News, Politics, Music, Comedy, Sports, Film, Pets, Entertainment, Gaming, "
            # "Science, Autos, Education, Style, Nonprofits, Travel, People, Food, "
            # "Relationship, Family, Beauty, Daily Life, Drama, Lipsync, Fitness, Society'. "
            """'News, Politics, `Music, Singing, & Dancing`, Comedy, Sports, Film & Animation, Pets & Animals, Entertainment & Shows, Gaming, Science & Technology, Autos & Vehicles, Education, `Outfit, Style, & Howto`, Nonprofits & Activism, Travel & Events, People & Blogs, Food, Relationship, Family, Beauty Care, Daily Life, Drama, Lipsync, Fitness & Health, Society'`
            Each video should be classified into only one category. Note that Music, Singing, & Dancing is one category and Outfit, Style, & Howto is another category."""
            f"Use the audio transcript to get more context. Audio Transcript: {transcript}. "
            "You must provide only a single category from the provided categories as the response."
        )

    return [{"role": "user", "content": [{"type": "video", "path": video_path}, {"type": "text", "text": text}]}]


def run_inference(processor, model, messages, max_new_tokens=140, mode="category"):
    """Run inference and measure time."""
    start = time.time()
    inputs = processor.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=True,
        return_dict=True, return_tensors="pt"
    ).to(model.device, dtype=torch.bfloat16)

    if mode == "category":
        max_new_tokens = 64
    ids = model.generate(**inputs, do_sample=False, max_new_tokens=max_new_tokens)
    text = processor.batch_decode(ids, skip_special_tokens=True)[0]
    end = time.time()
    return text.split("Assistant:")[-1].strip(), end - start


def save_results_to_csv(res_dict, csv_path):
    df = pd.DataFrame.from_dict(res_dict, orient="index").reset_index()
    df.rename(columns={"index": "video_id"}, inplace=True)
    df.to_csv(csv_path, index=False)
    print(f"✅ Saved results to {csv_path}")
    return df


def save_stats_to_json(model_name, model_load_time, total_time, summary_times, category_times, evaluation_results, output_path):
    stats = {
        "model_name": model_name,
        "model_load_time": model_load_time,
        "total_time": total_time,
        "summary_inference": {
            "mean": float(np.mean(summary_times)),
            "min": float(np.min(summary_times)),
            "max": float(np.max(summary_times)),
            "std": float(np.std(summary_times)),
        },
        "category_inference": {
            "mean": float(np.mean(category_times)),
            "min": float(np.min(category_times)),
            "max": float(np.max(category_times)),
            "std": float(np.std(category_times)),
        },
        "evaluation_results": evaluation_results
    }
    with open(output_path, 'w') as f:
        json.dump(stats, f, indent=4)
    print(f"📊 Saved statistics to {output_path}")
