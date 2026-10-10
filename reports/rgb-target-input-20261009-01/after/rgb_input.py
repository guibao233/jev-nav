"""Deterministic waypoint overlay for model input; no depth/map/action queries.

OpenRouter multimodal state schema checked 2026-10-09:
https://openrouter.ai/docs/guides/community/multimodal-decisions
"""
import hashlib
import math
import numpy as np
from PIL import Image, ImageDraw

RGB_INPUT_MODES = ('none', 'target_marked')
VERSION = 'target_marked_rgb_v1'


def rgb_input_mode(cfg):
    mode = cfg.get('rgb_input', 'none')
    if mode not in RGB_INPUT_MODES:
        raise ValueError('RGB input must be none or target_marked')
    return mode


def validate_rgb_input(cfg, renderer):
    if rgb_input_mode(cfg) == 'none':
        return
    if cfg['model'] != 'openai/gpt-6-luna-decisions':
        raise ValueError('RGB input currently requires --decision-model openai')
    if renderer not in ('gs', 'mesh'):
        raise ValueError('RGB input requires --rgb gs or mesh')


def project_target(target, pitch_deg, cfg, target_height_m=0.):
    """Project current waypoint; pitch is positive down, left is image-left.

    target_height_m is waypoint height relative to the agent's feet. In-frame
    means projected into the image, not visible/unoccluded or collision-free.
    """
    h, w = cfg['resolution']
    forward, left = target['forward_m'], target['left_m']
    if not all(math.isfinite(x) for x in (forward, left, pitch_deg, target_height_m)):
        raise ValueError('nonfinite target projection')
    down = cfg['camera_height_m'] - target_height_m
    pitch = math.radians(pitch_deg)
    y = down*math.cos(pitch) - forward*math.sin(pitch)
    z = forward*math.cos(pitch) + down*math.sin(pitch)
    info = {'projection_status': 'camera_plane' if abs(z) <= 1e-8 else 'behind_camera', 'pixel_xy': None,
            'target_height_above_agent_feet_m': float(target_height_m),
            'camera_forward_m': float(z), 'occlusion_checked': False}
    if z > 1e-8:
        focal = w/(2*math.tan(math.radians(cfg['hfov_deg']/2)))
        u, v = (w-1)/2 - focal*left/z, (h-1)/2 + focal*y/z
        info['pixel_xy'] = [float(u), float(v)]
        info['projection_status'] = 'in_frame' if 0 <= u < w and 0 <= v < h else 'outside_frame'
    return info


def annotate_target(rgb, target, pitch_deg, cfg, target_height_m=0.):
    if rgb is None:
        raise ValueError('RGB input image is missing')
    pixels = np.asarray(rgb)
    h, w = cfg['resolution']
    if pixels.shape != (h, w, 3) or pixels.dtype != np.uint8:
        raise ValueError('RGB input image must match configured resolution and uint8 RGB')
    image = Image.fromarray(pixels.copy())
    draw = ImageDraw.Draw(image)
    info = project_target(target, pitch_deg, cfg, target_height_m)
    info.update(version=VERSION, target_kind='final_goal' if target['is_final'] else 'local_waypoint')
    color = (255, 70, 215)
    label = ('FINAL GOAL PROJECTION' if target['is_final'] else 'WAYPOINT PROJECTION') if info['projection_status'] == 'in_frame' else (
        'TARGET BEHIND CAMERA' if info['projection_status'] == 'behind_camera' else 'TARGET OUTSIDE IMAGE')
    draw.rectangle((4, 4, w-5, 37), fill=(20, 20, 20))
    draw.text((10, 7), label+' (virtual marker)', fill=color)
    draw.text((10, 22), f"distance {target['distance_m']:.3f} m | bearing {target['bearing_deg']:+.2f} deg (left +)", fill=(245, 245, 245))
    if info['projection_status'] == 'in_frame':
        x, y = info['pixel_xy']
        draw.ellipse((x-12, y-12, x+12, y+12), outline=(0, 0, 0), width=5)
        draw.ellipse((x-11, y-11, x+11, y+11), outline=color, width=3)
        draw.line((x-5, y, x+5, y), fill=color, width=2)
        draw.line((x, y-5, x, y+5), fill=color, width=2)
        info['marker_kind'], info['marker_pixel_xy'] = 'projected_point', [x, y]
    else:
        cx, cy = (w-1)/2, (h-1)/2
        if info['projection_status'] == 'camera_plane':
            dx, dy = 0., 1.
        elif info['pixel_xy'] is None:
            dx, dy = (-1. if target['left_m'] >= 0 else 1.), 0.
        else:
            dx, dy = info['pixel_xy'][0]-cx, info['pixel_xy'][1]-cy
        pad = min(50., w/4, h/4)
        scale = min((cx-pad)/abs(dx) if abs(dx) > 1e-8 else float('inf'),
                    (cy-pad)/abs(dy) if abs(dy) > 1e-8 else float('inf'))
        x, y = cx + dx*scale, cy + dy*scale
        norm = math.hypot(dx, dy); ux, uy = dx/norm, dy/norm
        bx, by = x-22*ux, y-22*uy
        draw.polygon([(x, y), (bx-10*uy, by+10*ux), (bx+10*uy, by-10*ux)], fill=color, outline=(0, 0, 0))
        info['marker_kind'], info['marker_pixel_xy'] = 'offscreen_arrow', [x, y]
    return image, info


def save_model_image(root, index, rgb, target, pitch_deg, cfg, target_height_m=0.):
    image, marker = annotate_target(rgb, target, pitch_deg, cfg, target_height_m)
    name = f'frames/{index:05d}-model-rgb.jpg'
    image.save(root/name, format='JPEG', quality=90, subsampling=0)
    data = (root/name).read_bytes()
    return {'path': name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'mime_type': 'image/jpeg', 'width': image.width, 'height': image.height,
            'marker': marker}, data
