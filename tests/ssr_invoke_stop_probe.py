# -*- coding: utf-8 -*-
"""探针 3：job 渲染途中把 scene.frame_end 改小，能否让动画渲染提前收尾（用于"立即取消"）。"""
import os
import time

import bpy

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tmp_invoke3")
OUT = os.path.abspath(OUT)
ST = {"phase": "build", "ticks": 0, "job_seen": False, "t_edit": 0.0,
      "frame_at_edit": None, "frames_reported": []}


def log(*a):
    print("[probe3]", *a, flush=True)


def on_stats(scene, *a):
    try:
        ST["frames_reported"].append(scene.frame_current)
    except Exception:
        pass


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
    obj.keyframe_insert("location", frame=300)

    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x = 160
    sc.render.resolution_y = 90
    sc.render.fps = 24
    sc.frame_start = 1
    sc.frame_end = 300

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
    bpy.app.handlers.render_stats.append(on_stats)


def tick():
    if ST["phase"] == "build":
        ST["phase"] = "dispatch"
        return 0.1

    if ST["phase"] == "dispatch":
        win = bpy.context.window_manager.windows[0]
        with bpy.context.temp_override(window=win, screen=win.screen):
            bpy.ops.render.render("INVOKE_DEFAULT", animation=True)
        ST["phase"] = "wait"
        return 0.05

    running = bpy.app.is_job_running("RENDER")
    ST["ticks"] += 1
    if running:
        ST["job_seen"] = True

    if ST["phase"] == "wait" and running and len(ST["frames_reported"]) >= 8:
        sc = bpy.context.scene
        ST["frame_at_edit"] = sc.frame_current
        if ST["frames_reported"]:
            sc.frame_end = min(sc.frame_end, ST["frames_reported"][-1] + 1)
        log("EDIT_FRAME_END", "frame_current", sc.frame_current, "end", sc.frame_end)
        ST["t_edit"] = time.time()
        ST["phase"] = "stopping"
        return 0.05

    if ST["phase"] == "stopping" and not running:
        log("STOPPED_AFTER", round(time.time() - ST["t_edit"], 2))
        log("FRAMES_RENDERED", len(ST["frames_reported"]))
        log("FILES", sorted(os.listdir(OUT)) if os.path.isdir(OUT) else [])
        ST["phase"] = "done"
        bpy.app.timers.register(quit_now, first_interval=0.3)
        return None

    if ST["phase"] == "wait":
        return 0.05
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
