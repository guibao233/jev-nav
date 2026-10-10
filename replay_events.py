"""Display saved action outcomes on the following (post-action) observation."""
from PIL import ImageDraw, ImageFont

FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
COLLISION_COLOR = "#ff4b4b"
INVALID_COLOR = "#ffc247"
ACTIONS = {"move_forward":"前进", "move_backward":"后退", "move_left":"左移",
           "move_right":"右移", "turn_left":"左转", "turn_right":"右转",
           "look_up":"抬头", "look_down":"低头", "stop":"停止"}
EVENT_TIMING = "Previous completed action, displayed on the following observation (including terminal); never the current pending action."


def action_event(record):
    outcome = record.get("outcome") or {}
    kinds = []
    if outcome.get("collided") is True:
        kinds.append("collision")
    if outcome.get("valid") is False:
        kinds.append("invalid")
    if not kinds:
        return None
    action = outcome.get("action") or (record.get("decision") or {}).get("choice", "unknown")
    step = record["step"] + 1
    title = " + ".join("碰撞" if kind == "collision" else "无效动作" for kind in kinds)
    return {"kinds":kinds,"action":action,"step_1based":step,
            "label":f"{title} · 第 {step} 步 {ACTIONS.get(action, action)}后",
            "reason":outcome.get("result"),"position":record.get("after_position"),
            "color":COLLISION_COLOR if "collision" in kinds else INVALID_COLOR}


def observation_event(records, index):
    """The frame at index is before its action and after the previous action."""
    if index <= 0:
        return None
    event = action_event(records[index-1])
    if event is not None and event["position"] is None:
        event["position"] = records[index]["pose"]["position"]
    return event


def completed_events(records, index):
    # Deliberately exclude records[index].outcome: it happens after this image.
    return [event for i in range(1,index+1) if (event := observation_event(records,i)) is not None]


def draw_event_marker(draw, center, kinds, radius=8):
    x,y = center
    for kind in kinds:
        if kind == "collision":
            draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill="#131923",outline=COLLISION_COLOR,width=3)
            d = radius*.42
            draw.line((x-d,y-d,x+d,y+d),fill=COLLISION_COLOR,width=2)
            draw.line((x-d,y+d,x+d,y-d),fill=COLLISION_COLOR,width=2)
        else:
            # A square and exclamation mark also distinguish events without color.
            draw.rectangle((x-radius,y-radius,x+radius,y+radius),fill="#131923",outline=INVALID_COLOR,width=3)
            draw.line((x,y-radius*.5,x,y+radius*.1),fill=INVALID_COLOR,width=2)
            draw.ellipse((x-1,y+radius*.4-1,x+1,y+radius*.4+1),fill=INVALID_COLOR)


def annotate_event(image, event, *, top=12):
    """Return a display copy; never modify the source RGB or depth image."""
    canvas = image.convert("RGB").copy()
    if event is None:
        return canvas
    draw = ImageDraw.Draw(canvas)
    width,height = canvas.size
    size = min(18,max(10,width//34))
    font = ImageFont.truetype(FONT_PATH,size)
    margin = min(10,max(2,width//64))
    top = min(top,max(0,height-size-16))
    draw.rectangle((2,2,width-3,height-3),outline=event["color"],width=max(2,width//160))
    draw.rounded_rectangle((margin,top,width-margin,top+size+18),radius=5,fill="#131923",outline=event["color"],width=2)
    draw_event_marker(draw,(margin+16,top+(size+18)/2),event["kinds"],radius=8)
    draw.text((margin+32,top+5),event["label"],font=font,fill=event["color"])
    return canvas
