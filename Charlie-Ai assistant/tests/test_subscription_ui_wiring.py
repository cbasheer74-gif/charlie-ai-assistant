import unittest
from types import SimpleNamespace

from engine.commercial.models import PlanTier, SubscriptionStatus
from engine.commercial.plan_registry import PlanRegistry
from ui import MainWindow


class _Button:
    def __init__(self):
        self.text = ""
        self.style = ""

    def setText(self, value):
        self.text = value

    def setStyleSheet(self, value):
        self.style = value


class SubscriptionUiWiringTests(unittest.TestCase):
    def test_starter_plan_and_remaining_time_are_visible(self):
        engine = SimpleNamespace(
            get_account=lambda: SimpleNamespace(
                plan=PlanTier.STARTER,
                subscription_status=SubscriptionStatus.FREE,
            ),
            get_starter_time_status=lambda: {
                "is_starter": True,
                "remaining_seconds": 487,
            },
            plan_registry=PlanRegistry(),
        )
        window = SimpleNamespace(
            _get_commercial_engine=lambda: engine,
            _plan_header_btn=_Button(),
            _subscription_btn=_Button(),
        )

        MainWindow._refresh_subscription_ui(window)

        self.assertEqual(window._plan_header_btn.text, "Starter · 08:07 left")
        self.assertIn("Current plan: Starter", window._subscription_btn.text)

    def test_paid_plan_and_status_are_visible(self):
        engine = SimpleNamespace(
            get_account=lambda: SimpleNamespace(
                plan=PlanTier.PREMIUM,
                subscription_status=SubscriptionStatus.ACTIVE,
            ),
            get_starter_time_status=lambda: {"is_starter": False},
            plan_registry=PlanRegistry(),
        )
        window = SimpleNamespace(
            _get_commercial_engine=lambda: engine,
            _plan_header_btn=_Button(),
            _subscription_btn=_Button(),
        )

        MainWindow._refresh_subscription_ui(window)

        self.assertEqual(window._plan_header_btn.text, "Pro · Active")
        self.assertEqual(window._subscription_btn.text, "Current plan: Pro — Active")


if __name__ == "__main__":
    unittest.main()
