"""Compile station counts into the next public outcome ledger."""

from collections import Counter, defaultdict
from fractions import Fraction

from plans.absorption import hitting_probabilities
from plans.snapshot import PlanOutcome


def build_transfer_rows(revision):
    counts = defaultdict(Counter)
    for row in revision.counts:
        if row.count:
            counts[row.origin][row.destination] += row.count
    transitions = {}
    for station in revision.stations:
        station_counts = counts[station.name]
        total = sum(station_counts.values())
        transitions[station.name] = {
            destination: Fraction(count, total) for destination, count in station_counts.items()
        }

    public = tuple(station.name for station in revision.stations if station.public)
    private_rows = {
        station.name: transitions[station.name]
        for station in revision.stations if not station.public
    }
    exits = {station: station for station in public}
    exits[PlanOutcome.RELEASE] = revision.release
    exits[PlanOutcome.REJECT] = revision.reject
    zero = Fraction(0)
    ledger = {station: {} for station in public}
    for column, destination in exits.items():
        indirect = hitting_probabilities(private_rows, destination)
        for station in public:
            outgoing = transitions[station]
            ledger[station][column] = outgoing.get(destination, zero) + sum(
                weight * indirect.get(next_state, zero)
                for next_state, weight in outgoing.items()
            )
    for row in ledger.values():
        row[PlanOutcome.NEVER] = Fraction(1) - sum(row.values())
    return ledger
