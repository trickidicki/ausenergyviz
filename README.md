ausenergyviz
============

Python and R scripts to download and visualise Australian electricity market data.


Data Import Scripts
-------------------

These are in the python/ folder and require the scipy and netCDF4 packages.
They take a single command-line argument, the path to the data directory. The
script cron.sh demonstrates typical usage.

Data Directory Layout
---------------------

    aemo_data/
        AEMO_GENERATORS.csv: generator metadata used by import_aemo.py and
            the R package

        bom_stations.csv: a list of BoM stations, used by download_bom.py

        bom_recent/
            *.csv - CSV file containing weather observations for each
                city, downloaded from the BoM web site by download_bom.py

        dispatch_5min/
            *.zip - dispatch data downloaded by download_aemo.py containing
                an individual 5-minute data point

        dispatch_daily/
            *.zip - dispatch data downloaded by download_aemo.py containing
                a day of data (from archive folder on AEMO web site)

        dispatch_dvd/
            *.zip - bulk/historical AEMO data, not downloaded by script, but
                read by import_aemo.py when creating a new CDF file

        dispatch_swis/
            *.csv - dispatch data for South West Interconnected System (WA),
                downloaded by download_aemo.py

        pricedemand/
            *.csv - regional price and demand data from AEMO web site,
                downloaded by download_aemo.py

        cdf/
            dispatch.cdf: created by import_aemo.py after processing all
                zip files from AEMO

R Package: ausenergyviz
-----------------------

The ausenergyviz/ folder contains an R package to access the CDF data
downloaded by the Python scripts.

    > library(devtools)
    > install("ausenergyviz", args="--no-multiarch")
    > install.packages("reshape2")
    > install.packages("latticeExtra")
    > install_github("rCharts", "ramnathv")

Shiny Web App
-------------

The webapp/ folder contains a web application written in Shiny to visualise
electricity market data. To launch it, run:

    > library(shiny)
    > runApp("webapp", launch.browser=T)
