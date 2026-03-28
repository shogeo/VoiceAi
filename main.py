import asyncio
import base64
import json
import os
import socket

import pyaudio
import websockets
from dotenv import load_dotenv

# ====================== НАСТРОЙКИ ======================

FORMAT = pyaudio.paInt16

CHANNELS = 1

IN_RATE = 16000

OUT_RATE = 24000

CHUNK = 2048

audio_queue: asyncio.Queue = asyncio.Queue(maxsize=100)

is_ai_talking = False


# ======================================================


async def speaker_worker(speaker):
    global is_ai_talking

    while True:

        data = await audio_queue.get()

        is_ai_talking = True

        print("\r\033[95m🎙️  Gemini говорит...\033[0m", end="", flush=True)

        await asyncio.to_thread(speaker.write, data)

        audio_queue.task_done()

        if audio_queue.empty():
            await asyncio.sleep(0.5)

            is_ai_talking = False

            print("\r\033[92m✅ Слушаю...\033[0m", end="", flush=True)


async def receive_loop(websocket, setup_event):
    async for message in websocket:

        try:

            resp = json.loads(message)

            if "setupComplete" in resp:
                print("\n\033[92m✓ Gemini Live подключён\033[0m\n")

                setup_event.set()

                continue

            if "serverContent" in resp:

                sc = resp["serverContent"]

                if "modelTurn" in sc:

                    for part in sc.get("modelTurn", {}).get("parts", []):

                        if "inlineData" in part and part["inlineData"].get("mimeType") == "audio/pcm;rate=24000":
                            chunk = base64.b64decode(part["inlineData"]["data"])

                            await audio_queue.put(chunk)



        except Exception:

            pass


async def send_loop(websocket, mic):
    global is_ai_talking

    print("\033[93m🎤 Микрофон активен...\033[0m\n")

    while True:

        data = await asyncio.to_thread(mic.read, CHUNK, exception_on_overflow=False)

        # Защита от эха — отправляем только когда Gemini молчит

        if not is_ai_talking:

            msg = {

                "realtimeInput": {

                    "audio": {

                        "data": base64.b64encode(data).decode("utf-8"),

                        "mimeType": "audio/pcm;rate=16000"

                    }

                }

            }

            try:

                await websocket.send(json.dumps(msg))

            except:

                break

        await asyncio.sleep(0.001)


async def main():
    load_dotenv()

    api_key = os.getenv("API_KEY")

    if not api_key:
        print("\033[91mAPI_KEY не найден в .env\033[0m")

        return

    print("\033[1m\033[97m═══════════════════════════════════════\033[0m")

    print("\033[1m     Gemini Live Voice Assistant (минимальный)\033[0m")

    print("\033[1m\033[97m═══════════════════════════════════════\033[0m\n")

    p = pyaudio.PyAudio()

    mic = p.open(format=FORMAT, channels=CHANNELS, rate=IN_RATE, input=True, frames_per_buffer=CHUNK)

    speaker = p.open(format=FORMAT, channels=CHANNELS, rate=OUT_RATE, output=True, frames_per_buffer=CHUNK)

    setup_complete = asyncio.Event()

    try:

        ws_url = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={api_key}"

        async with websockets.connect(

                ws_url,

                family=socket.AF_INET,

                ping_interval=20,

                open_timeout=20

        ) as ws:

            # Минимальный setup без лишних настроек VAD

            setup = {

                "setup": {

                    "model": "models/gemini-3.1-flash-live-preview",

                    "generationConfig": {

                        "responseModalities": ["AUDIO"],

                        "speechConfig": {

                            "voiceConfig": {

                                "prebuiltVoiceConfig": {"voiceName": "Algieba"}

                            }

                        }

                    }

                }

            }

            await ws.send(json.dumps(setup))

            receive_task = asyncio.create_task(receive_loop(ws, setup_complete))

            await asyncio.wait_for(setup_complete.wait(), timeout=15)

            print("\033[92mГотов к работе.\033[0m\n")

            send_task = asyncio.create_task(send_loop(ws, mic))

            speaker_task = asyncio.create_task(speaker_worker(speaker))

            await asyncio.wait([receive_task, send_task, speaker_task], return_when=asyncio.FIRST_COMPLETED)



    except Exception as e:

        print(f"\n\033[91mОшибка: {e}\033[0m")

    finally:

        print("\n\033[93mЗавершение...\033[0m")

        if mic.is_active():
            mic.stop_stream()
            mic.close()

        if speaker.is_active():
            speaker.stop_stream()
            speaker.close()

        p.terminate()

if __name__ == "__main__":
    asyncio.run(main())
