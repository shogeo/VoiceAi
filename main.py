import asyncio
import base64
import io
import json
import os
import socket
import time
from typing import Any, Dict, List, Optional, Literal

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

# ====================== TOOL SYSTEM ======================

class Tool:
    """Represents a single callable tool for the AI."""
    def __init__(self, name: str, description: str, parameters: Dict[str, Any], handler):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler

    def to_declaration(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }

    async def execute(self, args: Dict[str, Any]) -> Any:
        return await self.handler(**args)


class ToolRegistry:
    """Central registry for all tools."""
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def get_declarations(self) -> List[Dict[str, Any]]:
        return [tool.to_declaration() for tool in self._tools.values()]


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

        # Registry for all AI-accessible tools
        self.registry = ToolRegistry()
        self._register_tools()

    # ==================== COORDINATE UTILITIES ====================

    def norm_to_pixels(self, x_norm: int, y_norm: int) -> tuple[int, int]:
        """Convert normalized coordinates (0-1000) to actual pixel coordinates with safe margins."""
        x = int(x_norm / 1000 * self.screen_w)
        y = int(y_norm / 1000 * self.screen_h)

        return x, y

    def pixels_to_norm(self, x_px: int, y_px: int) -> tuple[int, int]:
        """Convert pixel coordinates to normalized (0-1000)."""
        x_norm = int(x_px / self.screen_w * 1000)
        y_norm = int(y_px / self.screen_h * 1000)
        return x_norm, y_norm

    # ==================== MOUSE TOOLS (HANDLERS) ====================

    async def _move_mouse(self, x: int, y: int) -> str:
        px, py = self.norm_to_pixels(x, y)
        pyautogui.moveTo(px, py, duration=0.25)
        return f"mouse moved to ({x}, {y}) → ({px}, {py})"

    async def _click(self, x: int, y: int, button: ButtonType = "left") -> str:
        px, py = self.norm_to_pixels(x, y)
        pyautogui.moveTo(px, py, duration=0.2)
        pyautogui.click(button=button)
        return f"{button} click at ({x}, {y})"

    async def _double_click(self, x: int, y: int, button: ButtonType = "left") -> str:
        px, py = self.norm_to_pixels(x, y)
        pyautogui.moveTo(px, py, duration=0.2)
        pyautogui.doubleClick(button=button)
        return f"double {button} click at ({x}, {y})"

    async def _mouse_down(self, x: int, y: int, button: ButtonType = "left") -> str:
        px, py = self.norm_to_pixels(x, y)
        pyautogui.moveTo(px, py, duration=0.2)
        pyautogui.mouseDown(button=button)
        return f"{button} button pressed at ({x}, {y})"

    async def _mouse_up(self, x: int, y: int, button: ButtonType = "left") -> str:
        px, py = self.norm_to_pixels(x, y)
        pyautogui.moveTo(px, py, duration=0.2)
        pyautogui.mouseUp(button=button)
        return f"{button} button released at ({x}, {y})"

    async def _drag_to(self, x: int, y: int, button: ButtonType = "left") -> str:
        px, py = self.norm_to_pixels(x, y)
        pyautogui.dragTo(px, py, duration=0.6, button=button)
        return f"dragged with {button} button to ({x}, {y})"

    async def _scroll(self, delta: int) -> str:
        pyautogui.scroll(delta)
        direction = "up" if delta > 0 else "down"
        return f"scrolled {direction} by {abs(delta)}"

    async def _get_mouse_position(self) -> dict:
        x, y = pyautogui.position()
        x_norm, y_norm = self.pixels_to_norm(x, y)
        return {"x": x_norm, "y": y_norm, "pixel_x": x, "pixel_y": y}

    # ==================== KEYBOARD TOOLS (HANDLERS) ====================

    async def _type_text(self, text: str) -> str:
        """Type a string of text."""
        pyautogui.write(text)
        return f"typed: '{text}'"

    async def _press_key(self, key: str) -> str:
        """Press and release a single key (e.g., 'enter', 'tab', 'a')."""
        pyautogui.press(key)
        return f"pressed key: {key}"

    async def _hotkey(self, keys: List[str]) -> str:
        """Press a combination of keys (e.g., ['ctrl', 'c'])."""
        pyautogui.hotkey(*keys)
        return f"hotkey pressed: {'+'.join(keys)}"

    async def _key_down(self, key: str) -> str:
        """Press and hold a key."""
        pyautogui.keyDown(key)
        return f"key down: {key}"

    async def _key_up(self, key: str) -> str:
        """Release a key."""
        pyautogui.keyUp(key)
        return f"key up: {key}"

    # ==================== TOOL REGISTRATION ====================

    def _register_tools(self):
        """Register all tools with their descriptions and schemas."""
        # Mouse tools
        self.registry.register(Tool(
            name="move_mouse",
            description="Move mouse cursor to normalized coordinates (0-1000).",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate 0-1000"},
                    "y": {"type": "integer", "description": "Y coordinate 0-1000"}
                },
                "required": ["x", "y"]
            },
            handler=self._move_mouse
        ))

        self.registry.register(Tool(
            name="click",
            description="Click at normalized coordinates with a mouse button.",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"}
                },
                "required": ["x", "y"]
            },
            handler=self._click
        ))

        self.registry.register(Tool(
            name="double_click",
            description="Double-click at normalized coordinates.",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"}
                },
                "required": ["x", "y"]
            },
            handler=self._double_click
        ))

        self.registry.register(Tool(
            name="mouse_down",
            description="Press and hold a mouse button at normalized coordinates.",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"}
                },
                "required": ["x", "y"]
            },
            handler=self._mouse_down
        ))

        self.registry.register(Tool(
            name="mouse_up",
            description="Release a mouse button at normalized coordinates.",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"}
                },
                "required": ["x", "y"]
            },
            handler=self._mouse_up
        ))

        self.registry.register(Tool(
            name="drag_to",
            description="Drag from current position to normalized coordinates while holding a button.",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"}
                },
                "required": ["x", "y"]
            },
            handler=self._drag_to
        ))

        self.registry.register(Tool(
            name="scroll",
            description="Scroll the mouse wheel. Positive delta scrolls up, negative down.",
            parameters={
                "type": "object",
                "properties": {
                    "delta": {"type": "integer", "description": "Number of scroll steps"}
                },
                "required": ["delta"]
            },
            handler=self._scroll
        ))

        self.registry.register(Tool(
            name="get_mouse_position",
            description="Get current mouse cursor position in normalized and pixel coordinates.",
            parameters={"type": "object", "properties": {}},
            handler=self._get_mouse_position
        ))

        # Keyboard tools
        self.registry.register(Tool(
            name="type_text",
            description="Type a string of text at the current cursor position.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"}
                },
                "required": ["text"]
            },
            handler=self._type_text
        ))

        self.registry.register(Tool(
            name="press_key",
            description="Press and release a single key. Common keys: 'enter', 'tab', 'space', 'backspace', 'delete', 'escape', 'up', 'down', 'left', 'right', 'a'..'z', '0'..'9', etc.",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key name"}
                },
                "required": ["key"]
            },
            handler=self._press_key
        ))

        self.registry.register(Tool(
            name="hotkey",
            description="Press a combination of keys (e.g., ['ctrl', 'c'] for copy).",
            parameters={
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of key names to press in order"
                    }
                },
                "required": ["keys"]
            },
            handler=self._hotkey
        ))

        self.registry.register(Tool(
            name="key_down",
            description="Press and hold a key. Use key_up to release.",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key name"}
                },
                "required": ["key"]
            },
            handler=self._key_down
        ))

        self.registry.register(Tool(
            name="key_up",
            description="Release a key that was held down.",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key name"}
                },
                "required": ["key"]
            },
            handler=self._key_up
        ))

    # ==================== MAIN LOOPS (unchanged except tool handling) ====================

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
                    print("\n✅ Gemini Live подключён — полный контроль мыши и клавиатуры активен\n")
                    continue

                # Audio playback
                if "serverContent" in resp:
                    sc = resp["serverContent"]
                    if "modelTurn" in sc:
                        for part in sc.get("modelTurn", {}).get("parts", []):
                            if "inlineData" in part and part["inlineData"].get("mimeType") == "audio/pcm;rate=24000":
                                await self.audio_queue.put(base64.b64decode(part["inlineData"]["data"]))

                # Tool calls
                if "toolCall" in resp:
                    calls = resp["toolCall"].get("functionCalls", [resp["toolCall"]])
                    function_responses = []

                    for call in calls:
                        name = call.get("name")
                        args = call.get("args", {})
                        call_id = call.get("id")

                        tool = self.registry.get(name)
                        if tool:
                            try:
                                result = await tool.execute(args)
                            except Exception as e:
                                result = f"Error executing {name}: {e}"
                        else:
                            result = f"Unknown tool: {name}"

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
                print(f"Error in receive_loop: {e}")

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
        print("   Gemini Live — Полный контроль мыши и клавиатуры (Computer Use)")
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
                        "tools": [{"functionDeclarations": self.registry.get_declarations()}]
                    }
                }

                await ws.send(json.dumps(setup))

                # Wait for setupComplete
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