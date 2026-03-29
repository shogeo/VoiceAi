import pyautogui

class CoordinateConverter:
    def __init__(self):
        self.screen_w, self.screen_h = pyautogui.size()

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
