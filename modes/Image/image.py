import os
import cv2
import numpy as np
from flask import Blueprint, current_app, render_template, request, flash, redirect, url_for
from werkzeug.utils import secure_filename

image = Blueprint("image", __name__, static_folder="static", template_folder="templates")

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'webp'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _cleanup(folder, *filenames):
    for f in filenames:
        path = os.path.join(folder, f)
        if os.path.exists(path):
            os.remove(path)


@image.route("/encode")
def image_encode():
    folder = current_app.config['UPLOAD_IMAGE_FOLDER']
    _cleanup(folder, "adjusted_sample.jpg", "encrypted_image.png")
    return render_template("encode-image.html")


@image.route("/encode-result", methods=['POST'])
def image_encode_result():
    folder = current_app.config['UPLOAD_IMAGE_FOLDER']
    carrier_file = request.files.get('carrier')
    secret_file  = request.files.get('secret')

    if not carrier_file or carrier_file.filename == '':
        flash("Please upload a carrier image.", "error")
        return redirect(url_for('image.image_encode'))
    if not secret_file or secret_file.filename == '':
        flash("Please upload a secret image.", "error")
        return redirect(url_for('image.image_encode'))
    if not allowed_file(carrier_file.filename) or not allowed_file(secret_file.filename):
        flash("Only image files are allowed (PNG, JPG, BMP, WEBP).", "error")
        return redirect(url_for('image.image_encode'))

    try:
        carrier_path = os.path.join(folder, secure_filename(carrier_file.filename))
        secret_path  = os.path.join(folder, secure_filename(secret_file.filename))
        carrier_file.save(carrier_path)
        secret_file.save(secret_path)

        output_path = encrypt(carrier_path, secret_path, folder)
        return render_template("encode-result.html",
                               carrier_name=carrier_file.filename,
                               secret_name=secret_file.filename,
                               success=True)
    except Exception as e:
        flash(f"Encoding failed: {str(e)}", "error")
        return redirect(url_for('image.image_encode'))


@image.route("/decode")
def image_decode():
    folder = current_app.config['UPLOAD_IMAGE_FOLDER']
    _cleanup(folder, "decrypted_sample.png", "decrypted_secret.png")
    return render_template("decode-image.html")


@image.route("/decode-result", methods=['POST'])
def image_decode_result():
    folder = current_app.config['UPLOAD_IMAGE_FOLDER']
    file = request.files.get('image')

    if not file or file.filename == '':
        flash("Please upload an encoded image.", "error")
        return redirect(url_for('image.image_decode'))
    if not allowed_file(file.filename):
        flash("Only image files are allowed.", "error")
        return redirect(url_for('image.image_decode'))

    try:
        path = os.path.join(folder, secure_filename(file.filename))
        file.save(path)
        decrypt(path, folder)
        return render_template("decode-result.html",
                               filename=file.filename,
                               success=True)
    except Exception as e:
        flash(f"Decoding failed: {str(e)}", "error")
        return redirect(url_for('image.image_decode'))


# ── Core algorithms (fully vectorised with NumPy — no Python loops) ──────────

def encrypt(carrier_path, secret_path, out_folder):
    """
    Hides the secret image inside the carrier using 4 MSBs each.
    Result pixel = MSB4(carrier) | MSB4(secret)
    Vectorised: ~100x faster than nested Python loops.
    """
    carrier = cv2.imread(carrier_path)
    secret  = cv2.imread(secret_path)

    if carrier is None:
        raise ValueError("Cannot read carrier image.")
    if secret is None:
        raise ValueError("Cannot read secret image.")

    # Resize secret to match carrier dimensions
    h, w = carrier.shape[:2]
    secret = cv2.resize(secret, (w, h))

    # Vectorised combine: keep top 4 bits of carrier, put top 4 bits of secret in lower nibble
    result = (carrier & np.uint8(0xF0)) | (secret >> 4).astype(np.uint8)

    out_path = os.path.join(out_folder, "encrypted_image.png")
    cv2.imwrite(out_path, result)
    return out_path


def decrypt(image_path, out_folder):
    """
    Extracts both images from the encoded file.
    img1 (carrier approx) = top nibble * 16
    img2 (secret approx)  = bottom nibble * 16
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("Cannot read the encoded image.")

    img1 = img & np.uint8(0xF0)                    # carrier bits (top nibble, lower set to 0)
    img2 = (img & np.uint8(0x0F)).astype(np.uint8) * 16  # secret bits scaled up

    cv2.imwrite(os.path.join(out_folder, "decrypted_sample.png"), img1)
    cv2.imwrite(os.path.join(out_folder, "decrypted_secret.png"), img2)
