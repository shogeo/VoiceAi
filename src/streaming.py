import asyncio
import base64
import io
import json
import pyautogui
from PIL import Image
from src.config import CONFIG

class StreamingManager:
    def __init__(self, controller):
        self.controller = controller

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
            data = await self.controller.audio_queue.get()
            self.controller.is_ai_talking = True
            print("\r🎙️  Gemini говорит...  ", end="", flush=True)

            await asyncio.to_thread(self.controller.speaker.write, data)
            self.controller.audio_queue.task_done()

            if self.controller.audio_queue.empty():
                await asyncio.sleep(0.5)
                self.controller.is_ai_talking = False
                print("\r✅ Слушаю...         ", end="", flush=True)

    async def receive_loop(self, ws):
        async for message in ws:
            try:
                resp = json.loads(message)

                if "setupComplete" in resp:
                    print("\n✅ Gemini Live подключён — полный контроль мыши и клавиатуры активен\n")
                    continue

                if "serverContent" in resp:
                    sc = resp["serverContent"]
                    if "modelTurn" in sc:
                        for part in sc.get("modelTurn", {}).get("parts", []):
                            if "inlineData" in part and part["inlineData"].get("mimeType") == "audio/pcm;rate=24000":
                                await self.controller.audio_queue.put(base64.b64decode(part["inlineData"]["data"]))

                if "toolCall" in resp:
                    calls = resp["toolCall"].get("functionCalls", [resp["toolCall"]])
                    function_responses = []

                    for call in calls:
                        name = call.get("name")
                        args = call.get("args", {})
                        call_id = call.get("id")

                        tool = self.controller.registry.get(name)
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
            data = await asyncio.to_thread(self.controller.mic.read, CONFIG["audio"]["chunk"], exception_on_overflow=False)
            if not self.controller.is_ai_talking:
                msg = {"realtimeInput": {"audio": {"data": base64.b64encode(data).decode("utf-8"), "mimeType": "audio/pcm;rate=16000"}}}
                try:
                    await ws.send(json.dumps(msg))
                except:
                    break
            await asyncio.sleep(0.001)
