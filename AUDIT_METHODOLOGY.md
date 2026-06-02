# Bristol bus punctuality audit: methodology

An independent measurement of First Bristol (operator code FBRI) punctuality,
built only from First's own public open data and compared against the published
95% punctuality target. This page sets out exactly how the figures are produced
and where they can be wrong.

## Data sources

Two public feeds, both from the Department for Transport's Bus Open Data Service
(BODS):

- SIRI-VM real-time vehicle positions for FBRI, polled continuously.
- The GTFS timetable in force on the day, used as the schedule to measure against.

Nothing is bought, scraped from behind a login, or supplied privately by the
operator. Anyone with a free BODS key can pull the same data.

## Matching a vehicle to a scheduled trip

First's SIRI feed labels each vehicle with a DatedVehicleJourneyRef that is the
scheduled start time (HHMM), not a unique journey ID. So a live bus is matched to
a timetabled trip by four things together: route, direction, first-stop departure
time (within 10 minutes), and the calendar day's service pattern. This is a fuzzy
match, not a guaranteed one. Where a confident match cannot be made, the reading
is dropped, not guessed.

## Where delay is measured

Delay is recorded at timing points, the registered points the punctuality
standard is based on, not at every stop. For each timing point on each day we
keep the single reading where the bus passed physically closest to it, by GPS
distance. Only readings taken within 150 metres of the timing point count towards
the published figure; readings further out are stored but excluded. We report how
many were excluded and the median distance of those kept, so the gate is visible
rather than hidden. There is no interpolation and no assumed speed: every figure
is a real recorded position.

## On-time definition

A departure counts as on time if it is between 1 minute early and 5 minutes 59
seconds late (delay between -60 and +359 seconds). This is the Department for
Transport's statistical "on time" band, chosen because it matches the convention
behind the official published figures, so this number is comparable to what DfT
and the West of England Combined Authority report. The target is 95% on time, the
figure adopted in the West of England Bus Service Improvement Plan and in the
Traffic Commissioner's window of tolerance.

## Coverage

Coverage is the share of scheduled trips we actually observed running on the
feed. It is a rough indicator only. A trip we did not see is not proof of a
cancellation: it may be a vehicle that was not broadcasting, a GPS dropout, or a
match we could not make. Coverage is reported as context, never as a count of
cancelled services.

## Honest limitations

- A bus missing from the feed is not the same as a bus that did not run.
- Positions are sampled roughly every 30 seconds, so the closest-approach reading
  is within a few seconds of the truth, not exact.
- The match is fuzzy, so some trips are unmatched and excluded.
- We measure at timing points only, which is the official basis, not at every stop.
- Early days carry small samples, so per-route figures can swing until enough days
  accumulate. Low-sample routes are flagged on the site.

## What this is not

First publishes the timetable, vehicle-location and fares data it is legally
required to publish under the Bus Services Act 2017 and the 2020 Open Data
Regulations. Performance figures are not on that list, so this audit does not
claim First is breaking any publication duty. The point is narrower and factual:
a public 95% target exists, the data to measure against it is free and open, but
no accessible, ongoing, route-level public record of actual performance exists.
This fills that gap. These figures are an independent estimate built to the
official definition, not the official figures themselves, and will differ from
any operator or regulator measurement that uses different sampling.

## Sources

- Bus open data policy, GOV.UK: https://www.gov.uk/government/collections/bus-open-data-service
- BODS operator requirements: https://publish.bus-data.dft.gov.uk/guidance/operator-requirements/
- Senior Traffic Commissioner, Statutory Document No. 14: https://www.gov.uk/government/publications/traffic-commissioners-local-bus-services-in-england-outside-london-and-wales-november-2018
- DfT, Proportion of bus services running on time: https://www.gov.uk/government/publications/proportion-of-bus-services-running-on-time
- West of England Bus Service Improvement Plan (2024): https://www.westofengland-ca.gov.uk/wp-content/uploads/2024/07/3882.Bus-Service-Plan-2024_v2-1.pdf
