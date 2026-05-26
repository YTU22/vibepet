import os
from PIL import Image, ImageDraw

def create_pixel_frame(state, frame_idx, total_frames):
    # Create a 32x32 canvas for pixel art
    im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    
    # Coordinates of the pet body
    # Center of body is roughly (16, 20)
    # Idle state
    if state == "idle":
        color = (100, 181, 246, 255) # Pastel Blue
        # Breathing effect: body squishes up/down
        h_offset = 0 if frame_idx % 2 == 0 else 1
        draw.ellipse([8, 12 + h_offset, 24, 28], fill=color, outline=(40, 90, 150, 255), width=1)
        # Eyes
        draw.rectangle([12, 17 + h_offset, 13, 19 + h_offset], fill=(33, 33, 33, 255))
        draw.rectangle([19, 17 + h_offset, 20, 19 + h_offset], fill=(33, 33, 33, 255))
        # Rosy cheeks
        draw.point((11, 20 + h_offset), fill=(255, 138, 128, 255))
        draw.point((21, 20 + h_offset), fill=(255, 138, 128, 255))
        # Mouth
        draw.line([(15, 20 + h_offset), (17, 20 + h_offset)], fill=(33, 33, 33, 255))
        
    elif state == "work":
        color = (129, 199, 132, 255) # Pastel Green
        draw.ellipse([8, 12, 24, 28], fill=color, outline=(30, 100, 40, 255), width=1)
        # Glasses (brown frame)
        draw.rectangle([11, 16, 14, 18], outline=(121, 85, 72, 255), fill=(255, 255, 255, 180))
        draw.rectangle([18, 16, 21, 18], outline=(121, 85, 72, 255), fill=(255, 255, 255, 180))
        draw.line([(14, 17), (18, 17)], fill=(121, 85, 72, 255))
        
        # Laptop
        # Alternating laptop screen/hands animation
        laptop_y = 22
        draw.rectangle([13, laptop_y, 22, 28], fill=(200, 200, 200, 255), outline=(100, 100, 100, 255))
        if frame_idx % 2 == 0:
            # Screen open and glowing
            draw.rectangle([14, laptop_y + 1, 21, laptop_y + 4], fill=(135, 206, 250, 255))
            # Hands typing
            draw.point((11, 24), fill=color)
            draw.point((23, 24), fill=color)
        else:
            # Hands in different positions
            draw.rectangle([14, laptop_y + 1, 21, laptop_y + 4], fill=(135, 206, 250, 200))
            draw.point((12, 23), fill=color)
            draw.point((22, 23), fill=color)

    elif state == "happy":
        color = (255, 213, 79, 255) # Pastel Yellow
        # Bouncing effect
        y_offset = -3 if frame_idx % 2 == 1 else 0
        w_offset = 1 if frame_idx % 2 == 1 else 0 # stretch vertical, narrow horizontal
        
        draw.ellipse([8 + w_offset, 12 + y_offset, 24 - w_offset, 28 + y_offset], fill=color, outline=(180, 130, 20, 255), width=1)
        # Happy eyes (^^)
        # Left eye ^
        draw.point((12, 17 + y_offset), fill=(33, 33, 33, 255))
        draw.point((13, 16 + y_offset), fill=(33, 33, 33, 255))
        draw.point((14, 17 + y_offset), fill=(33, 33, 33, 255))
        # Right eye ^
        draw.point((18, 17 + y_offset), fill=(33, 33, 33, 255))
        draw.point((19, 16 + y_offset), fill=(33, 33, 33, 255))
        draw.point((20, 17 + y_offset), fill=(33, 33, 33, 255))
        
        # Rosy cheeks
        draw.point((11, 19 + y_offset), fill=(255, 138, 128, 255))
        draw.point((21, 19 + y_offset), fill=(255, 138, 128, 255))
        
        # Open mouth (smiley)
        draw.rectangle([15, 19 + y_offset, 17, 21 + y_offset], fill=(239, 83, 80, 255))

    elif state == "tired":
        color = (176, 190, 197, 255) # Pastel Grey/Blue
        # Drooping body
        draw.ellipse([7, 14, 25, 28], fill=color, outline=(80, 90, 100, 255), width=1)
        # Worried/sad eyes
        draw.line([(12, 18), (14, 19)], fill=(60, 60, 60, 255))
        draw.line([(20, 18), (18, 19)], fill=(60, 60, 60, 255))
        # Sighing mouth
        draw.ellipse([15, 21, 17, 23], fill=(80, 90, 100, 255))
        
        # Sweat drop animation
        sweat_y = 10 + (frame_idx * 3)
        if sweat_y < 28:
            # Blue sweat drop
            draw.point((24, sweat_y), fill=(33, 150, 243, 255))
            draw.point((25, sweat_y + 1), fill=(33, 150, 243, 255))

    elif state == "sleep":
        color = (209, 196, 233, 255) # Pastel Lavender
        # Flattened sleeping body
        draw.ellipse([6, 16, 26, 28], fill=color, outline=(90, 80, 110, 255), width=1)
        # Sleeping closed eyes (--)
        draw.line([(10, 21), (13, 21)], fill=(74, 20, 140, 255))
        draw.line([(19, 21), (22, 21)], fill=(74, 20, 140, 255))
        
        # Zzz animation
        z_size = frame_idx
        z_x = 24 + z_size * 2
        z_y = 14 - z_size * 3
        if z_size > 0:
            # Draw a tiny Z
            draw.text((z_x, z_y), "z", fill=(103, 58, 183, 255))

    elif state == "angry":
        color = (239, 83, 80, 255) # Pastel Red
        # Shaking body
        shake_x = -1 if frame_idx % 2 == 0 else 1
        draw.ellipse([8 + shake_x, 12, 24 + shake_x, 28], fill=color, outline=(150, 30, 30, 255), width=1)
        # Angry eyes (\\ //)
        draw.line([(12, 16), (14, 18)], fill=(33, 33, 33, 255))
        draw.line([(20, 16), (18, 18)], fill=(33, 33, 33, 255))
        # Grumpy mouth (inverted arc)
        draw.line([(14, 21), (18, 21)], fill=(33, 33, 33, 255))
        draw.point((14, 22), fill=(33, 33, 33, 255))
        draw.point((18, 22), fill=(33, 33, 33, 255))
        
        # Steam clouds
        if frame_idx % 2 == 1:
            draw.ellipse([6 + shake_x, 6, 10 + shake_x, 10], fill=(255, 255, 255, 180))
            draw.ellipse([22 + shake_x, 6, 26 + shake_x, 10], fill=(255, 255, 255, 180))

    # Resize to 150x150 using NEAREST to preserve pixel art look
    return im.resize((150, 150), Image.Resampling.NEAREST)

def generate_assets():
    assets_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets"))
    os.makedirs(assets_dir, exist_ok=True)
    
    # 1. Generate PNG Icon (32x32 for System Tray)
    icon_im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    icon_draw = ImageDraw.Draw(icon_im)
    # A cute simple blue face for tray icon
    icon_draw.ellipse([4, 4, 28, 28], fill=(100, 181, 246, 255), outline=(40, 90, 150, 255), width=2)
    icon_draw.rectangle([10, 13, 12, 15], fill=(33, 33, 33, 255))
    icon_draw.rectangle([20, 13, 22, 15], fill=(33, 33, 33, 255))
    icon_draw.line([(14, 18), (18, 18)], fill=(33, 33, 33, 255))
    icon_im.save(os.path.join(assets_dir, "icon.png"))
    print("Generated icon.png")
    
    # 2. Generate animated GIFs
    states = ["idle", "work", "happy", "tired", "sleep", "angry"]
    durations = {
        "idle": 500,
        "work": 400,
        "happy": 300,
        "tired": 400,
        "sleep": 600,
        "angry": 200
    }
    
    for state in states:
        num_frames = 4
        frames = []
        for i in range(num_frames):
            frames.append(create_pixel_frame(state, i, num_frames))
        
        # Save as animated GIF
        gif_path = os.path.join(assets_dir, f"{state}.gif")
        frames[0].save(
            gif_path,
            save_all=True,
            append_images=frames[1:],
            optimize=False,
            duration=durations[state],
            loop=0,
            disposal=2 # Clear frame canvas before drawing next frame
        )
        print(f"Generated {state}.gif")

if __name__ == "__main__":
    generate_assets()
