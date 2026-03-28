import asyncio
import base64
import io
import json
import os
import socket
import time
from typing import Literal

import pyaudio
import websockets
import pyautogui
from dotenv import load_dotenv
from PIL import Image

# ====================== CONFIG ======================

CONFIG = {
    "model": "models/gemini-3.1-flash-live-preview",
    "voice": "Algieba",
    "screen": {
        "max_size": (1024, 768),
        "jpeg_quality": 68,
        "interval": 2.0,           # 0.5 FPS
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

# ====================== MAIN CLASS ======================

class GeminiLiveComputerControl:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("API_KEY")
        if not self.api_key:
            raise ValueError("API_KEY не найден в .env")

        self.is_ai_talking = False
        self.audio_queue: asyncio.Queue = asyncio.Queue(maxsize=100)

        self.p = pyaudio.PyAudio()
        self.mic = self.p.open(format=CONFIG["audio"]["format"], channels=CONFIG["audio"]["channels"],
                               rate=CONFIG["audio"]["in_rate"], input=True, frames_per_buffer=CONFIG["audio"]["chunk"])
        self.speaker = self.p.open(format=CONFIG["audio"]["format"], channels=CONFIG["audio"]["channels"],
                                   rate=CONFIG["audio"]["out_rate"], output=True, frames_per_buffer=CONFIG["audio"]["chunk"])

        self.screen_w, self.screen_h = pyautogui.size()
        pyautogui.FAILSAFE = False  # Отключаем fail-safe для агентного управления

        print(f"🖥️  Экран: {self.screen_w}×{self.screen_h} | Fail-safe отключён")

    def norm_to_pixels(self, x_norm: int, y_norm: int) -> tuple[int, int]:
        """0-1000 → реальные пиксели с небольшой защитой от краёв"""
        x = int(x_norm / 1000 * self.screen_w)
        y = int(y_norm / 1000 * self.screen_h)
        # Защита от краёв (10 пикселей отступ)
        x = max(10, min(x, self.screen_w - 10))
        y = max(10, min(y, self.screen_h - 10))
        return x, y

    # ==================== MOUSE TOOLS ====================

    async def move_mouse(self, x: int, y: int) -> str:
        px, py = self.norm_to_pixels(x, y)
        pyautogui.moveTo(px, py, duration=0.25)
        return f"mouse moved to ({x}, {y}) → ({px}, {py})"

    async def click(self, x: int, y: int, button: ButtonType = "left") -> str:
        px, py = self.norm_to_pixels(x, y)
        pyautogui.moveTo(px, py, duration=0.2)
        pyautogui.click(button=button)
        return f"{button} click at ({x}, {y})"

    async def double_click(self, x: int, y: int, button: ButtonType = "left") -> str:
        px, py = self.norm_to_pixels(x, y)
        pyautogui.moveTo(px, py, duration=0.2)
        pyautogui.doubleClick(button=button)
        return f"double {button} click at ({x}, {y})"

    async def mouse_down(self, x: int, y: int, button: ButtonType = "left") -> str:
        px, py = self.norm_to_pixels(x, y)
        pyautogui.moveTo(px, py, duration=0.2)
        pyautogui.mouseDown(button=button)
        return f"{button} button pressed at ({x}, {y})"

    async def mouse_up(self, x: int, y: int, button: ButtonType = "left") -> str:
        px, py = self.norm_to_pixels(x, y)
        pyautogui.moveTo(px, py, duration=0.2)
        pyautogui.mouseUp(button=button)
        return f"{button} button released at ({x}, {y})"

    async def drag_to(self, x: int, y: int, button: ButtonType = "left") -> str:
        """Перетаскивание из текущей позиции в новую"""
        px, py = self.norm_to_pixels(x, y)
        pyautogui.dragTo(px, py, duration=0.6, button=button)
        return f"dragged with {button} button to ({x}, {y})"

    async def scroll(self, delta: int) -> str:
        pyautogui.scroll(delta)
        direction = "up" if delta > 0 else "down"
        return f"scrolled {direction} by {abs(delta)}"

    async def get_mouse_position(self) -> dict:
        x, y = pyautogui.position()
        # Преобразуем обратно в нормализованные координаты
        x_norm = int(x / self.screen_w * 1000)
        y_norm = int(y / self.screen_h * 1000)
        return {"x": x_norm, "y": y_norm, "pixel_x": x, "pixel_y": y}

    # ==================== MAIN LOOPS ====================

    async def screen_stream_task(self, ws):
        print("📺 Поток экрана запущен")
        while True:
            try:
                screenshot = pyautogui.screenshot()
                img = screenshot.convert("RGB")
                img.thumbnail(CONFIG["screen"]["max_size"], Image.Resampling.LANCZOS)

                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=CONFIG["screen"]["jpeg_quality"], optimize=True)
                b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

                msg = {"realtimeInput": {"video": {"mimeType": "image/jpeg", "data": b64}}}
                await ws.send(json.dumps(msg))

                await asyncio.sleep(CONFIG["screen"]["interval"])
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"❌ Screen error: {e}")
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
                    print("\n✅ Gemini Live подключён — полный контроль мыши активен\n")
                    continue

                # Аудио
                if "serverContent" in resp:
                    sc = resp["serverContent"]
                    if "modelTurn" in sc:
                        for part in sc.get("modelTurn", {}).get("parts", []):
                            if "inlineData" in part and part["inlineData"].get("mimeType") == "audio/pcm;rate=24000":
                                await self.audio_queue.put(base64.b64decode(part["inlineData"]["data"]))

                # Function Calling
                if "toolCall" in resp:
                    calls = resp["toolCall"].get("functionCalls", [resp["toolCall"]])
                    function_responses = []

                    for call in calls:
                        name = call.get("name")
                        args = call.get("args", {})
                        call_id = call.get("id")

                        result = "unknown function"

                        if name == "move_mouse":
                            result = await self.move_mouse(args.get("x"), args.get("y"))
                        elif name == "click":
                            result = await self.click(args.get("x"), args.get("y"), args.get("button", "left"))
                        elif name == "double_click":
                            result = await self.double_click(args.get("x"), args.get("y"), args.get("button", "left"))
                        elif name == "mouse_down":
                            result = await self.mouse_down(args.get("x"), args.get("y"), args.get("button", "left"))
                        elif name == "mouse_up":
                            result = await self.mouse_up(args.get("x"), args.get("y"), args.get("button", "left"))
                        elif name == "drag_to":
                            result = await self.drag_to(args.get("x"), args.get("y"), args.get("button", "left"))
                        elif name == "scroll":
                            result = await self.scroll(args.get("delta", 0))
                        elif name == "get_mouse_position":
                            result = await self.get_mouse_position()

                        function_responses.append({
                            "id": call_id,
                            "name": name,
                            "response": {"result": result}
                        })

                    if function_responses:
                        await ws.send(json.dumps({
                            "toolResponse": {"functionResponses": function_responses}
                        }))

            except Exception as e:
                pass

    async def send_loop(self, ws):
        print("🎤 Микрофон активен\n")
        while True:
            data = await asyncio.to_thread(self.mic.read, CONFIG["audio"]["chunk"], exception_on_overflow=False)
            if not self.is_ai_talking:
                msg = {"realtimeInput": {"audio": {"data": base64.b64encode(data).decode("utf-8"), "mimeType": "audio/pcm;rate=16000"}}}
                try:
                    await ws.send(json.dumps(msg))
                except:
                    break
            await asyncio.sleep(0.001)

    async def run(self):
        print("\n" + "="*75)
        print("   Gemini Live — Полный контроль мыши (Computer Use)")
        print("="*75 + "\n")

        try:
            ws_url = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={self.api_key}"

            async with websockets.connect(ws_url, family=socket.AF_INET, ping_interval=20, open_timeout=30) as ws:
                setup = {
                    "setup": {
                        "model": CONFIG["model"],
                        "generationConfig": {
                            "responseModalities": ["AUDIO"],
                            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": CONFIG["voice"]}}}
                        },
                        "tools": [{"functionDeclarations": [
                            {"name": "move_mouse", "description": "Переместить мышь в указанные координаты (0-1000)", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]}},
                            {"name": "click", "description": "Кликнуть кнопкой мыши", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "button": {"type": "string", "enum": ["left", "right", "middle"]}}}},
                            {"name": "double_click", "description": "Двойной клик", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "button": {"type": "string", "enum": ["left", "right", "middle"]}}}},
                            {"name": "mouse_down", "description": "Зажать кнопку мыши", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "button": {"type": "string", "enum": ["left", "right", "middle"]}}}},
                            {"name": "mouse_up", "description": "Отпустить кнопку мыши", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "button": {"type": "string", "enum": ["left", "right", "middle"]}}}},
                            {"name": "drag_to", "description": "Перетащить мышь с зажатой кнопкой в новую позицию", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "button": {"type": "string", "enum": ["left", "right", "middle"]}}}},
                            {"name": "scroll", "description": "Прокрутить колесико мыши (положительное = вверх)", "parameters": {"type": "object", "properties": {"delta": {"type": "integer"}}}},
                            {"name": "get_mouse_position", "description": "Получить текущие координаты курсора", "parameters": {"type": "object", "properties": {}}}
                        ]}]
                    }
                }

                await ws.send(json.dumps(setup))

                async for msg in ws:
                    if "setupComplete" in json.loads(msg):
                        break

                print("🚀 Готов к работе. Управляй компьютером голосом!\n")

                tasks = [
                    asyncio.create_task(self.receive_loop(ws)),
                    asyncio.create_task(self.send_loop(ws)),
                    asyncio.create_task(self.speaker_worker()),
                    asyncio.create_task(self.screen_stream_task(ws)),
                ]

                await asyncio.gather(*tasks, return_exceptions=True)

        except KeyboardInterrupt:
            print("\n\n👋 Завершено пользователем")
        except Exception as e:
            print(f"\n❌ Ошибка: {e}")
        finally:
            self.mic.stop_stream()
            self.mic.close()
            self.speaker.stop_stream()
            self.speaker.close()
            self.p.terminate()


if __name__ == "__main__":
    assistant = GeminiLiveComputerControl()
    asyncio.run(assistant.run())