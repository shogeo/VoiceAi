import pyperclip
import pyautogui
from typing import List

class ClipboardTools:
    async def _copy_text(self, text: str) -> str:
        """Copies the given text to the clipboard."""
        pyperclip.copy(text)
        return f"Text copied to clipboard."

    async def _paste_text(self) -> str:
        """Pastes the text from the clipboard by simulating Ctrl+V."""
        pyautogui.hotkey('ctrl', 'v')
        return "Pasted text from clipboard."

    async def _read_clipboard(self) -> str:
        """Reads and returns the current text from the clipboard."""
        content = pyperclip.paste()
        return content
