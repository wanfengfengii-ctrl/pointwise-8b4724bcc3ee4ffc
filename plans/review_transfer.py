"""Compile labeled source counts into V2 joint outcome/phase transfer rows.

Private processing keeps its original transfer interpretation: every private
hop is resolved until the flow first reaches a public station, a terminal, or
never returns to anything observable. Review labels on public and private
stations are applied exactly once per actual arrival; a departure never
re-processes the label of the station being left.
"""

from collections import Counter, defaultdict
from fractions import Fraction

from plans.absorption import absorption_distributions
from plans.review_snapshot import PHASES, review_outcome_keys
from plans.snapshot import PlanOutcome


def apply_label(phase, label):
    if label == 'recheck':
        return max(phase, 1)
    if label == 'witness':
        return 2 if phase in (1, 2) else phase
    if label == 'reset':
        return 0
    return phase


def _normalized_outgoing(revision):
    counts = defaultdict(Counter)
    for row in revision.counts:
        if row.count:
            counts[row.origin][row.destination] += row.count
    outgoing = {}
    for station in revision.stations:
        total = sum(counts[station.name].values())
        outgoing[station.name] = {
            destination: Fraction(count, total)
            for destination, count in counts[station.name].items()
        }
    return outgoing


def build_review_rows(revision):
    labels = dict(revision.labels)
    outgoing = _normalized_outgoing(revision)
    public = tuple(station.name for station in revision.stations if station.public)
    private = tuple(station.name for station in revision.stations if not station.public)
    public_set = set(public)
    terminals = {revision.release: PlanOutcome.RELEASE, revision.reject: PlanOutcome.REJECT}
    zero = Fraction(0)

    # Augmented private chain. States are (private station, phase); internal
    # hops point at chain states, observable exits use synthetic absorbing
    # tokens that retain the arrival phase for the public ledger.
    states = [(name, phase) for name in private for phase in PHASES]
    chain = {state: {} for state in states}
    targets = []
    target_set = set(states)
    for name in private:
        for phase in PHASES:
            edges = chain[(name, phase)]
            for destination, weight in outgoing[name].items():
                next_phase = apply_label(phase, labels.get(destination))
                if destination in public_set:
                    token = ('pub', destination, next_phase)
                elif destination in terminals:
                    token = ('term', destination, phase)
                else:
                    token = (destination, next_phase)
                edges[token] = edges.get(token, zero) + weight
                if token not in target_set and token not in targets:
                    targets.append(token)

    canonical = review_outcome_keys(public)
    distributions = absorption_distributions(chain, states, targets)
    rows = []
    for station in public:
        phase_rows = []
        for entry_phase in PHASES:
            row = {key: zero for key in canonical}
            for destination, weight in outgoing[station].items():
                if destination in terminals:
                    row[(terminals[destination], entry_phase)] += weight
                elif destination in public_set:
                    next_phase = apply_label(entry_phase, labels.get(destination))
                    row[(destination, next_phase)] += weight
                else:
                    seed_phase = apply_label(entry_phase, labels.get(destination))
                    seed = (destination, seed_phase)
                    for token, probability in distributions[seed].items():
                        if probability == 0:
                            continue
                        kind, name, phase = token
                        mass = weight * probability
                        if kind == 'pub':
                            row[(name, phase)] += mass
                        else:
                            row[(terminals[name], phase)] += mass
            observed = sum(row.values())
            row[(PlanOutcome.NEVER, None)] = Fraction(1) - observed
            phase_rows.append(tuple(row[key] for key in canonical))
        rows.append(tuple(phase_rows))
    return public, tuple(rows)
