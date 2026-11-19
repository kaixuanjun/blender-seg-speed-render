# -*- coding: utf-8 -*-
"""探针 2：job 渲染期间能否用 event_simulate(ESC) 立刻取消？
   - 观察 is_job_running 在帧与帧之间是否会短暂变 False（决定轮询要几次确认）
   - 观察 ESC 后 job 是否在 ~1 秒内结束
"""
import os
import time

import bpy

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tmp_invoke2")
OUT = os.path.abspath(OUT)
ST = {"phase": "build", "ticks": 0, "drops": 0, "job_seen": False,
      "esc_t": 0.0, "dispatched": 0.0, "first_job": 0.0, "last_running": None}


def log(*a):
    print("[probe2]", *a, flush=True)


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
    obj.keyframe_insert("location", frame=120)

    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x = 160
    sc.render.resolution_y = 90
    sc.render.fps = 24
    sc.frame_start = 1
    sc.frame_end = 120

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
    if ST["phase"] == "build":
        ST["phase"] = "dispatch"
        return 0.1

    if ST["phase"] == "dispatch":
        win = bpy.context.window_manager.windows[0]
        with bpy.context.temp_override(window=win, screen=win.screen):
            bpy.ops.render.render("INVOKE_DEFAULT", animation=True)
        ST["dispatched"] = time.time()
        ST["phase"] = "wait"
        return 0.05

    running = bpy.app.is_job_running("RENDER")
    ST["ticks"] += 1
    if running:
        if not ST["job_seen"]:
            ST["job_seen"] = True
            ST["first_job"] = time.time()
        ST["last_running"] = True
    elif ST["job_seen"]:
        ST["drops"] += 1
        ST["last_running"] = False

    if ST["phase"] == "wait":
        # 渲染 1.2 秒后发 ESC，看能不能立刻停
        if running and time.time() - ST["first_job"] > 1.2:
            win = bpy.context.window_manager.windows[0]
            try:
                win.event_simulate(type="ESC", value="PRESS")
                log("ESC_SENT")
            except Exception as exc:
                log("ESC_ERROR", exc)
            ST["esc_t"] = time.time()
            ST["phase"] = "cancel"
        return 0.05

    if ST["phase"] == "cancel":
        if running:
            return 0.05
        log("STOPPED_AFTER", round(time.time() - ST["esc_t"], 2))
        log("DROPS", ST["drops"])
        log("TICKS", ST["ticks"])
        log("FILES", sorted(os.listdir(OUT)) if os.path.isdir(OUT) else [])
        ST["phase"] = "done"
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
