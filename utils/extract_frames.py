import cv2
import os
import numpy as np
import math

# Extract frames from videos

def extract_frames_1fps(video_path, video_id, output_folder):
    """
    Extracts frames from a video at a rate of 1 frame per second using OpenCV.

    Args:
        video_path (str): Path to the input video file.
        output_folder (str): Folder to save the extracted frames.
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video {video_path}")
        return

    native_fps = cap.get(cv2.CAP_PROP_FPS)
    if native_fps == 0:
        print(f"Warning: Could not determine FPS for video {video_path}. Skipping.")
        cap.release()
        return
        
    target_fps = 1
    # Calculate the frame interval (hop)
    # Use max(1,...) to avoid division by zero or infinite loop if target_fps > native_fps
    hop = round(native_fps / target_fps) if target_fps > 0 else 1 

    frame_count = 0
    saved_frame_count = 0

    cur_frames_folder = os.path.join(output_folder, video_id)
    if not os.path.exists(cur_frames_folder):
        os.makedirs(cur_frames_folder)

    while True:
        ret, frame = cap.read()
        if not ret:
            break # End of video

        # Save frame if it's at the desired interval
        if frame_count % hop == 0:
            # Calculate timestamp for the frame (in seconds)
            timestamp_sec = frame_count / native_fps
            # Format timestamp for filename (e.g., 00012.345s)
            timestamp_str = f"{timestamp_sec:08.3f}s".replace('.', '_') 
            
            frame_filename = os.path.join(cur_frames_folder, f"frame_{timestamp_str}.jpg")
            try:
                cv2.imwrite(frame_filename, frame)
                saved_frame_count += 1
            except Exception as e:
                print(f"Error writing frame {frame_filename}: {e}")

        frame_count += 1

    cap.release()
    print(f"Finished processing {video_path}. Saved {saved_frame_count} frames at approx 1 FPS.")

# Example usage:
# video_file = "path/to/your/tiktok_video.mp4"
# output_dir = "path/to/output/frames"
# extract_frames_1fps(video_file, output_dir)

