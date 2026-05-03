import os
from PIL import Image
from flask import Blueprint, current_app, render_template, request, flash, redirect, url_for
from werkzeug.utils import secure_filename

text = Blueprint("text", __name__, static_folder="static", template_folder="templates")

ALLOWED = {'png', 'jpg', 'jpeg', 'bmp', 'webp'}
SENTINEL = "\x00\x00\x00"   # three null bytes as end marker


def _allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED


@text.route("/encode")
def text_encode():
    out = os.path.join(current_app.config['UPLOAD_TEXT_FOLDER'], "encrypted_text_image.png")
    if os.path.exists(out):
        os.remove(out)
    return render_template("encode-text.html")


@text.route("/encode-result", methods=['POST'])
def text_encode_result():
    folder  = current_app.config['UPLOAD_TEXT_FOLDER']
    message = request.form.get('message', '').strip()
    file    = request.files.get('image')

    if not message:
        flash("Please enter a message to hide.", "error")
        return redirect(url_for('text.text_encode'))
    if not file or file.filename == '':
        flash("Please upload an image file.", "error")
        return redirect(url_for('text.text_encode'))
    if not _allowed(file.filename):
        flash("Only image files are supported (PNG, JPG, BMP, WEBP).", "error")
        return redirect(url_for('text.text_encode'))

    try:
        in_path  = os.path.join(folder, secure_filename(file.filename))
        out_path = os.path.join(folder, "encrypted_text_image.png")
        file.save(in_path)
        encrypt_text(in_path, message, out_path)
        return render_template("encode-text-result.html",
                               filename=file.filename,
                               message=message,
                               success=True)
    except OverflowError as e:
        flash(str(e), "error")
        return redirect(url_for('text.text_encode'))
    except Exception as e:
        flash(f"Encoding failed: {str(e)}", "error")
        return redirect(url_for('text.text_encode'))


@text.route("/decode")
def text_decode():
    return render_template("decode-text.html")


@text.route("/decode-result", methods=['POST'])
def text_decode_result():
    folder = current_app.config['UPLOAD_TEXT_FOLDER']
    file   = request.files.get('image')

    if not file or file.filename == '':
        flash("Please upload an encoded image.", "error")
        return redirect(url_for('text.text_decode'))
    if not _allowed(file.filename):
        flash("Only image files are supported.", "error")
        return redirect(url_for('text.text_decode'))

    try:
        path = os.path.join(folder, secure_filename(file.filename))
        file.save(path)
        message = decrypt_text(path)
        if not message:
            flash("No hidden message found in this image.", "warning")
            return redirect(url_for('text.text_decode'))
        return render_template("decode-text-result.html",
                               filename=file.filename,
                               message=message,
                               success=True)
    except Exception as e:
        flash(f"Decoding failed: {str(e)}", "error")
        return redirect(url_for('text.text_decode'))


# ── Core algorithms (pure Pillow, no stepic dependency) ──────────────────────

def encrypt_text(in_path, message, out_path):
    """Encodes message into image LSBs. Output is always PNG to preserve bits."""
    img = Image.open(in_path).convert('RGB')
    pixels = list(img.getdata())

    payload = (message + SENTINEL).encode('utf-8')
    bits_needed = len(payload) * 8

    if bits_needed > len(pixels) * 3:
        raise OverflowError(
            f"Message too long for this image. "
            f"Max ~{len(pixels) * 3 // 8} characters, got {len(payload)}."
        )

    # Convert payload to bit list
    bits = [int(b) for byte in payload for b in format(byte, '08b')]

    new_pixels = []
    bit_idx = 0
    for r, g, b in pixels:
        if bit_idx < len(bits):
            r = (r & 0xFE) | bits[bit_idx]; bit_idx += 1
        if bit_idx < len(bits):
            g = (g & 0xFE) | bits[bit_idx]; bit_idx += 1
        if bit_idx < len(bits):
            b = (b & 0xFE) | bits[bit_idx]; bit_idx += 1
        new_pixels.append((r, g, b))

    out = Image.new('RGB', img.size)
    out.putdata(new_pixels)
    out.save(out_path, format='PNG')


def decrypt_text(path):
    """Decodes message from image LSBs."""
    img = Image.open(path).convert('RGB')
    pixels = list(img.getdata())

    bits = []
    for r, g, b in pixels:
        bits.extend([r & 1, g & 1, b & 1])

    chars = []
    for i in range(0, len(bits) - 7, 8):
        byte_val = int(''.join(map(str, bits[i:i+8])), 2)
        chars.append(byte_val)
        # Check for sentinel in decoded bytes
        if len(chars) >= 3:
            tail = bytes(chars[-3:])
            if tail == SENTINEL.encode('utf-8'):
                try:
                    return bytes(chars[:-3]).decode('utf-8')
                except UnicodeDecodeError:
                    break

    # Fallback: try to return whatever looks readable
    try:
        raw = bytes(chars).decode('utf-8', errors='replace')
        return raw[:500] if raw else ""
    except Exception:
        return ""
