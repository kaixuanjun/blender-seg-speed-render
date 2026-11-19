# -*- coding: utf-8 -*-
"""探针 4：Cycles 慢速渲染中把 scene.frame_end 改小，能否让动画渲染提前收尾。"""
import os
import time

import bpy

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tmp_invoke4")
OUT = os.path.abspath(OUT)
ST = {"phase": "build", "job_seen": False, "t_edit": 0.0, "frames": 0, "samples": 24}


def log(*a):
    print("[probe4]", *a, flush=True)


def on_post(scene, *a):
    ST["frames"] += 1


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
    obj.keyframe_insert("location", frame=100)

    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = ST["samples"]
    sc.render.resolution_x = 320
    sc.render.resolution_y = 180
    sc.render.fps = 24
    sc.frame_start = 1
    sc.frame_end = 100

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
    bpy.app.handlers.render_post.append(on_post)


def tick():
    if ST["phase"] == "build":
        ST["phase"] = "dispatch"
        return 0.1
    if ST["phase"] == "dispatch":
        win = bpy.context.window_manager.windows[0]
        with bpy.context.temp_override(window=win, screen=win.screen):
            bpy.ops.render.render("INVOKE_DEFAULT", animation=True)
        ST["t0"] = time.time()
        ST["phase"] = "wait"
        return 0.05

    running = bpy.app.is_job_running("RENDER")
    if running:
        ST["job_seen"] = True

    if ST["phase"] == "wait":
        if running and time.time() - ST["t0"] > 3.0:
            sc = bpy.context.scene
            log("BEFORE frame_current", sc.frame_current, "end", sc.frame_end, "done", ST["frames"])
            sc.frame_end = 99  # 只改一点点，避免渲染器内部状态被打乱
            ST["t_edit"] = time.time()
            ST["phase"] = "trimmed"
            return 0.05
        if not running and ST["job_seen"]:
            log("FINISHED_NORMALLY frames", ST["frames"])
            ST["phase"] = "done"
            bpy.app.timers.register(quit_now, first_interval=0.3)
        return 0.05

    # trimmed：观察 job 是否很快结束
    if not running:
        log("STOPPED_AFTER", round(time.time() - ST["t_edit"], 2), "frames", ST["frames"])
        log("FILES", sorted(os.listdir(OUT)) if os.path.isdir(OUT) else [])
        ST["phase"] = "done"
        bpy.app.timers.register(quit_now, first_interval=0.3)
        return None
    if time.time() - ST["t_edit"] > 8.0:
        log("STILL_RUNNING frames", ST["frames"], "=> frame_end 修改无效")
        ST["phase"] = "done"
        bpy.app.timers.register(quit_now, first_interval=0.3)
        return None
    return 0.05


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
