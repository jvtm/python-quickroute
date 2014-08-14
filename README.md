Python QuickRoute
=================

Library for reading [QuickRoute](http://www.matstroeng.se/quickroute) data files in Python.

Contains also utility to convert the data to other formats (eg. to `.gpx` with heart rate info).


Command line utility
--------------------

The command line utliity can dump data from existing QuickRoute JPEG file to following formats:

* plain JSON (mainly for debugging purposes)
* *TODO* GPX (including heart rate info)
* *TODO* KML (for viewing in Google Earth etc)
* *TODO* GeoJSON

Example #1 (my_qrt_file.jpg to out.json):

    python -m quickroute.cli --format json my_qrt_file.jpg > out.json


File format
-----------

QuickRoute saves an additional APP0 section to JPEG file it creates. This section starts with `QuickRoute` string,
followed by the actual binary contents.

Most of the file follows this format:

* tag number (single byte)
* data length (uint32)
* data to decode (tag specific binary contents)

On some parts the parsing is recursive (data contents contain more data in the same format).

_To be documented better, see the source..._


Python representation
---------------------

For now see the command line utility and its JSON output format.

_To be documented and might get reformatted alot._


Links
-----

* [QuickRoute source repository](https://code.google.com/p/quickroute-gps/)
* [QuickRoute website](http://www.matstroeng.se/quickroute)
* [DOMA](http://matstroeng.se/doma/) includes PHP library for reading the same files
* [World of O](http://worldofo.com) has a huge [DOMA map collection](http://omaps.worldofo.com/?cid=2)

