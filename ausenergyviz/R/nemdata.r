# nemdata.r: 
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

# all NEM data is stored in Queensland time, i.e. east coast
# without daylight savings
nemdata_timezone <- "Australia/Brisbane"

nemdata_open <-
function(base_path) {
    self <- list(base_path = base_path)
    class(self) <- "nemdata"
    self$dispatch_cdf <- paste(base_path, "/cdf/dispatch.cdf", sep="")
    self$generator_csv <- paste(base_path, "/AEMO_GENERATORS.csv", sep="")
    self$timescales <- list()
    self$timescales[["5min"]] <- as.difftime(5, units="mins")
    self$timescales[["30min"]] <- as.difftime(30, units="mins")
    self$timescales[["daily"]] <- as.difftime(1, units="days")
    self <- nemdata_fetch_info(self)
    self
}

interpret_fuel <-
function(ft) {
#    if (ft == "Kerosene" || ft == "Diesel")
#        return ("Diesel")
#    else if (ft == "Brown Coal")
#        return ("Brown Coal")
#    else if (ft == "Black Coal" || ft == "Coal Tailings")
#        return ("Black Coal")
    if (any(grep(ft, "^Natural Gas")) || ft == "Coal Seam Methane")
        return ("Gas")
    else if (ft == "Black Coal" || ft == "Brown Coal" || ft == "Coal Tailings")
        return ("Coal")
    else if (ft == "Water")
        return ("Hydro")
    else if (ft == "Wind")
        return ("Wind")
    else
        return ("Other")
}

nemdata_fetch_info <-
function(self) {
    nc <- nc_open(self$dispatch_cdf)
    self$num_gens <- nc$dim$gens$len
    self$rows <- list()
    for (scale in names(self$timescales)) {
        dim <- nc$dim[[paste("time_", scale, sep="")]]
        self$rows[[scale]] <- dim$len
    }
    start_date <- ncvar_get(nc, "start_date")
    generator_ids <- ncvar_get(nc, "gen_ids")
    nc_close(nc)

    self$start_date <- ISOdatetime(start_date[1], start_date[2], 
                                   start_date[3], 0, 0, 0, tz=nemdata_timezone)
    self$finish_date <- nemdata_time_for_record_num(self, self$rows[["5min"]])
    self$generator_ids <- data.frame(seq(1, length(generator_ids)))
    rownames(self$generator_ids) <- generator_ids
    
    gen_csv <- read.csv(self$generator_csv)
    gen_csv <- gen_csv[gen_csv$DUID != "-",]
    gen_csv$DUID <- factor(gen_csv$DUID)
    levels(gen_csv$Region) <- sub("1$", "", levels(gen_csv$Region))
    levels(gen_csv$Fuel.Source...Descriptor) <- sapply(
        levels(gen_csv$Fuel.Source...Descriptor), interpret_fuel)
    fuel_levels <- c("Coal", "Gas", "Hydro", "Wind", "Other")
    region_levels <- c("VIC", "NSW", "QLD", "SA", "TAS")
    self$generator_info <- data.table(
        id = gen_csv$DUID,
        region = ordered(gen_csv$Region, levels=region_levels),
        fuel = ordered(gen_csv$Fuel.Source...Descriptor, levels=fuel_levels),
        capacity = gen_csv$Max.Cap..MW.)
    row.names(self$generator_info) <- self$generator_info$id
    
    self
}

nemdata_record_num_for_time <-
function(self, datetime, timescale="5min") {
    timedelta <- datetime - self$start_date
    return (1 + round(as.numeric(timedelta, units="mins") / as.numeric(self$timescales[[timescale]], units="mins")))
}

nemdata_time_for_record_num <-
function(self, record_num, timescale="5min") {
    timedelta <- (record_num - 1) * self$timescales[[timescale]]
    return (self$start_date + timedelta)
}

clamp <- function(x, lower, higher) {
    max(min(x, higher), lower)
}

dateToDateTime <-
function(dt, hour, min, sec, tz=NULL) {
    ISOdatetime(year(dt), month(dt), mday(dt), hour, min, sec, tz=tz)
}

nemdata_fetch_dispatch <-
function(self, generator_ids, dt_start, dt_finish, timescale="5min") {
    if (is.null(generator_ids)) {
        generator_ids <- self$generator_info$id
    }
    if (class(dt_start) == "Date") {
        dt_start <- dateToDateTime(dt_start, 0, 0, 0, tz=nemdata_timezone)
    }
    if (class(dt_finish) == "Date") {
        dt_finish <- dateToDateTime(dt_finish, 23, 55, 0, tz=nemdata_timezone)
    }
    start <- clamp(nemdata_record_num_for_time(self, dt_start, timescale), 1, self$rows[[timescale]])
    finish <- clamp(nemdata_record_num_for_time(self, dt_finish, timescale), 1, self$rows[[timescale]])
    dt_start <- nemdata_time_for_record_num(self, start, timescale)
    dt_finish <- nemdata_time_for_record_num(self, finish, timescale)
    npoints <- finish - start + 1
    if (npoints < 2 || length(generator_ids) < 1) {
        return (NULL)
    }
    time <- seq(dt_start, dt_finish, self$timescales[[timescale]])
    if (is.null(generator_ids)) generator_ids <- row.names(self$generator_ids)
    df <- matrix(nrow=npoints, ncol=length(generator_ids))
    colnames(df) <- generator_ids
    
    nc <- nc_open(self$dispatch_cdf)
    coldata <- ncvar_get(nc, paste("dispatch_", timescale, sep=""), 
                           start=c(1, start), count=c(self$num_gens, npoints))
    nc_close(nc)
    
    for (gen_id in generator_ids) {
        gen_num <- self$generator_ids[gen_id,]
        df[,gen_id] <- coldata[gen_num,]
    }
    df <- data.table(time=time, df, check.names=FALSE)
    df
}

nemdata_generators_by_state <-
function(self, state) {
    self$generator_info$id[self$generator_info$region == state]
}

nemdata_generators_by_fuel <-
function(self, fuel) {
    self$generator_info$id[self$generator_info$fuel == fuel]
}
