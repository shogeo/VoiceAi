import asyncio
from src.main_controller import GeminiLiveComputerControl

if __name__ == "__main__":
    assistant = GeminiLiveComputerControl()
    asyncio.run(assistant.run())
