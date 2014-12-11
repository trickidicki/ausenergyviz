# server.r: Shiny server code for energy visualisation web app
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

library(shiny)
library(reshape2)
library(lattice)
library(latticeExtra)
library(rCharts)
library(data.table)
library(ausenergyviz)

nd <- nemdata_open(AEMO_DATA_DIR)

fuel_palette <- c("#85511D", "#D4DE18", "#11BA2A", "#548BB3", "#C55DE8")
state_palette <- brewer.pal(8, 'Dark2')
aggregate_palette <- c("#103090", "#c0c2d0")


##
prepanel.zeromin <- function(x, y, ...) {
    if (length(y) == 0 || max(y) == 0.0)
       list(ylim=c(0, 0.1))
    else
       list(ylim=c(0, max(y)))
}


### stacked area plot code from https://github.com/oscarperpinan/spacetime-vis/
## Copyright (C) 2013-2012 Oscar Perpiñán Lamigueiro
## licensed under GPL v2
panel.flow <- function(x, y, subscripts, groups, origin, ...){
    groups <- groups[subscripts]
    dat <- data.frame(x=x, y=y, groups=groups)
    nVars <- nlevels(groups)
    groupLevels <- levels(groups)

    ## From long to wide
    yWide <- unstack(dat, y~groups)
    yWide <- as.data.frame(lapply(yWide, function(c) if(is.null(c)) 0 else c))

    ##Origin calculated following Havr.eHetzler.ea2002
    if (origin=='themeRiver') origin= -1/2*rowSums(yWide)
    else origin=0 
    yWide <- cbind(origin=origin, yWide)
    ## Cumulative sums to define the polygon
    yCumSum <- t(apply(yWide, 1, cumsum))
    Y <- as.data.frame(sapply(seq_len(nVars),
                              function(iCol)c(yCumSum[,iCol+1],
                                              rev(yCumSum[,iCol]))))
    names(Y) <- levels(groups)
    ## Back to long format, since xyplot works that way
    y <- stack(Y)$values

    ## Similar but easier for x
    xWide <- unstack(dat, x~groups)
    xWide <- as.data.frame(xWide[!sapply(xWide, is.null)])
    x <- rep(c(xWide[,1], rev(xWide[,1])), nVars)
    ## Groups repeated twice (upper and lower limits of the polygon)
    groups <- ordered(rep(levels(groups), each=nrow(Y)), levels=levels(groups))
      
    ## Graphical parameters
    superpose.polygon <- trellis.par.get("superpose.polygon")
    col = superpose.polygon$col
    border = superpose.polygon$border 
    lwd = superpose.polygon$lwd

    ## Draw polygons
    for (i in seq_len(nVars)){
        xi <- x[groups==groupLevels[i]]
        yi <- y[groups==groupLevels[i]]
        panel.polygon(xi, yi, border=border,
                      lwd=lwd, col=col[i])
    }
}

prepanel.flow <- function(x, y, subscripts, groups, origin, ...){
    groups <- groups[subscripts]
    dat <- data.frame(x=x, y=y, groups=groups)
    nVars <- nlevels(groups)
    groupLevels <- levels(groups)
    yWide <- unstack(dat, y~groups)
    yWide <- as.data.frame(lapply(yWide, function(c) if(is.null(c)) 0 else c))
    if (origin=='themeRiver') origin= -1/2*rowSums(yWide)
    else origin=0
    yWide <- cbind(origin=origin, yWide)
    yCumSum <- t(apply(yWide, 1, cumsum))

    list(xlim=range(x),
         ylim=c(min(yCumSum[,1]), max(yCumSum[,nVars+1])),
         dx=diff(x),
         dy=diff(c(yCumSum[,-1])))
}
##### end stacked area code

## trellis panel function to draw a line with a shaded region showing
## minimum and maximum
panel.errbars <- function(x, y, subscripts, groups, type, ...) {
    groups <- groups[subscripts]
    dat <- data.frame(x=x, y=y, groups=groups)

    ## From long to wide
    yWide <- unstack(dat, y~groups)
    yPoly <- c(yWide$min, rev(yWide$max))
    yLine <- yWide$mean

    ## Similar but easier for x
    xWide <- unstack(dat, x~groups)
    xPoly <- c(xWide[,1], rev(xWide[,1]))
    xLine <- xWide[,1]
      
    ## Graphical parameters
    superpose.line <- trellis.par.get("superpose.line")
    col <- superpose.line$col
    lwd <- superpose.line$lwd
    superpose.symbol <- trellis.par.get("superpose.symbol")
    pch <- superpose.symbol$pch

    ## Draw polygon for min/max bounds
    panel.polygon(xPoly, yPoly, border=NA, col=col[2])

    ## Draw lines and points
    if (type == "l" || type == "b") {
        panel.lines(xLine, yLine, lwd=lwd, col=col[1])
    }
    if (type == "p" || type == "b") {
        panel.points(xLine, yLine, lwd=lwd, pch=pch, col=col[1])
    }
}


shinyServer(function(input, output) {

    # determine a list of generators required, according to the user's selections
    generatorList <- reactive({
        gens <- nd$generator_info
        if (length(input$regions) > 0) {
            gens <- gens[region %in% input$regions]
        }
        if (length(input$fuels) > 0) {
            gens <- gens[fuel %in% input$fuels]
        }
        return(gens)
    })

    # returns a list containing information about the time range
    # and time resolution required
    timeInfo <- reactive({
        start_date <- input$daterange[1]
        finish_date <- input$daterange[2]
        timespan <- finish_date - start_date + 1

        timescale <- input$timescale
        if (timescale == "auto") {
            if (timespan <= as.difftime(3, units="days")) {
                timescale <- "5min"
            } else if (timespan <= as.difftime(27, units="days")) {
                timescale <- "30min"
            } else {
                timescale <- "daily"
            }
        }
        aggregate_range <- FALSE
        aggregate_timescale <- NULL
        if (timescale == "daily_minmax") {
            timescale <- "30min"
            aggregate_timescale <- "days"
            aggregate_range <- TRUE
        }
        else if (timescale == "weekly") {
            timescale <- "daily"
            aggregate_timescale <- "weeks"
            aggregate_range <- FALSE
        }
        else if (timescale == "weekly_minmax") {
            timescale <- "30min"
            aggregate_timescale <- "weeks"
            aggregate_range <- TRUE
        }
        else if (timescale == "monthly") {
            timescale <- "daily"
            aggregate_timescale <- "months"
            aggregate_range <- FALSE
        }
        else if (timescale == "monthly_minmax") {
            timescale <- "30min"
            aggregate_timescale <- "months"
            aggregate_range <- TRUE
        }

        list(start = start_date, finish = finish_date,
             timescale = timescale, aggregate_timescale = aggregate_timescale,
             aggregate_range = aggregate_range)
    })

    groupBy <- reactive({
        if (timeInfo()$aggregate_range) {
            group_by <- "agg"
        } else if (input$group_by != "none") {
            group_by <- input$group_by
        } else {
            group_by <- NULL
        }

        for (sb in input$split_by) {
            if (!is.null(group_by) && group_by == sb) {
                group_by <- NULL
            }
        }

        return(group_by)
    })

    rawDispatchData <- reactive({
        time_info <- timeInfo()
        nemdata_fetch_dispatch(nd, NULL, time_info$start, time_info$finish, time_info$timescale)
    })

    cookedDispatchData <- reactive({
        gens <- generatorList()
        time_info <- timeInfo()
        group_by <- groupBy()
        df <- rawDispatchData()
        if (is.null(df)) {
            return(NULL)
        }

        df <- df[, list(id=names(.SD), output=unlist(.SD, use.names=F)), by=time]
        df <- merge(df, gens, by="id")
        df <- df[,list(output=sum(output)),by=c("time", input$split_by, if(time_info$aggregate_range) NULL else group_by)]
        if (!is.null(time_info$aggregate_timescale)) {
            df$time <- as.POSIXct(cut(df$time, time_info$aggregate_timescale))
            if (time_info$aggregate_range) {
                df <- df[,list(agg=c("mean", "min", "max"),
                               output=c(mean(output), min(output), max(output))),
                         by=c("time", input$split_by)]
                df$agg <- ordered(df$agg, levels=c("mean", "min", "max"))
            } else {
                df <- df[,list(output=mean(output)),
                         by=c("time", input$split_by, group_by)]
            }
        }
        df$output <- df$output / 1000
        return(data.frame(df))
    })

    output$aemoPlot <- renderPlot({
        time_info <- timeInfo()
        df <- cookedDispatchData()
        if (is.null(df)) return(NULL)
        
        formula_str <- "output ~ time"
        if (length(input$split_by) > 0) {
            formula_str <- paste(formula_str, "|",
                                 paste0(input$split_by, collapse=" * "))
        }

        group_by <- groupBy()
        if (is.null(group_by))
            palette <- "#000000"
        else if (group_by == "region")
            palette <- state_palette
        else if (group_by == "agg")
            palette <- aggregate_palette
        else
            palette <- fuel_palette
        group_col <- if(!is.null(group_by)) df[,group_by] else NULL

        factor_len <- 1
        for (f in input$split_by) {
            factor_len <- factor_len * length(levels(df[,f]))
        }
        if (!is.null(group_col)) {
            factor_len <- factor_len * length(levels(group_col))
        }

        type_str <- if((nrow(df)/factor_len) > 100) "l" else "b"
        scale_rel <- if(input$fixed_scale) "same" else "free"

        prepanel_fn <- prepanel.zeromin;
        if (!is.null(group_col) && group_by != "agg") {
            prepanel_fn <- prepanel.flow;
            panel_fn <- panel.flow;
        } else if (!is.null(group_by) && group_by == "agg") {
            panel_fn <- panel.errbars;
        } else {
            panel_fn <- panel.xyplot;
        }

        parset = list(
            plot.line=list(lwd=2, col=palette),
            superpose.line=list(lwd=2, col=palette),
            plot.symbol=list(pch=19, col=palette),
            superpose.symbol=list(pch=19, col=palette),
            superpose.polygon=list(col=palette)
        )
        xyplot(x=as.formula(formula_str), data=df,
               type=type_str,
               scales=list(relation=scale_rel, col=1, axs="i"),
               groups=group_col,
               key=if (!is.null(group_col) && group_by != "agg")
                    list(text=list(levels(group_col)),
                        columns=nlevels(group_col),
                        lines=list(lwd=2, col=palette[1:nlevels(group_col)]))
                   else NULL,
               par.settings=parset,
               prepanel=prepanel_fn,
               panel=panel_fn,
               origin=0,
               ylab="Generator Output (GW)", xlab="Time",
               as.table=T
        )
    })

    output$aemoPlotJS <- renderChart2({
        gens <- generatorList()
        time_info <- timeInfo()
        df <- cookedDispatchData()
        if (is.null(df)) return(NULL)

        chart <- nPlot(output ~ time, data=df,
                       type="stackedAreaChart", group=groupBy())
        time_format = "%d/%m/%Y"
        chart$xAxis(axisLabel = "Time",
                    tickFormat = paste("#! function(d) {return d3.time.format('", time_format, "')(new Date(d*1000));} !#", sep=""))
        chart$yAxis(axisLabel = "Generator Output (GW)") #, axisLabelDistance=40)
        chart$chart(useInteractiveGuideline=T) # , margin="{ right: 100 }")
        chart$params$width <- 1000
        chart$params$height <- 800
        return(chart)
    })
})
