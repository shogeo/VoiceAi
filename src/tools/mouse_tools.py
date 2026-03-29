import pyautogui
from src.config import ButtonType
from src.utils import CoordinateConverter

class MouseTools:
    def __init__(self, converter: CoordinateConverter):
        self.converter = converter

    async def _move_mouse(self, x: int, y: int) -> str:
        px, py = self.converter.norm_to_pixels(x, y)
        pyautogui.moveTo(px, py, duration=0.25)
        return f"mouse moved to ({x}, {y}) → ({px}, {py})"

    async def _click(self, x: int, y: int, button: ButtonType = "left") -> str:
        px, py = self.converter.norm_to_pixels(x, y)
        pyautogui.moveTo(px, py, duration=0.2)
        pyautogui.click(button=button)
        return f"{button} click at ({x}, {y})"

    async def _double_click(self, x: int, y: int, button: ButtonType = "left") -> str:
        px, py = self.converter.norm_to_pixels(x, y)
        pyautogui.moveTo(px, py, duration=0.2)
        pyautogui.doubleClick(button=button)
        return f"double {button} click at ({x}, {y})"

    async def _mouse_down(self, x: int, y: int, button: ButtonType = "left") -> str:
        px, py = self.converter.norm_to_pixels(x, y)
        pyautogui.moveTo(px, py, duration=0.2)
        pyautogui.mouseDown(button=button)
        return f"{button} button pressed at ({x}, {y})"

    async def _mouse_up(self, x: int, y: int, button: ButtonType = "left") -> str:
        px, py = self.converter.norm_to_pixels(x, y)
        pyautogui.moveTo(px, py, duration=0.2)
        pyautogui.mouseUp(button=button)
        return f"{button} button released at ({x}, {y})"

    async def _drag_to(self, x: int, y: int, button: ButtonType = "left") -> str:
        px, py = self.converter.norm_to_pixels(x, y)
        pyautogui.dragTo(px, py, duration=0.6, button=button)
        return f"dragged with {button} button to ({x}, {y})"

    async def _scroll(self, delta: int) -> str:
        pyautogui.scroll(delta)
        direction = "up" if delta > 0 else "down"
        return f"scrolled {direction} by {abs(delta)}"

    async def _get_mouse_position(self) -> dict:
        x, y = pyautogui.position()
        x_norm, y_norm = self.converter.pixels_to_norm(x, y)
        return {"x": x_norm, "y": y_norm, "pixel_x": x, "pixel_y": y}
