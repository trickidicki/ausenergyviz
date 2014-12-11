# server.r: Shiny user interface code for energy visualisation web app
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
library(rCharts)

# List of available states to filter generator data on, and associated abbreviations
state.list <- list("Victoria" = "VIC",
                   "New South Wales" = "NSW",
                   "Queensland" = "QLD",
                   "South Australia" = "SA",
                   "Tasmania" = "TAS")
fuel.list <- list("Coal", "Gas", "Hydro", "Wind", "Other")

shinyUI(fluidPage(
    fluidRow(
        column(9,
               tabsetPanel(
                tabPanel("Static Plot", plotOutput("aemoPlot", height=700)),
                tabPanel("Interactive Plot", showOutput("aemoPlotJS", "nvd3")),
                tabPanel("Top Generators", p("xxx"))
               )),
        column(3,
            h3("Electricity Generation"),
            dateRangeInput("daterange", "Dates to plot:", 
                           start=Sys.Date() - 6, end=Sys.Date(),
                           min="1999-01-01", max=Sys.Date()),
            checkboxGroupInput("split_by", "Seperate plots:",
                           list("State" = "region",
                                "Fuel Type" = "fuel"),
                           "region"),
            checkboxInput("fixed_scale", "All plots have same scale"),
            selectInput("group_by", "Separate lines for:",
                        list("None" = "none",
                             "State" = "region",
                             "Fuel Type" = "fuel"),
                        "fuel"),
            h4("Restrict Data"),
            selectInput("regions", "State:", state.list, multiple=T),
            selectInput("fuels", "Fuel types:", fuel.list, multiple=T),
            h4("Time Scale"),
            selectInput("timescale", "Resolution:", 
                        list("Automatic" = "auto",
                             "5 minutes" = "5min",
                             "30 minutes" = "30min",
                             "Daily average" = "daily",
                             "Weekly average" = "weekly",
                             "Monthly average" = "monthly",
                             "Daily average/min/max" = "daily_minmax",
                             "Weekly average/min/max" = "weekly_minmax",
                             "Monthly average/min/max" = "monthly_minmax"))
        )
    )
))

