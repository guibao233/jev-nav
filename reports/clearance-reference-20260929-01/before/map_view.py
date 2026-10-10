"""Offline NavMesh overlays from the path and targets actually stored in a run.

Only horizontal X/Z coordinates are shown. The request's rounded forward/left
values are inverted using that observation's body pose; no planner is called.
"""
import math

from PIL import Image, ImageDraw, ImageFont
from replay_events import (COLLISION_COLOR, INVALID_COLOR, annotate_event,
                           completed_events, draw_event_marker, observation_event)


COLORS = {"path":"#2974ee", "trajectory":"#ef9024", "start":"#0eaa50",
          "goal":"#ed394e", "target":"#d81b97", "preview":"#00acb8", "robot":"#ffffff"}
FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
PANEL_SIZE = (640,480)
MAP_BOX = (12,8,628,408)


def relative_to_world(point, pose):
    """Invert body-relative forward/left on the observation's horizontal plane."""
    x, y, z = pose["position"]
    yaw = pose["yaw_rad"]
    forward, left = point["forward_m"], point["left_m"]
    return [x-forward*math.sin(yaw)-left*math.cos(yaw), y,
            z-forward*math.cos(yaw)+left*math.sin(yaw)]


def recorded_targets(record):
    request = record.get("request")
    if not request:
        return {"current_target_world":None,"ordered_preview_world":[]}
    reference = request["state"]["reference"]
    return {"current_target_world":relative_to_world(reference["current_target"],record["pose"]),
            "ordered_preview_world":[relative_to_world(p,record["pose"]) for p in reference["ordered_preview"]]}


def world_pixel(point, metadata):
    m = metadata["map"]
    return ((point[0]-m["origin_x"])/m["resolution_m"],
            (point[2]-m["origin_z"])/m["resolution_m"])


def map_view(metadata, records):
    """One fixed crop per episode, covering start/goal, path and all observations."""
    task = metadata["task"]
    points = [task["start"],task["goal"],*task["path"]]
    for record in records:
        points.append(record["pose"]["position"])
        if record.get("after_position") is not None:
            points.append(record["after_position"])
        targets = recorded_targets(record)
        if targets["current_target_world"] is not None:
            points.append(targets["current_target_world"])
        points.extend(targets["ordered_preview_world"])
    pixels = [world_pixel(p,metadata) for p in points]
    xs, ys = zip(*pixels)
    pad = 1.0/metadata["map"]["resolution_m"]
    width, height = max(xs)-min(xs)+2*pad, max(ys)-min(ys)+2*pad
    aspect = (MAP_BOX[2]-MAP_BOX[0])/(MAP_BOX[3]-MAP_BOX[1])
    width = max(width,height*aspect)
    height = width/aspect
    cx, cy = (max(xs)+min(xs))/2, (max(ys)+min(ys))/2
    return {"crop_pixels":[cx-width/2,cy-height/2,cx+width/2,cy+height/2],
            "panel_size":list(PANEL_SIZE),"map_box":list(MAP_BOX),
            "axes":"world +X right, +Z down", "target_source":"actual request.state.reference, inverse body transform",
            "target_precision":"forward/left were logged to 0.001 m; horizontal projection only"}


def panel_pixel(point, metadata, view):
    x,y = world_pixel(point,metadata)
    left,top,right,bottom = view["crop_pixels"]
    return (MAP_BOX[0]+(x-left)/(right-left)*(MAP_BOX[2]-MAP_BOX[0]),
            MAP_BOX[1]+(y-top)/(bottom-top)*(MAP_BOX[3]-MAP_BOX[1]))


def draw_map(navmap, metadata, records, index, view=None):
    view = view or map_view(metadata,records)
    canvas = Image.new("RGB",PANEL_SIZE,"#131923")
    size = (MAP_BOX[2]-MAP_BOX[0],MAP_BOX[3]-MAP_BOX[1])
    cropped = navmap.convert("RGB").transform(size,Image.Transform.EXTENT,
        view["crop_pixels"],resample=Image.Resampling.NEAREST,fillcolor="#202020")
    canvas.paste(cropped,MAP_BOX[:2])
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(FONT_PATH,15)
    label_font = ImageFont.truetype(FONT_PATH,16)
    r = records[index]
    targets = recorded_targets(r)
    point = lambda p: panel_pixel(p,metadata,view)

    def line(points,color,width=3):
        if len(points)>1:
            draw.line([point(p) for p in points],fill=color,width=width,joint="curve")

    def label(x,y,text,color):
        draw.text((x,y),text,font=label_font,fill=color,stroke_width=2,stroke_fill="#131923")

    def dot(p,color,radius=6):
        x,y = point(p)
        draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=color,outline="#131923",width=2)
        return x,y

    line(metadata["task"]["path"],COLORS["path"],4)
    line([row["pose"]["position"] for row in records[:index+1]],COLORS["trajectory"],4)
    for i,p in enumerate(targets["ordered_preview_world"],1):
        x,y = dot(p,COLORS["preview"],5)
        label(x+9,y-10,str(i),COLORS["preview"])
    for key,text in [("start","S 起点"),("goal","G 终点")]:
        x,y = dot(metadata["task"][key],COLORS[key],8)
        label(x+13,y+5 if key=="start" else y-24,text,COLORS[key])
    # Only past completed actions are shown; positions are the agent's actual
    # post-action positions, not inferred mesh contact points.
    for event in completed_events(records,index):
        draw_event_marker(draw,point(event["position"]),event["kinds"])
    target = targets["current_target_world"]
    if target is not None:
        x,y = point(target)
        draw.polygon([(x,y-9),(x+9,y),(x,y+9),(x-9,y)],fill=COLORS["target"],outline="#131923",width=2)
        label(x-98,y-13,"T 当前目标",COLORS["target"])
        ref = r["request"]["state"]["reference"]
        caption = f"当前目标 {ref['current_target']['distance_m']:.2f} m；前方采样 {len(targets['ordered_preview_world'])} 点"
    else:
        caption = "终态：未再次请求 Jev，无新的目标点"
    # Body arrow: yaw-positive means turning towards world -X from world -Z.
    pose = r["pose"]
    front = relative_to_world({"forward_m":.38,"left_m":0},pose)
    left = relative_to_world({"forward_m":-.10,"left_m":.13},pose)
    right = relative_to_world({"forward_m":-.10,"left_m":-.13},pose)
    draw.polygon([point(front),point(left),point(right)],fill=COLORS["robot"],outline="#131923",width=2)
    x,y = point(pose["position"])
    event = observation_event(records,index)
    if event:
        # Ring the current body position without hiding its heading arrow.
        color = event["color"]
        draw.ellipse((x-20,y-20,x+20,y+20),outline=color,width=4)
    label(x-76,y+24 if event else y+14,"机器人",COLORS["robot"])
    draw.rounded_rectangle((18,14,400,40),radius=4,fill="#131923")
    draw.text((24,16),caption,font=font,fill="#e4e9ef")
    # Metric scale and explicit world axes, independent of camera orientation.
    scale = (MAP_BOX[2]-MAP_BOX[0])/(view["crop_pixels"][2]-view["crop_pixels"][0])/metadata["map"]["resolution_m"]
    draw.line([(28,382),(28+scale,382)],fill="#ffffff",width=3)
    draw.text((28,355),"1 m",font=font,fill="white",stroke_width=1,stroke_fill="#131923")
    draw.text((450,18),"+X →    +Z ↓",font=font,fill="white",stroke_width=1,stroke_fill="#131923")
    legends = [("S 起点","start",16,418),("G 终点","goal",120,418),
               ("机器人朝向","robot",224,418),("◆ 当前目标","target",390,418),
               ("━ 初始最短路径","path",16,448),("━ 已执行轨迹","trajectory",210,448),
               ("● 1…n 前方采样","preview",390,448)]
    for text,color,x,y in legends:
        draw.text((x,y),text,font=font,fill=COLORS[color])
    draw.rounded_rectangle((315,370,620,399),radius=4,fill="#131923")
    draw_event_marker(draw,(329,384),["collision"],7)
    draw.text((342,373),"碰撞位置",font=font,fill=COLLISION_COLOR)
    draw_event_marker(draw,(450,384),["invalid"],7)
    draw.text((463,373),"无效动作位置",font=font,fill=INVALID_COLOR)
    return annotate_event(canvas,event,top=46)
