from datetime import datetime, timedelta
import random

class MockAdServer:
    """
    A mock ad server to simulate campaign delivery and status.
    """
    def __init__(self, media_buy_data: dict):
        self.media_buy = media_buy_data
        self.start_date = datetime.fromisoformat(self.media_buy['start_time'])
        self.end_date = datetime.fromisoformat(self.media_buy['end_time'])
        self.total_budget = self.media_buy['total_budget']
        self.total_days = (self.end_date - self.start_date).days
        self.daily_budget = self.total_budget / self.total_days if self.total_days > 0 else self.total_budget

    def get_status(self, today: datetime) -> dict:
        """Calculates the delivery status of the campaign for a given day."""
        # Delivery data is for the previous day.
        reporting_date = today - timedelta(days=1)

        if reporting_date < self.start_date:
            return {"status": "live", "spend": 0, "impressions": 0, "pacing": "on_track"}

        if reporting_date > self.end_date:
            reporting_date = self.end_date
        
        days_elapsed = (reporting_date - self.start_date).days + 1
        
        total_spend = 0
        for day in range(days_elapsed):
            pacing_multiplier = random.uniform(0.5, 1.0)
            total_spend += self.daily_budget * pacing_multiplier
        
        avg_cpm = sum(pkg['cpm'] for pkg in self.media_buy['media_packages']) / len(self.media_buy['media_packages'])
        impressions = int((total_spend / avg_cpm) * 1000) if avg_cpm > 0 else 0

        return {
            "status": "live" if today <= self.end_date else "completed",
            "spend": round(total_spend, 2),
            "impressions": impressions,
            "pacing": "on_track"
        }

    def get_package_delivery(self, today: datetime) -> list:
        """Calculates delivery for each package."""
        # Delivery data is for the previous day.
        reporting_date = today - timedelta(days=1)

        if reporting_date < self.start_date:
            return []

        if reporting_date > self.end_date:
            reporting_date = self.end_date
            
        days_elapsed = (reporting_date - self.start_date).days + 1
            
        package_delivery = []

        for package in self.media_buy['media_packages']:
            package_total_days = (self.end_date - self.start_date).days
            package_daily_budget = package['budget'] / package_total_days if package_total_days > 0 else package['budget']
            
            package_spend = 0
            for day in range(days_elapsed):
                pacing_multiplier = random.uniform(0.5, 1.0)
                package_spend += package_daily_budget * pacing_multiplier

            package_impressions = int((package_spend / package['cpm']) * 1000) if package['cpm'] > 0 else 0
            
            package_delivery.append({
                "package_id": package['package_id'],
                "spend": round(package_spend, 2),
                "impressions": package_impressions
            })
            
        return package_delivery
