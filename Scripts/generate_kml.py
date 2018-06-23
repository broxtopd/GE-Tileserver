# Top level script to either display web tiles or a local gdal-supported dataset in Google Earth.
# This script should be run using a web server.
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

from cgi import parse_qs, escape
import os, sys
import subprocess
from random import randint
import re
import urllib
from osgeo import gdal
from gdalconst import *
import kml_for_tiles
import generate_tiles
from xml.etree import ElementTree
import zipfile

# sys.stderr = open(os.path.abspath(__file__).replace(os.path.basename(__file__),'') + 'logs/generate_kml.txt', 'w')

addr_file = os.path.abspath(__file__).replace(os.path.basename(__file__),'') + '/addr.txt'
with open(addr_file) as f:
    for line in f:
        vals = line.split(' ')
        kmlscriptloc = vals[0] + ':' + vals[1].strip()
        tilescriptloc = vals[0] + ':' + vals[2].strip()    
        transparentpng = tilescriptloc

def generate_kml(environ, start_response):

    querystring = environ['QUERY_STRING']
    
    if querystring == '':
        response_body = ''
        status = '200 OK'
        response_headers = [('Content-Type', 'text/html'),
                  ('Content-Length', str(len(response_body)))]
        start_response(status, response_headers)
        return response_body
    
    fs = parse_qs(environ['QUERY_STRING'])
    url = escape(fs.get('url', [''])[0])
    zoom = escape(fs.get('zoom', [''])[0])
    if zoom == '':
        zoom = '0-31'
    ullr = escape(fs.get('ullr', [''])[0]).replace(' ','_') 
    if ullr == '':
        ullr = '-180_90_180_-89.9'
    zxy = escape(fs.get('zxy', [''])[0])
    
    if 'bgurl=' in querystring:
        bgurl = escape(fs.get('bgurl', [''])[0]) 
    else:
        bgurl = '';
            
    
    # If already a web tile format ({$z},{$x},{$y} are defined), generate kml for the top level tiles for the region defined by ullr in the querystring (if applicable)
    if 'profile' in querystring:
        profile = escape(fs.get('profile', [''])[0])
    else:
        if ('$z' in url) or ('$z' in bgurl):
            profile = 'mercator'
            querystring = querystring + '&profile=mercator;'
        else:
            profile = 'geodetic'
            querystring = querystring + '&profile=geodetic;'
        
    if ('$z' in url) or ('WMS:BBOX' in url):
        webTiles = 1

        # Bypass and enter the kml generation script if being called recursively
        if zxy != '':
            tile_kml = kml_for_tiles.KMLForTiles(kmlscriptloc,tilescriptloc,transparentpng,querystring,fs,zxy,webTiles,profile)
            kml = tile_kml.generate_tiles()
        else:
        # Else if called for the first time, append all children to root kml, and return the result
            tminz, tmaxz = zoom.split('-')
            ulx, uly, lrx, lry = ullr.split('_')
            tminz = int(tminz)
                
            if profile == 'mercator':
                tile_math = kml_for_tiles.GlobalMercator()
                ominx, omaxy = tile_math.LatLonToMeters(float(uly),float(ulx))
                omaxx, ominy = tile_math.LatLonToMeters(float(lry),float(lrx))
                
                # Generate table with min max tile coordinates for all zoomlevels
                tminmax = list(range(0,32))
                for tz in range(0, 32):
                    tminx, tminy = tile_math.MetersToTile( ominx, ominy, tz )
                    tmaxx, tmaxy = tile_math.MetersToTile( omaxx, omaxy, tz )
                    # crop tiles extending world limits (+-180,+-90)
                    tminx, tminy = max(0, tminx), max(0, tminy)
                    tmaxx, tmaxy = min(2**tz-1, tmaxx), min(2**tz-1, tmaxy)
                    tminmax[tz] = (tminx, tminy, tmaxx, tmaxy)
                    
            if profile == 'geodetic':
                tile_math = kml_for_tiles.GlobalGeodetic() # from globalmaptiles.py
                ominx, omaxy = float(ulx), float(uly)
                omaxx, ominy = float(lrx), float(lry)

                # Generate table with min max tile coordinates for all zoomlevels
                tminmax = list(range(0,32))
                for tz in range(0, 32):
                    tminx, tminy = tile_math.LatLonToTile( ominx, ominy, tz )
                    tmaxx, tmaxy = tile_math.LatLonToTile( omaxx, omaxy, tz )
                    # crop tiles extending world limits (+-180,+-90)
                    tminx, tminy = max(0, tminx), max(0, tminy)
                    tmaxx, tmaxy = min(2**(tz+1)-1, tmaxx), min(2**tz-1, tmaxy)
                    tminmax[tz] = (tminx, tminy, tmaxx, tmaxy)
                
            #tminz = min(tminz,13)
            children = []
            xmin, ymin, xmax, ymax = tminmax[tminz]
            for x in range(xmin, xmax+1):
                for y in range(ymin, ymax+1):
                    children.append( [ x, y, tminz ] ) 
                    
            tile_kml = kml_for_tiles.KMLForTiles(kmlscriptloc,tilescriptloc,transparentpng,querystring,fs,'0/0/0',webTiles,profile)
            # Generate Root KML
            kml = tile_kml.generate_kml( None, None, None, children)

    else:
    # Else, open the raster data source, and figure out its extents and appropriate top level zoom

        webTiles = 0
        checkStatus = False

        # Bypass and enter the kml generation script if being called recursively
        if zxy != '':
            tile_kml = kml_for_tiles.KMLForTiles(kmlscriptloc,tilescriptloc,transparentpng,querystring,fs,zxy,webTiles,profile)
            kml = tile_kml.generate_tiles()
        else:
            # Else if called for the first time, get the raster extents (warping if necessary), and then generate root kml structure as above
            gdal.AllRegister()
            
            import tempfile
            tempfilename = tempfile.mktemp('-TileOverlay.vrt')
            
            # In some cases, a special file should be used to open different maps with different zoom levels.  Here, only open the file for the largest zoom levels
            if url.find('.pyr') >= 0:
                file = open(url,'r')
                zoom, raster_url = file.readline().split(',')
                raster_url = raster_url.strip()
                file.close()
            else:
                raster_url = url
            
            # Warp to WGS84 to ensure that dataset bounds are read correctly
            command = 'gdalwarp -t_srs "+proj=latlong +datum=wgs84 +nodefs" -of vrt "' + raster_url + '" ' + tempfilename
            subprocess.call(command, shell=True, stdout=open(os.devnull, 'wb'))
            
            ds = gdal.Open(tempfilename, GA_ReadOnly)
            if ds is None:
                print('Content-Type: text/html\n')
                print('Could not open raster')
                sys.exit(1)
                
            tilesize = 256
            rows = ds.RasterYSize
            cols = ds.RasterXSize
            transform = ds.GetGeoTransform()
            ulx = transform[0]
            uly = transform[3]
            pixelWidth = transform[1]
            pixelHeight = transform[5]
            lrx = ulx + (cols * pixelWidth)
            lry = uly + (rows * pixelHeight)
            
            del ds
            os.unlink(tempfilename)

            uly = min(uly,89.9)
            lry = max(lry,-89.9)
            ulx = max(ulx,-180)
            lrx - min(lrx,180)

            ullr = str(ulx) + '_' + str(uly) + '_' + str(lrx) + '_' + str(lry)
                
            if profile == 'mercator':
                tile_math = kml_for_tiles.GlobalMercator()
                ominx, omaxy = tile_math.LatLonToMeters(float(uly),float(ulx))
                omaxx, ominy = tile_math.LatLonToMeters(float(lry),float(lrx))
                pixelWidth = (omaxx - ominx) / cols
                
                # Generate table with min max tile coordinates for all zoomlevels
                tminmax = list(range(0,32))
                for tz in range(0, 32):
                    tminx, tminy = tile_math.MetersToTile( ominx, ominy, tz )
                    tmaxx, tmaxy = tile_math.MetersToTile( omaxx, omaxy, tz )
                    # crop tiles extending world limits (+-180,+-90)
                    tminx, tminy = max(0, tminx), max(0, tminy)
                    tmaxx, tmaxy = min(2**tz-1, tmaxx), min(2**tz-1, tmaxy)
                    tminmax[tz] = (tminx, tminy, tmaxx, tmaxy)
                    
            if profile == 'geodetic':
                tile_math = kml_for_tiles.GlobalGeodetic() # from globalmaptiles.py
                ominx, omaxy = float(ulx), float(uly)
                omaxx, ominy = float(lrx), float(lry)

                # Generate table with min max tile coordinates for all zoomlevels
                tminmax = list(range(0,32))
                for tz in range(0, 32):
                    tminx, tminy = tile_math.LatLonToTile( ominx, ominy, tz )
                    tmaxx, tmaxy = tile_math.LatLonToTile( omaxx, omaxy, tz )
                    # crop tiles extending world limits (+-180,+-90)
                    tminx, tminy = max(0, tminx), max(0, tminy)
                    tmaxx, tmaxy = min(2**(tz+1)-1, tmaxx), min(2**tz-1, tmaxy)
                    tminmax[tz] = (tminx, tminy, tmaxx, tmaxy)
                
            tminz = tile_math.ZoomForPixelSize( pixelWidth * max( cols, rows) / float(tilesize) )
            
            children = []
            xmin, ymin, xmax, ymax = tminmax[tminz]
            for x in range(xmin, xmax+1):
                for y in range(ymin, ymax+1):
                    children.append( [ x, y, tminz ] ) 
                    
            tile_kml = kml_for_tiles.KMLForTiles(kmlscriptloc,tilescriptloc,transparentpng,querystring,fs,'0/0/0',webTiles,profile)
            # Generate Root KML
            kml = tile_kml.generate_kml( None, None, None, children)
           
    response_body = str(kml)
    status = '200 OK'
    response_headers = [('Content-Type', 'text/xml'),
                  ('Content-Length', str(len(response_body)))]
    try: 
        start_response(status, response_headers)
    except:
        dummy = ''

    (major,minor,micro,releaselevel,serial) = sys.version_info
    if major == 2:
        return [response_body]
    elif major == 3:
        return [response_body.encode('utf-8')]
    

