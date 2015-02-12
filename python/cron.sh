#! /bin/sh

ADDRESS="cameron@largestprime.net"

set -e

cd ~/aemo_code/python

if ! python download_aemo.py ~/aemo_data >download_log.txt 2>&1; then
    mail -s "AEMO download failed" $ADDRESS < download_log.txt
fi
if ! python import_aemo.py ~/aemo_data >import_log.txt 2>&1; then
    mail -s "AEMO import failed" $ADDRESS < import_log.txt
fi
if ! python download_bom.py ~/aemo_data >download_bom_log.txt 2>&1; then
    mail -s "BoM download failed" $ADDRESS < download_bom_log.txt
fi

