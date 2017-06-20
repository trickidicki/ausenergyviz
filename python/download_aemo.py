#!/usr/bin/env python2
#
# download_aemo.py: download AEMO dispatch, price and demand data.
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

import urllib3
import re
import os
import sys
import datetime
import argparse
import socket

# base URLs for AEMO/NEM data
URL_DISPATCH_CURRENT = 'http://www.nemweb.com.au/REPORTS/CURRENT/Dispatch_SCADA/'
URL_DISPATCH_ARCHIVE = 'http://www.nemweb.com.au/REPORTS/ARCHIVE/Dispatch_SCADA/'
URL_DISPATCH_SWIS = 'http://data.imowa.com.au/datafiles/facility-scada/'
URL_PRICEDEMAND = 'http://www.nemweb.com.au/mms.GRAPHS/data/'
RETRY_LIMIT = 5

# List of regions (states) for price/demand data. Each state has a start date
# which is the first month for which data is available, and an optional finish
# date which is the last month for which data is available.
STATES_PRICEDEMAND = [
        ('NSW1', (1998, 12), None),
        ('QLD1', (1998, 12), None),
        ('SA1', (1998, 12), None),
        ('SNOWY1', (1998, 12), (2008, 6)),
        ('VIC1', (1998, 12), None),
        ('TAS1', (2005, 5), None)
    ]


def fetch_url(url):
    """Returns the contents of a URL as a string."""
    retry = 0
    while True:
        try:
            http = urllib3.PoolManager()
            response = http.urlopen('GET', url)
            content = response.data
            break
        except (urllib3.exceptions, socket.error) as e:
            retry = retry + 1
            if retry > RETRY_LIMIT:
                sys.stderr.write("***FAILED*** reason: %s\n" % str(e.reason))
                sys.exit(1)
    return content

def extract_regexp_set(page, regexp):
    """Returns an alphabetically sorted list of matches to a regular expression.
    Useful for finding file names in a blob of HTML, for example.
    """
    return sorted(set(re.findall(regexp, page)))

def archived_zip_exists(z, archive_list):
    """Given a 'long' dispatch zip name (for a 5 minute data point), see
    if there is a matching daily archive zip present in the given set.
    """
    date_match = re.search(r'(?i)_([0-9_]+).zip', z)
    if date_match is None:
        return False
    date_str = date_match.group(1)
    archive_file = 'PUBLIC_DISPATCHSCADA_%s.ZIP' % date_str[0:8]
    return archive_file in archive_list

def fetch_aemo_zips(index_url, dir, dir_archive=None):
    """Downloads AEMO dispatch zip files from the AEMO web site. Zip files which
    have already been downloaded are skipped. Zip files containing 5min data
    where we already have the daily archive file are not downloaded, and any
    existing ones are deleted.
    
    Args:
        index_url: the URL of the base directory on the AEMO web site to
            download zip files from
        dir: the path to save dispatch data to
        dir_archive: if present, the path to archived dispatch data so we know
            what 5min data can be skipped or deleted
    """
    sys.stderr.write("%s: " % index_url)
    index_html = fetch_url(index_url)

    zip_list = extract_regexp_set(index_html, r'(?i)PUBLIC_DISPATCHSCADA_[0-9_]+.zip')
    sys.stderr.write("found %d zips.\n" % len(zip_list))

    if not os.path.isdir(dir):
        os.makedirs(dir)

    # make a list of archived/aggregated zips so we can skip duplicates
    if dir_archive is not None:
        archive_list = set(s.upper() for s in os.listdir(dir_archive))
    else:
        archive_list = set()

    existing_list = set(z.upper() for z in os.listdir(dir))

    skipped = 0
    for z in zip_list:
        path = os.path.join(dir, z)

        # skip non-aggregate files if we have the aggregated version
        if archived_zip_exists(z, archive_list):
            skipped += 1
            continue

        # skip files that already exist (case insensitive)
        if z.upper() in existing_list:
            skipped += 1
            continue

        # download from web site
        sys.stderr.write("Downloading: %s " % z)
        zip_content = fetch_url(index_url + z)

        # save to file
        f = file(path, 'wb')
        f.write(zip_content)
        f.close()
        
        sys.stderr.write("[%d bytes]\n" % len(zip_content))
    sys.stderr.write("Skipped %d zips.\n" % skipped)

    # clean old zip files
    for filename in os.listdir(dir):
        if archived_zip_exists(filename, archive_list):
            sys.stderr.write("Deleting:    %s\n" % filename)
            os.unlink(os.path.join(dir, filename))

def fetch_aemo_pricedemand(url, path, state, first, last=None):
    """Download price and demand data from the AEMO web site.
    
    Args:
        url: the base URL of the price/demand CSVs to download
        state: string containing the NEM state or region to download
        first: tuple (year,month) of the first month to download
        last: tuple (year,month) of the last month to download, or None to
            use the current date.
    """
    if last is None:
        today = datetime.date.today()
        last = (today.year, today.month)

    if not os.path.isdir(path):
        os.makedirs(path)
    
    cur = None
    while True:
        # advance to next month
        if cur is None:
            cur = first
        else:
            # increment month
            cur = (cur[0], cur[1] + 1)
            # if month passes 12, increment year
            if cur[1] > 12:
                cur = (cur[0] + 1, 1)
        # have we reached the current month yet?
        if cur >= last:
            break

        # determine name of file to download, skip if it exists
        filename = 'DATA%.4d%.2d_%s.csv' % (cur[0], cur[1], state)
        outfile = os.path.join(path, filename)
        if os.path.exists(outfile):
            continue

        # download from web site
        sys.stderr.write("Downloading: %s ..." % filename)
        csv_content = fetch_url(url + filename)
    
        # save to file
        f = file(outfile, 'wb')
        f.write(csv_content)
        f.close()
        sys.stderr.write(" done\n")

def fetch_swis_dispatch(url, path):
    """Download dispatch data for Western Australia (SWIS)."""

    if not os.path.isdir(path):
        os.makedirs(path)
    existing_list = set(s.lower() for s in os.listdir(path))

    # the most recent CSV file we have might have changed since last download.
    # if any newer CSV files are present, we assume that older ones are up-to-date.
    last_existing = None
    if len(existing_list) > 0:
        last_existing = sorted(existing_list, reverse=True)[0]

    sys.stderr.write("%s: " % url)
    index_html = fetch_url(url)
    csv_list = extract_regexp_set(index_html, r'(?i)facility-scada-[0-9]+-[0-9]+.csv')
    sys.stderr.write("found %d CSVs.\n" % len(csv_list))

    skipped = 0
    for z in csv_list:
        outfile = os.path.join(path, z)

        # skip files that already exist (case insensitive)
        if z.lower() in existing_list and z.lower() != last_existing:
            skipped += 1
            continue

        # download from web site
        sys.stderr.write("Downloading: %s " % z)
        csv_content = fetch_url(url + z)

        # save to file
        f = file(outfile, 'wb')
        f.write(csv_content)
        f.close()
        
        sys.stderr.write("[%d bytes]\n" % len(csv_content))
    sys.stderr.write("Skipped %d CSVs.\n" % skipped)

if __name__ == '__main__':
    # parse arguments
    parser = argparse.ArgumentParser(description='Download AEMO dispatch and demand data.')
    parser.add_argument('path_base', metavar='PATH',
            help='base directory to store downloaded data in')
    args = parser.parse_args()

    # determine output directories based on our base path
    path_archive = os.path.join(args.path_base, 'dispatch_daily')
    path_current = os.path.join(args.path_base, 'dispatch_5min')
    path_pricedemand = os.path.join(args.path_base, 'pricedemand')
    path_swis_dispatch = os.path.join(args.path_base, 'dispatch_swis')
    
    # download dispatch data - first daily archives, then 5 minute current data
    fetch_aemo_zips(URL_DISPATCH_ARCHIVE, path_archive)
    fetch_aemo_zips(URL_DISPATCH_CURRENT, path_current, path_archive)
    
    # download price and demand data
    for state, first, last in STATES_PRICEDEMAND:
        fetch_aemo_pricedemand(URL_PRICEDEMAND, path_pricedemand, state, first, last)

    # download SWIS (IMOWA) dispatch data
    fetch_swis_dispatch(URL_DISPATCH_SWIS, path_swis_dispatch)
