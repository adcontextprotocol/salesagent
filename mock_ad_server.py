from datetime import date, timedelta
import random
from typing import List

from schemas import CreateMediaBuyRequest, Product

class MockAdServer:
    """A mock ad server that simulates delivery based on advanced pricing and pacing models."""

    def __init__(self, media_buy_request: CreateMediaBuyRequest, products: List[Product]):
        self.request = media_buy_request
        self.products = {p.product_id: p for p in products}
        self.start_date = self.request.flight_start_date
        self.end_date = self.request.flight_end_date
        self.total_budget = self.request.total_budget
        self.total_days = (self.end_date - self.start_date).days

    def get_daily_spend_target(self) -> float:
        """Determines the daily spend target based on the pacing mode."""
        if self.request.pacing == "daily_budget":
            return self.request.daily_budget
        elif self.request.pacing == "asap":
            # Spend 2x the "even" rate to finish faster
            return (self.total_budget / self.total_days) * 2 if self.total_days > 0 else self.total_budget
        else: # "even" pacing
            return self.total_budget / self.total_days if self.total_days > 0 else self.total_budget

    def get_delivery_status(self, today: date) -> dict:
        """Calculates the delivery status of the campaign for a given day."""
        if today <= self.start_date:
            return {"status": "pending_start", "spend": 0, "impressions": 0, "pacing": "on_track", "days_elapsed": 0, "total_days": self.total_days}

        reporting_date = today - timedelta(days=1)
        is_complete = reporting_date >= self.end_date
        if is_complete:
            reporting_date = self.end_date

        days_elapsed = (reporting_date - self.start_date).days + 1
        daily_spend_target = self.get_daily_spend_target()
        
        total_spend = 0
        total_impressions = 0
        
        for day in range(days_elapsed):
            # Stop spending if the total budget is reached
            if total_spend >= self.total_budget:
                break
            
            # Simulate daily variance
            spend_for_the_day = daily_spend_target * random.uniform(0.9, 1.1)
            
            # Ensure we don't overshoot the total budget
            if total_spend + spend_for_the_day > self.total_budget:
                spend_for_the_day = self.total_budget - total_spend

            # Simplified model: assume budget is split evenly across products for impression calculation
            spend_per_product = spend_for_the_day / len(self.products)
            for product_id in self.request.product_ids:
                product = self.products[product_id]
                cpm = product.cpm if product.is_fixed_price else random.uniform(product.price_guidance.p50, product.price_guidance.p75)
                total_impressions += int((spend_per_product / cpm) * 1000) if cpm > 0 else 0
            
            total_spend += spend_for_the_day

        expected_spend = daily_spend_target * days_elapsed
        pacing = "on_track"
        if total_spend > expected_spend * 1.1: pacing = "ahead"
        elif total_spend < expected_spend * 0.9: pacing = "behind"

        final_status = "completed" if is_complete or total_spend >= self.total_budget else "live"

        return {
            "status": final_status,
            "spend": round(total_spend, 2),
            "impressions": total_impressions,
            "pacing": pacing,
            "days_elapsed": days_elapsed,
            "total_days": self.total_days
        }