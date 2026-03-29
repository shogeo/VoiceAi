import pyaudio
from typing import Literal

CONFIG = {
    "model": "models/gemini-3.1-flash-live-preview",
    "voice": "Algieba",
    "screen": {
        "max_size": (1024, 768),
        "jpeg_quality": 68,
        "interval": 2.0,  # 0.5 FPS
    },
    "audio": {
        "in_rate": 16000,
        "out_rate": 24000,
        "chunk": 2048,
        "channels": 1,
        "format": pyaudio.paInt16,
    }
}

ButtonType = Literal["left", "right", "middle"]
