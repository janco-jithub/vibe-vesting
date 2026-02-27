"""
Alerting system for auto-trader monitoring.

Supports:
- Console alerts (stdout/logging)
- File-based alerts (for review)
- Slack webhooks (optional)
- Email alerts (optional)

Features:
- Deduplication: Doesn't spam same alert repeatedly
- Severity levels: INFO, WARNING, ERROR, CRITICAL
- Cooldown periods between same alerts
"""

import logging
import os
import json
import requests
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertManager:
    """
    Manage alerts for trading system issues.

    Features:
    - Deduplication: Doesn't spam same alert repeatedly
    - Multiple channels: Console, file, Slack, email
    - Severity-based routing
    """

    def __init__(
        self,
        alert_log_file: str = "logs/alerts.log",
        slack_webhook: Optional[str] = None,
        min_alert_interval_seconds: int = 300,  # 5 minutes between same alert
        console_enabled: bool = True
    ):
        self.alert_log_file = Path(alert_log_file)
        self.alert_log_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.slack_webhook = slack_webhook or os.getenv("SLACK_WEBHOOK", "")
        self.min_alert_interval = min_alert_interval_seconds
        self.console_enabled = console_enabled

        # Deduplication tracking
        self._last_alert_times: Dict[str, datetime] = {}
        self._alert_counts: Dict[str, int] = {}

    def _should_send_alert(self, alert_key: str) -> bool:
        """Check if enough time has passed since last alert of this type."""
        if alert_key not in self._last_alert_times:
            return True

        elapsed = (datetime.now() - self._last_alert_times[alert_key]).total_seconds()
        return elapsed >= self.min_alert_interval

    def send_alert(
        self,
        message: str,
        severity: AlertSeverity = AlertSeverity.WARNING,
        details: Optional[str] = None,
        force: bool = False
    ) -> bool:
        """
        Send alert to configured channels.

        Args:
            message: Short alert message
            severity: Alert severity level
            details: Optional detailed information
            force: Send even if within cooldown period

        Returns:
            True if alert was sent, False if deduplicated
        """
        alert_key = f"{severity.value}:{message}"

        if not force and not self._should_send_alert(alert_key):
            logger.debug(f"Skipping duplicate alert: {message}")
            return False

        # Track alert
        self._last_alert_times[alert_key] = datetime.now()
        self._alert_counts[alert_key] = self._alert_counts.get(alert_key, 0) + 1

        # Build alert data
        alert_data = {
            'timestamp': datetime.now().isoformat(),
            'severity': severity.value,
            'message': message,
            'details': details,
            'count': self._alert_counts[alert_key]
        }

        # Send to all channels
        self._send_to_console(alert_data)
        self._send_to_file(alert_data)
        
        if self.slack_webhook and severity in [AlertSeverity.ERROR, AlertSeverity.CRITICAL]:
            self._send_to_slack(alert_data)

        return True

    def _send_to_console(self, alert_data: dict):
        """Send alert to console/logging."""
        if not self.console_enabled:
            return

        severity = alert_data['severity']
        message = alert_data['message']
        
        log_level = {
            'info': logging.INFO,
            'warning': logging.WARNING,
            'error': logging.ERROR,
            'critical': logging.CRITICAL
        }.get(severity, logging.WARNING)

        logger.log(log_level, f"[ALERT] {message}")
        
        if alert_data.get('details'):
            logger.log(log_level, f"  Details: {alert_data['details']}")

    def _send_to_file(self, alert_data: dict):
        """Append alert to log file."""
        try:
            with open(self.alert_log_file, 'a') as f:
                f.write(json.dumps(alert_data) + '\n')
        except Exception as e:
            logger.error(f"Failed to write alert to file: {e}")

    def _send_to_slack(self, alert_data: dict):
        """Send alert to Slack webhook."""
        if not self.slack_webhook:
            return

        try:
            color_map = {
                'info': '#36a64f',
                'warning': '#ff9900',
                'error': '#ff0000',
                'critical': '#8B0000'
            }

            payload = {
                "attachments": [{
                    "color": color_map.get(alert_data['severity'], '#ff9900'),
                    "title": f"Trading Bot Alert: {alert_data['severity'].upper()}",
                    "text": alert_data['message'],
                    "fields": [
                        {
                            "title": "Time",
                            "value": alert_data['timestamp'],
                            "short": True
                        },
                        {
                            "title": "Alert Count",
                            "value": str(alert_data['count']),
                            "short": True
                        }
                    ],
                    "footer": "Auto-Trading System"
                }]
            }

            if alert_data.get('details'):
                payload["attachments"][0]["fields"].append({
                    "title": "Details",
                    "value": alert_data['details'][:500],
                    "short": False
                })

            response = requests.post(
                self.slack_webhook,
                json=payload,
                timeout=5
            )
            response.raise_for_status()
            logger.debug("Slack alert sent")

        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")

    def send_startup_alert(self):
        """Send alert that system is starting."""
        self.send_alert(
            message="Auto-trader starting up",
            severity=AlertSeverity.INFO,
            details=f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            force=True
        )

    def send_shutdown_alert(self, reason: str = "Normal shutdown"):
        """Send alert that system is shutting down."""
        self.send_alert(
            message=f"Auto-trader shutting down: {reason}",
            severity=AlertSeverity.WARNING,
            force=True
        )

    def send_trade_alert(self, symbol: str, action: str, quantity: int, price: float):
        """Send alert for executed trade."""
        self.send_alert(
            message=f"Trade executed: {action} {quantity} {symbol} @ ${price:.2f}",
            severity=AlertSeverity.INFO,
            force=True  # Always log trades
        )

    def send_error_alert(self, error_type: str, error_message: str):
        """Send alert for errors."""
        self.send_alert(
            message=f"Error: {error_type}",
            severity=AlertSeverity.ERROR,
            details=error_message
        )

    def send_health_alert(self, status_summary: str, issues: List[str]):
        """Send alert for health issues."""
        severity = AlertSeverity.CRITICAL if len(issues) > 2 else AlertSeverity.WARNING
        self.send_alert(
            message=f"Health check failed: {status_summary}",
            severity=severity,
            details="; ".join(issues)
        )

    def get_recent_alerts(self, hours: int = 24) -> List[dict]:
        """Get alerts from the last N hours."""
        alerts = []
        cutoff = datetime.now() - timedelta(hours=hours)
        
        try:
            if self.alert_log_file.exists():
                with open(self.alert_log_file, 'r') as f:
                    for line in f:
                        try:
                            alert = json.loads(line.strip())
                            alert_time = datetime.fromisoformat(alert['timestamp'])
                            if alert_time > cutoff:
                                alerts.append(alert)
                        except:
                            continue
        except Exception as e:
            logger.error(f"Failed to read alerts: {e}")
        
        return alerts


# Import timedelta for get_recent_alerts
from datetime import timedelta
