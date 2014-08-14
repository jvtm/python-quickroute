"""
Python module for reading QuickRoute files

QuickRoute data is embedded in exported JPEG files,
more specifically in its APP0 section starting with "QuickRoute" string.

All numeric values inside the data structure are little-endian
"""
from math import radians, cos, sin, asin, sqrt
from datetime import datetime, timedelta
import json
import logging
import struct
import sys


def haversine_distance(pos1, pos2, radius=6372000):
    """
    Reference http://stackoverflow.com/q/4913349
    """
    lat1 = radians(pos1['lat'])
    lon1 = radians(pos1['lon'])
    lat2 = radians(pos2['lat'])
    lon2 = radians(pos2['lon'])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))

    return radius * c


def format_dotnet_time(ntime):
    """
    Formats .NET style timestamp to datetime object
    Clears two most significant bits (timezone info?)
    """
    ntime &= ~(2**62 | 2**63)
    return datetime(1, 1, 1) + timedelta(microseconds=ntime/10)


class DateTimeEncoder(json.JSONEncoder):
    """ Replacement JSON encoder supporting datetime and timedelta objects """
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, timedelta):
            return str(obj)
        else:
            return super(DateTimeEncoder, self).default(obj)


def read_app_sections(stream):
    """
    Read APPn sections from JPEG file
    """
    marker = "init"
    while marker:
        marker = stream.read(2)
        if marker == '\xFF\xD8':
            # SOA, start of image. Read next chunk.
            continue
        if len(marker) < 2 or marker[0] != '\xFF':
            # somehow reading got out-of-sync
            #print "OOPS %r %r" % (marker, stream.tell())
            break
        if '\xE0' <= marker[1] <= '\xEF':
            # APPn, size includes the two bytes for len
            csize = struct.unpack('!H', stream.read(2))[0] - 2
            cid = ord(marker[1]) - 0xE0
            cdata = stream.read(csize)
            yield (cid, cdata)
        else:
            # Found first non-app section. so assuming real image data begins
            break


def read_quickroute_section(stream):
    """
    Read QuickRoute data section from JPEG file
    """
    for app, data in read_app_sections(stream):
        if app == 0 and data.startswith('QuickRoute'):
            return data[10:]

QR_TAGS = {
    1: 'Version',
    2: 'MapCornerPositions',
    3: 'ImageCornerPositions',
    4: 'MapLocationAndSizeInPixels',
    5: 'Sessions',
    6: 'Session',
    7: 'Route',
    8: 'Handles',
    9: 'ProjectionOrigin',
    10: 'Laps',
    11: 'SessionInfo',
    12: 'MapReadingInfo',
}

# inside Sessions -> Session -> Route
QR_ATTR_POSITION = 1
QR_ATTR_TIME = 2
QR_ATTR_HEARTRATE = 4
QR_ATTR_ALTITUDE = 8

# lap types
QR_LAP_TYPES = {
    0: 'start',
    1: 'lap',
    2: 'stop',
}


class QuickRouteData(dict):
    """
    """
    def __init__(self, jpeg=None, data=None):
        dict.__init__(self)
        if jpeg:
            with open(jpeg, "rb") as qrtfile:
                data = read_quickroute_section(qrtfile)
        if data:
            self.update(self.read(data))

    def read(self, data):
        """
        Construct internal data from binary data
        """
        ret = {}
        for key, value in self.read_data(data):
            logging.debug("%s: %.1024r", key, value)
            ret[key] = value
        return ret

    def read_data(self, data):
        """
        Reads (tag, datalen, data) blocks from the input string.
        This gets called recursively, since internal data parts
        use similar structure.
        """
        pos = 0
        while pos < len(data):
            tag, tlen = struct.unpack_from("<BI", data, pos)
            pos += 1+4
            tdata = data[pos:pos+tlen]
            pos += tlen
            tname = QR_TAGS.get(tag)
            logging.debug("tag: %s, tag name: %s, bytes: %s", tag, tname, tlen)

            func = getattr(self, '_handle_%s' % tname, None)
            if func:
                value = func(tdata)
            else:
                logging.warning("unhandled section %r %r %r", tag, tname, tlen)
                value = None
            yield tname, value

    def _handle_Version(self, data):
        """
        Read Version info
        - 4x unsigned char
        - join by dots
        """
        value = struct.unpack_from("<4B", data)
        value = ".".join(str(x) for x in value)
        return value

    def _handle_Sessions(self, data):
        """
        Reads Sessions structure:
        - number of sessions
        - tag/data pairs using generic read_data()
        """
        sessions = []
        scount = struct.unpack_from("<I", data)[0]
        logging.debug("reading %d sessions", scount)
        for key, value in self.read_data(data[4:]):
            if key != "Session":
                logging.warning("Found %r inside Sessions", key)
                continue
            sessions.append(value)
        assert len(sessions) == scount
        return sessions

    def _handle_Session(self, data):
        """
        Read (single) Session structure
        Utilizes generic read_data()
        """
        session = {}
        for key, value in self.read_data(data):
            session[key] = value
        return session

    def _handle_Laps(self, data):
        """
        Read Laps structure:
        - number of laps
        - multiple time/type pairs
        """
        laps = []
        lcount = struct.unpack_from("<I", data)[0]
        pos = 4
        for _ in range(lcount):
            ltime, ltype = struct.unpack_from("<QB", data, pos)
            pos += 9
            ltime = format_dotnet_time(ltime)
            ltype = QR_LAP_TYPES.get(ltype, ltype)
            laps.append({"time": ltime, "type": ltype})
        return laps

    def _handle_Route(self, data):
        """
        Read Route data structure
        Route can have multiple Segments
        Each segment has multiple waypoints with various attributes
        """
        route = []
        pos = 0
        attrs, extralen, segcount = struct.unpack_from("<HHI", data, pos)
        pos += 2+2+4
        logging.debug("route: attrs: %r, extralen: %r, segment count: %r", attrs, extralen, segcount)
        for i in range(segcount):
            segment = []
            wpcount = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            logging.debug("segment: %d waypoints", wpcount)
            tstamp = None
            tfirst = None
            for j in range(wpcount):
                waypoint = {}
                if attrs & QR_ATTR_POSITION:
                    coords = self._handle_coord(data[pos:pos+8])
                    waypoint.update(coords)
                    if segment:
                        waypoint['distance'] = segment[-1]['distance'] + haversine_distance(segment[-1], coords)
                    else:
                        waypoint['distance'] = 0
                    pos += 8
                if attrs & QR_ATTR_TIME:
                    ttype = ord(data[pos])
                    pos += 1
                    if ttype == 0:
                        # full date
                        tstamp = format_dotnet_time(struct.unpack_from("<Q", data, pos)[0])
                        pos += 8
                    else:
                        # diff in milisecs
                        tstamp += timedelta(milliseconds=struct.unpack_from("<H", data, pos)[0])
                        pos += 2
                    if tfirst is None:
                        tfirst = tstamp
                    waypoint['time'] = tstamp
                    waypoint['elapsed_time'] = tstamp - tfirst
                if attrs & QR_ATTR_HEARTRATE:
                    waypoint['hr'] = struct.unpack_from("<B", data, pos)[0]
                    pos += 1
                if attrs & QR_ATTR_ALTITUDE:
                    waypoint['alt'] = struct.unpack_from("<H", data, pos)[0]
                    pos += 2
                # extra bits for future proofing?
                pos += extralen
                logging.debug("waypoint: %r", waypoint)
                segment.append(waypoint)
            route.append(segment)
        return route

    def _handle_corners(self, data):
        """
        Read four coordinates for SW, NW, NE, SE corners
        """
        return {
            "SW": self._handle_coord(data[0:8]),
            "NW": self._handle_coord(data[8:16]),
            "NE": self._handle_coord(data[16:24]),
            "SE": self._handle_coord(data[24:32]),
        }
    _handle_ImageCornerPositions = _handle_corners
    _handle_MapCornerPositions = _handle_corners

    def _handle_coord(self, data):
        """
        Read a lon/lat coordinate pair.
        Stored as two uint32 (kind of integer milliseconds)
        """
        lon, lat = struct.unpack_from("<2I", data)
        return {'lat': lat/3600000.0, 'lon': lon/3600000.0}
    _handle_ProjectionOrigin = _handle_coord

    def _handle_Handles(self, data):
        """
        Read Handles

        These are related to adjusting route data to the bitmap image.
        See QuickRoute source code for how to actually use this data.
        """
        handles = []
        pos = 0
        hcount = struct.unpack_from("<I", data, pos)[0]
        logging.debug("reading %d handles", hcount)
        pos += 4
        for i in range(hcount):
            handle = {}
            # 3x3 doubles, not sure what would be the best data structure here, so keeping a simple flattened list for now
            # last row (or column? :) is usually 0.0, 0.0, 1.0
            tmatrix = []
            for j in range(3):
                row = struct.unpack_from("<3d", data, pos)
                tmatrix.append(row)
                pos += 8+8+8
            handle['matrix'] = tmatrix

            # ParametereizedLocation (not sure what it's used for)
            # uint32 + double, first value is "segment index"
            handle['parameterized_location'] = struct.unpack_from("<Id", data, pos)
            pos += 4+8

            # possible sub-pixels, ummhh.. ok.
            handle['pixel_location'] = struct.unpack_from("<dd", data, pos)
            pos += 8+8

            # uint32, type, usually 0?
            handle['type'] = struct.unpack_from("<H", data, pos)[0]
            pos += 2

            handles.append(handle)
        return handles

    def _handle_MapLocationAndSizeInPixels(self, data):
        """
        Read MapLocationAndSizeInPixels structure:
        - x
        - y
        - width
        - height
        """
        return struct.unpack_from("<4H", data)

    def _handle_SessionInfo(self, data):
        """
        Read SessionInfo structure:
        - name (string)
        - club (sting)
        - id (uint32)
        - description (string)
        """
        info = {}
        pos = 0

        # string length + string
        slen = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        info['name'] = data[pos:pos+slen]
        pos += slen

        # string length + string
        slen = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        info['club'] = data[pos:pos+slen]
        pos += slen

        # uint32, usually 0
        info['id'] = struct.unpack_from("<I", data, pos)[0]
        pos += 4

        # string length + string
        slen = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        info['description'] = data[pos:pos+slen]
        pos += slen

        # in case the structure contained more data
        if len(data) > pos:
            logging.warning("%d bytes remaining", len(data)-pos)

        return info


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    logging.basicConfig(level=logging.DEBUG)
    qrt = QuickRouteData(jpeg=argv[0])
    print json.dumps(qrt, sort_keys=True, indent=2, cls=DateTimeEncoder)


if __name__ == '__main__':
    main()
