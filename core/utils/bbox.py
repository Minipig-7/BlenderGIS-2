from typing import Sequence

from . import XY
import logging

log = logging.getLogger(__name__)


class BBOX:
    """A class to represent a bounding box"""
    __slots__ = ('__data',)

    def __init__(self,
                 xmin: int | float,
                 xmax: int | float,
                 ymin: int | float,
                 ymax: int | float,
                 zmin: int | float | None = None,
                 zmax: int | float | None = None):

        if not self.__validate(xmin, ymin, xmax, ymax, zmin or 0, zmax or 0):
            raise TypeError("Arguments must be 'float' or 'int' type")

        self.__data: list[int | float | None] = [xmin, ymin, xmax, ymax, zmin, zmax]

    def __validate(self, *args):
        return all(isinstance(a, (int, float)) for a in list(args))

    def __str__(self):
        if self.hasZ:
            return 'xmin:%g, ymin:%g, zmin:%g, xmax:%g, ymax:%g, zmax:%g' % tuple(self.__data)
        return 'xmin:%g, ymin:%g, xmax:%g, ymax:%g' % tuple(self.__data[:4])
    
    def __repr__(self):
        return self.__str__()

    def __iter__(self):
        """iterate overs values in bottom left to upper right order
        allows support of unpacking and conversion to tuple or list"""
        if self.hasZ:
            return iter(self.__data)
        return iter(self.__data[:4])

    @classmethod
    def fromXYZ(cls, seq: Sequence[int | float]):
        """Create a BBOX from a flat sequence of values ordered following XYZ axis
        --> (xmin, xmax, ymin, ymax) or (xmin, xmax, ymin, ymax, zmin, zmax)"""
        if not isinstance(seq, Sequence):
            raise TypeError('Invalid sequence type for BBOX creation')
        match len(seq):
            case 4:
                return cls(seq[0], seq[1], seq[2], seq[3])
            case 6:
                return cls(seq[0], seq[1], seq[2], seq[3], seq[4], seq[5])
            case _:
                raise ValueError('Sequence length must be 4 or 6 for BBOX creation')

    def toXYZ(self) -> list[int | float]:
        """Export to a simple tuple of values ordered following XYZ axis"""
        if self.hasZ:
            return self.__data  # type: ignore
        return self.__data[:4]

    @classmethod
    def fromLatlon(cls, seq: Sequence[int | float]):
        """Create a 2D BBOX from a list of values ordered as latlon format
         (latmin, lonmin, latmax, lonmax) <--> (min, xmin, ymax, xmax)"""
        if not isinstance(seq, Sequence):
            raise TypeError('Invalid sequence type for BBOX creation')
        if len(seq) != 4:
            raise ValueError('Sequence length must be 4 for BBOX creation')
        return cls(seq[0], seq[1], seq[2], seq[3])

    def toLatLon(self) -> list[int | float]:
        """Export to a simple tuple of values ordered as LatLon format in 2D"""
        return self.__data[:4]

    @property
    def data(self) -> list[int | float | None]:
        return self.__data.copy()

    @property
    def hasZ(self) -> bool:
        """Check if this bbox is in 3D"""
        return None not in self.__data[4:]

    def to2D(self):
        """Cast 3d bbox to 2d >> discard zmin and zmax values"""
        self.__data[4] = self.__data[5] = None
        return self

    def toGeo(self, geoscn):
        """Convert the BBOX into Spatial Ref System space defined in Scene"""
        if geoscn.isBroken or not geoscn.isGeoref:
            log.warning('Cannot convert bbox, invalid georef')
            return None
        xmax = geoscn.crsx + (self.xmax * geoscn.scale)
        ymax = geoscn.crsy + (self.ymax * geoscn.scale)
        xmin = geoscn.crsx + (self.xmin * geoscn.scale)
        ymin = geoscn.crsy + (self.ymin * geoscn.scale)
        if self.hasZ:
            return BBOX(xmin, ymin, self.zmin, xmax, ymax, self.zmax)
        else:
            return BBOX(xmin, ymin, xmax, ymax)

    def __eq__(self, other):
        """Test if 2 bbox are equals"""
        return self.__data == other.data

    def overlap(self, bb) -> bool:
        """Test if 2 bbox objects have intersection areas (in 2D only)"""
        return (self.__test_overlap(self.xmin, self.xmax, bb.xmin, bb.xmax)
                and self.__test_overlap(self.ymin, self.ymax, bb.ymin, bb.ymax))
    
    @staticmethod
    def __test_overlap(a_min, a_max, b_min, b_max) -> bool:
        return not ((a_min > b_max) or (b_min > a_max))

    def isWithin(self, bb) -> bool:
        """Test if this bbox is within another bbox"""
        return (bb.xmin <= self.xmin and bb.xmax >= self.xmax
                and bb.ymin <= self.ymin and bb.ymax >= self.ymax)

    def contains(self, bb) -> bool:
        """Test if this bbox contains another bbox"""
        return (bb.xmin > self.xmin and bb.xmax < self.xmax
                and bb.ymin > self.ymin and bb.ymax < self.ymax)

    def __add__(self, bb):
        """Use '+' operator to perform the union of 2 bbox"""
        xmax = max(self.xmax, bb.xmax)
        xmin = min(self.xmin, bb.xmin)
        ymax = max(self.ymax, bb.ymax)
        ymin = min(self.ymin, bb.ymin)
        if self.hasZ and bb.hasZ:
            zmax = max(self.zmax, bb.zmax)
            zmin = min(self.zmin, bb.zmin)
            return BBOX(xmin, ymin, zmin, xmax, ymax, zmax)
        return BBOX(xmin, ymin, xmax, ymax)

    def shift(self, dx: int | float, dy: int | float):
        """translate the bbox in 2D"""
        self.__data[0] += dx
        self.__data[1] += dx
        self.__data[2] += dy
        self.__data[3] += dy

    @property
    def center(self) -> XY:
        x = (self.xmin + self.xmax) / 2
        y = (self.ymin + self.ymax) / 2
        if self.hasZ:
            z = (self.zmin + self.zmax) / 2
            return XY(x, y, z)
        return XY(x, y)

    @property
    def dimensions(self) -> XY:
        dx = self.xmax - self.xmin
        dy = self.ymax - self.ymin
        if self.hasZ:
            dz = self.zmax - self.zmin
            return XY(dx, dy, dz)
        else:
            return XY(dx, dy)

    ################
    ## 2D properties

    @property
    def corners(self) -> list[XY]:
        """Get the list of corners coords, starting from upperleft and ordered clockwise"""
        return [self.ul, self.ur, self.br, self.bl]

    @property
    def ul(self) -> XY:
        """upper left corner"""
        return XY(self.xmin, self.ymax)

    @property
    def ur(self) -> XY:
        """upper right corner"""
        return XY(self.xmax, self.ymax)

    @property
    def bl(self) -> XY:
        """bottom left corner"""
        return XY(self.xmin, self.ymin)

    @property
    def br(self) -> XY:
        """bottom right corner"""
        return XY(self.xmax, self.ymin)

    # other properties

    @property
    def xmin(self):
        return self.__data[0]

    @property
    def xmax(self):
        return self.__data[1]

    @property
    def ymin(self):
        return self.__data[2]

    @property
    def ymax(self):
        return self.__data[3]

    @property
    def zmin(self):
        return self.__data[4]

    @property
    def zmax(self):
        return self.__data[5]
