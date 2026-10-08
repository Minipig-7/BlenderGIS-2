'''
Pure spherical/cartesian conversion helpers.
This module must stay free of any blender (``bpy``) import so that it can be
used and tested outside of the blender python runtime.
'''

from math import sqrt, cos, sin, asin, atan2, radians, degrees


def xyz2lonlat(x, y, z):
	'''Cartesian coordinates on a sphere to longitude/latitude in radians
	x, y, z >> cartesian coords, z being the polar axis (north)
	return >> (lon_rad, lat_rad, r) with lon in [-pi, pi], lat in [-pi/2, pi/2]
	r is the distance to the sphere center and can be 0 for a degenerate vertex'''
	if x == 0.0 and y == 0.0 and z == 0.0:
		return 0.0, 0.0, 0.0
	r = sqrt(x * x + y * y + z * z)
	lon = atan2(y, x)
	lat = asin(max(-1.0, min(1.0, z / r)))
	return lon, lat, r


def lonlat2xyz(lon_rad, lat_rad, r):
	'''Longitude/latitude in radians and radius to cartesian coordinates
	z being the polar axis (north)
	This is the mathematical inverse of ``xyz2lonlat``'''
	x = r * cos(lat_rad) * cos(lon_rad)
	y = r * cos(lat_rad) * sin(lon_rad)
	z = r * sin(lat_rad)
	return x, y, z


def xyz2lonlatDeg(x, y, z):
	'''Same as ``xyz2lonlat`` but longitude/latitude are returned in decimal degrees'''
	lon, lat, r = xyz2lonlat(x, y, z)
	return degrees(lon), degrees(lat), r


def lonlatDeg2xyz(lon_deg, lat_deg, r):
	'''Same as ``lonlat2xyz`` but longitude/latitude are expected in decimal degrees'''
	return lonlat2xyz(radians(lon_deg), radians(lat_deg), r)