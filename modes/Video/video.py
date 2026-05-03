"""
Video steganography with fixed-frame LSB embedding.
Encodes and decodes from the same frame index to avoid mismatch.
"""

import os

import cv2
import numpy as np
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

video = Blueprint("video", __name__, static_folder="static", template_folder="templates")

ALLOWED = {"mp4", "avi", "mov", "mkv"}
FRAME_INDEX = 0
SENTINEL = "<<EOM>>".encode("utf-8")


def _allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED


# Routes
@video.route("/encode")
def video_encode():
    return render_template("encode-video.html")


@video.route("/encode-result", methods=["POST"])
def video_encode_result():
    folder = current_app.config["UPLOAD_VIDEO_FOLDER"]
    message = request.form.get("message", "").strip()
    file = request.files.get("video")

    if not message:
        flash("Please enter a message to hide.", "error")
        return redirect(url_for("video.video_encode"))
    if not file or file.filename == "":
        flash("Please upload a video file.", "error")
        return redirect(url_for("video.video_encode"))
    if not _allowed(file.filename):
        flash("Only MP4, AVI, MOV, or MKV video files are supported.", "error")
        return redirect(url_for("video.video_encode"))

    try:
        in_path = os.path.join(folder, secure_filename(file.filename))
        out_path = os.path.join(folder, "encoded_video.avi")
        file.save(in_path)
        encode_video(in_path, message, out_path)
        return render_template(
            "encode-video-result.html",
            filename=file.filename,
            message=message,
            success=True,
        )
    except OverflowError as e:
        flash(str(e), "error")
        return redirect(url_for("video.video_encode"))
    except Exception as e:
        flash(f"Encoding failed: {str(e)}", "error")
        return redirect(url_for("video.video_encode"))


@video.route("/decode")
def video_decode():
    return render_template("decode-video.html")


@video.route("/decode-result", methods=["POST"])
def video_decode_result():
    folder = current_app.config["UPLOAD_VIDEO_FOLDER"]
    file = request.files.get("video")

    if not file or file.filename == "":
        flash("Please upload a video file.", "error")
        return redirect(url_for("video.video_decode"))
    if not _allowed(file.filename):
        flash("Only MP4, AVI, MOV, or MKV video files are supported.", "error")
        return redirect(url_for("video.video_decode"))

    try:
        path = os.path.join(folder, secure_filename(file.filename))
        file.save(path)
        message = decode_video(path)
        if not message:
            flash("No hidden message found in this video.", "warning")
            return redirect(url_for("video.video_decode"))
        return render_template(
            "decode-video-result.html",
            filename=file.filename,
            message=message,
            success=True,
        )
    except Exception as e:
        flash(f"Decoding failed: {str(e)}", "error")
        return redirect(url_for("video.video_decode"))


# Core algorithms
def _message_to_bits(message):
    """UTF-8 encode text, append sentinel, and return MSB-first bits."""
    payload = message.encode("utf-8") + SENTINEL
    return [int(bit) for byte in payload for bit in format(byte, "08b")]


def _bits_to_message(bits):
    """
    Decode bytes from bits until sentinel appears.
    Returns (message, delimiter_found).
    """
    decoded_bytes = []
    sentinel_len = len(SENTINEL)

    for i in range(0, len(bits) - 7, 8):
        byte_val = int("".join(map(str, bits[i : i + 8])), 2)
        decoded_bytes.append(byte_val)

        if len(decoded_bytes) >= sentinel_len:
            tail = bytes(decoded_bytes[-sentinel_len:])
            if tail == SENTINEL:
                try:
                    message = bytes(decoded_bytes[:-sentinel_len]).decode("utf-8")
                    return message, True
                except UnicodeDecodeError:
                    return "", True

    return "", False


def _load_frames(video_path):
    """Load all frames to preserve original sequence while changing one frame."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("Cannot open video file.")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()

    if not frames:
        raise ValueError("Video has no readable frames.")
    return frames, fps, width, height


def _write_video_with_safe_codec(out_path, fps, size, frames):
    """
    Use AVI codecs that preserve LSB data better than lossy MP4/H264.
    Tries lossless FFV1 first, then near-lossless MJPG.
    """
    writer = None
    chosen_codec = None
    for codec in ("FFV1", "MJPG"):
        fourcc = cv2.VideoWriter_fourcc(*codec)
        candidate = cv2.VideoWriter(out_path, fourcc, fps, size)
        if candidate.isOpened():
            writer = candidate
            chosen_codec = codec
            break
        candidate.release()

    if writer is None:
        raise RuntimeError("Could not initialize AVI writer with FFV1 or MJPG codec.")

    print(f"[video][debug] Writer codec: {chosen_codec}")
    for frame in frames:
        writer.write(frame)
    writer.release()


def encode_video(in_path, message, out_path):
    """
    Embed message bits in one fixed frame and keep all frames in sequence.
    Encoding and decoding both use FRAME_INDEX and identical bit traversal.
    """
    frames, fps, width, height = _load_frames(in_path)
    if FRAME_INDEX >= len(frames):
        raise ValueError(f"Frame index {FRAME_INDEX} is out of range for this video.")

    bits = _message_to_bits(message)
    target_frame = frames[FRAME_INDEX]
    capacity = target_frame.size
    payload_bytes = len(message.encode("utf-8")) + len(SENTINEL)
    if len(bits) > capacity:
        raise OverflowError(
            f"Message too long for frame[{FRAME_INDEX}]. "
            f"Max ~{capacity // 8} bytes (including delimiter), got {payload_bytes}."
        )

    print(f"[video][debug] Encode frame index: {FRAME_INDEX}")

    frame_flat = target_frame.reshape(-1).astype(np.uint8)
    bits_arr = np.array(bits, dtype=np.uint8)
    frame_flat[: len(bits_arr)] = (frame_flat[: len(bits_arr)] & np.uint8(0xFE)) | bits_arr
    frames[FRAME_INDEX] = frame_flat.reshape(target_frame.shape)

    debug_frame_path = os.path.join(os.path.dirname(out_path), "encoded_frame_debug.png")
    cv2.imwrite(debug_frame_path, frames[FRAME_INDEX])

    _write_video_with_safe_codec(out_path, fps, (width, height), frames)


def decode_video(in_path):
    """
    Decode from the exact same frame index used in encode_video().
    """
    cap = cv2.VideoCapture(in_path)
    if not cap.isOpened():
        raise ValueError("Cannot open video file.")

    target_frame = None
    current_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if current_index == FRAME_INDEX:
            target_frame = frame
            break
        current_index += 1
    cap.release()

    if target_frame is None:
        raise ValueError(f"Could not read frame[{FRAME_INDEX}] from the video.")

    print(f"[video][debug] Decode frame index: {FRAME_INDEX}")

    bits = [int(byte) & 1 for byte in target_frame.reshape(-1)]
    message, delimiter_found = _bits_to_message(bits)
    return message if delimiter_found else ""
