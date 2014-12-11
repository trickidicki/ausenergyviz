#!/usr/bin/env python2
#
# import_aemo.py: import AEMO dispatch data into a CDF file.
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
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, see <http://www.gnu.org/licenses/>.

from cStringIO import StringIO
import zipfile
import netCDF4
import numpy
import datetime
import os
import re
import sys
import argparse

def read_generators_csv(path):
    gen_list = []

    # read contents of CSV file
    f = file(path, 'rb')
    text = f.read()
    f.close()

    # deal with broken line endings
    text = text.replace('\r\n', '\n')
    text = text.replace('\r', '\n')
    
    # parse each line, ignoring the first (column headings)
    lines = text.split('\n')[1:]
    for line in lines:
        fields = line.strip().split(',')
        if len(fields) < 17: continue
        id = fields[13]
        # skip stations with no ID
        if id == '-': continue

        # store tuple of (id, region, max power)
        region = fields[2]
        max_power = float(fields[15])
        gen_list.append((id, region, max_power))

    # sort by region and descending power output
    gen_list.sort(key=lambda row: (row[1], -row[2]))

    sys.stderr.write('Read %d generators from %s\n' % (len(gen_list), path))
    
    # return list of IDs only
    return [row[0] for row in gen_list]

class AemoCDF(object):
    STRING_LEN = 64

    def __init__(self, filename):
        dirname = os.path.dirname(filename)
        if len(dirname) > 0 and not os.path.exists(dirname):
            os.makedirs(dirname)

        if os.path.exists(filename):
            self.root = netCDF4.Dataset(filename, 'a')
            new_file = False
        else:
            self.root = netCDF4.Dataset(filename, 'w')
            new_file = True

        if new_file:
            self.root.createDimension('time_5min')
            self.root.createDimension('time_30min')
            self.root.createDimension('time_daily')
            self.root.createDimension('date_field', 3)
            self.root.createDimension('gens')
            self.root.createDimension('string_len', self.STRING_LEN) # ewww bodgy
        self.dim_time_5min = self.root.dimensions['time_5min']
        self.dim_time_30min = self.root.dimensions['time_30min']
        self.dim_time_daily = self.root.dimensions['time_daily']
        self.dim_gens = self.root.dimensions['gens']
        self.dim_str = self.root.dimensions['string_len']

        if new_file:
            self.root.createVariable('start_date', 'i4', ('date_field',))
            self.root.variables['start_date'][:] = [0,0,0]
            self.root.createVariable('dispatch_5min', 'f4', ('time_5min', 'gens'), 
                                     zlib=True, chunksizes=(16, 288))
            self.root.createVariable('dispatch_30min', 'f4', ('time_30min', 'gens'), 
                                     zlib=True, chunksizes=(16, 336))
            self.root.createVariable('dispatch_daily', 'f4', ('time_daily', 'gens'), 
                                     zlib=True, chunksizes=(16, 365))
            self.root.createVariable('dispatch_daily_min', 'f4', ('time_daily', 'gens'), 
                                     zlib=True, chunksizes=(16, 365))
            self.root.createVariable('dispatch_daily_max', 'f4', ('time_daily', 'gens'), 
                                     zlib=True, chunksizes=(16, 365))
            self.root.createVariable('seen', 'i1', ('time_5min',), 
                                     zlib=True, chunksizes=(288,), fill_value=0)
            self.root.createVariable('gen_ids', 'S1', ('gens', 'string_len'))
        self.var_dispatch_5min = self.root.variables['dispatch_5min']
        self.var_dispatch_30min = self.root.variables['dispatch_30min']
        self.var_dispatch_daily = self.root.variables['dispatch_daily']
        self.var_dispatch_daily_min = self.root.variables['dispatch_daily_min']
        self.var_dispatch_daily_max = self.root.variables['dispatch_daily_max']
        self.var_seen = self.root.variables['seen']
        self.var_gen_ids = self.root.variables['gen_ids']

        start_date = self.root.variables['start_date'][:]
        if start_date[0] > 0:
            self.start_date = datetime.datetime(start_date[0], start_date[1], start_date[2], 0, 0, 0)
        else:
            self.start_date = None
        
        self.update_gen_id_dict()
        
        self.dates_changed = set()

        self.sync()

    def sync(self):
        self.root.sync()
    
    def num_rows(self):
        return len(self.dim_time_5min)

    def update_gen_id_dict(self):
        gen_ids = []
        if len(self.dim_gens) > 0:
            gen_ids = netCDF4.chartostring(self.var_gen_ids[:])
        self.gen_id_dict = dict((gen_ids[i], i) for i in range(len(gen_ids)))
    
    def add_generator(self, gen_id):
        if gen_id in self.gen_id_dict: return
        i = len(self.dim_gens)
        self.gen_id_dict[gen_id] = i
        self.var_gen_ids[i,:] = netCDF4.stringtoarr(gen_id, len(self.dim_str))
        for var in [self.var_dispatch_5min, self.var_dispatch_30min,
                    self.var_dispatch_daily, self.var_dispatch_daily_min, self.var_dispatch_daily_max]:
            npoints = var.shape[0]
            var[:,i] = numpy.zeros((npoints, 1))
    
    def add_generators(self, generators):
        for new_gen in generators:
            self.add_generator(new_gen)
        self.sync()
    
    def record_num_for(self, dt, fill_in=False):
        if self.start_date is None:
            if fill_in:
                self.start_date = datetime.datetime(dt.year, dt.month, dt.day, 0, 0, 0)
                self.root.variables['start_date'][:] = [dt.year, dt.month, dt.day]
            else:
                return None
        delta = dt - self.start_date
        if delta < datetime.timedelta(0):
            return None
        record_num = delta.days*24*12 + delta.seconds//300
        return record_num

    def have_row_data(self, dt):
        record_num = self.record_num_for(dt)
        if record_num is None or record_num >= len(self.dim_time_5min):
            return False
        return self.var_seen[record_num] != 0
    
    def have_date_data(self, date):
        dt_start = datetime.datetime(date.year, date.month, date.day, 0, 0, 0)
        first_record = self.record_num_for(dt_start)
        if first_record is None or (first_record + 288) > len(self.dim_time_5min):
            return False
        return sum(self.var_seen[first_record+2:first_record+290]) == 288

    def have_zipfile_data(self, filename):
        date_match = re.search(r'(?i)_([0-9_]+).zip', filename)
        if date_match is None:
            return False
        date_str = date_match.group(1)
        if len(date_str) == 8:
            date = datetime.date(int(date_str[0:4]), int(date_str[4:6]), int(date_str[6:8]))
            return self.have_date_data(date)
        elif len(date_str) >= 12:
            dt = datetime.datetime(int(date_str[0:4]), int(date_str[4:6]), int(date_str[6:8]),
                                   int(date_str[8:10]), int(date_str[10:12]), 0)
            return self.have_row_data(dt)
        return False

    def add_dispatch_row(self, dt, data):
        record_num = self.record_num_for(dt, True)
        if record_num is None:
            print "WARNING: can't add data from before start date"
            return

        for station_id in data.iterkeys():
            if station_id not in self.gen_id_dict:
                print "WARNING: adding station", station_id
                self.add_generator(station_id)
        
        self.dates_changed.add((dt.year, dt.month, dt.day))

        row = numpy.zeros((1,len(self.dim_gens)), 'f')
        for station_id, megawatts in data.iteritems():
            row[0,self.gen_id_dict[station_id]] = megawatts
        self.var_dispatch_5min[record_num,:] = row
        self.var_seen[record_num] = 1

    def update_summary_day(self, year, month, day):
        dt_start = datetime.datetime(year, month, day, 0, 0, 0)
        record_num = self.record_num_for(dt_start)
        record_num_30min = record_num // 6
        record_num_daily = record_num // 288

        # fetch dispatch data for that day
        day_data = self.var_dispatch_5min[record_num:record_num+288,:]
        seen_data = self.var_seen[record_num:record_num+288]
        nseen_day = sum(seen_data)
        if nseen_day < 1:
            return
        print "Processing summary data for %.4d-%.2d-%.2d" % (year,month,day)

        # average daily load
        shape = (1, len(self.dim_gens))
        self.var_dispatch_daily[record_num_daily,:] = \
            numpy.reshape(sum(day_data) / sum(seen_data), shape)
        self.var_dispatch_daily_min[record_num_daily,:] = \
            numpy.reshape(numpy.amin(day_data, 0), shape)
        self.var_dispatch_daily_max[record_num_daily,:] = \
            numpy.reshape(numpy.amax(day_data, 0), shape)

        # average 30 minute periods
        for i in xrange(48):
            start = i*6
            end = (i+1)*6
            nseen = sum(seen_data[start:end])
            if nseen < 1: continue
            self.var_dispatch_30min[record_num_30min + i,:] = \
                numpy.reshape(sum(day_data[start:end,:]) / nseen, shape)

    def update_summaries(self):
        dates = list(self.dates_changed)
        dates.sort()
        for year, month, day in dates:
            self.update_summary_day(year, month, day)
        self.dates_changed = set()

def load_dispatch_csv(file_obj, aemo_cdf):
    dt = None
    data = {}
    for line in file_obj:
        if not line.startswith('D,'): continue
        fields = line.split(',')
        if len(fields) < 7:
            print "WARNING: unexpected number of fields in SCADA dispatch file"
            continue
        if dt is None:
            try:
                dt = datetime.datetime.strptime(fields[4], '"%Y/%m/%d %H:%M:%S"')
            except ValueError:
                print "warning: failed to parse AEMO time"
        station_id = fields[5]
        megawatts = float(fields[6])
        if megawatts > 0:
            data[station_id] = megawatts
    if dt is None: return
    aemo_cdf.add_dispatch_row(dt, data)


def load_dispatch_zip(file_path, aemo_cdf):
    rows = 0
    bigzip = zipfile.ZipFile(file_path, 'r')
    contents = bigzip.namelist()
    contents.sort()
    for f in contents:
        ziptext = StringIO(bigzip.read(f))
        if f.lower().endswith('.zip'):
            if aemo_cdf.have_zipfile_data(f): continue
            rows += load_dispatch_zip(ziptext, aemo_cdf)
        elif f.lower().endswith('.csv'):
            rows += 1
            load_dispatch_csv(ziptext, aemo_cdf)
    bigzip.close()
    return rows


def load_dispatch_zips(zip_dir, aemo_cdf):
    if not os.path.isdir(zip_dir):
        sys.stderr.write('WARNING: zip file directory %s does not exist\n' % zip_dir)
        return

    files = os.listdir(zip_dir)
    files.sort()
    for f in files:
        if not f.lower().endswith('.zip'): continue
        if aemo_cdf.have_zipfile_data(f): continue
        rows = load_dispatch_zip(os.path.join(zip_dir, f), aemo_cdf)
        if rows > 0:
            aemo_cdf.sync()
            print "%s, %d rows" % (f, rows)


def load_dispatch_dvd_csv(file_obj, aemo_cdf):
    cur_timestamp = None
    dt = None
    data = None
    rows = 0
    for line in file_obj:
        fields = line.strip().split(",")
        if len(fields) < 14: continue
        if fields[0] != "D": continue
        timestamp = fields[4]
        station_id = fields[6]
        intervention = int(fields[9])
        megawatts = float(fields[13])
        if timestamp != cur_timestamp:
            if dt is not None:
                aemo_cdf.add_dispatch_row(dt, data)
                rows += 1
            cur_timestamp = timestamp
            dt = datetime.datetime.strptime(timestamp, '"%Y/%m/%d %H:%M:%S"')
            data = {}
        if megawatts > 0:
            if (station_id not in data) or (intervention == 1):
                data[station_id] = megawatts
    if dt is not None:
        aemo_cdf.add_dispatch_row(dt, data)
        rows += 1
    return rows

def load_dispatch_dvd_zip(file_path, aemo_cdf):
    bigzip = zipfile.ZipFile(file_path, 'r')
    contents = bigzip.namelist()
    contents.sort()
    for f in contents:
        if f.lower().endswith('.csv'):
            csv = bigzip.open(f, 'r')
            rows = load_dispatch_dvd_csv(csv, aemo_cdf)
            if rows > 0:
                aemo_cdf.sync()
                print "%s, %d rows" % (f, rows)
            csv.close()
    bigzip.close()

def load_dispatch_dvd_zips(zip_dir, aemo_cdf):
    if not os.path.isdir(zip_dir):
        return
    print "*** Scanning for bulk AEMO data in %s ***" % zip_dir
    files = os.listdir(zip_dir)
    files.sort()
    for f in files:
        fp = os.path.join(zip_dir, f)
        if os.path.isdir(fp):
            load_dispatch_dvd_zips(fp, aemo_cdf)
        elif f.lower().endswith('.zip'):
            load_dispatch_dvd_zip(fp, aemo_cdf)

if __name__ == '__main__':
    # set up argument parser
    parser = argparse.ArgumentParser(description='Import AEMO dispatch and demand data to CDF.')
    parser.add_argument('path_base', metavar='PATH',
            help='base directory to store downloaded data in')
    parser.add_argument('-g', '--generators', metavar='FILE', nargs=1,
            help='path to generators CSV file [default: PATH/AEMO_GENERATORS.csv]')
    parser.add_argument('-c', '--cdf', metavar='FILE', nargs=1,
            help='path to NetCDF file to write [default: PATH/cdf/dispatch.cdf]')

    # parse command line arguments and fill in default parameters
    args = parser.parse_args()
    if args.generators is None:
        args.generators = os.path.join(args.path_base, 'AEMO_GENERATORS.csv')
    if args.cdf is None:
        args.cdf = os.path.join(args.path_base, 'cdf', 'dispatch.cdf')

    # read in generators.csv file
    if os.path.exists(args.generators):
        generators = read_generators_csv(args.generators)
    else:
        generators = []
        sys.stderr.write('WARNING: generator list %s does not exist\n' % args.generators)

    # open (create if necessary) the CDF output file, add in any known
    # generators not yet present in the CDF
    cdf = AemoCDF(args.cdf)
    cdf.add_generators(generators)

    # if the CDF is brand new, look for bulk data from AEMO DVDs
    if cdf.num_rows() == 0:
        load_dispatch_dvd_zips(os.path.join(args.path_base, 'dispatch_dvd'), cdf)

    # read in any daily and 5min dispatch zips we haven't seen yet
    zip_dirs = [os.path.join(args.path_base, 'dispatch_daily'),
                os.path.join(args.path_base, 'dispatch_5min')]
    for dir in zip_dirs:
        load_dispatch_zips(dir, cdf)

    # update daily and 30 min summaries where necessary
    # TODO: add option to recalculate completely?
    cdf.update_summaries()
    cdf.sync()
