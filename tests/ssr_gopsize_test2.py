# -*- coding: utf-8 -*-
"""测不同 CRF 档位在 1080p 3D 场景下的实际码率。"""
import math
import os
_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.abspath(os.path.join(_TEST_HERE, ".."))
import random

import bpy

OUT = os.path.join(_WS, "tmp", "gop_test2")

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# 地面 + 随机方块 + 相机环绕，制造有代表性的运动与细节
mesh = bpy.data.meshes.new("ground")
obj = bpy.data.objects.new("ground", mesh)
scene.collection.objects.link(obj)
import bmesh
bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=12.0)
bm.to_mesh(mesh)
bm.free()

mat = bpy.data.materials.new("gm")
mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.35, 0.33, 0.30, 1.0)
bsdf.inputs["Roughness"].default_value = 0.6
obj.data.materials.append(mat)

random.seed(7)
for i in range(24):
    m = bpy.data.meshes.new("b%d" % i)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=random.uniform(0.3, 1.1))
    bm.to_mesh(m)
    bm.free()
    o = bpy.data.objects.new("b%d" % i, m)
    scene.collection.objects.link(o)
    o.location = (random.uniform(-5, 5), random.uniform(-5, 5), random.uniform(0.4, 2.0))
    o.rotation_euler = (random.uniform(0, 3), random.uniform(0, 3), random.uniform(0, 3))
    mm = bpy.data.materials.new("m%d" % i)
    mm.use_nodes = True
    p = mm.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (
        random.random(), random.random(), random.random(), 1.0)
    p.inputs["Roughness"].default_value = random.uniform(0.2, 0.9)
    o.data.materials.append(mm)

cam_data = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
for f, ang in [(1, 0.0), (120, 6.0)]:
    cam.location = (13 * math.cos(ang), 13 * math.sin(ang), 6.0)
    cam.rotation_euler = (1.15, 0.0, ang + math.pi / 2)
    cam.keyframe_insert("location", frame=f)
    cam.keyframe_insert("rotation_euler", frame=f)

sun_data = bpy.data.lights.new("sun", type="SUN")
sun_data.energy = 4.0
sun = bpy.data.objects.new("sun", sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (0.7, 0.2, 0.9)

for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        scene.render.engine = eng
        print("ENGINE", eng, flush=True)
        break
    except Exception:
        continue

try:
    scene.eevee.taa_render_samples = 16
except Exception:
    pass

r = scene.render
r.resolution_x = 640
r.resolution_y = 360
r.resolution_percentage = 100
r.fps = 24
scene.frame_start = 1
scene.frame_end = 120

os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    try:
        os.remove(os.path.join(OUT, f))
    except Exception:
        pass

res = []
s = bpy.context.scene
for g in (18, 96):
    r.image_settings.media_type = "VIDEO"
    r.image_settings.file_format = "FFMPEG"
    r.ffmpeg.format = "MPEG4"
    r.ffmpeg.codec = "H264"
    r.ffmpeg.constant_rate_factor = "HIGH"
    r.ffmpeg.gopsize = g
    r.ffmpeg.ffmpeg_preset = "GOOD"
    r.ffmpeg.audio_codec = "NONE"
    r.use_file_extension = True
    r.filepath = os.path.join(OUT, "g_%03d" % g)
    bpy.ops.render.render(animation=True)

for f in sorted(os.listdir(OUT)):
    p = os.path.join(OUT, f)
    sz = os.path.getsize(p)
    mbps = sz * 8 / 5.0 / 1000000.0
    print("RESULT %s bytes=%d MB=%.2f Mbps=%.2f" % (f, sz, sz / 1048576.0, mbps), flush=True)

print("DONE", flush=True)

