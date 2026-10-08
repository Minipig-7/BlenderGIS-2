import logging
import os
from typing import Optional
from tiffdata import TIFF, TIFFTag

from ..utils.bbox import BBOX

log = logging.getLogger(__name__)


from ..georaster.georef import GeoRef
from ..georaster.npimg import NpImage
from ..georaster.img_utils import getImgFormat, getImgDim

from ..utils.xy import XY
from ..checkdeps import HAS_GDAL

if HAS_GDAL:
    from osgeo import gdal


class GeoRaster:
    """A class to represent a georaster file"""

    def __init__(self,
                 path: str,
                 subBoxGeo: BBOX | None=None,
                 useGDAL: bool=False):
        """
        subBoxGeo: a BBOX object in CRS coordinate space
        useGDAL: use GDAL (if available) for extract raster informations
        """
        self.path: str = path
        self.wfPath: Optional[str] = self._getWfPath()

        self.format: str = ''  # image file format (jpeg, tiff, png ...)
        self.size: XY = XY(0, 0)  # raster dimension (width, height) in pixel
        self.depth: int = int()  # 8, 16, 32
        self.dtype: str = 'uint'  # int, uint, float
        self.nbBands: int = int()  # number of bands
        self.noData: Optional[int] = None

        self.georef: Optional[GeoRef] = None

        if not useGDAL or not HAS_GDAL:

            self.format = getImgFormat(path)
            if self.format not in ['TIFF', 'BMP', 'PNG', 'JPEG', 'JPEG2000']:
                raise IOError(f"Unsupported format {self.format}")

            if self.isTiff:
                self.__fromTIFF()
                if not self.isGeoref and self.hasWorldFile:
                    self.georef = GeoRef.fromWorldFile(self.wfPath, self.size)
                else:
                    pass
            else:
                # Try to read file header
                w, h = getImgDim(self.path)
                if w is None or h is None:
                    raise IOError("Unable to read raster size")
                else:
                    self.size = XY(w, h)
                # georef
                if self.hasWorldFile:
                    self.georef = GeoRef.fromWorldFile(self.wfPath, self.size)
        # TODO add function to extract dtype, nBands & depth from jpg, png, bmp or jpeg2000

        else:
            self._fromGDAL()

        if not self.isGeoref:
            raise IOError("Unable to read georef infos from worldfile or geotiff tags")

        if subBoxGeo is not None:
            self.georef.setSubBoxGeo(subBoxGeo)

    # GeoGef delegation by composition instead of inheritance
    # this special method is called whenever the requested attribute or method is not found in the object
    '''def __getattr__(self, attr):
        return getattr(self.georef, attr)'''

    @property
    def center(self) -> XY:
        return self.georef.center

    @property
    def rotation(self) -> XY:
        return self.georef.rotation

    @property
    def pxSize(self) -> Optional[XY]:
        return self.georef.pxSize

    @property
    def geoSize(self) -> XY:
        return self.georef.geoSize

    @property
    def bbox(self) -> BBOX:
        return self.georef.bbox

    @property
    def corners(self) -> tuple[XY, XY, XY, XY]:
        return self.georef.corners

    @property
    def cornersCenter(self) -> tuple[XY, XY, XY, XY]:
        return self.georef.cornersCenter

    @property
    def origin(self) -> Optional[XY]:
        return self.georef.origin

    @property
    def subBoxPx(self) -> Optional[BBOX]:
        return self.georef.subBoxPx

    @property
    def subBoxGeo(self) -> Optional[BBOX]:
        return self.georef.subBoxGeo

    def getSubBoxGeoRef(self) -> GeoRef:
        return self.georef.getSubBoxGeoRef()

    def pxFromGeo(self,
                  x: int | float,
                  y: int | float,
                  reverseY: bool=False,
                  round2Floor: bool=False) -> XY:
        return self.georef.pxFromGeo(x, y, reverseY, round2Floor)

    ############################################
    # Initialization Helpers
    ############################################

    def _getWfPath(self) -> Optional[str]:
        """Try to find a worlfile path for this raster"""
        ext = self.path[-3:].lower()
        extTest = []
        extTest.append(ext[0] + ext[2] + 'w')  # tfx, jgw, pgw ...
        extTest.append(extTest[0] + 'x')  # tfwx
        extTest.append(ext + 'w')  # tifw
        extTest.append('wld')  # *.wld
        extTest.extend([ext.upper() for ext in extTest])
        for wfExt in extTest:
            pathTest = self.path[0 : len(self.path) - 3] + wfExt
            if os.path.isfile(pathTest):
                return pathTest
        return None

    def __fromTIFF(self) -> None:
        """Use tiffdata library to extract raster info from geotiff tags"""
        if not self.fileExists:
            return
        tiff = TIFF(self.path)

        x = int(tiff.get(TIFFTag.ImageWidth, first=True))  # type: ignore[type-hint]
        y = int(tiff.get(TIFFTag.ImageLength, first=True))  # type: ignore[type-hint]
        self.size = XY(x, y)

        nbBands = int(tiff.get(TIFFTag.SamplesPerPixel, first=True))  # type: ignore[type-hint]
        self.nbBands = nbBands

        depth = tiff.get(TIFFTag.BitsPerSample, first=True)
        if self.nbBands > 1:
            self.depth = depth[0]
        else:
            self.depth = depth

        sampleFormatMap = {1: 'uint', 2: 'int', 3: 'float', None: 'uint', 6: 'complex'}
        try:
            self.dtype = sampleFormatMap[tiff.get(TIFFTag.SampleFormat, first=True)]
        except KeyError:
            pass

        nodata = tiff.get(TIFFTag.GDALNoData, first=True)
        if nodata is not None:
            self.noData = float(nodata)

        # Get Georef
        try:
            self.georef = GeoRef.fromTIFF(tiff)
        except Exception as e:
            log.warning(f'Cannot extract georefencing informations from tif tags:\n\n{e}')

    def _fromGDAL(self) -> None:
        """Use GDAL to extract raster infos and init"""
        if self.path is None or not self.fileExists:
            raise IOError("Cannot find file on disk")
        ds: gdal.Dataset = gdal.Open(self.path, gdal.GA_ReadOnly)
        self.size = XY(ds.RasterXSize, ds.RasterYSize)
        self.format = ds.GetDriver().ShortName
        if self.format in ['JP2OpenJPEG', 'JP2ECW', 'JP2KAK', 'JP2MrSID']:
            self.format = 'JPEG2000'
        self.nbBands = ds.RasterCount
        b1: gdal.Band = ds.GetRasterBand(1)  # first band (band index does not count from 0)
        self.noData = b1.GetNoDataValue()
        ddtype: str = gdal.GetDataTypeName(b1.DataType)  # Byte, UInt16, Int16, UInt32, Int32, Float32, Float64
        if ddtype == "Byte":
            self.dtype = 'uint'
            self.depth = 8
        else:
            self.dtype = ddtype[:-2].lower()
            self.depth = int(ddtype[-2:])
        # Get Georef
        self.georef = GeoRef.fromGDAL(ds)
        # Close (gdal has no garbage collector)
        ds, b1 = None, None

    #######################################
    # Dynamic properties
    #######################################
    @property
    def fileExists(self) -> bool:
        """Test if the file exists on disk"""
        return os.path.isfile(self.path)

    @property
    def baseName(self) -> str | None:
        if self.path is not None:
            folder, fileName = os.path.split(self.path)
            baseName, ext = os.path.splitext(fileName)
            return baseName
        return None

    @property
    def hasWorldFile(self) -> bool:
        return self.wfPath is not None

    @property
    def isTiff(self) -> bool:
        return self.format in ['TIFF', 'GTiff']

    @property
    def isGeoref(self) -> bool:
        """Flag if georef parameters have been extracted"""
        try:
            return None not in [self.georef, self.origin, self.pxSize, self.rotation]
        except AttributeError:
            return False

    @property
    def isOneBand(self) -> bool:
        return self.nbBands == 1

    @property
    def isFloat(self) -> bool:
        return self.dtype in ['Float', 'float']

    @property
    def ddtype(self) -> str | None:
        """
        Get data type and depth in a concatenate string like
        'int8', 'int16', 'uint16', 'int32', 'uint32', 'float32' ...
        Can be used to define numpy or gdal data type
        """
        if not self.dtype or not self.depth:
            return None
        else:
            return self.dtype + str(self.depth)

    def __repr__(self):
        return '\n'.join([
            '* Paths infos :',
            f' path {self.path}',
            f' worldfile {self.wfPath}',
            f' format {self.format}',
            "* Data infos :",
            f" size {self.size}",
            f" bit depth {self.depth}",
            f" data type {self.dtype}",
            f" number of bands {self.nbBands}",
            f" nodata value {self.noData}",
            f"* Georef & Geometry : \n{self.georef}"
        ])

    #######################################
    # Methods
    #######################################

    def toGDAL(self):
        """Get GDAL dataset"""
        return gdal.Open(self.path, gdal.GA_ReadOnly)

    def readAsNpArray(self, subset=True, dtype: str | None=None) -> NpImage:
        """Read raster pixels values as Numpy Array
        dtype : optional numpy like dtype string (eg 'float32') used to convert
        data on the fly during reading (GDAL engine only, saves memory)
        """

        bufType = None
        if dtype is not None and HAS_GDAL:
            bufType = gdal.GetDataTypeByName(dtype)

        if subset and self.subBoxGeo is not None:
            img = NpImage(self.path, subBoxPx=self.subBoxPx, noData=self.noData, georef=self.georef,
                          adjustGeoref=True, bufType=bufType)
        else:
            img = NpImage(self.path, noData=self.noData, georef=self.georef, bufType=bufType)
        return img


if __name__ == "__main__":
    path = r"C:\Users\svintys\Desktop\FDem_103_196.tif"
    raster = GeoRaster(path)
    print(raster)

    img = raster.readAsNpArray()
    data = img.data
    print(data)
    print(img.getMin(), img.getMax())