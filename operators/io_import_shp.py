import os, sys, time
import bpy
from bpy.props import StringProperty, BoolProperty, EnumProperty, IntProperty
from bpy.types import Operator
import bmesh
import numpy as np

import logging

log = logging.getLogger(__name__)

from ..core.lib.shapefile import Reader as shpReader

from ..geoscene import GeoScene, georefManagerLayout
from ..prefs import PredefCRS
from ..core import BBOX
from ..core.proj import Reproj
from ..core.utils import perf_clock

from .utils import adjust3Dview, getBBOX, DropToGround

PKG, SUBPKG = __package__.split('.', maxsplit=1)

featureType = {
    0: 'Null',
    1: 'Point',
    3: 'PolyLine',
    5: 'Polygon',
    8: 'MultiPoint',
    11: 'PointZ',
    13: 'PolyLineZ',
    15: 'PolygonZ',
    18: 'MultiPointZ',
    21: 'PointM',
    23: 'PolyLineM',
    25: 'PolygonM',
    28: 'MultiPointM',
    31: 'MultiPatch'
}


def signedArea(ring):
    """Compute the signed area of a ring (list of (x, y, z) tuples, no repeated first/last point).
    Anticlockwise rings have a positive area, clockwise rings a negative area."""

    area = 0
    nb = len(ring)
    for k in range(nb):
        x1, y1 = ring[k][0], ring[k][1]
        x2, y2 = ring[(k + 1) % nb][0], ring[(k + 1) % nb][1]
        area += x1 * y2 - x2 * y1
    return area / 2


def pointInRing(pt, ring):
    """Return True if the 2d point is inside the ring (ray casting in the XY plane)."""

    x, y = pt[0], pt[1]
    inside = False
    nb = len(ring)
    for k in range(nb):
        x1, y1 = ring[k][0], ring[k][1]
        x2, y2 = ring[(k + 1) % nb][0], ring[(k + 1) % nb][1]
        if (y1 > y) != (y2 > y):
            xint = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xint:
                inside = not inside
    return inside


# Max number of vertices accumulated in the working bmesh before flushing it to a chunk mesh
CHUNK_VERTS = 100000
# Max number of vertices of the final mesh to run a global remove doubles
# (bounded to avoid a huge memory peak when merging chunks of very large imports)
MERGE_LIMIT = 500000


def flushBmeshToChunk(bm, chunkMeshes, mergeDoubles):
    """Write the current content of the bmesh to a new chunk mesh and empty the bmesh.
    Keeping the bmesh small bounds both memory usage and the cost of remove doubles."""

    if len(bm.verts) == 0:
        return
    if mergeDoubles:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
    mesh = bpy.data.meshes.new(".chunk")
    bm.to_mesh(mesh)
    mesh.validate(verbose=False)
    chunkMeshes.append(mesh)
    bm.clear()


def buildRingFaces(bm, ringList, offset, op):
    """Create one ngon face per ring, holes are filled with separate polygons.
    Hole rings winding is flipped so their face normal points up."""

    for geom, isHole in ringList:
        verts = [bm.verts.new(pt) for pt in geom]
        if isHole:
            verts.reverse()
        face = bm.faces.new(verts)
        # update normal to avoid null vector
        face.normal_update()
        # Extrusion
        if op.fieldExtrudeName and offset > 0:
            # build translate vector
            if op.extrusionAxis == 'NORMAL':
                normal = face.normal
                vect = normal * offset
            elif op.extrusionAxis == 'Z':
                vect = (0, 0, offset)
            faces = bmesh.ops.extrude_discrete_faces(bm, faces=[face])  # return {'faces': [BMFace]}
            verts = faces['faces'][0].verts
            if op.elevSource == 'OBJ':
                # Making flat roof (TODO add an user input parameter to setup this behaviour)
                z = max([v.co.z for v in verts]) + offset  # get max z coord
                for v in verts:
                    v.co.z = z
            else:
                bmesh.ops.translate(bm, verts=verts, vec=vect)


def buildObjFromChunks(chunkMeshes, objName, collection, context, mergeDoubles):
    """Create one object by joining the given chunk meshes.
    Returns the created (object, mesh) tuple."""

    bpy.ops.object.select_all(action='DESELECT')
    objs = []
    for mesh in chunkMeshes:
        obj = bpy.data.objects.new(objName, mesh)
        collection.objects.link(obj)
        obj.select_set(True)
        objs.append(obj)
    context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        # only one join call, this is fine even with a big scene
        bpy.ops.object.join()
    obj = objs[0]
    mesh = obj.data
    mesh.name = objName

    # Remove now unused chunk meshes
    for chunk in chunkMeshes:
        if chunk != mesh and chunk.users == 0:
            bpy.data.meshes.remove(chunk)

    if mergeDoubles and len(mesh.vertices) <= MERGE_LIMIT:
        # Merge doubles accross chunk boundaries
        # bounded to small meshes to avoid a huge memory peak on large imports
        # (within chunks, duplicates have already been merged during flush)
        bm2 = bmesh.new()
        bm2.from_mesh(mesh)
        bmesh.ops.remove_doubles(bm2, verts=bm2.verts, dist=0.0001)
        bm2.to_mesh(mesh)
        bm2.free()
        mesh.validate(verbose=False)

    return obj, mesh


def setGeometryOrigin(obj, mesh):
    """Calc mesh bbox, compute geometry origin and translate coords according to it.
    The object location is set to the initial geometry origin.
    It's a work around to bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')
    which is slow on large meshes."""

    nbVerts = len(mesh.vertices)
    if nbVerts == 0:
        return
    co = np.empty(nbVerts * 3, dtype=np.float32)
    mesh.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    ox = (co[:, 0].min() + co[:, 0].max()) / 2
    oy = (co[:, 1].min() + co[:, 1].max()) / 2
    oz = co[:, 2].min()
    co[:, 0] -= ox
    co[:, 1] -= oy
    co[:, 2] -= oz
    mesh.vertices.foreach_set('co', co.ravel())
    mesh.update()
    obj.location = (ox, oy, oz)

"""
dbf fields type:
	C is ASCII characters
	N is a double precision integer limited to around 18 characters in length
	D is for dates in the YYYYMMDD format, with no spaces or hyphens between the sections
	F is for floating point numbers with the same length limits as N
	L is for logical data which is stored in the shapefile's attribute table as a short integer as a 1 (true) or a 0 (false).
	The values it can receive are 1, 0, y, n, Y, N, T, F or the python builtins True and False
"""


class IMPORTGIS_OT_shapefile_file_dialog(Operator):
    """Select shp file, loads the fields and start importgis.shapefile_props_dialog operator"""

    bl_idname = "importgis.shapefile_file_dialog"
    bl_description = 'Import ESRI shapefile (.shp)'
    bl_label = "Import SHP"
    bl_options = {'INTERNAL'}

    # Import dialog properties
    filepath: StringProperty(
        name="File Path",
        description="Filepath used for importing the file",
        maxlen=1024,
        subtype='FILE_PATH')

    filename_ext = ".shp"

    filter_glob: StringProperty(
        default="*.shp",
        options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        layout = self.layout
        layout.label(text="Options will be available")
        layout.label(text="after selecting a file")

    def execute(self, context):
        if os.path.exists(self.filepath):
            bpy.ops.importgis.shapefile_props_dialog('INVOKE_DEFAULT', filepath=self.filepath)
        else:
            self.report({'ERROR'}, "Invalid filepath")
        return {'FINISHED'}


class IMPORTGIS_OT_shapefile_props_dialog(Operator):
    """Shapefile importer properties dialog"""

    bl_idname = "importgis.shapefile_props_dialog"
    bl_description = 'Import ESRI shapefile (.shp)'
    bl_label = "Import SHP"
    bl_options = {"INTERNAL"}

    filepath: StringProperty()

    # special function to auto redraw an operator popup called through invoke_props_dialog
    def check(self, context):
        return True

    def listFields(self, context):
        fieldsItems = []
        try:
            shp = shpReader(self.filepath)
        except Exception as e:
            log.warning("Unable to read shapefile fields", exc_info=True)
            return fieldsItems
        fields = [field for field in shp.fields if field[0] != 'DeletionFlag']  # ignore default DeletionFlag field
        for i, field in enumerate(fields):
            # put each item in a tuple (key, label, tooltip)
            fieldsItems.append((field[0], field[0], ''))
        return fieldsItems

    # Shapefile CRS definition
    def listPredefCRS(self, context):
        return PredefCRS.getEnumItems()

    def isPolygonLayer(self):
        try:
            shp = shpReader(self.filepath)
            return featureType[shp.shapeType] in ('Polygon', 'PolygonZ')
        except Exception as e:
            return False

    def listObjects(self, context):
        objs = []
        for index, object in enumerate(bpy.context.scene.objects):
            if object.type == 'MESH':
                # put each object in a tuple (key, label, tooltip) and add this to the objects list
                objs.append((object.name, object.name, "Object named " + object.name))
        return objs

    reprojection: BoolProperty(
        name="Specifiy shapefile CRS",
        description="Specifiy shapefile CRS if it's different from scene CRS",
        default=False)

    shpCRS: EnumProperty(
        name="Shapefile CRS",
        description="Choose a Coordinate Reference System",
        items=listPredefCRS)

    # Elevation source
    vertsElevSource: EnumProperty(
        name="Elevation source",
        description="Select the source of vertices z value",
        items=[
            ('NONE', 'None', "Flat geometry"),
            ('GEOM', 'Geometry', "Use z value from shape geometry if exists"),
            ('FIELD', 'Field', "Extract z elevation value from an attribute field"),
            ('OBJ', 'Object', "Get z elevation value from an existing ground mesh")
        ],
        default='GEOM')

    # Elevation object
    objElevLst: EnumProperty(
        name="Elev. object",
        description="Choose the mesh from which extract z elevation",
        items=listObjects)

    # Elevation field
    '''
    useFieldElev: BoolProperty(
            name="Elevation from field",
            description="Extract z elevation value from an attribute field",
            default=False )
    '''
    fieldElevName: EnumProperty(
        name="Elev. field",
        description="Choose field",
        items=listFields)

    # Extrusion field
    useFieldExtrude: BoolProperty(
        name="Extrusion from field",
        description="Extract z extrusion value from an attribute field",
        default=False)

    fieldExtrudeName: EnumProperty(
        name="Field",
        description="Choose field",
        items=listFields)

    # Extrusion axis
    extrusionAxis: EnumProperty(
        name="Extrude along",
        description="Select extrusion axis",
        items=[('Z', 'z axis', "Extrude along Z axis"),
               ('NORMAL', 'Normal', "Extrude along normal")])

    # Inner rings handling
    ringsMode: EnumProperty(
        name="Inner rings",
        description="How to handle inner rings (holes) of polygons",
        items=[
            ('FILL', 'Fill rings', "Fill inner rings with separate polygons (eg. lakes of a continent polygon are imported as separate polygons in the same mesh)"),
            ('SEPARATE', 'Separate holes', "Import inner rings (holes) into a separate object ; the polygon keeps only its outer rings")
        ],
        default='FILL')

    # Create separate objects
    separateObjects: BoolProperty(
        name="Separate objects",
        description="Warning : can be very slow with lot of features",
        default=False)

    # Name objects from field
    useFieldName: BoolProperty(
        name="Object name from field",
        description="Extract name for created objects from an attribute field",
        default=False)
    fieldObjName: EnumProperty(
        name="Field",
        description="Choose field",
        items=listFields)

    def draw(self, context):
        # Function used by blender to draw the panel.
        scn = context.scene
        layout = self.layout

        #
        layout.prop(self, 'vertsElevSource')
        #
        # layout.prop(self, 'useFieldElev')
        if self.vertsElevSource == 'FIELD':
            layout.prop(self, 'fieldElevName')
        elif self.vertsElevSource == 'OBJ':
            layout.prop(self, 'objElevLst')
        #
        layout.prop(self, 'useFieldExtrude')
        if self.useFieldExtrude:
            layout.prop(self, 'fieldExtrudeName')
            layout.prop(self, 'extrusionAxis')
        #
        if self.isPolygonLayer():
            layout.prop(self, 'ringsMode')
        #
        layout.prop(self, 'separateObjects')
        if self.separateObjects:
            layout.prop(self, 'useFieldName')
        else:
            self.useFieldName = False
        if self.separateObjects and self.useFieldName:
            layout.prop(self, 'fieldObjName')
        #
        geoscn = GeoScene()
        # geoscnPrefs = context.preferences.addons['geoscene'].preferences
        if geoscn.isPartiallyGeoref:
            layout.prop(self, 'reprojection')
            if self.reprojection:
                self.shpCRSInputLayout(context)
            #
            georefManagerLayout(self, context)
        else:
            self.shpCRSInputLayout(context)

    def shpCRSInputLayout(self, context):
        layout = self.layout
        row = layout.row(align=True)
        # row.prop(self, "shpCRS", text='CRS')
        split = row.split(factor=0.35, align=True)
        split.label(text='CRS:')
        split.prop(self, "shpCRS", text='')
        row.operator("bgis.add_predef_crs", text='', icon='ADD')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):

        # elevField = self.fieldElevName if self.useFieldElev else ""
        elevField = self.fieldElevName if self.vertsElevSource == 'FIELD' else ""
        extrudField = self.fieldExtrudeName if self.useFieldExtrude else ""
        nameField = self.fieldObjName if self.useFieldName else ""
        if self.vertsElevSource == 'OBJ':
            if not self.objElevLst:
                self.report({'ERROR'}, "No elevation object")
                return {'CANCELLED'}
            else:
                objElevName = self.objElevLst
        else:
            objElevName = ''  # will not be used

        geoscn = GeoScene()
        if geoscn.isBroken:
            self.report({'ERROR'}, "Scene georef is broken, please fix it beforehand")
            return {'CANCELLED'}

        if geoscn.isGeoref:
            if self.reprojection:
                shpCRS = self.shpCRS
            else:
                shpCRS = geoscn.crs
        else:
            shpCRS = self.shpCRS

        try:
            bpy.ops.importgis.shapefile('INVOKE_DEFAULT', filepath=self.filepath, shpCRS=shpCRS,
                                        elevSource=self.vertsElevSource,
                                        fieldElevName=elevField, objElevName=objElevName, fieldExtrudeName=extrudField,
                                        fieldObjName=nameField,
                                        extrusionAxis=self.extrusionAxis, separateObjects=self.separateObjects,
                                        ringsMode=self.ringsMode)
        except Exception as e:
            log.error('Shapefile import fails', exc_info=True)
            self.report({'ERROR'}, 'Shapefile import fails, check logs.')
            return {'CANCELLED'}

        return {'FINISHED'}


class IMPORTGIS_OT_shapefile(Operator):
    """Import from ESRI shapefile file format (.shp)"""

    bl_idname = "importgis.shapefile"  # important since its how bpy.ops.import.shapefile is constructed (allows calling operator from python console or another script)
    # bl_idname rules: must contain one '.' (dot) charactere, no capital letters, no reserved words (like 'import')
    bl_description = 'Import ESRI shapefile (.shp)'
    bl_label = "Import SHP"
    bl_options = {"UNDO"}

    filepath: StringProperty()

    shpCRS: StringProperty(name="Shapefile CRS", description="Coordinate Reference System")

    elevSource: StringProperty(name="Elevation source", description="Elevation source",
                               default='GEOM')  # [NONE, GEOM, OBJ, FIELD]
    objElevName: StringProperty(name="Elevation object name", description="")

    fieldElevName: StringProperty(name="Elevation field", description="Field name")
    fieldExtrudeName: StringProperty(name="Extrusion field", description="Field name")
    fieldObjName: StringProperty(name="Objects names field", description="Field name")

    # Extrusion axis
    extrusionAxis: EnumProperty(
        name="Extrude along",
        description="Select extrusion axis",
        items=[('Z', 'z axis', "Extrude along Z axis"),
               ('NORMAL', 'Normal', "Extrude along normal")]
    )
    # Create separate objects
    separateObjects: BoolProperty(
        name="Separate objects",
        description="Import to separate objects instead one large object",
        default=False
    )

    # Inner rings handling
    ringsMode: EnumProperty(
        name="Inner rings",
        description="How to handle inner rings (holes) of polygons",
        items=[
            ('FILL', 'Fill rings', "Fill inner rings with separate polygons (eg. lakes of a continent polygon are imported as separate polygons in the same mesh)"),
            ('SEPARATE', 'Separate holes', "Import inner rings (holes) into a separate object ; the polygon keeps only its outer rings")
        ],
        default='FILL')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def __del__(self):
        bpy.context.window.cursor_set('DEFAULT')

    def execute(self, context):

        prefs = bpy.context.preferences.addons[PKG].preferences

        # Set cursor representation to 'loading' icon
        w = context.window
        w.cursor_set('WAIT')
        t0 = perf_clock()

        bpy.ops.object.select_all(action='DESELECT')

        # Path
        shpName = os.path.basename(self.filepath)[:-4]

        # Get shp reader
        log.info("Read shapefile...")
        try:
            shp = shpReader(self.filepath)
        except Exception as e:
            log.error("Unable to read shapefile", exc_info=True)
            self.report({'ERROR'}, "Unable to read shapefile, check logs")
            return {'CANCELLED'}

        # Check shape type
        shpType = featureType[shp.shapeType]
        log.info('Feature type : ' + shpType)
        if shpType not in ['Point', 'PolyLine', 'Polygon', 'PointZ', 'PolyLineZ', 'PolygonZ']:
            self.report({'ERROR'},
                        "Cannot process multipoint, multipointZ, pointM, polylineM, polygonM and multipatch feature type")
            return {'CANCELLED'}

        if self.elevSource != 'FIELD':
            self.fieldElevName = ''

        if self.elevSource == 'OBJ':
            scn = bpy.context.scene
            elevObj = scn.objects[self.objElevName]
            rayCaster = DropToGround(scn, elevObj)

        # Get fields
        fields = [field for field in shp.fields if field[0] != 'DeletionFlag']  # ignore default DeletionFlag field
        fieldsNames = [field[0] for field in fields]
        log.debug("DBF fields : " + str(fieldsNames))

        if self.separateObjects or self.fieldElevName or self.fieldObjName or self.fieldExtrudeName:
            self.useDbf = True
        else:
            self.useDbf = False

        if self.fieldObjName and self.separateObjects:
            try:
                nameFieldIdx = fieldsNames.index(self.fieldObjName)
            except Exception as e:
                log.error('Unable to find name field', exc_info=True)
                self.report({'ERROR'}, "Unable to find name field")
                return {'CANCELLED'}

        if self.fieldElevName:
            try:
                zFieldIdx = fieldsNames.index(self.fieldElevName)
            except Exception as e:
                log.error('Unable to find elevation field', exc_info=True)
                self.report({'ERROR'}, "Unable to find elevation field")
                return {'CANCELLED'}

            if fields[zFieldIdx][1] not in ['N', 'F', 'L']:
                self.report({'ERROR'}, "Elevation field do not contains numeric values")
                return {'CANCELLED'}

        if self.fieldExtrudeName:
            try:
                extrudeFieldIdx = fieldsNames.index(self.fieldExtrudeName)
            except ValueError:
                log.error('Unable to find extrusion field', exc_info=True)
                self.report({'ERROR'}, "Unable to find extrusion field")
                return {'CANCELLED'}

            if fields[extrudeFieldIdx][1] not in ['N', 'F', 'L']:
                self.report({'ERROR'}, "Extrusion field do not contains numeric values")
                return {'CANCELLED'}

        # Get shp and scene georef infos
        shpCRS = self.shpCRS
        geoscn = GeoScene()
        if geoscn.isBroken:
            self.report({'ERROR'}, "Scene georef is broken, please fix it beforehand")
            return {'CANCELLED'}

        scale = geoscn.scale  # TODO

        if not geoscn.hasCRS:  # if not geoscn.isGeoref:
            try:
                geoscn.crs = shpCRS
            except Exception as e:
                log.error("Cannot set scene crs", exc_info=True)
                self.report({'ERROR'}, "Cannot set scene crs, check logs for more infos")
                return {'CANCELLED'}

        # Init reprojector class
        if geoscn.crs != shpCRS:
            log.info("Data will be reprojected from {} to {}".format(shpCRS, geoscn.crs))
            try:
                rprj = Reproj(shpCRS, geoscn.crs)
            except Exception as e:
                log.error('Reprojection fails', exc_info=True)
                self.report({'ERROR'}, "Unable to reproject data, check logs for more infos.")
                return {'CANCELLED'}
            if rprj.iproj == 'EPSGIO':
                if shp.numRecords > 100:
                    self.report({'ERROR'},
                                "Reprojection through online epsg.io engine is limited to 100 features. \nPlease install GDAL or pyproj module.")
                    return {'CANCELLED'}

        # Get bbox
        bbox = BBOX.fromXYZ(shp.bbox)
        if geoscn.crs != shpCRS:
            bbox = rprj.bbox(bbox)

        # Get or set georef dx, dy
        if not geoscn.isGeoref:
            dx, dy = bbox.center.xy
            geoscn.setOriginPrj(dx, dy)
        else:
            dx, dy = geoscn.getOriginPrj()

        # Get reader iterator (using iterator avoids loading all data in memory)
        # warn, shp with zero field will return an empty shapeRecords() iterator
        # to prevent this issue, iter only on shapes if there is no field required
        if self.useDbf:
            # Note: using shapeRecord solve the issue where number of shapes does not match number of table records
            # because it iter only on features with geom and record
            shpIter = shp.iterShapeRecords()
        else:
            shpIter = shp.iterShapes()
        nbFeats = shp.numRecords

        # Create an empty BMesh
        bm = bmesh.new()
        # Extrusion is exponentially slow with large bmesh
        # and a large bmesh is memory hungry
        # so without the separate objects option, the bmesh is regularly flushed
        # to chunk meshes (see main loop) and chunks are merged at the end
        if not self.separateObjects:
            chunkMeshes = []
        # Bmesh and chunks accumulating inner rings geometry
        # when ringsMode is 'SEPARATE' (holes are imported in a dedicated object)
        holeBm = None
        holeChunkMeshes = []

        progress = -1

        if self.separateObjects:
            layer = bpy.data.collections.new(shpName)
            context.scene.collection.children.link(layer)

        # Main iteration over features
        for i, feat in enumerate(shpIter):

            if self.useDbf:
                shape = feat.shape
                record = feat.record
            else:
                shape = feat

            # Progress infos
            pourcent = round(((i + 1) * 100) / nbFeats)
            if pourcent in list(range(0, 110, 10)) and pourcent != progress:
                progress = pourcent
                if pourcent == 100:
                    print(str(pourcent) + '%')
                else:
                    print(str(pourcent), end="%, ")
                sys.stdout.flush()  # we need to flush or it won't print anything until after the loop has finished

            # Deal with multipart features
            # If the shape record has multiple parts, the 'parts' attribute will contains the index of
            # the first point of each part. If there is only one part then a list containing 0 is returned
            if shpType == 'PointZ' or shpType == 'Point':  # point layer has no attribute 'parts'
                partsIdx = [0]
            else:
                try:  # prevent "_shape object has no attribute parts" error
                    partsIdx = shape.parts
                except Exception as e:
                    log.warning('Cannot access "parts" attribute for feature {} : {}'.format(i, e))
                    partsIdx = [0]
            nbParts = len(partsIdx)

            # Get list of shape's points
            pts = shape.points
            nbPts = len(pts)

            # Skip null geom
            if nbPts == 0:
                continue  # go to next iteration of the loop

            # Reproj geom
            if geoscn.crs != shpCRS:
                pts = rprj.pts(pts)

            # Get extrusion offset
            offset = 0
            if self.fieldExtrudeName:
                try:
                    offset = float(record[extrudeFieldIdx])
                except Exception as e:
                    log.warning('Cannot extract extrusion value for feature {} : {}'.format(i, e))
                    offset = 0  # null values will be set to zero

            # For polygon features, rings of all parts are collected in this list
            # faces are built after the parts loop (see buildPolygonFaces)
            rings = []

            # Iter over parts
            for j in range(nbParts):

                # EXTRACT 3D GEOM

                geom = []  # will contains a list of 3d points

                # Find first and last part index
                idx1 = partsIdx[j]
                if j + 1 == nbParts:
                    idx2 = nbPts
                else:
                    idx2 = partsIdx[j + 1]

                # Build 3d geom
                for k, pt in enumerate(pts[idx1:idx2]):

                    if self.elevSource == 'OBJ':
                        rcHit = rayCaster.rayCast(x=pt[0] - dx, y=pt[1] - dy)
                        z = rcHit.loc.z  # will be automatically set to zero if not rcHit.hit

                    elif self.elevSource == 'FIELD':
                        try:
                            z = float(record[zFieldIdx])
                        except Exception as e:
                            log.warning('Cannot extract elevation value for feature {} : {}'.format(i, e))
                            z = 0  # null values will be set to zero

                    elif shpType[-1] == 'Z' and self.elevSource == 'GEOM':
                        z = shape.z[idx1:idx2][k]

                    else:
                        z = 0

                    geom.append((pt[0], pt[1], z))

                # Shift coords
                geom = [(pt[0] - dx, pt[1] - dy, pt[2]) for pt in geom]

                # BUILD BMESH

                # POINTS
                if shpType == 'PointZ' or shpType == 'Point':
                    vert = [bm.verts.new(pt) for pt in geom]
                    # Extrusion
                    if self.fieldExtrudeName and offset > 0:
                        vect = (0, 0, offset)  # along Z
                        result = bmesh.ops.extrude_vert_indiv(bm, verts=vert)
                        verts = result['verts']
                        bmesh.ops.translate(bm, verts=verts, vec=vect)

                # LINES
                if shpType == 'PolyLine' or shpType == 'PolyLineZ':
                    verts = [bm.verts.new(pt) for pt in geom]
                    edges = []
                    for i in range(len(geom) - 1):
                        edge = bm.edges.new([verts[i], verts[i + 1]])
                        edges.append(edge)
                    # Extrusion
                    if self.fieldExtrudeName and offset > 0:
                        vect = (0, 0, offset)  # along Z
                        result = bmesh.ops.extrude_edge_only(bm, edges=edges)
                        verts = [elem for elem in result['geom'] if isinstance(elem, bmesh.types.BMVert)]
                        bmesh.ops.translate(bm, verts=verts, vec=vect)

                # POLYGONS
                if shpType == 'Polygon' or shpType == 'PolygonZ':
                    # According to the shapefile spec, polygons points are clockwise and polygon holes are counterclockwise
                    geom.reverse()
                    geom.pop()  # exlude last point because it's the same as first pt
                    if len(geom) >= 3:  # needs 3 points to get a valid face
                        rings.append(geom)

            # BUILD POLYGON FACES
            if (shpType == 'Polygon' or shpType == 'PolygonZ') and rings:

                # After the reverse, outer rings are anticlockwise (positive signed area) and holes clockwise
                ringList = [(geom, signedArea(geom) < 0) for geom in rings]

                if self.ringsMode == 'SEPARATE':
                    # only top level rings stay in the main geometry
                    # rings nested inside another ring (holes and islands) are built
                    # into a dedicated bmesh (imported as a separate object at the end)
                    outerRings = []
                    holeRings = []
                    for geom, isHole in ringList:
                        depth = 0
                        for otherGeom, otherIsHole in ringList:
                            if otherGeom is not geom and pointInRing(geom[0], otherGeom):
                                depth += 1
                        if depth == 0:
                            outerRings.append((geom, isHole))
                        else:
                            holeRings.append((geom, isHole))
                else:
                    outerRings = ringList
                    holeRings = []

                buildRingFaces(bm, outerRings, offset, self)

                if holeRings:
                    if holeBm is None:
                        holeBm = bmesh.new()
                    buildRingFaces(holeBm, holeRings, offset, self)

            if self.separateObjects:

                if self.fieldObjName:
                    try:
                        name = record[nameFieldIdx]
                    except Exception as e:
                        log.warning('Cannot extract name value for feature {} : {}'.format(i, e))
                        name = ''
                    # null values will return a bytes object containing a blank string of length equal to fields length definition
                    if isinstance(name, bytes):
                        name = ''
                    else:
                        name = str(name)
                else:
                    name = shpName

                # Calc bmesh bbox
                _bbox = getBBOX.fromBmesh(bm)

                # Calc bmesh geometry origin and translate coords according to it
                # then object location will be set to initial bmesh origin
                # its a work around to bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')
                ox, oy, oz = _bbox.center.xyz
                oz = _bbox.zmin
                bmesh.ops.translate(bm, verts=bm.verts, vec=(-ox, -oy, -oz))

                # Create new mesh from bmesh
                mesh = bpy.data.meshes.new(name)
                bm.to_mesh(mesh)
                bm.clear()

                # Validate new mesh
                mesh.validate(verbose=False)

                # Place obj
                obj = bpy.data.objects.new(name, mesh)
                layer.objects.link(obj)
                context.view_layer.objects.active = obj
                obj.select_set(True)
                obj.location = (ox, oy, oz)

                # bpy operators can be very cumbersome when scene contains lot of objects
                # because it cause implicit scene updates calls
                # so we must avoid using operators when created many objects with the 'separate objects' option)
                ##bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')

                # write attributes data
                for i, field in enumerate(shp.fields):
                    fieldName, fieldType, fieldLength, fieldDecLength = field
                    if fieldName != 'DeletionFlag':
                        if fieldType in ('N', 'F'):
                            v = record[i - 1]
                            if v is not None:
                                # cast to float to avoid overflow error when affecting custom property
                                obj[fieldName] = float(record[i - 1])
                        else:
                            obj[fieldName] = record[i - 1]

            elif len(bm.verts) >= CHUNK_VERTS:
                # flush the bmesh to a chunk mesh to keep it small
                flushBmeshToChunk(bm, chunkMeshes, prefs.mergeDoubles)

            if holeBm is not None and len(holeBm.verts) >= CHUNK_VERTS:
                flushBmeshToChunk(holeBm, holeChunkMeshes, prefs.mergeDoubles)

        # Write back the whole mesh
        if not self.separateObjects:

            # Flush remaining geometry
            flushBmeshToChunk(bm, chunkMeshes, prefs.mergeDoubles)

            if chunkMeshes:
                # Merge chunk meshes into a single object
                obj, mesh = buildObjFromChunks(chunkMeshes, shpName, context.scene.collection, context, prefs.mergeDoubles)
                setGeometryOrigin(obj, mesh)
            else:
                # No geometry imported, create an empty object
                mesh = bpy.data.meshes.new(shpName)
                obj = bpy.data.objects.new(shpName, mesh)
                context.scene.collection.objects.link(obj)

        # Import inner rings into a separate object (ringsMode == 'SEPARATE')
        if holeBm is not None:
            flushBmeshToChunk(holeBm, holeChunkMeshes, prefs.mergeDoubles)
            if holeChunkMeshes:
                coll = layer if self.separateObjects else context.scene.collection
                holesObj, holesMesh = buildObjFromChunks(holeChunkMeshes, shpName + "_holes", coll, context, prefs.mergeDoubles)
                setGeometryOrigin(holesObj, holesMesh)
            holeBm.free()

        context.view_layer.objects.active = obj
        obj.select_set(True)

        # free the bmesh
        bm.free()

        t = perf_clock() - t0
        log.info('Build in %f seconds' % t)

        # Adjust grid size
        if prefs.adjust3Dview:
            bbox.shift(-dx, -dy)  # convert shapefile bbox in 3d view space
            adjust3Dview(context, bbox)

        return {'FINISHED'}


classes = [
    IMPORTGIS_OT_shapefile_file_dialog,
    IMPORTGIS_OT_shapefile_props_dialog,
    IMPORTGIS_OT_shapefile
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
