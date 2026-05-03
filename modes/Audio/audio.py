import os
import wave
from flask import Blueprint, current_app, render_template, request, flash, redirect, url_for
from werkzeug.utils import secure_filename

audio = Blueprint("audio", __name__, static_folder="static", template_folder="templates")

# Unique end-of-message sentinel (unlikely to appear in normal text)
SENTINEL = "<<EOM>>"


def _allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'wav'}


@audio.route("/encode")
def audio_encode():
    return render_template("encode-audio.html")


@audio.route("/encode-result", methods=['POST'])
def audio_encode_result():
    folder  = current_app.config['UPLOAD_AUDIO_FOLDER']
    message = request.form.get('message', '').strip()
    file    = request.files.get('audio')

    if not message:
        flash("Please enter a message to hide.", "error")
        return redirect(url_for('audio.audio_encode'))
    if not file or file.filename == '':
        flash("Please upload a WAV audio file.", "error")
        return redirect(url_for('audio.audio_encode'))
    if not _allowed(file.filename):
        flash("Only WAV audio files are supported.", "error")
        return redirect(url_for('audio.audio_encode'))

    try:
        in_path  = os.path.join(folder, secure_filename(file.filename))
        out_path = os.path.join(folder, "encoded_audio.wav")
        file.save(in_path)
        encrypt_audio(in_path, message, out_path)
        return render_template("encode-audio-result.html",
                               filename=file.filename,
                               message=message,
                               success=True)
    except OverflowError as e:
        flash(str(e), "error")
        return redirect(url_for('audio.audio_encode'))
    except Exception as e:
        flash(f"Encoding failed: {str(e)}", "error")
        return redirect(url_for('audio.audio_encode'))


@audio.route("/decode")
def audio_decode():
    return render_template("decode-audio.html")


@audio.route("/decode-result", methods=['POST'])
def audio_decode_result():
    folder = current_app.config['UPLOAD_AUDIO_FOLDER']
    file   = request.files.get('audio')

    if not file or file.filename == '':
        flash("Please upload a WAV audio file.", "error")
        return redirect(url_for('audio.audio_decode'))
    if not _allowed(file.filename):
        flash("Only WAV audio files are supported.", "error")
        return redirect(url_for('audio.audio_decode'))

    try:
        path = os.path.join(folder, secure_filename(file.filename))
        file.save(path)
        message = decrypt_audio(path)
        if not message:
            flash("No hidden message found in this audio file.", "warning")
            return redirect(url_for('audio.audio_decode'))
        return render_template("decode-audio-result.html",
                               filename=file.filename,
                               message=message,
                               success=True)
    except Exception as e:
        flash(f"Decoding failed: {str(e)}", "error")
        return redirect(url_for('audio.audio_decode'))


# ── Core algorithms ───────────────────────────────────────────────────────────

def encrypt_audio(in_path, message, out_path):
    with wave.open(in_path, 'rb') as song:
        params = song.getparams()
        frame_bytes = bytearray(song.readframes(song.getnframes()))

    full_message = message + SENTINEL
    bits_needed  = len(full_message) * 8

    if bits_needed > len(frame_bytes):
        raise OverflowError(
            f"Message too long for this audio file. "
            f"Max ~{len(frame_bytes) // 8} characters, got {len(full_message)}."
        )

    # Convert message to bit array
    bits = [int(b) for ch in full_message for b in format(ord(ch), '08b')]

    # Replace LSB of each audio byte with one message bit
    for i, bit in enumerate(bits):
        frame_bytes[i] = (frame_bytes[i] & 0xFE) | bit

    with wave.open(out_path, 'wb') as fd:
        fd.setparams(params)
        fd.writeframes(bytes(frame_bytes))


def decrypt_audio(path):
    with wave.open(path, 'rb') as song:
        frame_bytes = bytearray(song.readframes(song.getnframes()))

    # Extract LSBs
    bits = [frame_bytes[i] & 1 for i in range(len(frame_bytes))]

    # Reconstruct characters
    chars = []
    for i in range(0, len(bits) - 7, 8):
        ch = chr(int(''.join(map(str, bits[i:i+8])), 2))
        chars.append(ch)

    text = ''.join(chars)
    # Find our sentinel and cut
    if SENTINEL in text:
        return text.split(SENTINEL)[0]

    # Fallback: old-format files that used '#' padding
    if '#' in text:
        return text.split('##')[0]

    return text[:500]  # safety cap
