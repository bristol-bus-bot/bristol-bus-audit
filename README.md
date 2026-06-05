# WECA bus punctuality audit

An independent, non-commercial monitor of bus punctuality across the West of
England, built from the operators' own public open data and compared against
the published 95% punctuality target.

**Live site:** https://bristol-bus-bot.github.io/bristol-bus-audit/

## What this is

Bus operators across the West of England publish their live vehicle data through
the Bus Open Data Service (BODS), and there is a public 95% punctuality target
for the area. There is no accessible, route-level public scorecard showing
whether that target is being met. This project builds one from the operators'
own open data, to the official definition, so anyone can check.

## What this is not

This project does not claim any operator is breaking the law or withholding
required data. Operators are legally required to publish timetables, vehicle
locations and fares, and they do. Performance figures are not a statutory
publication requirement. These figures are an independent measurement and will
differ from any official operator or regulator measurement, which use different
sampling.

## How it works

A collector polls the operators' public SIRI-VM feeds continuously and matches
each vehicle to a scheduled trip. When a bus passes within 150 m of a timing
point, its lateness against the timetable is recorded. The timetable to measure
against is layered from three open sources (BODS South West GTFS, operators'
own BODS TransXChange, and the Traveline National Dataset) because no single one
is complete. Daily rollups produce the operator, route, area, ward and fleet
figures the site serves. Full detail is in AUDIT_METHODOLOGY.md.

- docs/        the static site (HTML, CSS, JS) and the daily data file
- pipeline/    the collection, rollup and export code
- AUDIT_METHODOLOGY.md   the measurement method and its limitations

## Data and licence

Contains public sector information licensed under the Open Government Licence
v3.0. This service uses information from the Department for Transport's Bus Open
Data Service (BODS). The Department for Transport and its agencies accept no
responsibility for the accuracy, timeliness or completeness of the data.

Not affiliated with, endorsed by, or funded by any bus operator, the West of
England Combined Authority, or any authority.
