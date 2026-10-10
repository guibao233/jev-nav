"""Export existing navigation observations to MP4, GIF, and a contact sheet, offline."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont, ImageSequence
from map_view import draw_map, map_view, recorded_targets
from replay_events import annotate_event, observation_event, EVENT_TIMING


ACTIONS = {"move_forward":"前进", "move_backward":"后退", "move_left":"左移",
           "move_right":"右移", "turn_left":"左转", "turn_right":"右转",
           "look_up":"抬头", "look_down":"低头", "stop":"停止"}


def export(run, out, ffmpeg, ffprobe):
    run, out = run.resolve(), out.resolve()
    inputs = {}

    def source(name):
        path = (run/name).resolve()
        path.relative_to(run)
        inputs[str(path.relative_to(run))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path

    records = [json.loads(line) for line in source("steps.jsonl").read_text().splitlines()]
    metadata = json.loads(source("metadata.json").read_text())
    summary = json.loads(source("summary.json").read_text())
    if not records:
        raise ValueError("No recorded frames to export")
    with Image.open(source("navmap.png")) as image:
        navmap = image.convert("RGB")
    view = map_view(metadata,records)
    for record in records:
        for name in record["images"].values():
            if name:
                with Image.open(source(name)) as im:
                    im.verify()
    out.mkdir(parents=True, exist_ok=False)
    (out/"frames").mkdir()
    (out/"maps").mkdir()
    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    title_font = ImageFont.truetype(font_path, 26)
    font = ImageFont.truetype(font_path, 20)
    small_font = ImageFont.truetype(font_path, 17)
    no_depth_input = metadata.get("depth_input") == "none" or metadata.get("depth_provided_to_model") is False
    frames = []
    hold_ms = 1500
    for i, r in enumerate(records):
        canvas = Image.new("RGB",(1920,688),(19,25,35))
        draw = ImageDraw.Draw(canvas)
        event = observation_event(records,i)
        state = (r.get("request") or {}).get("state")
        decision, outcome = r.get("decision"), r.get("outcome")
        phase = f"第 {state['task']['step']} 步执行前" if state else "最后一次动作后的终态"
        draw.text((16,8),f"观察 {i+1}/{len(records)}  ·  {phase}",font=title_font,fill="#e4e9ef")
        if decision and outcome:
            action = ACTIONS.get(decision["choice"],decision["choice"])
            result = "碰撞" if outcome["collided"] else "无效动作" if not outcome["valid"] else "正常执行，无碰撞"
            caption = f"本帧之后的动作：{action}    |    执行结果：{result}"
        elif state:
            caption = "本帧未执行动作；请查阅原始日志中的服务或执行状态。"
        else:
            caption = f"结束状态：{summary['status']}    |    本帧未再次请求模型"
        draw.text((16,47),caption,font=font,fill="#ffd27c")
        rgb_label = "GS RGB" if metadata["rgb_mode"] == "gs" else "Mesh RGB"
        draw.text((16,83),f"{rgb_label}（仅供回放）",font=small_font,fill="#b8c5d6")
        depth_title = "Mesh 深度（仅供回放，未提供给模型）；0–6 m" if no_depth_input else "Mesh 深度：黄色近、紫色远；固定色标 0–6 m"
        draw.text((656,83),depth_title,font=small_font,fill="#b8c5d6")
        draw.text((1296,83),"NavMesh 局部俯视图：灰色可通行区；仅供回放",font=small_font,fill="#b8c5d6")
        map_image = draw_map(navmap,metadata,records,i,view)
        map_image.save(out/"maps"/f"{i:05d}.png")
        canvas.paste(map_image,(1280,112))
        for column, channel in enumerate(["rgb","depth"]):
            name = r["images"].get(channel)
            if name:
                with Image.open(run/name) as im:
                    panel = im.convert("RGB").resize((640,480),Image.Resampling.LANCZOS)
                    if channel == "rgb":
                        panel = annotate_event(panel,event)
                    canvas.paste(panel,(column*640,112))
            else:
                draw.text((column*640+16,250),"未保存该通道",font=font,fill="white")
        if state:
            if state.get("depth") is not None:
                sector = state["depth"]["sectors"][4]
                check = state["depth"]["move_checks"]["move_forward"]["status"]
                if state["depth"].get("format") == "semantic":
                    depth_caption = f"正前方：{sector['distance_band']} / {sector['observation']}   |   前进检查：{check}"
                else:
                    near = sector["nearest_obstacle_m"]
                    depth_caption = f"正前方区间最近障碍：{near} m   |   前进检查：{check}"
            else:
                depth_caption = "本帧未向模型提供深度摘要（无障碍距离或前进检查）"
            bearing = state["reference"]["current_target"]["bearing_deg"]
            draw.text((16,604),f"当前局部目标方位：{bearing:+.2f}°（左正右负）   |   {depth_caption}",font=small_font,fill="#e4e9ef")
            distance = state["reference"]["final_goal"]["distance_m"]
            draw.text((16,633),f"本帧到最终目标的水平直线距离：{distance:.3f} m",font=small_font,fill="#e4e9ef")
        else:
            distance = r["metrics"].get("distance_to_goal_geodesic_m")
            draw.text((16,604),f"终态到最终目标的 NavMesh 路径距离：{distance} m",font=small_font,fill="#e4e9ef")
        draw.text((16,660),"每幅观察停留 1.5 秒；仅使用已保存帧，无运动插值；播放时间不是实验实际耗时。",font=small_font,fill="#b8c5d6")
        canvas.save(out/"frames"/f"{i:05d}.png")
        frames.append(canvas)

    video = out/"rgb-depth.mp4"
    cmd = [str(ffmpeg),"-hide_banner","-loglevel","error","-n","-framerate","2/3",
           "-i",str(out/"frames/%05d.png"),"-vf","fps=30","-c:v","libx264","-crf","18",
           "-pix_fmt","yuv420p","-movflags","+faststart","-an",str(video)]
    subprocess.run(cmd,check=True)
    probe = json.loads(subprocess.check_output([str(ffprobe),"-v","error","-select_streams","v:0",
        "-count_frames","-show_entries","stream=codec_name,pix_fmt,width,height,nb_read_frames,r_frame_rate:format=duration",
        "-of","json",str(video)],text=True))
    stream = probe["streams"][0]
    assert stream["codec_name"] == "h264" and stream["pix_fmt"] == "yuv420p"
    assert (stream["width"],stream["height"]) == (1920,688)
    assert int(stream["nb_read_frames"]) == len(frames)*45
    assert abs(float(probe["format"]["duration"])-len(frames)*1.5) < .05
    subprocess.run([str(ffmpeg),"-v","error","-i",str(video),"-f","null","-"],check=True)
    frames[0].save(out/"rgb-depth.gif",save_all=True,append_images=frames[1:],duration=hold_ms,loop=0)
    with Image.open(out/"rgb-depth.gif") as gif:
        assert gif.n_frames == len(frames)
        assert sum(frame.info["duration"] for frame in ImageSequence.Iterator(gif)) == len(frames)*hold_ms
    sheet = Image.new("RGB",(1920,344*((len(frames)+1)//2)),(19,25,35))
    for i, frame in enumerate(frames):
        sheet.paste(frame.resize((960,344),Image.Resampling.LANCZOS),((i%2)*960,(i//2)*344))
    sheet.save(out/"contact-sheet.png")
    # A viewer requiring neither JavaScript nor sidecar image paths.
    import base64
    encoded = base64.b64encode((out/"rgb-depth.gif").read_bytes()).decode("ascii")
    (out/"view.html").write_text('<!doctype html><meta charset="utf-8"><title>导航决策逐帧回放</title>'
        '<body style="background:#131923;color:white;font:18px sans-serif"><p>RGB + 深度 + NavMesh 逐帧回放；每幅 1.5 秒，可直接查看同目录 GIF 或 MP4。</p>'
        '<img style="max-width:100%" src="data:image/gif;base64,'+encoded+'"></body>',encoding="utf-8")
    for name, digest in inputs.items():
        assert hashlib.sha256((run/name).read_bytes()).hexdigest() == digest,name
    (out/"export.json").write_text(json.dumps({"source_run":str(run),"source_sha256":inputs,
        "source_observations":len(frames),"seconds_per_observation":1.5,"timing":"constant display timing, not wall clock",
        "interpolation":False,"reran_simulator":False,"called_jev":False,"event_timing":EVENT_TIMING,"ffprobe":probe},indent=2))
    (out/"map-points.json").write_text(json.dumps({"view":view,"frames":[
        {"step":r["step"],"frame_kind":r["frame_kind"],"previous_action_event":observation_event(records,i),**recorded_targets(r)} for i,r in enumerate(records)]},indent=2))
    (out/"README.md").write_text(f"# 已保存观察的离线回放\n\n来源：`{run}`。共 {len(frames)} 幅观察，每幅停留 1.5 秒，展示时长 {len(frames)*1.5:g} 秒。包含动作前的观察及最后的终态，无运动插值，展示时间不代表实验耗时。\n\n"
        "- [MP4 视频](rgb-depth.mp4)：H.264/yuv420p，可下载后用本地播放器打开。\n"
        "- [GIF 动图](rgb-depth.gif)：适合 VS Code 图片预览。\n"
        "- [全部观察总览](contact-sheet.png)：静态图片。\n"
        "- [单文件页面](view.html)：内嵌 GIF，不依赖 JavaScript 或旁侧图片路径。\n\n"
        "三列依次为 RGB、mesh 深度、NavMesh 局部俯视图。绿色 S 为起点，红色 G 为终点；蓝线为初始最短路径，橙线为已执行轨迹；白箭头是当前机器人，粉色菱形 T 是当前目标，青色编号点是给模型 的前方采样。目标从当帧真实请求及身体位姿反算，水平坐标有原日志毫米级舍入误差；终态不伪造新的目标。\n\n"
        "红色圈叉/边框表示碰撞，黄色方框叹号/边框表示无效动作；RGB 与地图高亮上一动作完成后的观察，地图保留已发生事件的机器人位置，不是精确接触点。顶部动作结果文字仍对应本帧之后的动作。\n\n"
        "`maps/` 可单独查看地图帧，`map-points.json` 保存反算坐标和裁剪范围。动作与执行结果对应其前方显示的观察。原始日志及图像没有改写，没有重跑仿真或调用模型。`export.json` 保存源文件 SHA-256 及视频格式验证结果。\n",encoding="utf-8")
    print(json.dumps({"output":str(out),"observations":len(frames),"duration_s":len(frames)*1.5,"verified":True},ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--ffmpeg",type=Path,default=Path("/data/guiyuanze/miniconda3/envs/concerto/bin/ffmpeg"))
    p.add_argument("--ffprobe",type=Path,default=Path("/data/guiyuanze/miniconda3/envs/concerto/bin/ffprobe"))
    args = p.parse_args()
    export(args.run,args.out,args.ffmpeg,args.ffprobe)
