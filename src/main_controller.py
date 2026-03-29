import asyncio
import os
import socket
import json
import websockets
import pyaudio
from dotenv import load_dotenv

from src.config import CONFIG
from src.tools.tool_system import Tool, ToolRegistry
from src.tools.mouse_tools import MouseTools
from src.tools.keyboard_tools import KeyboardTools
from src.utils import CoordinateConverter
from src.streaming import StreamingManager

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

        self.converter = CoordinateConverter()
        self.registry = ToolRegistry()
        self.mouse_tools = MouseTools(self.converter)
        self.keyboard_tools = KeyboardTools()
        self.streaming_manager = StreamingManager(self)
        self._register_tools()

    def _register_tools(self):
        # Mouse tools
        self.registry.register(Tool(
            name="move_mouse",
            description="Move mouse cursor to normalized coordinates (0-1000) over a specified duration.",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate 0-1000"},
                    "y": {"type": "integer", "description": "Y coordinate 0-1000"},
                    "duration": {"type": "number", "description": "Time in seconds to perform the move.", "default": 0.25}
                },
                "required": ["x", "y"]
            },
            handler=self.mouse_tools._move_mouse
        ))

        self.registry.register(Tool(
            name="click",
            description="Click a mouse button at the current cursor position.",
            parameters={
                "type": "object",
                "properties": {
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"}
                },
                "required": []
            },
            handler=self.mouse_tools._click
        ))

        self.registry.register(Tool(
            name="double_click",
            description="Double-click a mouse button at the current cursor position.",
            parameters={
                "type": "object",
                "properties": {
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"}
                },
                "required": []
            },
            handler=self.mouse_tools._double_click
        ))

        self.registry.register(Tool(
            name="mouse_down",
            description="Press and hold a mouse button at the current cursor position.",
            parameters={
                "type": "object",
                "properties": {
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"}
                },
                "required": []
            },
            handler=self.mouse_tools._mouse_down
        ))

        self.registry.register(Tool(
            name="mouse_up",
            description="Release a mouse button at the current cursor position.",
            parameters={
                "type": "object",
                "properties": {
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"}
                },
                "required": []
            },
            handler=self.mouse_tools._mouse_up
        ))

        self.registry.register(Tool(
            name="drag_to",
            description="Drag from current position to normalized coordinates while holding a button over a specified duration.",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                    "duration": {"type": "number", "description": "Time in seconds to perform the drag.", "default": 0.6}
                },
                "required": ["x", "y"]
            },
            handler=self.mouse_tools._drag_to
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
            handler=self.mouse_tools._scroll
        ))

        self.registry.register(Tool(
            name="get_mouse_position",
            description="Get current mouse cursor position in normalized and pixel coordinates.",
            parameters={"type": "object", "properties": {}},
            handler=self.mouse_tools._get_mouse_position
        ))

        # Keyboard tools
        self.registry.register(Tool("type_text", "Type a string of text.", {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}, self.keyboard_tools._type_text))
        self.registry.register(Tool("press_key", "Press a single key.", {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}, self.keyboard_tools._press_key))
        self.registry.register(Tool("hotkey", "Press a combination of keys.", {"type": "object", "properties": {"keys": {"type": "array", "items": {"type": "string"}}}, "required": ["keys"]}, self.keyboard_tools._hotkey))
        self.registry.register(Tool("key_down", "Press and hold a key.", {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}, self.keyboard_tools._key_down))
        self.registry.register(Tool("key_up", "Release a key.", {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}, self.keyboard_tools._key_up))

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

                async for msg in ws:
                    if "setupComplete" in json.loads(msg):
                        break

                print("🚀 Готов к работе. Управляй компьютером голосом!\n")

                tasks = [
                    asyncio.create_task(self.streaming_manager.receive_loop(ws)),
                    asyncio.create_task(self.streaming_manager.send_loop(ws)),
                    asyncio.create_task(self.streaming_manager.speaker_worker()),
                    asyncio.create_task(self.streaming_manager.screen_stream_task(ws)),
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
