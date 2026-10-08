import os
import io
import gc
import math
import random
from typing import Optional
from ...common_types import RGBA

import numpy as np
from PIL.Image import Image
from numpy import ndarray


from ..georaster.georef import GeoRef
from ..proj.reproj import reprojImg
from ..maths.fillnodata import replace_nans  # inpainting function (ie fill nodata)
from ..utils import XY, BBOX
from ..checkdeps import HAS_GDAL, HAS_PIL, HAS_IMGIO
from .. import settings

if HAS_PIL:
    from PIL import Image

if HAS_GDAL:
    from osgeo import gdal

if HAS_IMGIO:
    from ..lib import imageio


def _getIFACE() -> str:
    engine = settings.img_engine

    if engine == 'AUTO':
        if HAS_GDAL:
            return 'GDAL'
        elif HAS_IMGIO:
            return 'IMGIO'
        elif HAS_PIL:
            return 'PIL'
        else:
            raise ImportError("No image engine available")
    elif engine == 'GDAL' and HAS_GDAL:
        return 'GDAL'
    elif engine == 'IMGIO' and HAS_IMGIO:
        return 'IMGIO'
    elif engine == 'PIL' and HAS_PIL:
        return 'PIL'
    else:
        raise ImportError(str(engine) + " interface unavailable")


class NpImage:
    """Represent an image as Numpy array"""

    # GeoGef delegation by composition instead of inheritance
    # this special method is called whenever the requested attribute or method is not found in the object
    def __getattr__(self, attr):
        if self.isGeoref:
            return getattr(self.georef, attr)
        else:  # TODO raise specific msg if request for a georef attribute and not self.isgeoref
            raise AttributeError(f"{self.__class__.__name__} object has no attribute {attr}")

    def __init__(self,
                 data,
                 subBoxPx: Optional[BBOX]=None,
                 noData:   Optional[float | int]=None,
                 georef:   Optional[GeoRef]=None,
                 adjustGeoref: bool=False,
                 bufType:  Optional[int]=None):
        """
        init from file path, bytes data, Numpy array, NpImage, PIL Image or GDAL dataset
        subBoxPx : a BBOX object in pixel coordinates space used as data filter (will by applyed) (y counting from top)
        noData : the value used to represent nodata, will be used to define a numpy mask
        georef : a Georef object used to set georeferencing informations, optional
        adjustGeoref: determine if the submited georef must be adjusted against the subbox or if its already correct
        bufType : a GDAL data type constant (eg gdal.GDT_Float32) used to convert data on the fly during reading.
        Only used by the GDAL engine, it avoids allocating an intermediate array when the data
        must be cast anyway (eg a 16 bits DEM that will be converted to float32)

        Notes :
        * With GDAL the subbox filter can be applyed at reading level whereas with others imaging
        library, all the data must be extracted before we can extract the subset (using numpy slice).
        In this case, the dataset must fit entirely in memory otherwise it will raise an overflow error
        * If no georef was submited and when the class is init using gdal support or from another npImage instance,
        existing georef of input data will be automatically extracted and adjusted against the subbox
        """
        self.IFACE: str = _getIFACE()

        self.data = None
        self.subBoxPx: Optional[BBOX] = subBoxPx
        self.noData:   Optional[float | int] = noData
        self.bufType:  Optional[int] = bufType

        self.georef = georef
        if self.subBoxPx is not None and self.georef is not None:
            if adjustGeoref:
                self.georef.setSubBoxPx(subBoxPx)
                self.georef.applySubBox()

        # init from another NpImage instance
        if isinstance(data, NpImage):
            self.data = self._applySubBox(data.data)
            if data.isGeoref and not self.isGeoref:
                self.georef = data.georef
                # adjust georef against subbox
                if self.subBoxPx is not None:
                    self.georef.setSubBoxPx(subBoxPx)
                    self.georef.applySubBox()

        # init from numpy array
        if isinstance(data, ndarray):
            self.data = self._applySubBox(data)

        # init from bytes data (BLOB)
        if isinstance(data, bytes):
            self.data = self._npFromBLOB(data)

        # init from file path
        if isinstance(data, str):
            if os.path.exists(data):
                self.data = self._npFromPath(data)
            else:
                raise ValueError('Unable to load image data')

        # init from GDAL dataset instance
        if HAS_GDAL:
            if isinstance(data, gdal.Dataset):
                self.data = self._npFromGDAL(data)

        # init from PIL Image instance
        if HAS_PIL:
            if isinstance(data, Image.Image):
                self.data = self._npFromPIL(data)

        if self.data is None:
            raise ValueError('Unable to load image data')

        # Mask nodata value to avoid bias when computing min or max statistics
        if self.noData is not None:
            self.data = np.ma.masked_array(self.data, self.data == self.noData)


    @property
    def size(self) -> XY:
        return XY(self.data.shape[1], self.data.shape[0])


    @property
    def isGeoref(self) -> bool:
        """Flag if georef parameters have been extracted"""
        return self.georef is not None


    @property
    def nbBands(self):
        if len(self.data.shape) == 2:
            return 1
        elif len(self.data.shape) == 3:
            return self.data.shape[2]
        return None

    @property
    def hasAlpha(self) -> bool:
        return self.nbBands == 4


    @property
    def isOneBand(self) -> bool:
        return self.nbBands == 1


    @property
    def dtype(self) -> str:
        """return string ['int8', 'uint8', 'int16', 'uint16', 'int32', 'uint32', 'float32', 'float64']"""
        return self.data.dtype  # type: ignore


    @property
    def isFloat(self) -> bool:
        return self.dtype in ['float16', 'float32', 'float64']


    def getMin(self, bandIdx: int=0) -> int:
        if self.nbBands == 1:
            return self.data.min()
        else:
            return self.data[:, :, bandIdx].min()


    def getMax(self, bandIdx: int=0) -> int:
        if self.nbBands == 1:
            return self.data.max()
        else:
            return self.data[:, :, bandIdx].max()


    @classmethod
    def new(cls, w, h,
            bkgColor: RGBA=(255, 255, 255, 255),
            noData: Optional[float | int]=None,
            georef: Optional[GeoRef]=None):
        r, g, b, a = bkgColor
        data = np.empty((h, w, 4), np.uint8)
        data[:, :, 0] = r
        data[:, :, 1] = g
        data[:, :, 2] = b
        data[:, :, 3] = a
        return cls(data, noData=noData, georef=georef)

    def _applySubBox(self, data: ndarray):
        """Use numpy slice to extract subset of data"""
        if self.subBoxPx is not None:
            x1, x2 = self.subBoxPx.xmin, self.subBoxPx.xmax + 1
            y1, y2 = self.subBoxPx.ymin, self.subBoxPx.ymax + 1
            if len(data.shape) == 2:  # one band
                data = data[y1:y2, x1:x2]
            else:
                data = data[y1:y2, x1:x2, :]
            self.subBoxPx = None
        return data

    def _npFromPath(self, path: str) -> ndarray | None:
        """Get Numpy array from a file path"""
        if self.IFACE == 'PIL':
            img = Image.open(path)
            return self._npFromPIL(img)
        elif self.IFACE == 'IMGIO':
            return self._npFromImgIO(path)
        elif self.IFACE == 'GDAL':
            ds = gdal.Open(path)
            return self._npFromGDAL(ds)
        return None

    def _npFromBLOB(self, data: bytes):
        """Get Numpy array from Bytes data"""

        if self.IFACE == 'PIL':
            # convert bytes object to bytesio (stream buffer) and open it with PIL
            img = Image.open(io.BytesIO(data))
            data = self._npFromPIL(img)

        elif self.IFACE == 'IMGIO':
            img = io.BytesIO(data)
            data = self._npFromImgIO(img)

        elif self.IFACE == 'GDAL':
            # Use a virtual memory file to create gdal dataset from buffer
            # build a random name to make the function thread safe
            vsipath = '/vsimem/' + ''.join(random.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(5))
            gdal.FileFromMemBuffer(vsipath, data)
            ds = gdal.Open(vsipath)
            data = self._npFromGDAL(ds)
            gdal.Unlink(vsipath)

        return data


    def _npFromImgIO(self, img):
        """Use ImageIO to extract numpy array from image path or bytesIO"""
        data = imageio.imread(img)
        return self._applySubBox(data)


    def _npFromPIL(self, img):
        """Get Numpy array from PIL Image instance"""
        if img.mode == 'P':  # palette (indexed color)
            img = img.convert('RGBA')
        data = np.asarray(img)
        # data.setflags(write=True) #PIL return a non writable array
        return self._applySubBox(data)


    def _npFromGDAL(self, ds):
        """Get Numpy array from GDAL dataset instance"""
        band1 = ds.GetRasterBand(1)
        ctable = band1.GetColorTable()
        # on the fly data conversion (only if there is no color table,
        # because converting indexed values would break the color lookup)
        useBuf = self.bufType is not None and ctable is None
        if self.subBoxPx is not None:
            startx, starty = self.subBoxPx.xmin, self.subBoxPx.ymin
            width = (self.subBoxPx.xmax - self.subBoxPx.xmin) + 1
            height = (self.subBoxPx.ymax - self.subBoxPx.ymin) + 1
            if useBuf:
                data = ds.ReadAsArray(startx, starty, width, height, buf_type=self.bufType)
            else:
                data = ds.ReadAsArray(startx, starty, width, height)
        else:
            if useBuf:
                data = ds.ReadAsArray(buf_type=self.bufType)
            else:
                data = ds.ReadAsArray()
        if len(data.shape) == 3:  # multiband
            data = np.rollaxis(data, 0, 3)  # because first axis is band index
        else:  # one band raster or indexed color (= palette = pseudo color table (pct))
            if ctable is not None:
                # Swap index values to their corresponding color (rgba)
                nbColors = ctable.GetCount()
                keys = np.array([i for i in range(nbColors)])
                values = np.array([ctable.GetColorEntry(i) for i in range(nbColors)])
                sortIdx = np.argsort(keys)
                idx = np.searchsorted(keys, data, sorter=sortIdx)
                data = values[sortIdx][idx]

        # Try to extract georef
        if not self.isGeoref:
            self.georef = GeoRef.fromGDAL(ds)
            # adjust georef against subbox
            if self.subBoxPx is not None and self.georef is not None:
                self.georef.applySubBox()

        return data


    def toBLOB(self, ext: str='PNG'):
        """Get bytes raw data"""
        if ext == 'JPG':
            ext = 'JPEG'

        data = None

        if self.IFACE == 'PIL':
            b = io.BytesIO()
            img = Image.fromarray(self.data)
            img.save(b, format=ext)
            data = b.getvalue()  # convert bytesio to bytes

        elif self.IFACE == 'IMGIO':
            if ext == 'JPEG' and self.hasAlpha:
                self.removeAlpha()
            data = imageio.imwrite(imageio.RETURN_BYTES, self.data, format=ext)

        elif self.IFACE == 'GDAL':
            mem = self.toGDAL()
            # build a random name to make the function thread safe
            name = ''.join(random.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(5))
            vsiname = '/vsimem/' + name + '.png'
            gdal.GetDriverByName(ext).CreateCopy(vsiname, mem)
            # Read /vsimem/output.png
            f = gdal.VSIFOpenL(vsiname, 'rb')
            gdal.VSIFSeekL(f, 0, 2)  # seek to end
            size = gdal.VSIFTellL(f)
            gdal.VSIFSeekL(f, 0, 0)  # seek to beginning
            data = gdal.VSIFReadL(1, size, f)
            gdal.VSIFCloseL(f)
            # Cleanup
            gdal.Unlink(vsiname)
            del mem

        return data

    def toPIL(self) -> Image:
        """Get PIL Image instance"""
        return Image.fromarray(self.data)

    def toGDAL(self):
        """Get GDAL memory driver dataset"""
        w, h = self.size
        n = self.nbBands
        dtype = str(self.dtype)
        if dtype == 'uint8': dtype = 'byte'
        dtype = gdal.GetDataTypeByName(dtype)
        mem = gdal.GetDriverByName('MEM').Create('', w, h, n, dtype)
        # writearray is available only at band level
        if self.isOneBand:
            mem.GetRasterBand(1).WriteArray(self.data)
        else:
            for bandIdx in range(n):
                bandArray = self.data[:, :, bandIdx]
                mem.GetRasterBand(bandIdx + 1).WriteArray(bandArray)
        # write georef
        if self.isGeoref:
            mem.SetGeoTransform(self.georef.toGDAL())
            if self.georef.crs is not None:
                mem.SetProjection(self.georef.crs.getOgrSpatialRef().ExportToWkt())
        return mem

    def _saveGDALChunked(self, path, blockRows: int=1024) -> None:
        """Write a GeoTIFF row block by row block (low memory footprint)"""
        w, h = self.size.xy
        n = self.nbBands
        dtype = str(self.dtype)
        if dtype == 'uint8':
            dtype = 'byte'
        gdalDtype = gdal.GetDataTypeByName(dtype)
        ds = gdal.GetDriverByName('Gtiff').Create(path, w, h, n, gdalDtype)
        if ds is None:
            raise IOError('Cannot create file ' + path)
        try:
            if self.isGeoref:
                ds.SetGeoTransform(self.georef.toGDAL())
                if self.georef.crs is not None:
                    ds.SetProjection(self.georef.crs.getOgrSpatialRef().ExportToWkt())
            data = self.data
            for y0 in range(0, h, blockRows):
                y1 = min(y0 + blockRows, h)
                if self.isOneBand:
                    ds.GetRasterBand(1).WriteArray(np.ascontiguousarray(data[y0:y1]), 0, y0)
                else:
                    for bandIdx in range(n):
                        block = np.ascontiguousarray(data[y0:y1, :, bandIdx])
                        ds.GetRasterBand(bandIdx + 1).WriteArray(block, 0, y0)
            ds.FlushCache()
        finally:
            ds, data = None, None  # close dataset (gdal has no garbage collector)

    def free(self) -> None:
        """Release pixel data from memory"""
        self.data = None
        gc.collect()

    def removeAlpha(self):
        if self.hasAlpha:
            self.data = self.data[:, :, 0:3]

    def addAlpha(self, opacity=255):
        if self.nbBands == 3:
            w, h = self.size
            alpha = np.empty((h, w), dtype=self.dtype)
            alpha.fill(opacity)
            alpha = np.expand_dims(alpha, axis=2)
            self.data = np.append(self.data, alpha, axis=2)

    def save(self, path):
        """
        save the numpy array to a new image file
        output format is defined by path extension
        """

        imgFormat = path[-3:]

        if self.IFACE == 'PIL':
            self.toPIL().save(path)
        elif self.IFACE == 'IMGIO':
            if imgFormat == 'jpg' and self.hasAlpha:
                self.removeAlpha()
            imageio.imwrite(path, self.data)  # float32 support ok
        elif self.IFACE == 'GDAL':
            if imgFormat == 'png':
                driver = 'PNG'
            elif imgFormat == 'jpg':
                driver = 'JPEG'
            elif imgFormat == 'tif':
                driver = 'Gtiff'
            else:
                raise ValueError('Cannot write to ' + imgFormat + ' image format')
            # Some format like jpg or png has no create method implemented
            # because we can't write data at random with these formats
            # so we must use an intermediate memory driver, write data to it
            # and then write the output file with the createcopy method
            if driver == 'Gtiff':
                # GeoTIFF supports direct creation, write data row block by row block
                # to avoid holding a full copy of the raster in a memory dataset
                self._saveGDALChunked(path)
            else:
                mem = self.toGDAL()
                gdal.GetDriverByName(driver).CreateCopy(path, mem)
                del mem

        if self.isGeoref:
            self.georef.toWorldFile(os.path.splitext(path)[0] + '.wld')


    def paste(self, data, x, y) -> None:
        img = NpImage(data)
        data = img.data
        w, h = img.size

        if img.isOneBand and self.isOneBand:
            self.data[y:y + h, x:x + w] = data
        elif (not img.isOneBand and self.isOneBand) or (img.isOneBand and not self.isOneBand):
            raise ValueError('Paste error, cannot mix one band with multiband')

        if self.hasAlpha:
            n = img.nbBands
            self.data[y:y + h, x:x + w, 0:n] = data
        else:
            n = self.nbBands
            self.data[y:y + h, x:x + w, :] = data[:, :, 0:n]


    def cast2float(self) -> None:
        if not self.isFloat:
            self.data = self.data.astype('float32')

    def decimate(self, maxSize: int) -> None:
        """Reduce image size by integer decimation so that max dimension <= maxSize.
        Georef is adjusted against the new pixel size."""
        w, h = self.size
        k = max(1, math.ceil(max(w, h) / maxSize))
        if k > 1:
            if self.georef is not None:
                self.georef.pxSize = XY(self.georef.pxSize.x * k, self.georef.pxSize.y * k)
                self.georef.rSize = XY(math.ceil(w / k), math.ceil(h / k))
            self.data = self.data[::k, ::k]


    def fillNodata(self) -> None:
        # if not self.noData in self.data:
        if not np.ma.is_masked(self.data):
            # do not process it if its not necessary
            return
        if self.IFACE == 'GDAL':
            # gdal.FillNodata need a band object to apply on
            # so we create a memory datasource (1 band, float)
            height, width = self.data.shape
            ds = gdal.GetDriverByName('MEM').Create('', width, height, 1, gdal.GetDataTypeByName('float32'))
            b = ds.GetRasterBand(1)
            b.SetNoDataValue(self.noData)
            self.data = np.ma.filled(self.data, self.noData)  # Fill mask with nodata value
            b.WriteArray(self.data)
            gdal.FillNodata(targetBand=b, maskBand=None, maxSearchDist=max(self.size.xy), smoothingIterations=0)
            self.data = b.ReadAsArray()
        else:  # Call the inpainting function
            # Cast to float
            self.cast2float()
            # Fill mask with nan (warning nan is a special value for float arrays only)
            self.data = np.ma.filled(self.data, np.nan)
            # Inpainting
            self.data = replace_nans(self.data, max_iter=5, tolerance=0.5, kernel_size=2, method='localmean')

    def reproj(self, crs1, crs2, out_ul=None, out_size=None, out_res=None, sqPx=False, resamplAlg='BL'):
        ds1 = self.toGDAL()
        if not self.isGeoref:
            raise IOError('Unable to reproject non georeferenced image')
        ds2 = reprojImg(crs1, crs2, ds1, out_ul=out_ul, out_size=out_size, out_res=out_res, sqPx=sqPx,
                        resamplAlg=resamplAlg)
        return NpImage(ds2)

    def __repr__(self):
        return '\n'.join([
            "* Data infos :",
            f" size {self.size}",
            f" type {self.dtype}",
            f" number of bands {self.nbBands}",
            f" nodata value {self.noData}",
            f"* Statistics : min {self.getMin()} max {self.getMax()}",
            f"* Georef & Geometry : \n{self.georef}"
        ])
