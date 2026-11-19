"""模拟用户真实操作：VSE 里丢一个 mp3，面板全部保持默认值，直接点渲染。

不加任何 audio_mode 预设，专测「默认配置下用户会不会没声音」。
"""
import bpy
import os
_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.abspath(os.path.join(_TEST_HERE, ".."))
import subprocess

WS = _WS
OUT = os.path.join(WS, "ssr_mp3_out")
FF = "ffmpeg"
os.makedirs(OUT, exist_ok=True)

MP3 = os.path.join(OUT, "bgm.mp3")
FINAL = os.path.join(OUT, "file_final.mp4")

subprocess.run([FF, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                "-ac", "2", "-ar", "48000", "-b:a", "192k", MP3],
               capture_output=True, text=True)
if os.path.exists(FINAL):
    os.remove(FINAL)

sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.render.resolution_x = 320
sc.render.resolution_y = 180
sc.render.resolution_percentage = 100
sc.render.fps = 24
sc.frame_start = 1
sc.frame_end = 48

if sc.camera is None:
    cd = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cd)
    sc.collection.objects.link(cam)
    cam.location = (7, -7, 5)
    cam.rotation_euler = (1.1, 0, 0.785)
    sc.camera = cam

se = sc.sequence_editor_create()
for s in list(se.strips):
    se.strips.remove(s)
st = se.strips.new_sound(name="BGM", filepath=MP3, channel=1, frame_start=1)
print("STRIP", st.type, st.frame_final_start, st.frame_final_end, st.sound.filepath)
print("SOUND_LOADED", len(st.sound.buffers) if hasattr(st.sound, "buffers") else "n/a",
      st.sound.samplerate if hasattr(st.sound, "samplerate") else "")
sc.render.use_sequencer = False

if not hasattr(bpy.types.Scene, "ssr"):
    import importlib
    importlib.import_module("bl_ext.user_default.seg_speed_render").register()

s = sc.ssr
print("DEFAULT_AUDIO_MODE", s.audio_mode, "| FILE", repr(s.audio_file),
      "| FOLLOW", s.audio_follow_speed, "| VOL", s.audio_volume, "| OFFSET", s.audio_offset)

s.segments.clear()
for a, b, stp in ((1, 24, 1), (25, 48, 1)):
    seg = s.segments.add()
    seg.start, seg.end, seg.step = a, b, stp
s.out_dir = OUT
s.output_mode = "VIDEO"
s.keep_segments = False
s.video_path = FINAL
s.audio_mode = "FILE"
s.audio_file = MP3
s.auto_shutter = False

started = bpy.ops.seg_speed.render("EXEC_DEFAULT")
print("STARTED", started, s.running)


def watch():
    txt = str(s.progress_text)
    print("TICK", txt[:200])
    if txt.startswith("完成") or "失败" in txt or "取消" in txt:
        print("FINAL_TEXT", txt)
        bpy.app.timers.register(lambda: (bpy.ops.wm.quit_blender() or None), first_interval=0.3)
        return None
    return 1.0


bpy.app.timers.register(watch, first_interval=2.0)