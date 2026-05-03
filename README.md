# StegaVault — Steganography Tool

Hide secret messages inside images, audio, and video files.

## Features
- **Text → Image**: Hide text in PNG/JPG using LSB encoding
- **Image → Image**: Conceal a secret image inside a carrier image
- **Text → Audio**: Embed text in WAV audio files
- **Text → Video**: Spread a message across video frames (requires ffmpeg)

## Setup

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Create a .env file
```env
SECRET_KEY=your_random_secret_key
```

### 3. Install ffmpeg (for Video steganography only)
- **Ubuntu/Debian**: `sudo apt install ffmpeg`
- **macOS**: `brew install ffmpeg`
- **Windows**: Download from https://ffmpeg.org/download.html and add to PATH

### 4. Run the app
```bash
python main.py
```

Open your browser at **http://127.0.0.1:5000**

## Notes
- Upload limit: 50 MB per file
- Audio: Only WAV files are supported
- Video: MP4, AVI, MOV, MKV supported (keep files small for faster processing)
- Image encoding output is always PNG to preserve LSB data
