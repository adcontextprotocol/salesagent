"""Delivery simulation service for mock adapter.

Provides time-accelerated campaign delivery simulation with webhook notifications.
Fires webhooks at configurable intervals to simulate real-world campaign delivery.

Example: 1 second = 1 hour of campaign time (configurable)
"""

import asyncio
import logging
import threading
from datetime import datetime, timedelta

from src.services.push_notification_service import push_notification_service

logger = logging.getLogger(__name__)


class DeliverySimulator:
    """Simulates accelerated campaign delivery with webhook notifications."""

    def __init__(self):
        """Initialize the delivery simulator."""
        self._active_simulations: dict[str, threading.Thread] = {}
        self._stop_signals: dict[str, threading.Event] = {}

    def start_simulation(
        self,
        media_buy_id: str,
        tenant_id: str,
        principal_id: str,
        start_time: datetime,
        end_time: datetime,
        total_budget: float,
        time_acceleration: int = 3600,  # 1 second = 1 hour (3600 seconds)
        update_interval_seconds: float = 1.0,  # Fire webhook every 1 second
    ):
        """Start delivery simulation for a media buy.

        Args:
            media_buy_id: Media buy identifier
            tenant_id: Tenant identifier
            principal_id: Principal identifier
            start_time: Campaign start datetime
            end_time: Campaign end datetime
            total_budget: Total campaign budget
            time_acceleration: How many real seconds = 1 simulated second (default: 3600 = 1 sec = 1 hour)
            update_interval_seconds: How often to fire webhooks in real time (default: 1 second)
        """
        # Don't start if already running
        if media_buy_id in self._active_simulations:
            logger.warning(f"Delivery simulation already running for {media_buy_id}")
            return

        # Create stop signal
        stop_signal = threading.Event()
        self._stop_signals[media_buy_id] = stop_signal

        # Start simulation thread
        thread = threading.Thread(
            target=self._run_simulation,
            args=(
                media_buy_id,
                tenant_id,
                principal_id,
                start_time,
                end_time,
                total_budget,
                time_acceleration,
                update_interval_seconds,
                stop_signal,
            ),
            daemon=True,
        )
        self._active_simulations[media_buy_id] = thread
        thread.start()

        logger.info(
            f"✅ Started delivery simulation for {media_buy_id} "
            f"(acceleration: {time_acceleration}x, interval: {update_interval_seconds}s)"
        )

    def stop_simulation(self, media_buy_id: str):
        """Stop delivery simulation for a media buy.

        Args:
            media_buy_id: Media buy identifier
        """
        if media_buy_id in self._stop_signals:
            self._stop_signals[media_buy_id].set()
            logger.info(f"🛑 Stopping delivery simulation for {media_buy_id}")

    def _run_simulation(
        self,
        media_buy_id: str,
        tenant_id: str,
        principal_id: str,
        start_time: datetime,
        end_time: datetime,
        total_budget: float,
        time_acceleration: int,
        update_interval_seconds: float,
        stop_signal: threading.Event,
    ):
        """Run the delivery simulation (thread worker).

        Args:
            media_buy_id: Media buy identifier
            tenant_id: Tenant identifier
            principal_id: Principal identifier
            start_time: Campaign start datetime
            end_time: Campaign end datetime
            total_budget: Total campaign budget
            time_acceleration: Seconds of real time = 1 second of simulated time
            update_interval_seconds: How often to fire webhooks
            stop_signal: Event to signal simulation stop
        """
        try:
            # Calculate campaign duration
            campaign_duration = (end_time - start_time).total_seconds()  # seconds
            simulation_duration = campaign_duration / time_acceleration  # real seconds

            # Calculate update interval in simulated time
            simulated_interval = update_interval_seconds * time_acceleration  # simulated seconds per update

            logger.info(
                f"📊 Simulation parameters for {media_buy_id}:\n"
                f"   Campaign duration: {campaign_duration / 3600:.1f} hours\n"
                f"   Simulation duration: {simulation_duration:.1f} seconds\n"
                f"   Update interval: {update_interval_seconds}s real time = {simulated_interval / 3600:.1f}h simulated time"
            )

            # Send initial webhook - campaign started
            asyncio.run(
                self._send_delivery_webhook(
                    media_buy_id=media_buy_id,
                    tenant_id=tenant_id,
                    principal_id=principal_id,
                    simulated_time=start_time,
                    elapsed_hours=0,
                    total_hours=campaign_duration / 3600,
                    impressions=0,
                    spend=0.0,
                    total_budget=total_budget,
                    status="started",
                )
            )

            elapsed_real_seconds = 0.0

            while elapsed_real_seconds < simulation_duration and not stop_signal.is_set():
                # Wait for update interval
                stop_signal.wait(update_interval_seconds)

                if stop_signal.is_set():
                    break

                elapsed_real_seconds += update_interval_seconds

                # Calculate simulated progress
                elapsed_simulated_seconds = elapsed_real_seconds * time_acceleration
                progress_ratio = min(elapsed_simulated_seconds / campaign_duration, 1.0)

                # Calculate simulated time
                simulated_time = start_time + timedelta(seconds=elapsed_simulated_seconds)

                # Calculate delivery metrics (realistic simulation)
                # Use even pacing with some variance
                base_spend = total_budget * progress_ratio
                variance = 0.05  # 5% variance
                import random

                spend = base_spend * (1 + random.uniform(-variance, variance))
                spend = min(spend, total_budget)  # Cap at total budget

                # Calculate impressions (assume $10 CPM)
                impressions = int(spend / 0.01)

                # Calculate elapsed hours for webhook
                elapsed_hours = elapsed_simulated_seconds / 3600
                total_hours = campaign_duration / 3600

                # Determine status
                if progress_ratio >= 1.0:
                    status = "completed"
                else:
                    status = "delivering"

                # Send delivery update webhook
                asyncio.run(
                    self._send_delivery_webhook(
                        media_buy_id=media_buy_id,
                        tenant_id=tenant_id,
                        principal_id=principal_id,
                        simulated_time=simulated_time,
                        elapsed_hours=elapsed_hours,
                        total_hours=total_hours,
                        impressions=impressions,
                        spend=spend,
                        total_budget=total_budget,
                        status=status,
                    )
                )

                # Stop if campaign completed
                if progress_ratio >= 1.0:
                    logger.info(f"🎉 Campaign {media_buy_id} simulation completed")
                    break

        except Exception as e:
            logger.error(f"❌ Error in delivery simulation for {media_buy_id}: {e}", exc_info=True)
        finally:
            # Cleanup
            if media_buy_id in self._active_simulations:
                del self._active_simulations[media_buy_id]
            if media_buy_id in self._stop_signals:
                del self._stop_signals[media_buy_id]

    async def _send_delivery_webhook(
        self,
        media_buy_id: str,
        tenant_id: str,
        principal_id: str,
        simulated_time: datetime,
        elapsed_hours: float,
        total_hours: float,
        impressions: int,
        spend: float,
        total_budget: float,
        status: str,
    ):
        """Send delivery update webhook.

        Args:
            media_buy_id: Media buy identifier
            tenant_id: Tenant identifier
            principal_id: Principal identifier
            simulated_time: Current simulated campaign time
            elapsed_hours: Hours elapsed in simulation
            total_hours: Total campaign hours
            impressions: Impressions delivered so far
            spend: Spend so far
            total_budget: Total campaign budget
            status: Campaign status (started, delivering, completed)
        """
        progress_pct = (elapsed_hours / total_hours * 100) if total_hours > 0 else 0
        pacing_pct = (spend / total_budget * 100) if total_budget > 0 else 0

        delivery_data = {
            "event_type": "delivery_update",
            "media_buy_id": media_buy_id,
            "status": status,
            "simulated_time": simulated_time.isoformat(),
            "progress": {
                "elapsed_hours": round(elapsed_hours, 2),
                "total_hours": round(total_hours, 2),
                "progress_percentage": round(progress_pct, 1),
            },
            "delivery": {
                "impressions": impressions,
                "spend": round(spend, 2),
                "total_budget": total_budget,
                "pacing_percentage": round(pacing_pct, 1),
            },
            "metrics": {
                "cpm": round((spend / impressions * 1000), 2) if impressions > 0 else 0,
                "clicks": int(impressions * 0.01),  # 1% CTR
                "ctr": 0.01,
            },
        }

        logger.info(
            f"📤 Delivery webhook for {media_buy_id}: "
            f"{elapsed_hours:.1f}/{total_hours:.1f}h "
            f"({progress_pct:.1f}% progress, {pacing_pct:.1f}% pacing) "
            f"- {impressions:,} imps, ${spend:,.2f} spend"
        )

        try:
            result = await push_notification_service.send_task_status_notification(
                tenant_id=tenant_id,
                principal_id=principal_id,
                task_id=media_buy_id,
                task_status=status,
                task_data=delivery_data,
            )

            if result["sent"] > 0:
                logger.debug(f"✅ Delivery webhook sent to {result['sent']} endpoint(s)")
            else:
                logger.debug(f"⚠️ No webhooks configured for {tenant_id}/{principal_id}")

        except Exception as e:
            logger.error(f"❌ Failed to send delivery webhook: {e}")


# Global singleton instance
delivery_simulator = DeliverySimulator()
