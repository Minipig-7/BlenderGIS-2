from math import sqrt, floor
from osgeo import gdal
from tiffdata import TIFFTag, TIFF

from ..proj import SRS
from ..utils import XY, BBOX
from ..errors import OverlapError


class GeoRef:
    """
    Represents georefencing informations of a raster image
    Note : image origin is upper-left whereas map origin is lower-left
    """

    def __init__(self, rSize: XY | None,
                 pxSize: XY | None,
                 origin: XY | None,
                 rot=XY(0, 0),
                 pxCenter=True,
                 subBoxGeo: BBOX | None=None,
                 crs: SRS | None=None):
        """
        rSize : dimensions of the raster in pixels (width, height) tuple
        pxSize : dimension of a pixel in map units (x scale, y scale) tuple. y is always negative
        origin : upper left geo coords of pixel center, (x, y) tuple
        pxCenter : set it to True is the origin anchor point is located at pixel center
            or False if it's lolcated at pixel corner
        rotation : rotation terms (xrot, yrot) <--> (yskew, xskew)
        subBoxGeo : a BBOX object that define the working extent (subdataset) in geographic coordinate space
        """
        self.rSize = rSize
        self.pxSize = pxSize
        self.origin = origin
        self.rotation = rot

        if not pxCenter:
            # adjust topleft coord to pixel center
            self.origin[0] += abs(self.pxSize.x / 2)
            self.origin[1] -= abs(self.pxSize.y / 2)

        self.subBoxGeo = subBoxGeo
        if subBoxGeo is not None:
            # Define a subbox at init is optionnal, we can also do it later
            # Setting the subBox will check if the box overlap the raster extent
            self.setSubBoxGeo(subBoxGeo)

        assert crs is None or isinstance(crs, SRS), "crs must be an instance of SRS class"
        self.crs = crs

    ############################################
    # Alternative constructors
    ############################################

    @classmethod
    def fromGDAL(cls, ds: gdal.Dataset):
        """init from gdal dataset instance"""
        geoTrans = ds.GetGeoTransform()
        if geoTrans is not None:
            xmin, resx, rotx, ymax, roty, resy = geoTrans
            w, h = ds.RasterXSize, ds.RasterYSize
            try:
                crs = SRS.fromGDAL(ds)
            except Exception as e:
                crs = None
            return cls(XY(w, h), XY(resx, resy), XY(xmin, ymax), rot=XY(rotx, roty), pxCenter=False, crs=crs)
        else:
            return None

    @classmethod
    def fromWorldFile(cls, wfPath, rasterSize):
        """init from a worldfile"""
        try:
            with open(wfPath, 'r') as f:
                wf = f.readlines()
            pxSize = XY(float(wf[0].replace(',', '.')), float(wf[3].replace(',', '.')))
            rotation = XY(float(wf[1].replace(',', '.')), float(wf[2].replace(',', '.')))
            origin = XY(float(wf[4].replace(',', '.')), float(wf[5].replace(',', '.')))
            return cls(rasterSize, pxSize, origin, rot=rotation, pxCenter=True, crs=None)
        except Exception as e:
            raise IOError("Unable to read worldfile. {}".format(e))

    @classmethod
    def fromTIFF(cls, tiff: TIFF):
        """read geotags from tiffdata.TIFF instance"""
        w = int(tiff.get(TIFFTag.ImageWidth, first=True))  # type: ignore
        h = int(tiff.get(TIFFTag.ImageLength, first=True))  # type: ignore

        # Search for transformation matrix
            # 34264: ("ModelTransformation", "a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p")
            # 4x4 transform matrix in 3D space
        # TODO ModelTransformationTag нужно устанавливать после чтения файла
        transformMatrix: tuple[int, ...] | None = tiff.get(TIFFTag.ModelTransformationTag)

        # Search for upper left coord and pixel scales

        # 33922: ("ModelTiePoint", "I,J,K,X,Y,Z")
        modelTiePoint: tuple[float, ...] | None = tiff.get(TIFFTag.ModelTiePointTag)
        # 33550 ("ModelPixelScale", "ScaleX, ScaleY, ScaleZ")
        modelPixelScale: tuple[float, ...] | None = tiff.get(TIFFTag.ModelPixelScaleTag)

        if transformMatrix is not None:
            (a, b, c, d,
             e, f, g, h,
             i, j, k, l,
             m, n, o, p) = transformMatrix
            # get only 2d affine parameters
            origin = XY(d, h)
            pxSize = XY(a, f)
            rotation = XY(e, b)
        elif modelTiePoint is not None and modelPixelScale is not None:
            origin = XY(float(modelTiePoint[3]), float(modelTiePoint[4]))
            pxSize = XY(float(modelPixelScale[0]), float(modelPixelScale[1]))
            pxSize[1] = -pxSize.y  # make negative value
            rotation = XY(0, 0)
        else:
            raise IOError("Unable to read geotags: tag 'ModelPixelScaleTag' not found.")

        # Define anchor point for top left coord
        #	http://www.remotesensing.org/geotiff/spec/geotiff2.5.html#2.5.2
        #	http://www.remotesensing.org/geotiff/spec/geotiff6.html#6.3.1.2
        # >> 1 = area (cell anchor = top left corner)
        # >> 2 = point (cell anchor = center)
        # tiffdata returns None for a missing tag instead of raising KeyError
        geotags = tiff.get(TIFFTag.GeoKeyDirectoryTag)
        if geotags is None:
            cellAnchor = 1  # if this key is missing then RasterPixelIsArea is the default
        else:
            # get GTRasterTypeGeoKey value
            cellAnchor = int(geotags[geotags.index(1025) + 3])  # http://www.remotesensing.org/geotiff/spec/geotiff2.4.html
        if cellAnchor == 1:
            # adjust topleft coord to pixel center
            origin[0] += abs(pxSize.x / 2)
            origin[1] -= abs(pxSize.y / 2)

        # TODO extract crs (transcript geokeys to proj4 string)

        return cls(XY(w, h), pxSize, origin, rot=rotation, pxCenter=True, crs=None)

    ############################################
    # Export
    ############################################

    def toGDAL(self) -> tuple[int | float, ...]:
        """return a tuple of georef parameters ordered to define geotransformation of a gdal datasource"""
        xmin, ymax = self.corners[0]
        xres, yres = self.pxSize.x, self.pxSize.y
        xrot, yrot = self.rotation.x, self.rotation.y
        return xmin, xres, xrot, ymax, yrot, yres

    def toWorldFile(self, path: str) -> None:
        """export geo transformation to a worldfile"""
        xmin, ymax = self.origin.x, self.origin.y
        xres, yres = self.pxSize.x, self.pxSize.y
        xrot, yrot = self.rotation.x, self.rotation.y
        wf = (xres, xrot, yrot, yres, xmin, ymax)
        with open(path, 'w') as f:
            f.write('\n'.join(list(map(str, wf))))

    ############################################
    # Dynamic properties
    ############################################

    @property
    def hasCRS(self) -> bool:
        return self.crs is not None

    @property
    def hasRotation(self) -> bool:
        return self.rotation.x != 0 or self.rotation.y != 0

    # TODO
    # def getCorners(self, center=True):
    # def getUL(self, center=True)

    """
    @property
    def ul(self):
        '''upper left corner'''
        return self.geoFromPx(0, yPxRange, True)
    @property
    def ur(self):
        '''upper right corner'''
        return self.geoFromPx(xPxRange, yPxRange, True)
    @property
    def bl(self):
        '''bottom left corner'''
        return self.geoFromPx(0, 0, True)
    @property
    def br(self):
        '''bottom right corner'''
        return self.geoFromPx(xPxRange, 0, True)
    """

    @property
    def cornersCenter(self) -> tuple[XY, XY, XY, XY]:
        """
        (x,y) geo coordinates of image corners (upper left, upper right, bottom right, bottom left)
        (pt1, pt2, pt3, pt4) <--> (upper left, upper right, bottom right, bottom left)
        The coords are located at the pixel center
        """
        xPxRange = self.rSize.x - 1
        yPxRange = self.rSize.y - 1
        # pixel center
        pt1 = self.geoFromPx(0, 0, pxCenter=True)  # upperLeft
        pt2 = self.geoFromPx(xPxRange, 0, pxCenter=True)  # upperRight
        pt3 = self.geoFromPx(xPxRange, yPxRange, pxCenter=True)  # bottomRight
        pt4 = self.geoFromPx(0, yPxRange, pxCenter=True)  # bottomLeft
        return (pt1, pt2, pt3, pt4)

    @property
    def corners(self) -> tuple[XY, XY, XY, XY]:
        """
        (x,y) geo coordinates of image corners (upper left, upper right, bottom right, bottom left)
        (pt1, pt2, pt3, pt4) <--> (upper left, upper right, bottom right, bottom left)
        Represent the true corner location (upper left for pt1, upper right for pt2 ...)
        """
        # get corners at center
        pt1, pt2, pt3, pt4 = self.cornersCenter
        # pixel center offset
        xOffset = abs(self.pxSize.x / 2)
        yOffset = abs(self.pxSize.y / 2)
        pt1 = XY(pt1.x - xOffset, pt1.y + yOffset)
        pt2 = XY(pt2.x + xOffset, pt2.y + yOffset)
        pt3 = XY(pt3.x + xOffset, pt3.y - yOffset)
        pt4 = XY(pt4.x - xOffset, pt4.y - yOffset)
        return (pt1, pt2, pt3, pt4)

    @property
    def bbox(self) -> BBOX:
        """Return a bbox class object"""
        pts = self.corners
        xmin = min([pt.x for pt in pts])
        xmax = max([pt.x for pt in pts])
        ymin = min([pt.y for pt in pts])
        ymax = max([pt.y for pt in pts])
        return BBOX(xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax)

    @property
    def bboxPx(self) -> BBOX:
        return BBOX(xmin=0, ymin=0, xmax=self.rSize.x, ymax=self.rSize.y)

    @property
    def center(self) -> XY:
        """(x,y) geo coordinates of image center"""
        return XY(self.corners[0].x + self.geoSize.x / 2, self.corners[0].y - self.geoSize.y / 2)

    @property
    def geoSize(self) -> XY:
        """raster dimensions (width, height) in map units"""
        x = self.rSize.x * abs(self.pxSize.x)
        y = self.rSize.y * abs(self.pxSize.y)
        return XY(x, y)

    @property
    def orthoGeoSize(self) -> XY:
        """ortho geo size when affine transfo applied a rotation"""
        pxWidth = sqrt(self.pxSize.x ** 2 + self.rotation.x ** 2)
        pxHeight = sqrt(self.pxSize.y ** 2 + self.rotation.y ** 2)
        return XY(self.rSize.x * pxWidth, self.rSize.y * pxHeight)

    @property
    def orthoPxSize(self) -> XY:
        """ortho pixels size when affine transfo applied a rotation"""
        pxWidth = sqrt(self.pxSize.x ** 2 + self.rotation.x ** 2)
        pxHeight = sqrt(self.pxSize.y ** 2 + self.rotation.y ** 2)
        return XY(pxWidth, pxHeight)

    def geoFromPx(self,
                  xPx: int | float,
                  yPx: int | float,
                  reverseY: bool=False,
                  pxCenter: bool=True) -> XY:
        """
        Affine transformation (cf. ESRI WorldFile spec.)
        Return geo coords of the center of an given pixel
        xPx = the column number of the pixel in the image counting from left
        yPx = the row number of the pixel in the image counting from top
        use reverseY option is yPx is counting from bottom instead of top
        Number of pixels is range from 0 (not 1)
        """

        if pxCenter:
            # force pixel center, in this case we need to cast the inputs to floor integer
            xPx, yPx = floor(xPx), floor(yPx)
            ox, oy = self.origin.x, self.origin.y
        else:
            # normal behaviour, coord at pixel's top left corner
            ox = self.origin.x - abs(self.pxSize.x / 2)
            oy = self.origin.y + abs(self.pxSize.y / 2)

        if reverseY:  # the users given y pixel in the image counting from bottom
            yPxRange = self.rSize.y - 1
            yPx = yPxRange - yPx

        x = self.pxSize.x * xPx + self.rotation.y * yPx + ox
        y = self.pxSize.y * yPx + self.rotation.x * xPx + oy

        return XY(x, y)

    def pxFromGeo(self,
                  x: int | float,
                  y: int | float,
                  reverseY: bool=False,
                  round2Floor: bool=False) -> XY:
        """
        Аффинное преобразование (см. спецификацию ESRI WorldFile).
        Возвращает положение пикселя по заданным географическим координатам.
        Используйте опцию reverseY, чтобы получить y пикселей, считая снизу.
        Положение пикселей находится в диапазоне от 0 (не 1).
        """
        # aliases for more readability
        pxSizex, pxSizey = self.pxSize.x, self.pxSize.y
        rotx, roty = self.rotation.x, self.rotation.y
        offx = self.origin.x - abs(self.pxSize.x / 2)
        offy = self.origin.y + abs(self.pxSize.y / 2)
        # transfo
        xPx = (pxSizey * x - rotx * y + rotx * offy - pxSizey * offx) / (pxSizex * pxSizey - rotx * roty)
        yPx = (-roty * x + pxSizex * y + roty * offx - pxSizex * offy) / (pxSizex * pxSizey - rotx * roty)
        if reverseY:  # пользователи хотят, чтобы положение пикселя y отсчитывалось от нижней части
            yPxRange = self.rSize.y - 1
            yPx = yPxRange - yPx
            yPx += 1  # настроить, потому что координаты начинаются с левой верхней координаты пикселя

        if round2Floor:
            xPx, yPx = floor(xPx), floor(yPx)
        return XY(xPx, yPx)

    # Alias
    def pxToGeo(self, xPx: int | float, yPx: int | float, reverseY: bool=False) -> XY:
        return self.geoFromPx(xPx, yPx, reverseY)

    def geoToPx(self, x: int | float, y: int | float, reverseY=False, round2Floor: bool=False) -> XY:
        return self.pxFromGeo(x, y, reverseY, round2Floor)

    ############################################
    # Subbox handlers
    ############################################

    def setSubBoxGeo(self, subBoxGeo: BBOX) -> None:
        """set a subbox in geographic coordinate space
        if needed, coords will be adjusted to avoid being outside raster size"""
        if self.hasRotation:
            raise IOError("A subbox cannot be define if the raster has rotation parameter")
        # Before set the property, ensure that the desired subbox overlap the raster extent
        if not self.bbox.overlap(subBoxGeo):
            raise OverlapError()
        elif self.bbox.isWithin(subBoxGeo):
            # Ignore because subbox is greater than raster extent
            return
        else:
            # convert the subbox in pixel coordinate space
            xminPx, ymaxPx = self.pxFromGeo(subBoxGeo.xmin, subBoxGeo.ymin,
                                            round2Floor=True)  # y pixels counting from top
            xmaxPx, yminPx = self.pxFromGeo(subBoxGeo.xmax, subBoxGeo.ymax, round2Floor=True)  # idem
            subBoxPx = BBOX(xmin=xminPx, ymin=yminPx, xmax=xmaxPx, ymax=ymaxPx)  # xmax and ymax include
            # set the subbox
            self.setSubBoxPx(subBoxPx)

    def setSubBoxPx(self, subBoxPx: BBOX) -> None:
        if not self.bboxPx.overlap(subBoxPx):
            raise OverlapError()
        xminPx, xmaxPx = subBoxPx.xmin, subBoxPx.xmax
        yminPx, ymaxPx = subBoxPx.ymin, subBoxPx.ymax
        # adjust against raster size if needed
        # we count pixel number from 0 but size represents total number of pixel (counting from 1), so we must use size-1
        sizex, sizey = self.rSize.x, self.rSize.y
        if xminPx < 0:
            xminPx = 0
        if xmaxPx >= sizex:
            xmaxPx = sizex - 1
        if yminPx < 0:
            yminPx = 0
        if ymaxPx >= sizey:
            ymaxPx = sizey - 1
        # get the adjusted geo coords at pixels center
        xmin, ymin = self.geoFromPx(xminPx, ymaxPx)
        xmax, ymax = self.geoFromPx(xmaxPx, yminPx)
        # set the subbox
        self.subBoxGeo = BBOX(xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax)

    def applySubBox(self) -> None:
        if self.subBoxGeo is not None:
            self.rSize = self.subBoxPxSize
            self.origin = self.subBoxGeoOrigin
            self.subBoxGeo = None

    def getSubBoxGeoRef(self):
        return GeoRef(self.subBoxPxSize, self.pxSize, self.subBoxGeoOrigin, pxCenter=True, crs=self.crs)

    @property
    def subBoxPx(self) -> BBOX | None:
        """return the subbox as bbox object in pixels coordinates space"""
        if self.subBoxGeo is None:
            return None
        xmin, ymax = self.pxFromGeo(self.subBoxGeo.xmin, self.subBoxGeo.ymin,
                                    round2Floor=True)  # y pixels counting from top
        xmax, ymin = self.pxFromGeo(self.subBoxGeo.xmax, self.subBoxGeo.ymax, round2Floor=True)
        return BBOX(xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax)  # xmax and ymax include

    @property
    def subBoxPxSize(self) -> XY | None:
        """dimension of the subbox in pixels"""
        if self.subBoxGeo is None:
            return None
        bbpx = self.subBoxPx
        w, h = bbpx.xmax - bbpx.xmin, bbpx.ymax - bbpx.ymin
        return XY(w + 1, h + 1)

    @property
    def subBoxGeoSize(self) -> XY | None:
        """dimension of the subbox in map units"""
        if self.subBoxGeo is None:
            return None
        sizex, sizey = self.subBoxPxSize.x, self.subBoxPxSize.y
        return XY(sizex * abs(self.pxSize.x), sizey * abs(self.pxSize.y))

    @property
    def subBoxPxOrigin(self) -> XY | None:
        """pixel coordinate of subbox origin"""
        if self.subBoxGeo is None:
            return None
        return XY(self.subBoxPx.xmin, self.subBoxPx.ymin)

    @property
    def subBoxGeoOrigin(self) -> XY | None:
        """geo coordinate of subbox origin, adjusted at pixel center"""
        if self.subBoxGeo is None:
            return None
        return XY(self.subBoxGeo.xmin, self.subBoxGeo.ymax)

    ####

    def __repr__(self):
        s = (f' spatial ref system {self.crs}\n'
             f' origin geo {self.origin}\n'
             f' pixel size {self.pxSize}\n'
             f' rotation {self.rotation}\n'
             f' bounding box {self.bbox}\n'
             f'.geoSize {self.geoSize}\n')

        if self.subBoxGeo is not None:
            s += (f' subbox origin (geo space) {self.subBoxGeoOrigin}\n'
                  f' subbox origin (px space) {self.subBoxPxOrigin}\n'
                  f' subbox (geo space) {self.subBoxGeo}\n'
                  f' subbox (px space) {self.subBoxPx}\n'
                  f' sub.geoSize {self.subBoxGeoSize}\n'
                  f' sub pxSize {self.subBoxPxSize}\n')

        return s
