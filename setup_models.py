import os
import easyocr
from easyocr.utils import download_and_unzip

# Define model storage directory
model_dir = os.path.expanduser("~/.EasyOCR")
os.makedirs(model_dir, exist_ok=True)

# Define model filenames
detection_model_filename = "craft_mlt_25k.pth"
recognition_model_filename = "english_g2.pth"

# Define URLs for EasyOCR models (manually specified)
detection_model_url = "https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/craft_mlt_25k.pth"
recognition_model_url = "https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/english_g2.pth"

# Download detection model
print("Downloading detection model...")
download_and_unzip(detection_model_url, detection_model_filename, model_dir)

# Download recognition model
print("Downloading recognition model...")
download_and_unzip(recognition_model_url, recognition_model_filename, model_dir)

print("Model download complete! Now you can run `numberplate.py`.")
