# Script to create a kml file from an map source xml file
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

import sys
import os
import xml.etree.ElementTree as ET
import urllib

MapSourceXMLFile = sys.argv[1]
OutputFile = sys.argv[2]

OutputPath,kmlfile = os.path.split(OutputFile)

addr_file = os.path.abspath(__file__).replace(os.path.basename(__file__),'') + '/Scripts/addr.txt'
with open(addr_file) as f:
    for line in f:
        vals = line.split(' ')
        mapping_script_url = vals[0] + ':' + vals[1].strip()

def add_screen_overlay_dynamic(kml_path,image_path):

    f = open(kml_path)
    kml_str = f.read()
    f.close()


    kml_rep = '''<ScreenOverlay>
        <Icon>
          <href>%s</href>
        </Icon>
        <overlayXY x="0" y="0.05" xunits="fraction" yunits="fraction"/>
        <screenXY x="0" y="0.05" xunits="fraction" yunits="fraction"/>
        <rotationXY x="0" y="0" xunits="fraction" yunits="fraction"/>
        <size x="0" y="0" xunits="fraction" yunits="fraction"/>
    </ScreenOverlay>
    </Document>''' %(image_path)

    kml_str = kml_str.replace('</Document>',kml_rep)

    fid_out = open(kml_path,'w')
    fid_out.write(kml_str);
    fid_out.close()
    
def generate_network_link(href_url,Name,visibility,LegendURL):
    # Get legend code from add_screen_overlay_dynamic in Mapping Scripts
    kml_str = """\n<Folder>
    	<name>%s</name>""" % (Name)
    kml_str += """\n<NetworkLink>
	<name>%s</name>
	<visibility>%d</visibility>
	<Link>
		<href>%s</href>
	</Link>
</NetworkLink>""" % (Name, visibility,href_url)

    if not LegendURL == "":
        kml_str += """\n<ScreenOverlay>
        <visibility>%d</visibility>
        <Icon>
            <href>%s</href>
        </Icon>
        <overlayXY x="0" y="0.98" xunits="fraction" yunits="fraction"/>
        <screenXY x="0" y="0.98" xunits="fraction" yunits="fraction"/>
        <rotationXY x="0" y="0" xunits="fraction" yunits="fraction"/>
        <size x="0" y="0" xunits="fraction" yunits="fraction"/>
    </ScreenOverlay>""" % (visibility,LegendURL)

    kml_str += """\n</Folder>"""
    return kml_str

kmlfilename = OutputPath + '/' + kmlfile

kml_str = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2" xmlns:kml="http://www.opengis.net/kml/2.2" xmlns:atom="http://www.w3.org/2005/Atom">
<Folder>
	<name>%s</name>
        <Style>
		<ListStyle>
			<listItemType>radioFolder</listItemType>
			<bgColor>00ffffff</bgColor>
			<maxSnippetLines>2</maxSnippetLines>
		</ListStyle>
	</Style>""" % (kmlfile.replace('.kml',''))

tree = ET.parse(MapSourceXMLFile)
root = tree.getroot()

for folder in root.findall('folder'):
    name = folder.attrib['name']
    type = folder.attrib['type']
    kml_str += """<Folder>
	<name>%s</name>""" % (name)
    if type == 'radio':
        kml_str += """        <Style>
		<ListStyle>
			<listItemType>radioFolder</listItemType>
		</ListStyle>
	</Style>"""

    for mapSource in folder.findall('customMapSource'):
        mapSourceName = mapSource.find('name').text
        QueryString = 'url=' + urllib.quote(mapSource.find('url').text, '') + ';'
        if mapSource.find('minZoom') is not None:
            QueryString = QueryString + '&amp;zoom=' + mapSource.find('minZoom').text + '-' + mapSource.find('maxZoom').text + ';'
        if mapSource.find('minX') is not None:
            QueryString = QueryString + '&amp;ullr=' + mapSource.find('minX').text + '_' + mapSource.find('maxY').text + '_' + mapSource.find('maxX').text + '_' + mapSource.find('minY').text + ';'
        if mapSource.find('serverparts') is not None:
            QueryString = QueryString + '&amp;serverparts=' + mapSource.find('serverparts').text.replace(' ','_') + ';'
        if mapSource.find('legend') is not None:
            LegendURL = mapSource.find('legend').text
        else:
            LegendURL = ""
        kml_str = kml_str + generate_network_link(mapping_script_url + '?' + QueryString, mapSourceName, 0, LegendURL)

    kml_str = kml_str + '\n</Folder>'

for mapSource in root.findall('customMapSource'):
    mapSourceName = mapSource.find('name').text
    QueryString = 'url=' + urllib.quote(mapSource.find('url').text, '') + ';'
    if mapSource.find('minZoom') is not None:
        QueryString = QueryString + '&amp;zoom=' + mapSource.find('minZoom').text + '-' + mapSource.find('maxZoom').text + ';'
    if mapSource.find('minX') is not None:
        QueryString = QueryString + '&amp;ullr=' + mapSource.find('minX').text + '_' + mapSource.find('maxY').text + '_' + mapSource.find('maxX').text + '_' + mapSource.find('minY').text + ';'
    if mapSource.find('serverparts') is not None:
        QueryString = QueryString + '&amp;serverparts=' + mapSource.find('serverparts').text.replace(' ','_') + ';'
    if mapSource.find('legend') is not None:
        LegendURL = mapSource.find('legend').text
    else:
        LegendURL = ""
    kml_str = kml_str + generate_network_link(mapping_script_url + '?' + QueryString, mapSourceName, 0, LegendURL)
        
kml_str = kml_str + '\n</Folder></kml>'
fid_out = open(kmlfilename,'w')
fid_out.write(kml_str);
fid_out.close()
print('Created ' + kmlfilename + ' (Make sure that a python webserver is running.')

