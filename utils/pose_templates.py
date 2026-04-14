from PIL import Image, ImageDraw
from typing import List

def get_pose_template(index: int, size=(512, 512)) -> Image.Image:
    """
    Returns a simple pose template image for ControlNet pose conditioning.
    In a real system, this would use OpenPose or a pose dataset.
    Here, we draw simple stick figures for demonstration.
    """
    img = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(img)
    w, h = size
    cx, cy = w // 2, h // 2

    # Different poses for each scene
    if index == 0:
        # Standing, arms out
        draw.line((cx, cy+80, cx, cy-80), fill="black", width=8)  # body
        draw.line((cx, cy-80, cx-40, cy-120), fill="black", width=6)  # left arm
        draw.line((cx, cy-80, cx+40, cy-120), fill="black", width=6)  # right arm
        draw.line((cx, cy+80, cx-30, cy+140), fill="black", width=6)  # left leg
        draw.line((cx, cy+80, cx+30, cy+140), fill="black", width=6)  # right leg
        draw.ellipse((cx-24, cy-120-24, cx+24, cy-120+24), outline="black", width=5)  # head
    elif index == 1:
        # Waving
        draw.line((cx, cy+80, cx, cy-80), fill="black", width=8)
        draw.line((cx, cy-80, cx-40, cy-120), fill="black", width=6)
        draw.line((cx, cy-80, cx+60, cy-160), fill="black", width=6)  # right arm up
        draw.line((cx, cy+80, cx-30, cy+140), fill="black", width=6)
        draw.line((cx, cy+80, cx+30, cy+140), fill="black", width=6)
        draw.ellipse((cx-24, cy-120-24, cx+24, cy-120+24), outline="black", width=5)
    elif index == 2:
        # Sitting
        draw.line((cx, cy+40, cx, cy-60), fill="black", width=8)
        draw.line((cx, cy-60, cx-40, cy-100), fill="black", width=6)
        draw.line((cx, cy-60, cx+40, cy-100), fill="black", width=6)
        draw.line((cx, cy+40, cx-40, cy+100), fill="black", width=6)
        draw.line((cx, cy+40, cx+40, cy+100), fill="black", width=6)
        draw.ellipse((cx-24, cy-100-24, cx+24, cy-100+24), outline="black", width=5)
    elif index == 3:
        # Hero pose
        draw.line((cx, cy+80, cx, cy-80), fill="black", width=8)
        draw.line((cx, cy-80, cx-60, cy-120), fill="black", width=6)
        draw.line((cx, cy-80, cx+60, cy-120), fill="black", width=6)
        draw.line((cx, cy+80, cx-40, cy+140), fill="black", width=6)
        draw.line((cx, cy+80, cx+40, cy+140), fill="black", width=6)
        draw.ellipse((cx-24, cy-120-24, cx+24, cy-120+24), outline="black", width=5)
    else:
        # Neutral
        draw.line((cx, cy+80, cx, cy-80), fill="black", width=8)
        draw.line((cx, cy-80, cx-40, cy-120), fill="black", width=6)
        draw.line((cx, cy-80, cx+40, cy-120), fill="black", width=6)
        draw.line((cx, cy+80, cx-30, cy+140), fill="black", width=6)
        draw.line((cx, cy+80, cx+30, cy+140), fill="black", width=6)
        draw.ellipse((cx-24, cy-120-24, cx+24, cy-120+24), outline="black", width=5)
    return img
