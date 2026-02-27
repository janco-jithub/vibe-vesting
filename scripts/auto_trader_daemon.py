#!/usr/bin/env python3
"""
Auto-Trader Daemon with Health Monitoring and Auto-Restart.

This daemon:
1. Starts auto_trader.py
2. Monitors its health every minute
3. Restarts if stuck/crashed
4. Sends alerts on issues
5. Maintains uptime log

Usage:
    python -m scripts.auto_trader_daemon
    python -m scripts.auto_trader_daemon --strategies simple_momentum --interval 300
"""

import argparse
import logging
import subprocess
import time
import os
import signal
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitoring.health_monitor import HealthMonitor
from monitoring.alerting import AlertManager, AlertSeverity

# Setup logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/daemon.log")
    ]
)
logger = logging.getLogger(__name__)


class AutoTraderDaemon:
    """
    Daemon process that monitors and restarts auto_trader.
    """

    def __init__(
        self,
        strategies: List[str],
        check_interval: int = 300,
        health_check_interval: int = 60,
        max_restart_attempts: int = 5,
        restart_backoff_seconds: int = 60,
        db_path: str = "data/quant.db"
    ):
        self.strategies = strategies
        self.check_interval = check_interval
        self.health_check_interval = health_check_interval
        self.max_restart_attempts = max_restart_attempts
        self.restart_backoff = restart_backoff_seconds
        self.db_path = db_path

        self.health_monitor = HealthMonitor(
            heartbeat_file="logs/auto_trader_heartbeat.json"
        )
        self.alert_manager = AlertManager(
            alert_log_file="logs/alerts.log",
            slack_webhook=os.getenv("SLACK_WEBHOOK", "")
        )

        self.process: Optional[subprocess.Popen] = None
        self.running = True
        self.restart_count = 0
        self.last_restart_time: Optional[datetime] = None
        self.start_time = datetime.now()

        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _build_auto_trader_command(self) -> List[str]:
        """Build the command to start auto_trader."""
        cmd = [
            sys.executable, "-m", "scripts.auto_trader",
            "--interval", str(self.check_interval),
            "--strategies"
        ] + self.strategies + [
            "--db", self.db_path
        ]
        return cmd

    def start_auto_trader(self) -> bool:
        """Start the auto_trader process."""
        try:
            logger.info("Starting auto_trader...")
            
            cmd = self._build_auto_trader_command()
            logger.info(f"Command: {' '.join(cmd)}")

            # Start process with output to log file
            log_file = open("logs/auto_trader_output.log", "a")
            
            self.process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )

            # Give it a moment to start
            time.sleep(5)

            # Check if it's still running
            if self.process.poll() is not None:
                logger.error(f"Auto-trader failed to start (exit code: {self.process.returncode})")
                return False

            logger.info(f"Auto-trader started (PID: {self.process.pid})")
            self.last_restart_time = datetime.now()
            
            self.alert_manager.send_alert(
                message="Auto-trader started successfully",
                severity=AlertSeverity.INFO,
                details=f"PID: {self.process.pid}, Strategies: {', '.join(self.strategies)}",
                force=True
            )
            
            return True

        except Exception as e:
            logger.error(f"Failed to start auto_trader: {e}")
            self.alert_manager.send_error_alert("Startup failure", str(e))
            return False

    def stop_auto_trader(self, force: bool = False):
        """Stop the auto_trader process."""
        if self.process is None:
            return

        try:
            logger.info("Stopping auto_trader...")

            if force:
                self.process.kill()
            else:
                self.process.terminate()
                # Wait up to 30s for graceful shutdown
                try:
                    self.process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    logger.warning("Auto-trader didn't stop gracefully, forcing...")
                    self.process.kill()

            self.process = None
            logger.info("Auto-trader stopped")

        except Exception as e:
            logger.error(f"Error stopping auto_trader: {e}")

    def restart_auto_trader(self, reason: str) -> bool:
        """Restart the auto_trader process."""
        logger.warning(f"Restarting auto_trader: {reason}")

        self.alert_manager.send_alert(
            message=f"Auto-trader restarting",
            severity=AlertSeverity.WARNING,
            details=f"Reason: {reason}\nRestart count: {self.restart_count + 1}"
        )

        # Stop current process
        self.stop_auto_trader(force=True)

        # Apply backoff if we've restarted recently
        if self.restart_count > 0:
            backoff_time = min(self.restart_backoff * self.restart_count, 600)  # Max 10 min
            logger.info(f"Waiting {backoff_time}s before restart (backoff)...")
            time.sleep(backoff_time)

        # Start new process
        if self.start_auto_trader():
            self.restart_count += 1

            # Reset restart count after 1 hour of stability
            if self.last_restart_time:
                time_since_restart = (datetime.now() - self.last_restart_time).total_seconds()
                if time_since_restart > 3600:
                    logger.info("System stable for 1 hour, resetting restart count")
                    self.restart_count = 0
            
            return True
        else:
            logger.error("Failed to restart auto_trader")

            if self.restart_count >= self.max_restart_attempts:
                self.alert_manager.send_alert(
                    message="Auto-trader failed to restart after maximum attempts",
                    severity=AlertSeverity.CRITICAL,
                    details=f"Attempted {self.restart_count} restarts. Manual intervention required.",
                    force=True
                )
            
            return False

    def run(self):
        """Main daemon loop."""
        logger.info("=" * 60)
        logger.info("Auto-trader daemon starting...")
        logger.info(f"Strategies: {', '.join(self.strategies)}")
        logger.info(f"Check interval: {self.check_interval}s")
        logger.info(f"Health check interval: {self.health_check_interval}s")
        logger.info("=" * 60)

        self.alert_manager.send_startup_alert()

        # Initial start
        if not self.start_auto_trader():
            logger.error("Failed to start auto_trader on initialization")
            self.alert_manager.send_alert(
                message="Daemon failed to start auto-trader",
                severity=AlertSeverity.CRITICAL,
                force=True
            )
            return

        # Monitor loop
        last_status_log = datetime.now()
        health_check_count = 0

        while self.running:
            try:
                logger.info(f"Health check #{health_check_count + 1} starting in {self.health_check_interval}s...")
                time.sleep(self.health_check_interval)
                health_check_count += 1
                logger.info(f"Running health check #{health_check_count}...")

                # Check health
                status = self.health_monitor.check_health(
                    expected_cycle_interval=self.check_interval
                )

                # Log status periodically (every 5 minutes)
                if (datetime.now() - last_status_log).total_seconds() > 300:
                    logger.info(f"Health: {self.health_monitor.get_status_summary()}")
                    logger.info(f"Memory: {status.memory_mb:.0f}MB, CPU: {status.cpu_percent:.0f}%")
                    last_status_log = datetime.now()

                if not status.is_healthy:
                    logger.warning(f"Health issues: {', '.join(status.issues)}")
                    self.alert_manager.send_health_alert(
                        self.health_monitor.get_status_summary(),
                        status.issues
                    )

                # Check if restart needed
                if self.health_monitor.should_restart():
                    reason = "Process dead" if not status.process_alive else \
                             "System stuck" if status.is_stuck else \
                             "Health check failure"
                    
                    if not self.restart_auto_trader(reason):
                        if self.restart_count >= self.max_restart_attempts:
                            logger.critical("Max restart attempts reached, stopping daemon")
                            self.running = False

            except Exception as e:
                logger.error(f"Error in daemon loop: {e}", exc_info=True)
                time.sleep(10)  # Brief pause before continuing

        # Cleanup
        self.stop_auto_trader()
        self.alert_manager.send_shutdown_alert("Daemon stopped")
        logger.info("Daemon stopped")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down daemon...")
        self.running = False

    def get_uptime(self) -> str:
        """Get daemon uptime as string."""
        uptime = datetime.now() - self.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"


def main():
    parser = argparse.ArgumentParser(
        description="Auto-trader daemon with health monitoring and auto-restart"
    )
    parser.add_argument(
        "--interval", type=int, default=300,
        help="Auto-trader check interval in seconds (default: 300)"
    )
    parser.add_argument(
        "--health-interval", type=int, default=60,
        help="Health check interval in seconds (default: 60)"
    )
    parser.add_argument(
        "--strategies", nargs="+", default=["simple_momentum"],
        help="Strategies to run (default: simple_momentum)"
    )
    parser.add_argument(
        "--db", type=str, default="data/quant.db",
        help="Database path"
    )
    parser.add_argument(
        "--max-restarts", type=int, default=5,
        help="Maximum restart attempts before giving up (default: 5)"
    )

    args = parser.parse_args()

    daemon = AutoTraderDaemon(
        strategies=args.strategies,
        check_interval=args.interval,
        health_check_interval=args.health_interval,
        max_restart_attempts=args.max_restarts,
        db_path=args.db
    )

    daemon.run()


if __name__ == "__main__":
    main()
