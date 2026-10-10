"""Build and optionally serve a portable, offline Jev navigation replay.

Example: python visualize.py --run runs/jev-first-5steps-02 --serve --port 8765
No simulator, GPU, network model requests, or API key required.
"""
import argparse
import copy
from datetime import datetime
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image

from replay import write_replay
from replay_events import EVENT_TIMING


def read_run(run):
    """Validate and snapshot only the inputs required to visualize a saved run."""
    run = Path(run).resolve()
    sources = {}

    def source(name):
        path = (run/name).resolve()
        try:
            relative = path.relative_to(run)
        except ValueError as exc:
            raise ValueError(f"记录中的文件路径超出实验目录：{name}") from exc
        if not path.is_file():
            raise ValueError(f"缺少回放文件：{path}")
        sources[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path

    metadata = json.loads(source("metadata.json").read_text())
    summary = json.loads(source("summary.json").read_text())
    records = [json.loads(line) for line in source("steps.jsonl").read_text().splitlines() if line.strip()]
    if not records:
        raise ValueError("该实验没有保存观察帧，无法可视化；请检查是否在初始化期间退出。")
    with Image.open(source("navmap.png")) as im:
        im.verify()
    images = []
    for index, record in enumerate(records):
        if not record.get("images",{}).get("depth"):
            raise ValueError(f"第 {index+1} 条记录没有深度图路径")
        channels = {}
        for channel in ("rgb","depth"):
            name = record["images"].get(channel)
            channels[channel] = source(name) if name else None
            if channels[channel]:
                with Image.open(channels[channel]) as im:
                    im.verify()
        images.append(channels)
    return run, metadata, summary, records, images, sources


def default_output(run):
    parent = Path(run).resolve()/"visualizations"
    stem = datetime.now().strftime("view-%Y%m%d-%H%M%S")
    path = parent/stem
    suffix = 1
    while path.exists():
        path = parent/f"{stem}-{suffix:02d}"
        suffix += 1
    return path


def encoder_path(name, supplied=None):
    if supplied:
        path = Path(supplied).expanduser()
    else:
        known = Path("/data/guiyuanze/miniconda3/envs/concerto/bin")/name
        found = shutil.which(name)
        path = known if known.is_file() else Path(found) if found else None
    if path is None or not path.is_file():
        raise ValueError(f"找不到 {name}；可通过 --{name} 指定路径，或不加 --media 只生成 HTML。")
    return path.resolve()


def build_viewer(run, out=None, *, media=False, ffmpeg=None, ffprobe=None):
    if out is not None and Path(out).exists():
        raise FileExistsError(f"输出目录已存在，不会覆盖：{out}")
    run, metadata, summary, records, images, sources = read_run(run)
    if media:
        ffmpeg, ffprobe = encoder_path("ffmpeg",ffmpeg), encoder_path("ffprobe",ffprobe)
    out = Path(out).resolve() if out is not None else default_output(run)
    out.mkdir(parents=True,exist_ok=False)
    (out/"observations").mkdir()
    print(f"[visualize] 已读取 {len(records)} 幅观察，正在生成：{out}",flush=True)
    display_records = copy.deepcopy(records)
    for i, channels in enumerate(images):
        for channel, path in channels.items():
            if path is not None:
                name = f"observations/{i:05d}-{channel}{path.suffix}"
                shutil.copyfile(path,out/name)
                display_records[i]["images"][channel] = name
    shutil.copyfile(run/"navmap.png",out/"navmap.png")
    # The embedded requests stay unchanged; only local display image paths differ.
    write_replay(out,metadata,display_records,summary,media_prefix="media" if media else None)
    if media:
        print("[visualize] 正在导出 MP4 / GIF / 静态总览（不调用 Jev）...",flush=True)
        from export_replay import export
        export(run,out/"media",ffmpeg,ffprobe)
    for name,digest in sources.items():
        if hashlib.sha256((run/name).read_bytes()).hexdigest()!=digest:
            raise RuntimeError(f"导出期间源文件发生变化：{name}；请在任务结束后重试。")
    manifest = {"source_run":str(run),"source_sha256":sources,"observations":len(records),
        "media_exported":bool(media),"entry":"index.html","portable":True,
        "reran_simulator":False,"called_jev":False,"event_timing":EVENT_TIMING,
        "target_source":"actual logged requests transformed by each observation's body pose"}
    (out/"visualization.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
    (out/"README.md").write_text(
        f"# Jev 导航可视化\n\n来源：`{run}`；共 {len(records)} 幅观察。\n\n"
        "打开 `index.html`，可播放、拖动时间轴、前后逐帧查看、调整播放间隔；键盘左右箭头也可切换。\n\n"
        "绿色 S 起点、红色 G 终点；蓝线初始最短路径、橙线已执行轨迹、白箭头当前机器人；粉色 T 为当前目标，青色编号点为实际发送给 Jev 的前方路径点。最后终态没有新的目标。\n\n"
        "碰撞显示红色圈叉/边框，无效动作显示黄色方框叹号/边框；RGB 和 NavMesh 同步高亮上一动作后的观察，终态也适用。地图保留已发生事件的机器人位置，并不表示精确接触点。\n\n"
        "此目录包含页面依赖的全部图像，可以整体下载到本机。播放间隔仅控制展示，不代表实验真实耗时。`visualization.json` 保存来源和哈希；没有重跑实验或调用 Jev。\n\n"
        +( "`media/` 中包含 MP4、GIF、总览和单独地图帧。\n" if media else "本次仅生成 HTML；使用 --media 可同时导出视频和动图。\n"),encoding="utf-8")
    print(f"[visualize] 回放入口：{out/'index.html'}",flush=True)
    return out


def make_server(directory, port):
    """Serve only the self-contained export directory, on loopback."""
    handler = partial(SimpleHTTPRequestHandler,directory=str(Path(directory).resolve()))
    return ThreadingHTTPServer(("127.0.0.1",port),handler)


def serve(directory, port):
    with make_server(directory,port) as server:
        actual_port = server.server_address[1]
        print(f"[visualize] 浏览器地址：http://127.0.0.1:{actual_port}/index.html",flush=True)
        print(f"[visualize] 远程服务器：在 VS Code 中转发端口 {actual_port} 后打开该地址；Ctrl+C 关闭服务。",flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n[visualize] 浏览服务已关闭，生成文件已保留。",flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",type=Path,required=True,help="实验目录，包含 metadata.json、steps.jsonl、summary.json、navmap.png 和帧图像")
    p.add_argument("--out",type=Path,help="新的输出目录；默认在实验目录的 visualizations/ 下自动生成")
    p.add_argument("--media",action="store_true",help="同时生成 RGB + 深度 + NavMesh 的 MP4、GIF 和总览")
    p.add_argument("--serve",action="store_true",help="生成后启动仅本机可访问的 HTTP 浏览服务")
    p.add_argument("--port",type=int,default=8765,help="浏览端口，默认 8765；0 表示自动选择")
    p.add_argument("--ffmpeg",type=Path,help="--media 使用的 ffmpeg 路径")
    p.add_argument("--ffprobe",type=Path,help="--media 使用的 ffprobe 路径")
    args = p.parse_args()
    if not 0<=args.port<=65535:
        p.error("--port 必须在 0～65535 之间")
    try:
        out = build_viewer(args.run,args.out,media=args.media,ffmpeg=args.ffmpeg,ffprobe=args.ffprobe)
        if args.serve:
            serve(out,args.port)
    except KeyboardInterrupt:
        return 130
    except (OSError,ValueError,KeyError,RuntimeError,subprocess.CalledProcessError) as exc:
        p.exit(2,f"[visualize] {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
