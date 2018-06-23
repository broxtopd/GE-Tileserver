# Script to dynamically generate web tiles, either blending existing tiles, 
# generating from a local data source, or blending the two.
#
###############################################################################
# Copyright (c) 2018, Patrick Broxton
# 
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation
#  the rights to use, copy, modify, merge, publish, distribute, sublicense,
#  and/or sell copies of the Software, and to permit persons to whom the
#  Software is furnished to do so, subject to the following conditions:
# 
#  The above copyright notice and this permission notice shall be included
#  in all copies or substantial portions of the Software.
# 
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
#  OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
#  THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.
###############################################################################

#from wsgiref.simple_server import make_server

import sys
from cgi import parse_qs, escape
import gdal, ogr, osr
import math
import subprocess
from PIL import Image, ImageMath
import numpy
(major,minor,micro,releaselevel,serial) = sys.version_info
if major == 2:
    from cStringIO import StringIO
elif major == 3:
    from io import BytesIO
    from urllib.request import urlopen
import os, sys
import time
import re
import urllib
import tempfile
import zipfile

# sys.stderr = open(os.path.abspath(__file__).replace(os.path.basename(__file__),'') + 'logs/generate_tiles.txt', 'w')

###############################################################################

__doc__globalmaptiles = """
globalmaptiles.py

Global Map Tiles as defined in Tile Map Service (TMS) Profiles
==============================================================

Functions necessary for generation of global tiles used on the web.
It contains classes implementing coordinate conversions for:

  - GlobalMercator (based on EPSG:900913 = EPSG:3785)
       for Google Maps, Yahoo Maps, Bing Maps compatible tiles
  - GlobalGeodetic (based on EPSG:4326)
       for OpenLayers Base Map and Google Earth compatible tiles

More info at:

http://wiki.osgeo.org/wiki/Tile_Map_Service_Specification
http://wiki.osgeo.org/wiki/WMS_Tiling_Client_Recommendation
http://msdn.microsoft.com/en-us/library/bb259689.aspx
http://code.google.com/apis/maps/documentation/overlays.html#Google_Maps_Coordinates

Created by Klokan Petr Pridal on 2008-07-03.
Google Summer of Code 2008, project KMLForTiles for OSGEO.

In case you use this class in your product, translate it to another language
or find it usefull for your project please let me know.
My email: klokan at klokan dot cz.
I would like to know where it was used.

Class is available under the open-source GDAL license (www.gdal.org).
"""

MAXZOOMLEVEL = 32

class GlobalMercator(object):
    """
    TMS Global Mercator Profile
    ---------------------------

  Functions necessary for generation of tiles in Spherical Mercator projection,
  EPSG:900913 (EPSG:gOOglE, Google Maps Global Mercator), EPSG:3785, OSGEO:41001.

  Such tiles are compatible with Google Maps, Bing Maps, Yahoo Maps,
  UK Ordnance Survey OpenSpace API, ...
  and you can overlay them on top of base maps of those web mapping applications.

    Pixel and tile coordinates are in TMS notation (origin [0,0] in bottom-left).

    What coordinate conversions do we need for TMS Global Mercator tiles::

         LatLon      <->       Meters      <->     Pixels    <->       Tile

     WGS84 coordinates   Spherical Mercator  Pixels in pyramid  Tiles in pyramid
         lat/lon            XY in metres     XY pixels Z zoom      XYZ from TMS
        EPSG:4326           EPSG:900913
         .----.              ---------               --                TMS
        /      \     <->     |       |     <->     /----/    <->      Google
        \      /             |       |           /--------/          QuadTree
         -----               ---------         /------------/
       KML, public         WebMapService         Web Clients      TileMapService

    What is the coordinate extent of Earth in EPSG:900913?

      [-20037508.342789244, -20037508.342789244, 20037508.342789244, 20037508.342789244]
      Constant 20037508.342789244 comes from the circumference of the Earth in meters,
      which is 40 thousand kilometers, the coordinate origin is in the middle of extent.
      In fact you can calculate the constant as: 2 * math.pi * 6378137 / 2.0
      $ echo 180 85 | gdaltransform -s_srs EPSG:4326 -t_srs EPSG:900913
      Polar areas with abs(latitude) bigger then 85.05112878 are clipped off.

    What are zoom level constants (pixels/meter) for pyramid with EPSG:900913?

      whole region is on top of pyramid (zoom=0) covered by 256x256 pixels tile,
      every lower zoom level resolution is always divided by two
      initialResolution = 20037508.342789244 * 2 / 256 = 156543.03392804062

    What is the difference between TMS and Google Maps/QuadTree tile name convention?

      The tile raster itself is the same (equal extent, projection, pixel size),
      there is just different identification of the same raster tile.
      Tiles in TMS are counted from [0,0] in the bottom-left corner, id is XYZ.
      Google placed the origin [0,0] to the top-left corner, reference is XYZ.
      Microsoft is referencing tiles by a QuadTree name, defined on the website:
      http://msdn2.microsoft.com/en-us/library/bb259689.aspx

    The lat/lon coordinates are using WGS84 datum, yeh?

      Yes, all lat/lon we are mentioning should use WGS84 Geodetic Datum.
      Well, the web clients like Google Maps are projecting those coordinates by
      Spherical Mercator, so in fact lat/lon coordinates on sphere are treated as if
      the were on the WGS84 ellipsoid.

      From MSDN documentation:
      To simplify the calculations, we use the spherical form of projection, not
      the ellipsoidal form. Since the projection is used only for map display,
      and not for displaying numeric coordinates, we don't need the extra precision
      of an ellipsoidal projection. The spherical projection causes approximately
      0.33 percent scale distortion in the Y direction, which is not visually noticable.

    How do I create a raster in EPSG:900913 and convert coordinates with PROJ.4?

      You can use standard GIS tools like gdalwarp, cs2cs or gdaltransform.
      All of the tools supports -t_srs 'epsg:900913'.

      For other GIS programs check the exact definition of the projection:
      More info at http://spatialreference.org/ref/user/google-projection/
      The same projection is degined as EPSG:3785. WKT definition is in the official
      EPSG database.

      Proj4 Text:
        +proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0
        +k=1.0 +units=m +nadgrids=@null +no_defs

      Human readable WKT format of EPGS:900913:
         PROJCS["Google Maps Global Mercator",
             GEOGCS["WGS 84",
                 DATUM["WGS_1984",
                     SPHEROID["WGS 84",6378137,298.257223563,
                         AUTHORITY["EPSG","7030"]],
                     AUTHORITY["EPSG","6326"]],
                 PRIMEM["Greenwich",0],
                 UNIT["degree",0.0174532925199433],
                 AUTHORITY["EPSG","4326"]],
             PROJECTION["Mercator_1SP"],
             PARAMETER["central_meridian",0],
             PARAMETER["scale_factor",1],
             PARAMETER["false_easting",0],
             PARAMETER["false_northing",0],
             UNIT["metre",1,
                 AUTHORITY["EPSG","9001"]]]
    """

    def __init__(self, tileSize=256):
        "Initialize the TMS Global Mercator pyramid"
        self.tileSize = tileSize
        self.initialResolution = 2 * math.pi * 6378137 / self.tileSize
        # 156543.03392804062 for tileSize 256 pixels
        self.originShift = 2 * math.pi * 6378137 / 2.0
        # 20037508.342789244

    def LatLonToMeters(self, lat, lon ):
        "Converts given lat/lon in WGS84 Datum to XY in Spherical Mercator EPSG:900913"

        mx = lon * self.originShift / 180.0
        my = math.log( math.tan((90 + lat) * math.pi / 360.0 )) / (math.pi / 180.0)

        my = my * self.originShift / 180.0
        return mx, my

    def MetersToLatLon(self, mx, my ):
        "Converts XY point from Spherical Mercator EPSG:900913 to lat/lon in WGS84 Datum"

        lon = (mx / self.originShift) * 180.0
        lat = (my / self.originShift) * 180.0

        lat = 180 / math.pi * (2 * math.atan( math.exp( lat * math.pi / 180.0)) - math.pi / 2.0)
        return lat, lon

    def PixelsToMeters(self, px, py, zoom):
        "Converts pixel coordinates in given zoom level of pyramid to EPSG:900913"

        res = self.Resolution( zoom )
        mx = px * res - self.originShift
        my = py * res - self.originShift
        return mx, my

    def MetersToPixels(self, mx, my, zoom):
        "Converts EPSG:900913 to pyramid pixel coordinates in given zoom level"

        res = self.Resolution( zoom )
        px = (mx + self.originShift) / res
        py = (my + self.originShift) / res
        return px, py

    def PixelsToTile(self, px, py):
        "Returns a tile covering region in given pixel coordinates"

        tx = int( math.ceil( px / float(self.tileSize) ) - 1 )
        ty = int( math.ceil( py / float(self.tileSize) ) - 1 )
        return tx, ty

    def PixelsToRaster(self, px, py, zoom):
        "Move the origin of pixel coordinates to top-left corner"

        mapSize = self.tileSize << zoom
        return px, mapSize - py

    def MetersToTile(self, mx, my, zoom):
        "Returns tile for given mercator coordinates"

        px, py = self.MetersToPixels( mx, my, zoom)
        return self.PixelsToTile( px, py)

    def TileBounds(self, tx, ty, zoom):
        "Returns bounds of the given tile in EPSG:900913 coordinates"

        minx, miny = self.PixelsToMeters( tx*self.tileSize, ty*self.tileSize, zoom )
        maxx, maxy = self.PixelsToMeters( (tx+1)*self.tileSize, (ty+1)*self.tileSize, zoom )
        return ( minx, miny, maxx, maxy )

    def TileLatLonBounds(self, tx, ty, zoom ):
        "Returns bounds of the given tile in latutude/longitude using WGS84 datum"

        bounds = self.TileBounds( tx, ty, zoom)
        minLat, minLon = self.MetersToLatLon(bounds[0], bounds[1])
        maxLat, maxLon = self.MetersToLatLon(bounds[2], bounds[3])

        return ( minLat, minLon, maxLat, maxLon )

    def Resolution(self, zoom ):
        "Resolution (meters/pixel) for given zoom level (measured at Equator)"

        # return (2 * math.pi * 6378137) / (self.tileSize * 2**zoom)
        return self.initialResolution / (2**zoom)

    def ZoomForPixelSize(self, pixelSize ):
        "Maximal scaledown zoom of the pyramid closest to the pixelSize."

        for i in range(MAXZOOMLEVEL):
            if pixelSize > self.Resolution(i):
                if i!=0:
                    return i-1
                else:
                    return 0 # We don't want to scale up

    def GoogleTile(self, tx, ty, zoom):
        "Converts TMS tile coordinates to Google Tile coordinates"

        # coordinate origin is moved from bottom-left to top-left corner of the extent
        return tx, (2**zoom - 1) - ty

    def QuadTree(self, tx, ty, zoom ):
        "Converts TMS tile coordinates to Microsoft QuadTree"

        quadKey = ""
        ty = (2**zoom - 1) - ty
        for i in range(zoom, 0, -1):
            digit = 0
            mask = 1 << (i-1)
            if (tx & mask) != 0:
                digit += 1
            if (ty & mask) != 0:
                digit += 2
            quadKey += str(digit)

        return quadKey

###############################################################################

class GlobalGeodetic(object):
    """
    TMS Global Geodetic Profile
    ---------------------------

    Functions necessary for generation of global tiles in Plate Carre projection,
    EPSG:4326, "unprojected profile".

    Such tiles are compatible with Google Earth (as any other EPSG:4326 rasters)
    and you can overlay the tiles on top of OpenLayers base map.

    Pixel and tile coordinates are in TMS notation (origin [0,0] in bottom-left).

    What coordinate conversions do we need for TMS Global Geodetic tiles?

      Global Geodetic tiles are using geodetic coordinates (latitude,longitude)
      directly as planar coordinates XY (it is also called Unprojected or Plate
      Carre). We need only scaling to pixel pyramid and cutting to tiles.
      Pyramid has on top level two tiles, so it is not square but rectangle.
      Area [-180,-90,180,90] is scaled to 512x256 pixels.
      TMS has coordinate origin (for pixels and tiles) in bottom-left corner.
      Rasters are in EPSG:4326 and therefore are compatible with Google Earth.

         LatLon      <->      Pixels      <->     Tiles     

     WGS84 coordinates   Pixels in pyramid  Tiles in pyramid
         lat/lon         XY pixels Z zoom      XYZ from TMS 
        EPSG:4326                                           
         .----.                ----                         
        /      \     <->    /--------/    <->      TMS      
        \      /         /--------------/                   
         -----        /--------------------/                
       WMS, KML    Web Clients, Google Earth  TileMapService
    """

    def __init__(self, tileSize = 256):
        self.tileSize = tileSize

    def LatLonToPixels(self, lat, lon, zoom):
        "Converts lat/lon to pixel coordinates in given zoom of the EPSG:4326 pyramid"

        res = 180.0 / self.tileSize / 2**zoom
        px = (180 + lat) / res
        py = (90 + lon) / res
        return px, py

    def PixelsToTile(self, px, py):
        "Returns coordinates of the tile covering region in pixel coordinates"

        tx = int( math.ceil( px / float(self.tileSize) ) - 1 )
        ty = int( math.ceil( py / float(self.tileSize) ) - 1 )
        return tx, ty

    def LatLonToTile(self, lat, lon, zoom):
        "Returns the tile for zoom which covers given lat/lon coordinates"

        px, py = self.LatLonToPixels( lat, lon, zoom)
        return self.PixelsToTile(px,py)

    def Resolution(self, zoom ):
        "Resolution (arc/pixel) for given zoom level (measured at Equator)"

        return 180.0 / self.tileSize / 2**zoom
        #return 180 / float( 1 << (8+zoom) )

    def ZoomForPixelSize(self, pixelSize ):
        "Maximal scaledown zoom of the pyramid closest to the pixelSize."

        for i in range(MAXZOOMLEVEL):
            if pixelSize > self.Resolution(i):
                if i!=0:
                    return i-1
                else:
                    return 0 # We don't want to scale up

    def TileBounds(self, tx, ty, zoom):
        "Returns bounds of the given tile"
        res = 180.0 / self.tileSize / 2**zoom
        return (
            tx*self.tileSize*res - 180,
            ty*self.tileSize*res - 90,
            (tx+1)*self.tileSize*res - 180,
            (ty+1)*self.tileSize*res - 90
        )

    def TileLatLonBounds(self, tx, ty, zoom):
        "Returns bounds of the given tile in the SWNE form"
        b = self.TileBounds(tx, ty, zoom)
        return (b[1],b[0],b[3],b[2])

###############################################################################


class GenerateDynamicTiles(object):

    def geo_query(self, ds, ulx, uly, lrx, lry, querysize = 0):
        """For given dataset and query in cartographic coordinates
        returns parameters for ReadRaster() in raster coordinates and
        x/y shifts (for border tiles). If the querysize is not given, the
        extent is returned in the native resolution of dataset ds."""

        geotran = ds.GetGeoTransform()
        rx= int((ulx - geotran[0]) / geotran[1] + 0.001)
        ry= int((uly - geotran[3]) / geotran[5] + 0.001)
        rxsize= int((lrx - ulx) / geotran[1] + 0.5)
        rysize= int((lry - uly) / geotran[5] + 0.5)

        if not querysize:
            wxsize, wysize = rxsize, rysize
        else:
            wxsize, wysize = querysize, querysize

        # Coordinates should not go out of the bounds of the raster
        wx = 0
        if rx < 0:
            rxshift = abs(rx)
            wx = int( wxsize * (float(rxshift) / rxsize) )
            wxsize = wxsize - wx
            rxsize = rxsize - int( rxsize * (float(rxshift) / rxsize) )
            rx = 0
        if rx+rxsize > ds.RasterXSize:
            wxsize = int( wxsize * (float(ds.RasterXSize - rx) / rxsize) )
            rxsize = ds.RasterXSize - rx

        wy = 0
        if ry < 0:
            ryshift = abs(ry)
            wy = int( wysize * (float(ryshift) / rysize) )
            wysize = wysize - wy
            rysize = rysize - int( rysize * (float(ryshift) / rysize) )
            ry = 0
        if ry+rysize > ds.RasterYSize:
            wysize = int( wysize * (float(ds.RasterYSize - ry) / rysize) )
            rysize = ds.RasterYSize - ry

        return (rx, ry, rxsize, rysize), (wx, wy, wxsize, wysize)

    # -------------------------------------------------------------------------
    def scale_query_to_tile(self, dsquery, dstile, tilefilename=''):
        """Scales down query dataset to the tile dataset"""

        querysize = dsquery.RasterXSize
        tilesize = dstile.RasterXSize
        tilebands = dstile.RasterCount

        if self.resample == 'average':

            # Function: gdal.RegenerateOverview()
            for i in range(1,tilebands+1):
                # Black border around NODATA
                #if i != 4:
                #   dsquery.GetRasterBand(i).SetNoDataValue(0)
                res = gdal.RegenerateOverview( dsquery.GetRasterBand(i),
                    dstile.GetRasterBand(i), 'average' )
                if res != 0:
                    self.error("RegenerateOverview() failed on %s, error %d" % (tilefilename, res))

        elif self.resample == 'antialias':

            # Scaling by PIL (Python Imaging Library) - improved Lanczos
            array = numpy.zeros((querysize, querysize, tilebands), numpy.uint8)
            for i in range(tilebands):
                array[:,:,i] = gdalarray.BandReadAsArray(dsquery.GetRasterBand(i+1), 0, 0, querysize, querysize)
            im = Image.fromarray(array, 'RGBA') # Always four bands
            im1 = im.resize((tilesize,tilesize), Image.ANTIALIAS)
            if os.path.exists(tilefilename):
                im0 = Image.open(tilefilename)
                im1 = Image.composite(im1, im0, im1) 
            im1.save(tilefilename,self.tiledriver)

        else:

            # Other algorithms are implemented by gdal.ReprojectImage().
            dsquery.SetGeoTransform( (0.0, tilesize / float(querysize), 0.0, 0.0, 0.0, tilesize / float(querysize)) )
            dstile.SetGeoTransform( (0.0, 1.0, 0.0, 0.0, 0.0, 1.0) )

            res = gdal.ReprojectImage(dsquery, dstile, None, None, self.ResampleAlg)
            if res != 0:
                self.error("ReprojectImage() failed on %s, error %d" % (tilefilename, res))
                
    # -------------------------------------------------------------------------
    def error(self, msg, details = "" ):
        """Print an error message and stop the processing"""

        if details:
            self.parser.error(msg + "\n\n" + details)
        else:
            self.parser.error(msg)
      

    # -------------------------------------------------------------------------
    def arrayToImage(self,a):
        """
        Converts a gdalnumeric array to a 
        Python Imaging Library Image.
        """
        #i=Image.frombytes('L',(a.shape[1],a.shape[0]),
        #    (a.astype('b')).tostring())
        i = Image.fromarray(a)
        return i

    def __init__(self,querystring,fs):
        """Constructor function - initialization"""

        self.tilesize = 256
        self.tileext = 'png'
        
        # Get the arguments from the query string
        if major == 2:
            self.url = urllib.unquote(fs.get('url', [''])[0]).decode('utf8')
        elif major == 3:
            self.url = urllib.parse.unquote(fs.get('url', [''])[0])

        if 'zxy=' in querystring:
            self.zxy = escape(fs.get('zxy', [''])[0])
        else:
            self.zxy = '0/0/0'
            
        self.tz, self.tx, self.ty = self.zxy.strip('/').split('/')
         
        if 'cachedir' in querystring:
            self.cachedir = escape(fs.get('cachedir', [''])[0])
        else:
            self.cachedir = ''
            
        if 'resample' in querystring:
            self.resample = escape(fs.get('resample', [''])[0])
        else:
            self.resample = 'near'
            
        if self.url.find('invY') > -1:
            self.invert_y = True
        else:
            self.invert_y = False
            
        self.profile = 'mercator'
        self.proj = 'geo'
        
    # -------------------------------------------------------------------------
    def generate_tiles(self):
        """
        Function to generate the dynamic tiles (either merging multiple web tile 
        sources and/or extracting data from a local GIS data source
        """ 

        # print('Content-Type: text/html\n')
        start = time.time()
        
        tz = int(self.tz)
        tx = int(self.tx)
        ty = int(self.ty)
        
        # In case of inverted y coordinate
        if self.invert_y:
            ty2 = ty
        else:
            if type(ty) is int:
                ty2 = (2**tz)-ty-1
            else:
                ty2 = ty
        
        tilefilename = os.path.join(self.cachedir, str(tz), str(tx), "%s.%s" % (ty, self.tileext))
        
        # Tile name used if tile is cached
        if self.cachedir != '':
            if os.path.exists(tilefilename):
                im = Image.open(tilefilename)
                if major == 2:
                    f = StringIO()
                elif major == 3:
                    f = BytesIO()
                im.save(f, "PNG")
                f.seek(0)
                return f.read()

        print('Getting Raster ' + str(time.time() - start) + ' s')
        
        if self.proj == 'geo':
            s_srs = "+proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0 +k=1.0 +units=m +nadgrids=@null +wktext +no_defs"
            t_srs = "+proj=latlong +datum=wgs84 +no_defs"
        
        if self.resample == 'near':
            self.ResampleAlg = gdal.GRA_NearestNeighbour
        elif self.resample == 'bilinear':
            self.ResampleAlg = gdal.GRA_Bilinear
            
        if self.profile == 'mercator':
            self.mercator = GlobalMercator()
            self.tileswne = self.mercator.TileLatLonBounds
            self.tilewsen_merc = self.mercator.TileBounds
            south, west, north, east = self.tileswne(tx, ty, tz)
            w, s, e, n = self.tilewsen_merc(tx, ty, tz)
            
        raster_url = self.url
        raster_url = raster_url.replace('{$x}', str(tx))
        raster_url = raster_url.replace('{$y}', str(ty2))
        raster_url = raster_url.replace('{$invY}', str(ty2))
        raster_url = raster_url.replace('{$z}', str(tz))
        
        try:
            if major == 2:
                f = StringIO(urllib.urlopen(raster_url).read())
            elif major == 3:
                f = BytesIO(urlopen(raster_url).read())
            im = Image.open(f).convert('RGBA') 
            if major == 2:
                f = StringIO()
            elif major == 3:
                f = BytesIO()
            
            im.save(f, "PNG")
            f.seek(0)
        except:
            im = Image.new('RGBA',(100, 100))
            if major == 2:
                f =StringIO()
            elif major == 3:
                f =BytesIO()
            im.save(f, "PNG")
            f.seek(0)
            return f.read()
             
        content = f.read()
        gdal.FileFromMemBuffer('/vsimem/inmem', content)
        src_ds = gdal.Open('/vsimem/inmem')
        src_srs = osr.SpatialReference()
        src_srs.ImportFromProj4(s_srs)
        src_wkt = src_srs.ExportToWkt()  
        dst_srs = osr.SpatialReference()
        dst_srs.ImportFromProj4(t_srs)
        dst_wkt = dst_srs.ExportToWkt()   

        nx = src_ds.RasterXSize
        ny = src_ds.RasterYSize
        nb = src_ds.RasterCount
       
        gt = [w, (e-w)/nx, 0, n, 0, (s-n)/ny]
        src_ds.SetGeoTransform(gt)
        reproj_ds = gdal.AutoCreateWarpedVRT(src_ds, src_wkt, dst_wkt,self.ResampleAlg,0)
        
        if nb == 1:
            im = self.arrayToImage(reproj_ds.GetRasterBand(1).ReadAsArray())
        elif nb == 3:
            r = self.arrayToImage(reproj_ds.GetRasterBand(1).ReadAsArray())
            g = self.arrayToImage(reproj_ds.GetRasterBand(2).ReadAsArray())
            b = self.arrayToImage(reproj_ds.GetRasterBand(3).ReadAsArray())
            im = Image.merge("RGB", (r,g,b))
        elif nb == 4:
            r = self.arrayToImage(reproj_ds.GetRasterBand(1).ReadAsArray())
            g = self.arrayToImage(reproj_ds.GetRasterBand(2).ReadAsArray())
            b = self.arrayToImage(reproj_ds.GetRasterBand(3).ReadAsArray())
            a = self.arrayToImage(reproj_ds.GetRasterBand(4).ReadAsArray())
            im = Image.merge("RGBA", (r,g,b,a))
        else:
            error('Images must have 1, 3, or 4 bands')
            
        if major == 2:
            f = StringIO()
        elif major == 3:
            f = BytesIO()
        im.save(f, "PNG")
        
        print('Saving image ' + str(time.time()-start) + ' s')
                
        # If specified, save a copy of the cached image  
        if self.cachedir != '':
            print('Saving copy ' + str(time.time()-start) + ' s')
            if not os.path.exists(os.path.dirname(tilefilename)):
                os.makedirs(os.path.dirname(tilefilename))
            im.save(tilefilename, "PNG")
          
        gdal.Unlink('/vsimem/tiffinmem')
        del(src_ds)
        del(reproj_ds)
        
        f.seek(0)
        return f.read()
            
###############################################################################

def generate_tiles(environ, start_response):
    querystring = environ['QUERY_STRING']
    fs = parse_qs(environ['QUERY_STRING'])
    
    response_body = GenerateDynamicTiles(querystring,fs).generate_tiles()
    
    status = '200 OK'
    response_headers = [('Content-Type', 'image/png')]
    
    try: 
        start_response(status, response_headers)
    except:
        dummy = ''

    if major == 2:
        return [response_body]
    elif major == 3:
        return [response_body]
    
