"""Audit complete, ordered transfer rows before freezing a plan."""

from fractions import Fraction

from plans.snapshot import PlanOutcome


class InvalidTransferLedger(ValueError):
    pass


def validate_transfer_ledger(stations, ledger):
    if not 1 <= len(stations) <= 6 or len(set(stations)) != len(stations):
        raise InvalidTransferLedger('invalid public station list')
    if tuple(ledger) != tuple(stations):
        raise InvalidTransferLedger('ledger rows do not match public stations in order')
    columns = (*stations, *PlanOutcome)
    for station, row in ledger.items():
        if tuple(row) != columns:
            raise InvalidTransferLedger(f'invalid or unordered outcomes at {station}')
        if any(type(value) is not Fraction or not 0 <= value <= 1 for value in row.values()):
            raise InvalidTransferLedger(f'invalid probability at {station}')
        if sum(row.values()) != 1:
            raise InvalidTransferLedger(f'probability does not balance at {station}')
