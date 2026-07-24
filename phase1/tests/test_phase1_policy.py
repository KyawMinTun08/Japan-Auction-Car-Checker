"""Policy-level tests independent from Supabase.

Run:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass


@dataclass
class Broker:
    code: str
    can_auction: bool
    can_outside: bool
    active_auction: int = 0
    active_outside: int = 0
    total_assigned: int = 0
    last_assigned_epoch: int | None = None
    available: bool = True


def eligible(broker: Broker, service_type: str) -> bool:
    if not broker.available:
        return False
    if service_type == "auction":
        return broker.can_auction and broker.active_auction == 0
    if service_type == "outside_car":
        return broker.can_outside and broker.active_outside == 0
    raise ValueError(service_type)


def fair_order(brokers: list[Broker], service_type: str) -> list[Broker]:
    available = [broker for broker in brokers if eligible(broker, service_type)]
    return sorted(
        available,
        key=lambda broker: (
            broker.last_assigned_epoch is not None,
            broker.last_assigned_epoch or 0,
            broker.total_assigned,
            broker.code,
        ),
    )


class Phase1PolicyTests(unittest.TestCase):
    def test_one_auction_slot_does_not_block_outside_slot(self) -> None:
        broker = Broker("B001", True, True, active_auction=1, active_outside=0)
        self.assertFalse(eligible(broker, "auction"))
        self.assertTrue(eligible(broker, "outside_car"))

    def test_one_outside_slot_does_not_block_auction_slot(self) -> None:
        broker = Broker("B001", True, True, active_auction=0, active_outside=1)
        self.assertTrue(eligible(broker, "auction"))
        self.assertFalse(eligible(broker, "outside_car"))

    def test_broker_without_matching_skill_is_not_eligible(self) -> None:
        broker = Broker("B001", False, True)
        self.assertFalse(eligible(broker, "auction"))
        self.assertTrue(eligible(broker, "outside_car"))

    def test_never_assigned_broker_gets_first_fair_turn(self) -> None:
        brokers = [
            Broker("B001", True, True, total_assigned=3, last_assigned_epoch=300),
            Broker("B002", True, True, total_assigned=0, last_assigned_epoch=None),
            Broker("B003", True, True, total_assigned=1, last_assigned_epoch=100),
        ]
        ordered = fair_order(brokers, "auction")
        self.assertEqual([b.code for b in ordered], ["B002", "B003", "B001"])

    def test_location_is_not_part_of_eligibility(self) -> None:
        # Broker model intentionally has no location field.
        broker = Broker("B001", True, True)
        self.assertTrue(eligible(broker, "auction"))
        self.assertTrue(eligible(broker, "outside_car"))


if __name__ == "__main__":
    unittest.main()
