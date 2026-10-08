import struct
from ..lib import imghdr


def isValidStream(data):
	if data is None:
		return False
	format = imghdr.what(None, data)
	if format is None:
		return False
	return True


def getImgFormat(filepath: str) -> str:
	"""
	Read header of an image file and try to determine it's format
	no requirements.txt, support JPEG, JPEG2000, PNG, GIF, BMP, TIFF, EXR
	"""
	format = 'UNKNOWN'
	with open(filepath, 'rb') as fhandle:
		head = fhandle.read(32)
		# handle GIFs
		if head[:6] in (b'GIF87a', b'GIF89a'):
			format = 'GIF'
		# handle PNG
		elif head.startswith(b'\211PNG\r\n\032\n'):
			format = 'PNG'
		# handle JPEGs
		#elif head[6:10] in (b'JFIF', b'Exif')
		elif (b'JFIF' in head or b'Exif' in head or b'8BIM' in head) or head.startswith(b'\xff\xd8'):
			format = 'JPEG'
		# handle JPEG2000s
		elif head.startswith(b'\x00\x00\x00\x0cjP  \r\n\x87\n'):
			format = 'JPEG2000'
		# handle BMP
		elif head.startswith(b'BM'):
			format = 'BMP'
		# handle TIFF
		elif head[:2] in (b'MM', b'II'):
			format = 'TIFF'
		# handle EXR
		elif head.startswith(b'\x76\x2f\x31\x01'):
			format = 'EXR'
	return format



def getImgDim(filepath):
	"""
	Return (width, height) for a given img file content
	no requirements.txt, support JPEG, JPEG2000, PNG, GIF, BMP
	"""
	width, height = None, None

	with open(filepath, 'rb') as fhandle:
		head = fhandle.read(32)
		# handle GIFs
		if head[:6] in (b'GIF87a', b'GIF89a'):
			try:
				width, height = struct.unpack("<hh", head[6:10])
			except struct.error:
				raise ValueError("Invalid GIF file")
		# handle PNG
		elif head.startswith(b'\211PNG\r\n\032\n'):
			try:
				width, height = struct.unpack(">LL", head[16:24])
			except struct.error:
				# Maybe this is for an older PNG version.
				try:
					width, height = struct.unpack(">LL", head[8:16])
				except struct.error:
					raise ValueError("Invalid PNG file")
		# handle JPEGs
		elif (b'JFIF' in head or b'Exif' in head or b'8BIM' in head) or head.startswith(b'\xff\xd8'):
			try:
				fhandle.seek(0) # Read 0xff next
				size = 2
				ftype = 0
				while not 0xc0 <= ftype <= 0xcf:
					fhandle.seek(size, 1)
					byte = fhandle.read(1)
					while ord(byte) == 0xff:
						byte = fhandle.read(1)
					ftype = ord(byte)
					size = struct.unpack('>H', fhandle.read(2))[0] - 2
				# We are at a SOFn block
				fhandle.seek(1, 1)  # Skip `precision' byte.
				height, width = struct.unpack('>HH', fhandle.read(4))
			except struct.error:
				raise ValueError("Invalid JPEG file")
		# handle JPEG2000s
		elif head.startswith(b'\x00\x00\x00\x0cjP  \r\n\x87\n'):
			fhandle.seek(48)
			try:
				height, width = struct.unpack('>LL', fhandle.read(8))
			except struct.error:
				raise ValueError("Invalid JPEG2000 file")
		# handle BMP
		elif head.startswith(b'BM'):
			imgtype = 'BMP'
			try:
				width, height = struct.unpack("<LL", head[18:26])
			except struct.error:
				raise ValueError("Invalid BMP file")

	return width, height
