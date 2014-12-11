#!/usr/bin/env python2
#
# download_bom.py: download recent weather observations from Bureau of Meteorology.
#
# Copyright (c) 2014 Cameron Patrick <cameron@largestprime.net>
#
# This file is part of AusEnergyViz. AusEnergyViz is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, see <http://www.gnu.org/licenses/>.

from cStringIO import StringIO
import urllib2
import re
import os
import sys
import datetime
import argparse
import socket
import shutil

# base URL for BoM observation data
URL_BASE = 'http://www.bom.gov.au/fwo/'
RETRY_LIMIT = 5

def fetch_url(url):
    """Returns the contents of a URL as a string."""
    retry = 0
    while True:
        try:
            response = urllib2.urlopen(url)
            content = response.read()
            break
        except (urllib2.URLError, socket.error) as e:
            retry = retry + 1
            if retry > RETRY_LIMIT:
                sys.stderr.write("***FAILED*** reason: %s\n" % str(e.reason))
                sys.exit(1)
    return content

def read_station_csv(file_path):
    """Read list of BoM stations to download data for."""
    stations = []

    f = file(file_path, 'rb')

    # skip header line
    f.readline()
    for line in f:
        fields = line.strip().split(",")
        if len(fields) < 1: continue
        if len(fields) < 3:
            print "WARNING: line in stations csv has too few fields"
            continue
        stations.append({ 'city': fields[0], 'id': fields[1], 'url': fields[2] })

    f.close()
    return stations

def read_timeseries_csv(file_path):
    """Read a CSV file containing weather timeseries."""
    if not os.path.exists(file_path):
        return []
    f = file(file_path, 'rb')

    # skip header line
    f.readline()

    # read rest of data
    timeseries = []
    for line in f:
        fields = line.strip().split(",")
        if len(fields) < 1: continue
        if len(fields) != 3:
            print "WARNING: line in weather csv has wrong number of fields"
            continue
        fields[0] = fields[0].replace('"', '') # remove quotation marks
        timeseries.append(tuple(fields))

    f.close()
    timeseries.sort()
    return timeseries

def write_timeseries_csv(file_path, timeseries):
    """Write a CSV file containing weather timeseries."""
    f = file(file_path + '.tmp', 'wb')
    f.write('Time,Air Temperature (degrees C),Relative Humidity (%)\n')
    for row in timeseries:
        f.write('"%s",%s,%s\n' % (row[0], row[1], row[2]))
    f.close()
    shutil.move(file_path + '.tmp', file_path)

def merge_timeseries(series1, series2):
    """Merge two sorted timeseries. If duplicate times are present, prefer series2."""
    output = []
    i = 0
    j = 0
    while i < len(series1) or j < len(series2):
        if i < len(series1) and j < len(series2) and series1[i][0] == series2[j][0]:
            output.append(series2[j])
            i += 1
            j += 1
        elif i < len(series1) and series1[i][0] < series2[j][0]:
            output.append(series1[i])
            i += 1
        else:
            output.append(series2[j])
            j += 1
    return output

def parse_bom_csv(file_obj):
    """Parse the CSV-ish format on the BoM web site."""
    FIELD_TIMESTAMP = 5
    FIELD_AIR_TEMP = 7
    FIELD_HUMIDITY = 25

    timeseries = []
    skipping = True # true if processing non-data part of file
    seen_header = False # true after processing header row
    for line in file_obj:
        line = line.strip()
        if skipping:
            if line == "[data]":
                skipping = False
            continue

        fields = line.split(",")
        if len(fields) < 2: continue
        if not seen_header:
            if fields[FIELD_TIMESTAMP] != "local_date_time_full[80]" or \
               fields[FIELD_AIR_TEMP] != "air_temp" or \
               fields[FIELD_HUMIDITY] != "rel_hum":
                print "ERROR: BoM data format has changed. doomed!"
                print line
                sys.exit(1)
            seen_header = True
            continue

        timestamp = fields[FIELD_TIMESTAMP].replace('"', '')
        timestamp = '%s/%s/%s %s:%s' % (timestamp[0:4], timestamp[4:6], timestamp[6:8], timestamp[8:10], timestamp[10:12])
        timeseries.append((timestamp, fields[FIELD_AIR_TEMP], fields[FIELD_HUMIDITY]))

    timeseries.sort()
    return timeseries

def fetch_bom_timeseries(station_url):
    bom_data = fetch_url(station_url)
    return parse_bom_csv(StringIO(bom_data))

if __name__ == '__main__':
    # parse arguments
    parser = argparse.ArgumentParser(description='Download BoM weather observations.')
    parser.add_argument('path_base', metavar='PATH',
            help='base directory to store downloaded data in')
    args = parser.parse_args()

    # determine output directories based on our base path
    path_current = os.path.join(args.path_base, 'bom_recent')
    path_stations = os.path.join(args.path_base, 'bom_stations.csv')
    
    if not os.path.isdir(path_current):
        os.makedirs(path_current)

    station_info = read_station_csv(path_stations)
    print "Read %d stations from %s" % (len(station_info), path_stations)
    for station in station_info:
        path_station_data = os.path.join(path_current, '%s.csv' % station['city'])
        cur_data = read_timeseries_csv(path_station_data)
        new_data = fetch_bom_timeseries(URL_BASE + station['url'])
        all_data = merge_timeseries(cur_data, new_data)
        print "%s: %d existing points, %d new points, %d points after merging" % \
            (station['city'], len(cur_data), len(new_data), len(all_data))
        write_timeseries_csv(path_station_data, all_data)
