# -*- coding: utf-8 -*-
"""验证 s.fps 是否真正决定成片帧率，且渲染后场景设置被还原。"""
import os
_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.abspath(os.path.join(_TEST_HERE, ".."))

import bpy

_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.abspath(os.path.join(_TEST_HERE, "..", "src", "__init__.py"))
OUT = os.path.join(_WS, "tmp", "ssr_fps_out")
video = os.path.join(OUT, "fps_final.mp4")

if not hasattr(bpy.types.Scene, "ssr"):
    exec(compile(open(ADDON, encoding="utf-8").read(), ADDON, "exec"), {})
    print("ADDON_EXEC_LOADED", flush=True)


def quit_now():
    print("QUIT", flush=True)
    bpy.ops.wm.quit_blender()
    return None


def check():
    s = bpy.context.scene.ssr
    if s.running:
        return 0.5
    r = bpy.context.scene.render
    print("FINAL_TEXT %s" % s.progress_text, flush=True)
    print("RESTORED fps=%d base=%.4f" % (r.fps, r.fps_base), flush=True)
    print("VIDEO_EXISTS %s" % os.path.isfile(video), flush=True)
    bpy.app.timers.register(quit_now, first_interval=0.3)
    return None


def setup():
    if bpy.context.window is None:
        return 0.3
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("C")
    cam = bpy.data.objects.new("C", cam_data)
    scene.collection.objects.link(cam)
    cam.location = (7.0, -7.0, 5.0)
    cam.rotation_euler = (1.1, 0.0, 0.785)
    scene.camera = cam

    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = 320
    scene.render.resolution_y = 180
    scene.render.fps = 24
    scene.render.fps_base = 1.0
    scene.frame_start = 1
    scene.frame_end = 48
    print("SCENE_FPS_BEFORE %d" % scene.render.fps, flush=True)

    if os.path.isdir(OUT):
        for f in os.listdir(OUT):
            try:
                os.remove(os.path.join(OUT, f))
            except Exception:
                pass
    os.makedirs(OUT, exist_ok=True)

    s = scene.ssr
    s.output_mode = "VIDEO"
    s.out_dir = OUT
    s.fps = 24
    s.fps_base = 1.001             # 真实帧率 23.976
    s.auto_compose = True
    s.keep_segments = False
    s.video_path = video
    s.audio_mode = "NONE"
    s.segments.clear()
    for start, end, step in [(1, 24, 1), (25, 48, 4)]:
        seg = s.segments.add()
        seg.start, seg.end, seg.step = start, end, step

    total = sum(sg.frame_count() for sg in s.segments)
    print("PLAN total=%d expect_sec=%.4f" % (total, total / (24.0 / 1.001)), flush=True)

    bpy.ops.seg_speed.render()
    bpy.app.timers.register(check, first_interval=1.0)
    return None


bpy.app.timers.register(setup, first_interval=0.5)
