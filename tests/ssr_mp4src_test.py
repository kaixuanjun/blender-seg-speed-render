"""复现用户的场景：VSE 里的音频条带，来源是「视频文件去掉画面只留音轨」。

两个 Sound strip 串行排布，源都是 mp4。渲染后检查成片各时间点的音频频率。
"""
import bpy
import os
_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.abspath(os.path.join(_TEST_HERE, ".."))
import subprocess

WS = _WS
OUT = os.path.join(WS, "ssr_mp4src_out")
FF = "ffmpeg"
os.makedirs(OUT, exist_ok=True)

A = os.path.join(OUT, "a.mp4")
B = os.path.join(OUT, "b.mp4")
FINAL = os.path.join(OUT, "mp4src_final.mp4")


def sh(args):
    return subprocess.run([FF, "-y"] + args, capture_output=True, text=True)


# 两段带音轨的视频：A=440Hz 2 秒，B=1320Hz 2 秒
sh(["-f", "lavfi", "-i", "testsrc=size=320x180:rate=24:duration=2",
    "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
    "-ac", "2", "-ar", "48000", "-shortest", A])
sh(["-f", "lavfi", "-i", "testsrc=size=320x180:rate=24:duration=2",
    "-f", "lavfi", "-i", "sine=frequency=1320:duration=2",
    "-ac", "2", "-ar", "48000", "-shortest", B])

for p in (FINAL,):
    if os.path.exists(p):
        os.remove(p)

# ---- 场景 ----
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.render.resolution_x = 320
sc.render.resolution_y = 180
sc.render.resolution_percentage = 100
sc.render.fps = 24
sc.frame_start = 1
sc.frame_end = 96

if sc.camera is None:
    cam_data = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cam_data)
    sc.collection.objects.link(cam)
    cam.location = (7, -7, 5)
    cam.rotation_euler = (1.1, 0, 0.785)
    sc.camera = cam

se = sc.sequence_editor_create()
for s in list(se.strips):
    se.strips.remove(s)

s1 = se.strips.new_sound(name="A", filepath=A, channel=1, frame_start=1)
s2 = se.strips.new_sound(name="B", filepath=B, channel=2, frame_start=49)
print("STRIPS", len(list(se.strips)), s1.frame_final_start, s1.frame_final_end,
      s2.frame_final_start, s2.frame_final_end)

sc.render.use_sequencer = False

# ---- 插件 ----
mod = "bl_ext.user_default.seg_speed_render"
if not hasattr(bpy.types.Scene, "ssr"):
    import importlib
    m = importlib.import_module(mod)
    m.register()

s = sc.ssr
s.segments.clear()
for a, b, st in ((1, 48, 1), (49, 96, 1)):
    seg = s.segments.add()
    seg.start, seg.end, seg.step = a, b, st
s.out_dir = OUT
s.output_mode = "VIDEO"
s.keep_segments = False
s.video_path = FINAL
s.fps = 24
s.fps_base = 1.0
s.quality = "HIGH"
s.audio_mode = "SCENE"
s.audio_follow_speed = True
s.auto_shutter = False


def quit_now():
    bpy.ops.wm.quit_blender()
    return None


def on_complete(scene, *a):
    if str(s.progress_text).startswith("完成") or "失败" in str(s.progress_text):
        print("FINAL_TEXT", s.progress_text)
        bpy.app.timers.register(quit_now, first_interval=0.2)


bpy.app.handlers.render_complete.append(on_complete)
print("PLAN", len(s.segments), "->", FINAL)
bpy.ops.seg_speed.render("EXEC_DEFAULT")
print("STARTED", s.running)
bpy.app.timers.register(lambda: (print("TICK", s.progress_text) or 1.0), first_interval=3.0)

