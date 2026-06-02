# Bristol bus punctuality audit

An independent, non-commercial monitor of First Bristol (FBRI) bus punctuality,
built from the operator''s own public open data.

**Live site:** https://bristol-bus-bot.github.io/bristol-bus-audit/

## What this is

First Bristol publishes its live vehicle data through the Bus Open Data Service
(BODS), and there is a public 95% punctuality target for the area. There is no
accessible, route-level public scorecard showing whether that target is being
met. This project builds one from the operator''s own open data.

## What this is not

This project does not claim First is breaking the law or withholding required
data. Operators are legally required to publish timetables, vehicle locations
and fares, and First does. Performance figures are not a statutory publication
requirement. These figures are an independent measurement and will differ from
any official operator or regulator measurement, which use different sampling.

## How it works

A collector polls First''s public SIRI-VM feed continuously and matches each
vehicle to a scheduled trip. When a bus passes within 150 m of a timing point,
its lateness against the timetable is recorded. Daily rollups produce the route
and network figures the site serves. Full detail is in AUDIT_METHODOLOGY.md.

- docs/        the static site (HTML, CSS, JS) and the daily data file
- pipeline/    the collection, rollup and export code
- AUDIT_METHODOLOGY.md   the measurement method and its limitations

## Data and licence

Contains public sector information licensed under the Open Government Licence
v3.0. This service uses information from the Department for Transport''s Bus Open
Data Service (BODS). The Department for Transport and its agencies accept no
responsibility for the accuracy, timeliness or completeness of the data.

Not affiliated with, endorsed by, or funded by First Bristol, the West of
England Combined Authority, or any operator or authority.
