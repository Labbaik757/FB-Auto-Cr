"""
Shared human-behavior utilities for ALL automation modules.
Used by: browser_register.py (Mode 2), fb_automation.py (Mode 3), outlook_register.py (Mode 4).

Implements:
1. Bezier-curve mouse movement (not straight lines)
2. Natural typing with typos + variable speed
3. Human scroll with reading pauses
"""
import random
import time


def human_pause(min_s=1.5, max_s=2.5):
    """Random pause between actions."""
    time.sleep(random.uniform(min_s, max_s))


def _bezier_points(x0, y0, x3, y3, num_points=20):
    """Generate Bezier curve points between two coordinates."""
    dx = abs(x3 - x0) * 0.3
    dy = abs(y3 - y0) * 0.3
    x1 = x0 + (x3 - x0) * 0.3 + random.uniform(-dx, dx)
    y1 = y0 + (y3 - y0) * 0.3 + random.uniform(-dy, dy)
    x2 = x0 + (x3 - x0) * 0.7 + random.uniform(-dx, dx)
    y2 = y0 + (y3 - y0) * 0.7 + random.uniform(-dy, dy)
    points = []
    for i in range(num_points):
        t = i / max(num_points - 1, 1)
        xt = (1-t)**3*x0 + 3*(1-t)**2*t*x1 + 3*(1-t)*t**2*x2 + t**3*x3
        yt = (1-t)**3*y0 + 3*(1-t)**2*t*y1 + 3*(1-t)*t**2*y2 + t**3*y3
        points.append((int(xt), int(yt)))
    return points


def human_mouse_move(page, x, y, from_x=None, from_y=None):
    """Move mouse along a natural Bezier curve (not a straight line)."""
    try:
        if from_x is None or from_y is None:
            # Start from a random nearby point if no start given
            from_x = x + random.randint(-200, 200)
            from_y = y + random.randint(-150, 150)
        points = _bezier_points(from_x, from_y, x, y)
        for px, py in points:
            page.mouse.move(px, py)
            time.sleep(random.uniform(0.005, 0.02))
    except Exception:
        try:
            page.mouse.move(x, y)
        except Exception:
            pass


def human_type(page_or_locator, text, make_typos=True):
    """Type text naturally: variable speed, slower at word edges, occasional typos."""
    for i, char in enumerate(text):
        # Occasional typo: wrong char -> pause -> backspace -> correct
        if make_typos and char.isalpha() and random.random() < 0.005:
            wrong = random.choice('qwertyuiopasdfghjklzxcvbnm')
            try:
                page_or_locator.type(wrong, delay=random.randint(30, 80))
            except Exception:
                pass
            time.sleep(random.uniform(0.2, 0.4))
            try:
                page_or_locator.press('Backspace')
            except Exception:
                pass
            time.sleep(random.uniform(0.1, 0.2))
        # Variable speed: slower at start/end of text
        delay = random.uniform(0.03, 0.12)
        if i == 0 or i == len(text) - 1:
            delay += random.uniform(0.05, 0.15)
        try:
            page_or_locator.type(char, delay=int(delay * 1000))
        except Exception:
            pass
        # Occasional thinking pause mid-typing
        if random.random() < 0.03:
            time.sleep(random.uniform(0.3, 0.8))


def human_scroll(page, min_scrolls=1, max_scrolls=3):
    """Scroll like a human reading: random direction, distance, and pauses."""
    scrolls = random.randint(min_scrolls, max_scrolls)
    for _ in range(scrolls):
        direction = 1 if random.random() > 0.2 else -1  # 80% down, 20% up
        distance = random.randint(100, 500) * direction
        try:
            page.mouse.wheel(0, distance)
        except Exception:
            pass
        time.sleep(random.uniform(0.8, 2.0))


def human_click(page, locator):
    """Click using Bezier mouse movement for natural cursor path."""
    try:
        box = locator.bounding_box(timeout=5000)
        if box:
            cx = box["x"] + box["width"] / 2
            cy = box["y"] + box["height"] / 2
            human_mouse_move(page, cx, cy)
            time.sleep(random.uniform(0.1, 0.3))
        locator.click(timeout=10000)
    except Exception:
        try:
            locator.click(force=True, timeout=5000)
        except Exception:
            pass
