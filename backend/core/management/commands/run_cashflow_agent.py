
import logging

from django.core.management.base import BaseCommand

from core.agent.loop import (
    generate_cash_flow_snapshot,
    run_agent_cycle,
)
from core.webhooks import retry_pending_webhook_events


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the Cash-Flow Guardian agent cycle."

    def handle(self, *args, **options):
        self.stdout.write(
            "Starting Cash-Flow Guardian agent..."
        )
        logger.info(
            "Cash-Flow Guardian agent cycle started."
        )

        try:
            # Step 1: Retry saved webhook events that are pending.
            webhook_results = retry_pending_webhook_events()

            webhook_message = (
                "Webhook retry results: "
                f"processed={webhook_results['processed']}, "
                f"pending={webhook_results['pending']}, "
                f"errors={webhook_results['errors']}"
            )

            self.stdout.write(webhook_message)
            logger.info(webhook_message)

            # Step 2: Process overdue invoices independently.
            results = run_agent_cycle()

            failures = 0

            if not results:
                message = "No overdue invoices found."
                self.stdout.write(self.style.SUCCESS(message))
                logger.info(message)

            for result in results:
                if result.get("success"):
                    message = (
                        f"Processed {result['invoice_id']}: "
                        f"risk={result['risk_level']}, "
                        f"reminder_status={result['reminder_status']}, "
                        f"draft_created={result['draft_created']}"
                    )

                    self.stdout.write(
                        self.style.SUCCESS(message)
                    )
                    logger.info(message)

                else:
                    failures += 1
                    message = (
                        "Failed to process "
                        f"{result.get('invoice_id', 'unknown invoice')}: "
                        f"{result.get('error', 'Unknown error')}"
                    )

                    self.stderr.write(
                        self.style.ERROR(message)
                    )
                    logger.error(message)

            # Step 3: Refresh the cash-flow forecast.
            # Do this even when there are no overdue invoices.
            snapshot = generate_cash_flow_snapshot()

            snapshot_message = (
                f"Cash-flow snapshot created for {snapshot.date}: "
                f"inflow={snapshot.expected_inflow}, "
                f"obligations={snapshot.upcoming_obligations}, "
                f"projected_gap={snapshot.projected_gap}"
            )

            self.stdout.write(
                self.style.SUCCESS(snapshot_message)
            )
            logger.info(snapshot_message)

            # Step 4: Report errors after attempting the snapshot.
            if webhook_results["errors"] or failures:
                raise RuntimeError(
                    "Agent cycle completed with errors: "
                    f"webhook_errors={webhook_results['errors']}, "
                    f"invoice_failures={failures}."
                )

            self.stdout.write(
                self.style.SUCCESS("Agent cycle finished.")
            )
            logger.info(
                "Agent cycle finished successfully."
            )

        except Exception:
            logger.exception(
                "Cash-Flow Guardian agent cycle failed."
            )
            raise
