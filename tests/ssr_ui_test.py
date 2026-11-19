"""GUI 实测：点击渲染后，面板进度会不会在渲染过程中动起来。

故意用较慢的设置（EEVEE 1080p + 高采样），保证渲染期间有足够时间截图。
"""
import bpy
import os
_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.abspath(os.path.join(_TEST_HERE, ".."))

WS = _WS
OUT = os.path.join(WS, "ssr_ui_out")
os.makedirs(OUT, exist_ok=True)
FINAL = os.path.join(OUT, "ui_final.mp4")

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = 960
sc.render.resolution_y = 540
sc.render.resolution_percentage = 100
sc.render.fps = 24
sc.frame_start = 1
sc.frame_end = 120

try:
    sc.eevee.taa_render_samples = 32
except Exception:
    pass

# 多摆点东西，让每帧真的慢下来
bpy.ops.mesh.primitive_plane_add(size=40)
for i in range(40):
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=0.6,
        location=((i % 8) * 2.2 - 8, (i // 8) * 2.2 - 4, 1.0),
    )
    ob = bpy.context.object
    mat = bpy.data.materials.new("m%d" % i)
    mat.diffuse_color = ((i * 0.13) % 1.0, (i * 0.31) % 1.0, (i * 0.57) % 1.0, 1.0)
    ob.data.materials.append(mat)

if sc.camera is None:
    cd = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cd)
    sc.collection.objects.link(cam)
    cam.location = (12, -12, 8)
    cam.rotation_euler = (1.05, 0, 0.785)
    sc.camera = cam

light_data = bpy.data.lights.new("Sun", type="SUN")
light = bpy.data.objects.new("Sun", light_data)
light.rotation_euler = (0.6, 0.2, 0.4)
sc.collection.objects.link(light)

if not hasattr(bpy.types.Scene, "ssr"):
    import importlib
    importlib.import_module("bl_ext.user_default.seg_speed_render").register()

s = sc.ssr
s.segments.clear()
for a, b, stp in ((1, 60, 1), (61, 120, 1)):
    seg = s.segments.add()
    seg.start, seg.end, seg.step = a, b, stp
s.out_dir = OUT
s.output_mode = "VIDEO"
s.keep_segments = False
s.video_path = FINAL
s.auto_shutter = False
s.audio_mode = "NONE"
s.quality = "HIGH"

# 把面板切到 3D 视图的侧栏，方便截图看进度
try:
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.show_region_ui = True
except Exception:
    pass

def _probe(text=None, dg=None):
    try:
        print("PROBE frame=%d | %s" % (bpy.context.scene.frame_current, s.progress_text))
    except Exception as exc:
        print("PROBE_ERR", exc)


bpy.app.handlers.render_stats.append(_probe)
print("READY", "frames", s.segments[0].start, s.segments[-1].end)
bpy.ops.seg_speed.render("EXEC_DEFAULT")
print("STARTED", s.running)



