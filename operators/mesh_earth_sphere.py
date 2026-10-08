import bpy
from bpy.types import Operator
from bpy.props import BoolProperty, EnumProperty, IntProperty

from math import sqrt

import logging

log = logging.getLogger(__name__)

from ..core.maths.sphere import xyz2lonlatDeg, lonlatDeg2xyz
from ..core.proj.reproj import Reproj
from ..geoscene import GeoScene
from ..prefs import PredefCRS

'''
Contract shared by ``earth.sphere`` and ``earth.sphere_to_lonlat`` :
* both operators read and write mesh data only, object transform
  (location/rotation/scale) is never applied, so a round trip is lossless
* both operators interpret/generate coordinates in blender units and never
  reproject to or from the scene CRS on their own, reprojection to a target
  CRS is an explicit extra step of ``earth.sphere_to_lonlat``
'''


def lonlatElev2xyz(obj, radius: int):
	mesh = obj.data
	nbVerts = len(mesh.vertices)
	buf = [0.0] * (nbVerts * 3)
	mesh.vertices.foreach_get("co", buf)
	# Spherical to Cartesian (lon east, lat north)
	out = []
	for i in range(nbVerts):
		out.extend(lonlatDeg2xyz(buf[i * 3], buf[i * 3 + 1], radius + buf[i * 3 + 2]))
	mesh.vertices.foreach_set("co", out)
	mesh.update()


def xyz2lonlatElev(obj, radius: int, keepElev: bool):
	'''Read a mesh lying on a sphere and return its vertices as a flat (x,y) list
	degenerate vertices (sitting on the sphere center) are skipped and left untouched
	return >> (indexes, pts, elevs, nbDegenerate)
	indexes >> position in the mesh vertex list of each converted vertex
	pts >> [(x, y)] in decimal degrees
	elevs >> [z] in blender units, [0.0] if keepElev is False'''
	mesh = obj.data
	nbVerts = len(mesh.vertices)
	buf = [0.0] * (nbVerts * 3)
	mesh.vertices.foreach_get("co", buf)

	indexes = []
	pts = []
	elevs = []
	nbDegenerate = 0
	for i in range(nbVerts):
		x, y, z = buf[i * 3], buf[i * 3 + 1], buf[i * 3 + 2]
		if x == 0.0 and y == 0.0 and z == 0.0:
			nbDegenerate += 1
			continue
		lon, lat, r = xyz2lonlatDeg(x, y, z)
		indexes.append(i)
		pts.append((lon, lat))
		elevs.append(r - radius if keepElev else 0.0)

	return buf, indexes, pts, elevs, nbDegenerate


class OBJECT_OT_earth_sphere(Operator):
	bl_idname = "earth.sphere"
	bl_label = "lonlat to sphere"
	bl_description = "Transform longitude/latitude data to a sphere like earth globe"
	bl_options = {"REGISTER", "UNDO"}

	radius: IntProperty(name="Radius", default=100, description="Sphere radius", min=1)

	def execute(self, context):
		objs = bpy.context.selected_objects

		if not objs:
			self.report({'INFO'}, "No selected object")
			return {'CANCELLED'}

		for obj in objs:
			if obj.type != 'MESH':
				log.warning(f"Object {obj.name} is not a mesh")
				continue

			w, h, thick = obj.dimensions.xyz
			if w > 360:
				log.warning(f"Longitude of object {obj.name} exceed 360°")
				continue
			if h > 180:
				log.warning(f"Latitude of object {obj.name} exceed 180°")
				continue

			lonlatElev2xyz(obj, self.radius)

		return {'FINISHED'}


class OBJECT_OT_earth_sphere_to_lonlat(Operator):
	bl_idname = "earth.sphere_to_lonlat"
	bl_label = "sphere to lonlat"
	bl_description = ("Flatten a mesh lying on a 3D globe back into a 2D coordinate system. "
					  "With WGS84 latlon as target, this is the exact inverse of 'lonlat to sphere', "
					  "any other target CRS adds a reprojection step. Object transform is not applied "
					  "and longitude wraps back at the antimeridian")
	bl_options = {"REGISTER", "UNDO"}

	radius: IntProperty(
		name="Radius",
		description="Sphere radius, must match the radius used by 'lonlat to sphere'",
		default=100,
		min=1
	)

	keepElev: BoolProperty(
		name="Keep elevation",
		description="Restore vertex Z from the distance to the sphere center, otherwise flatten every vertex to Z=0",
		default=True
	)

	useSceneCrs: BoolProperty(
		name="Use scene CRS",
		description="Flatten into the CRS of the scene instead of the selected target CRS",
		default=False,
		update=lambda self, context: self.layout.tag_redraw()
	)

	def listPredefCRS(self, context):
		# WGS84 latlon is the mathematical inverse of 'lonlat to sphere', so it's the relevant default
		items = PredefCRS.getEnumItems()
		for i, item in enumerate(items):
			if item[0] == 'EPSG:4326':
				return [items[i]] + items[:i] + items[i + 1:]
		return items

	crsEnum: EnumProperty(
		name="Target CRS",
		description="Coordinate Reference System to flatten the mesh into",
		items=listPredefCRS
	)

	def draw(self, context):
		self.layout.prop(self, "useSceneCrs")
		row = self.layout.row()
		row.enabled = not self.useSceneCrs
		row.prop(self, "crsEnum")
		self.layout.prop(self, "keepElev")
		self.layout.prop(self, "radius")

	def invoke(self, context, event):
		return context.window_manager.invoke_props_dialog(self, width=250)

	def execute(self, context):
		objs = bpy.context.selected_objects

		if not objs:
			self.report({'INFO'}, "No selected object")
			return {'CANCELLED'}

		crs = self.crsEnum
		if self.useSceneCrs:
			geoscn = GeoScene(context.scene)
			if not geoscn.isGeoref:
				self.report({'ERROR'}, "Scene is not correctly georeferencing, cannot use scene CRS")
				return {'CANCELLED'}
			crs = geoscn.crs

		# instantiate the reprojection once for the whole selection, Reproj init is slow
		rprj = None
		if str(crs) != '4326':
			try:
				rprj = Reproj('4326', crs)
			except Exception as e:
				log.error('Cannot initialize reprojection to %s' % crs, exc_info=True)
				self.report({'ERROR'}, 'Reprojection to %s failed. Check logs for more infos.' % crs)
				return {'CANCELLED'}

		nbDegenerate = 0
		for obj in objs:
			if obj.type != 'MESH':
				log.warning(f"Object {obj.name} is not a mesh")
				continue

			buf, indexes, pts, elevs, nbDeg = xyz2lonlatElev(obj, self.radius, self.keepElev)
			nbDegenerate += nbDeg

			try:
				if rprj is not None:
					pts = rprj.pts(pts)
			except Exception as e:
				log.error('Cannot reproject vertices of %s' % obj.name, exc_info=True)
				self.report({'ERROR'}, 'Reprojection failed. Check logs for more infos.')
				return {'CANCELLED'}

			for (i, (x, y)), z in zip(zip(indexes, pts), elevs):
				buf[i * 3] = x
				buf[i * 3 + 1] = y
				buf[i * 3 + 2] = z
			obj.data.vertices.foreach_set("co", buf)
			obj.data.update()

		if nbDegenerate:
			self.report({'WARNING'}, "%s vertex(es) on the sphere center were left untouched" % nbDegenerate)

		return {'FINISHED'}


EARTH_RADIUS = 6378137  # meters


def getZDelta(d):
	"""delta value for adjusting z across earth curvature
	http://webhelp.infovista.com/Planet/62/Subsystems/Raster/Content/help/analysis/viewshedanalysis.html"""
	return sqrt(EARTH_RADIUS ** 2 + d ** 2) - EARTH_RADIUS


class OBJECT_OT_earth_curvature(Operator):
	bl_idname = "earth.curvature"
	bl_label = "Earth curvature correction"
	bl_description = "Apply earth curvature correction for viewsheed analysis"
	bl_options = {"REGISTER", "UNDO"}

	def execute(self, context):
		scn = bpy.context.scene
		obj = bpy.context.view_layer.objects.active

		if not obj:
			self.report({'INFO'}, "No active object")
			return {'CANCELLED'}

		if obj.type != 'MESH':
			self.report({'INFO'}, "Selection isn't a mesh")
			return {'CANCELLED'}

		mesh = obj.data
		viewpt = scn.cursor.location

		for vertex in mesh.vertices:
			d = (viewpt.xy - vertex.co.xy).length
			vertex.co.z = vertex.co.z - getZDelta(d)

		return {'FINISHED'}


classes = [
	OBJECT_OT_earth_sphere,
	OBJECT_OT_earth_sphere_to_lonlat,
	OBJECT_OT_earth_curvature
]


def register():
	for cls in classes:
		try:
			bpy.utils.register_class(cls)
		except ValueError as e:
			log.warning('{} is already registered, now unregister and retry... '.format(cls))
			bpy.utils.unregister_class(cls)
			bpy.utils.register_class(cls)


def unregister():
	for cls in classes:
		bpy.utils.unregister_class(cls)