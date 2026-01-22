from pathlib import Path

import cv2


def extract_frames_1fps(video_path: Path, video_id: str, output_folder: Path) -> None:
    """Extracts frames from a video at a rate of 1 frame per second using OpenCV.

    Args:
        video_path (str): Path to the input video file.
        output_folder (str): Folder to save the extracted frames.

    """
    cur_frames_folder = output_folder / video_id
    cur_frames_folder.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video {video_path}")
        return

    native_fps = cap.get(cv2.CAP_PROP_FPS)
    if native_fps <= 0:
        print(f"Warning: Could not determine FPS for {video_path}. Skipping.")
        cap.release()
        return

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # We calculate the frame index for every second
    # Using a list of specific frame indices to "jump" to
    duration_sec = int(total_frames // native_fps)

    saved_frame_count = 0

    for second in range(duration_sec):
        # Calculate exactly which frame index corresponds to this second
        frame_id = int(second * native_fps)

        if frame_id >= total_frames:
            break

        # "Jump" the video pointer to the specific frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
        ret, frame = cap.read()

        if not ret:
            break

        # Format timestamp for filename (e.g., 00012_000s)
        timestamp_str = f"{second:08.3f}s".replace(".", "_")
        frame_filename = cur_frames_folder / f"frame_{timestamp_str}.jpg"

        try:
            cv2.imwrite(frame_filename, frame)
        except Exception as e:
            print(f"Error writing frame {frame_filename!s}: {e}")
        else:
            saved_frame_count += 1

    cap.release()
    print(f"Finished. Saved {saved_frame_count} frames to {cur_frames_folder}")


# output_dir = "path/to/output/frames"
# extract_frames_1fps(video_file, output_dir)
