import os
from flask import Flask, render_template
from modes.Image.image import image
from modes.Audio.audio import audio
from modes.Text.text import text
from modes.Video.video import video

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    raise ValueError("SECRET_KEY environment variable is required")

# Cross-platform upload folders
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app.config['UPLOAD_IMAGE_FOLDER'] = os.path.join(BASE_DIR, 'modes', 'Image', 'static')
app.config['UPLOAD_TEXT_FOLDER']  = os.path.join(BASE_DIR, 'modes', 'Text',  'static')
app.config['UPLOAD_AUDIO_FOLDER'] = os.path.join(BASE_DIR, 'modes', 'Audio', 'static')
app.config['UPLOAD_VIDEO_FOLDER'] = os.path.join(BASE_DIR, 'modes', 'Video', 'static')
app.config['MAX_CONTENT_LENGTH']  = 50 * 1024 * 1024  # 50 MB upload limit

# Ensure static folders exist
for key in ['UPLOAD_IMAGE_FOLDER', 'UPLOAD_TEXT_FOLDER', 'UPLOAD_AUDIO_FOLDER', 'UPLOAD_VIDEO_FOLDER']:
    os.makedirs(app.config[key], exist_ok=True)

app.register_blueprint(image, url_prefix="/image")
app.register_blueprint(audio, url_prefix="/audio")
app.register_blueprint(text,  url_prefix="/text")
app.register_blueprint(video, url_prefix="/video")


@app.route("/")
def home():
    return render_template("home.html")


@app.errorhandler(413)
def too_large(e):
    return render_template("home.html", error="File too large. Maximum size is 50 MB."), 413


if __name__ == "__main__":
    app.run(debug=False)
