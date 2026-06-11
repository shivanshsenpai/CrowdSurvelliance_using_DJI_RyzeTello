from pathlib import Path
import urllib.request


MODEL_URL = (
    "https://huggingface.co/Subh775/Threat-Detection-YOLOv8n"
    "/resolve/main/weights/best.pt"
)
OUTPUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "models"
    / "weapon_detection"
    / "threat_yolov8n.pt"
)


def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading weapon model to {OUTPUT_PATH}")
    with urllib.request.urlopen(MODEL_URL, timeout=120) as response:
        OUTPUT_PATH.write_bytes(response.read())
    size_mb = OUTPUT_PATH.stat().st_size / (1024 * 1024)
    print(f"Done: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
