import pyautogui
from typing import List

class KeyboardTools:
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
