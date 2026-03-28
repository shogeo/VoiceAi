import asyncio
import base64
import io
import json
import os
import socket
import time

import pyaudio
import websockets
from dotenv import load_dotenv
import pyautogui
from PIL import Image

# ====================== CONFIG ======================

CONFIG = {
    "model": "models/gemini-3.1-flash-live-preview",
    "voice": "Algieba",
    "screen": {
        "max_size": (1024, 768),
        "jpeg_quality": 68,
        "interval": 2.0,          # секунды между кадрами (0.5 FPS)
    },
    "audio": {
        "in_rate": 16000,
        "out_rate": 24000,
        "chunk": 2048,
        "channels": 1,
        "format": pyaudio.paInt16,
    }
}

# ====================== CORE ======================

class GeminiLiveAssistant:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("API_KEY")
        if not self.api_key:
            raise ValueError("API_KEY не найден в .env файле")

        self.is_ai_talking = False
        self.audio_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.last_screen_time = 0.0

        self.p = pyaudio.PyAudio()
        self.mic = self.p.open(
            format=CONFIG["audio"]["format"],
            channels=CONFIG["audio"]["channels"],
            rate=CONFIG["audio"]["in_rate"],
            input=True,
            frames_per_buffer=CONFIG["audio"]["chunk"]
        )
        self.speaker = self.p.open(
            format=CONFIG["audio"]["format"],
            channels=CONFIG["audio"]["channels"],
            rate=CONFIG["audio"]["out_rate"],
            output=True,
            frames_per_buffer=CONFIG["audio"]["chunk"]
        )

    async def send_screen_frame(self, ws):
        """Отправка экрана как видео-фрейм"""
        while True:
            try:
                now = time.time()
                if now - self.last_screen_time >= CONFIG["screen"]["interval"]:
                    screenshot = pyautogui.screenshot()
                    img = screenshot.convert("RGB")
                    img.thumbnail(CONFIG["screen"]["max_size"], Image.Resampling.LANCZOS)

                    buffer = io.BytesIO()
                    img.save(buffer, format="JPEG", quality=CONFIG["screen"]["jpeg_quality"], optimize=True)
                    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

                    msg = {
                        "realtimeInput": {
                            "video": {
                                "mimeType": "image/jpeg",
                                "data": b64
                            }
                        }
                    }

                    await ws.send(json.dumps(msg))
                    self.last_screen_time = now
                    print("📺 Экран → Gemini", end="\r")

                await asyncio.sleep(0.3)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"\n❌ Ошибка потока экрана: {e}")
                await asyncio.sleep(2)

    async def speaker_worker(self):
        while True:
            data = await self.audio_queue.get()
            self.is_ai_talking = True
            print("\r🎙️  Gemini говорит...  ", end="", flush=True)

            await asyncio.to_thread(self.speaker.write, data)
            self.audio_queue.task_done()

            if self.audio_queue.empty():
                await asyncio.sleep(0.5)
                self.is_ai_talking = False
                print("\r✅ Слушаю...         ", end="", flush=True)

    async def receive_loop(self, ws):
        async for message in ws:
            try:
                resp = json.loads(message)

                if "setupComplete" in resp:
                    print("\n✅ Gemini Live успешно подключён и видит ваш экран\n")
                    continue

                if "serverContent" in resp:
                    sc = resp["serverContent"]
                    if "modelTurn" in sc:
                        for part in sc.get("modelTurn", {}).get("parts", []):
                            if "inlineData" in part and part["inlineData"].get("mimeType") == "audio/pcm;rate=24000":
                                chunk = base64.b64decode(part["inlineData"]["data"])
                                await self.audio_queue.put(chunk)
            except Exception:
                pass

    async def send_loop(self, ws):
        print("🎤 Микрофон активен\n")
        while True:
            data = await asyncio.to_thread(
                self.mic.read, CONFIG["audio"]["chunk"], exception_on_overflow=False
            )

            if not self.is_ai_talking:
                msg = {
                    "realtimeInput": {
                        "audio": {
                            "data": base64.b64encode(data).decode("utf-8"),
                            "mimeType": "audio/pcm;rate=16000"
                        }
                    }
                }
                try:
                    await ws.send(json.dumps(msg))
                except:
                    break

            await asyncio.sleep(0.001)

    async def run(self):
        print("\n" + "="*60)
        print("       Gemini Live Voice Assistant + Screen Streaming")
        print("="*60 + "\n")

        try:
            ws_url = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={self.api_key}"

            async with websockets.connect(
                ws_url,
                family=socket.AF_INET,
                ping_interval=20,
                open_timeout=30
            ) as ws:

                # Setup
                setup = {
                    "setup": {
                        "model": CONFIG["model"],
                        "generationConfig": {
                            "responseModalities": ["AUDIO"],
                            "speechConfig": {
                                "voiceConfig": {
                                    "prebuiltVoiceConfig": {"voiceName": CONFIG["voice"]}
                                }
                            }
                        }
                    }
                }
                await ws.send(json.dumps(setup))

                # Ждём подтверждения
                async for msg in ws:
                    if "setupComplete" in json.loads(msg):
                        break

                print("🚀 Ассистент запущен и готов к работе!\n")

                # Запуск задач
                tasks = [
                    asyncio.create_task(self.receive_loop(ws)),
                    asyncio.create_task(self.send_loop(ws)),
                    asyncio.create_task(self.speaker_worker()),
                    asyncio.create_task(self.send_screen_frame(ws)),
                ]

                await asyncio.gather(*tasks, return_exceptions=True)

        except KeyboardInterrupt:
            print("\n\n👋 Завершение по запросу пользователя...")
        except Exception as e:
            print(f"\n❌ Критическая ошибка: {e}")
        finally:
            print("\n🛑 Завершение работы...")
            self.mic.stop_stream()
            self.mic.close()
            self.speaker.stop_stream()
            self.speaker.close()
            self.p.terminate()


if __name__ == "__main__":
    assistant = GeminiLiveAssistant()
    asyncio.run(assistant.run())