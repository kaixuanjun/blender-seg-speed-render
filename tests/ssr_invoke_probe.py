# -*- coding: utf-8 -*-
"""探针：验证 render.render('INVOKE_DEFAULT', animation=True) 是否把渲染丢进 job，
从而让主循环（bpy.app.timers）继续跑、界面不假死。

输出：
  TICKS_DURING  n   渲染期间 timer 还能被调到的次数（>0 说明主循环活着）
  JOB_SEEN      True/False  是否观察到 is_job_running('RENDER')
  FILE          path/None   视频产物
"""
import os
import time

import bpy

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tmp_invoke")
OUT = os.path.abspath(OUT)
STATE = {"phase": "build", "ticks": 0, "job_seen": False, "t0": 0.0, "dispatched": 0.0}


def log(*a):
    print("[probe]", *a, flush=True)


def build():
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    sc.collection.objects.link(cam)
    cam.location = (7, -7, 5)
    cam.rotation_euler = (1.1, 0, 0.785)
    sc.camera = cam
    bpy.ops.mesh.primitive_cube_add(size=2)
    obj = bpy.context.view_layer.objects.active
    obj.keyframe_insert("location", frame=1)
    obj.location.x = 3
    obj.keyframe_insert("location", frame=20)

    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x = 160
    sc.render.resolution_y = 90
    sc.render.fps = 24
    sc.frame_start = 1
    sc.frame_end = 20
    sc.frame_step = 1

    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        try:
            os.remove(os.path.join(OUT, f))
        except OSError:
            pass

    sc.render.image_settings.media_type = "VIDEO"
    sc.render.image_settings.file_format = "FFMPEG"
    sc.render.ffmpeg.format = "MPEG4"
    sc.render.ffmpeg.codec = "H264"
    sc.render.filepath = os.path.join(OUT, "probe_")


def tick():
    if STATE["phase"] == "build":
        STATE["phase"] = "dispatch"
        return 0.1

    if STATE["phase"] == "dispatch":
        win = bpy.context.window_manager.windows[0]
        with bpy.context.temp_override(window=win, screen=win.screen):
            r = bpy.ops.render.render("INVOKE_DEFAULT", animation=True)
        log("INVOKE_RESULT", r)
        STATE["dispatched"] = time.time()
        STATE["t0"] = time.time()
        STATE["phase"] = "wait"
        return 0.05

    # wait：每 tick 记一次，证明主循环还活着
    STATE["ticks"] += 1
    running = bpy.app.is_job_running("RENDER")
    if running:
        STATE["job_seen"] = True
    if running or (time.time() - STATE["dispatched"] < 3.0):
        return 0.05

    files = sorted(os.listdir(OUT)) if os.path.isdir(OUT) else []
    log("TICKS_DURING", STATE["ticks"])
    log("JOB_SEEN", STATE["job_seen"])
    log("ELAPSED", round(time.time() - STATE["t0"], 2))
    log("FILES", files)
    STATE["phase"] = "done"
    bpy.app.timers.register(quit_now, first_interval=0.3)
    return None


def quit_now():
    print("QUIT", flush=True)
    bpy.ops.wm.quit_blender()
    return None


def setup():
    if bpy.context.window is None:
        return 0.3
    build()
    bpy.app.timers.register(tick, first_interval=0.2)
    return None


bpy.app.timers.register(setup, first_interval=0.5)
