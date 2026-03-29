import pyautogui
from src.config import ButtonType
from src.utils import CoordinateConverter

class MouseTools:
    def __init__(self, converter: CoordinateConverter):
        self.converter = converter

    async def _move_mouse(self, x: int, y: int, duration: float = 0.25) -> str:
        px, py = self.converter.norm_to_pixels(x, y)
        pyautogui.moveTo(px, py, duration=duration)
        return f"mouse moved to ({x}, {y}) → ({px}, {py}) over {duration}s"

    async def _click(self, button: ButtonType = "left") -> str:
        pyautogui.click(button=button)
        return f"{button} click at current position"

    async def _double_click(self, button: ButtonType = "left") -> str:
        pyautogui.doubleClick(button=button)
        return f"double {button} click at current position"

    async def _mouse_down(self, button: ButtonType = "left") -> str:
        pyautogui.mouseDown(button=button)
        return f"{button} button pressed at current position"

    async def _mouse_up(self, button: ButtonType = "left") -> str:
        pyautogui.mouseUp(button=button)
        return f"{button} button released at current position"

    async def _drag_to(self, x: int, y: int, button: ButtonType = "left", duration: float = 0.6) -> str:
        px, py = self.converter.norm_to_pixels(x, y)
        pyautogui.dragTo(px, py, duration=duration, button=button)
        return f"dragged with {button} button to ({x}, {y}) over {duration}s"

    async def _scroll(self, delta: int) -> str:
        pyautogui.scroll(delta)
        direction = "up" if delta > 0 else "down"
        return f"scrolled {direction} by {abs(delta)}"

    async def _get_mouse_position(self) -> dict:
        x, y = pyautogui.position()
        x_norm, y_norm = self.converter.pixels_to_norm(x, y)
        return {"x": x_norm, "y": y_norm, "pixel_x": x, "pixel_y": y}
