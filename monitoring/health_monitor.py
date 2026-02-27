"""
Health Monitor for Auto-Trading System.

Monitors:
- Process liveness (heartbeat)
- Cycle completion times
- Trade execution rate
- Error rates
- Database health

Detects when the system is stuck or failing.
"""

import logging
import time
import json
import psutil
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """System health status."""
    timestamp: datetime
    is_healthy: bool
    is_stuck: bool
    process_alive: bool
    last_cycle_time: Optional[datetime]
    cycles_completed: int
    trades_last_hour: int
    errors_last_hour: int
    memory_mb: float
    cpu_percent: float
    issues: List[str]

    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'is_healthy': self.is_healthy,
            'is_stuck': self.is_stuck,
            'process_alive': self.process_alive,
            'last_cycle_time': self.last_cycle_time.isoformat() if self.last_cycle_time else None,
            'cycles_completed': self.cycles_completed,
            'trades_last_hour': self.trades_last_hour,
            'errors_last_hour': self.errors_last_hour,
            'memory_mb': self.memory_mb,
            'cpu_percent': self.cpu_percent,
            'issues': self.issues
        }


class HealthMonitor:
    """
    Monitor auto_trader health and detect stuck states.

    Detection criteria for "stuck":
    1. No cycle completion in 2x expected interval
    2. Process consuming high CPU but no progress
    3. Memory leak (excessive growth)
    4. High error rate
    """

    def __init__(
        self,
        heartbeat_file: str = "logs/auto_trader_heartbeat.json",
        cycle_timeout_multiplier: float = 2.5,
        max_memory_mb: float = 2000.0,
        error_rate_threshold: float = 0.5
    ):
        self.heartbeat_file = Path(heartbeat_file)
        self.cycle_timeout_multiplier = cycle_timeout_multiplier
        self.max_memory_mb = max_memory_mb
        self.error_rate_threshold = error_rate_threshold

        # Tracking
        self._last_health_status: Optional[HealthStatus] = None
        self._consecutive_unhealthy = 0
        self._baseline_memory_mb: Optional[float] = None

    def read_heartbeat(self) -> Optional[Dict]:
        """Read the last heartbeat from auto_trader."""
        try:
            if not self.heartbeat_file.exists():
                return None

            with open(self.heartbeat_file, 'r') as f:
                data = json.load(f)

            return data
        except Exception as e:
            logger.error(f"Failed to read heartbeat: {e}")
            return None

    def find_auto_trader_process(self) -> Optional[psutil.Process]:
        """Find the auto_trader process."""
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline', [])
                if cmdline:
                    cmdline_str = ' '.join(cmdline)
                    # Match both direct script and module invocation
                    if 'auto_trader.py' in cmdline_str or 'scripts.auto_trader' in cmdline_str:
                        # Exclude the daemon itself
                        if 'auto_trader_daemon' not in cmdline_str:
                            return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def check_health(self, expected_cycle_interval: int = 300) -> HealthStatus:
        """
        Check system health and return status.

        Args:
            expected_cycle_interval: Expected seconds between cycles (default 300)

        Returns:
            HealthStatus object
        """
        issues = []
        is_healthy = True
        is_stuck = False

        # Check 1: Process alive
        process = self.find_auto_trader_process()
        process_alive = process is not None

        if not process_alive:
            issues.append("Auto-trader process not running")
            is_healthy = False

        # Check 2: Read heartbeat
        heartbeat = self.read_heartbeat()

        last_cycle_time = None
        cycles_completed = 0
        trades_last_hour = 0
        errors_last_hour = 0

        if heartbeat:
            try:
                last_cycle_time = datetime.fromisoformat(heartbeat.get('timestamp', ''))
            except:
                last_cycle_time = None
                
            cycles_completed = heartbeat.get('cycle_number', 0)
            trades_last_hour = heartbeat.get('trades_last_hour', 0)
            errors_last_hour = heartbeat.get('errors_last_hour', 0)

            # Check if stuck (no progress)
            if last_cycle_time:
                time_since_last_cycle = (datetime.now() - last_cycle_time).total_seconds()
                timeout_threshold = expected_cycle_interval * self.cycle_timeout_multiplier

                if time_since_last_cycle > timeout_threshold:
                    issues.append(
                        f"No cycle completion in {time_since_last_cycle:.0f}s "
                        f"(expected every {expected_cycle_interval}s)"
                    )
                    is_stuck = True
                    is_healthy = False
        else:
            if process_alive:
                # Process running but no heartbeat - might be starting up
                issues.append("No heartbeat file - system may be starting")

        # Check 3: Resource usage
        memory_mb = 0.0
        cpu_percent = 0.0

        if process:
            try:
                memory_mb = process.memory_info().rss / 1024 / 1024
                cpu_percent = process.cpu_percent(interval=0.5)

                # Set baseline memory on first check
                if self._baseline_memory_mb is None:
                    self._baseline_memory_mb = memory_mb

                # Check for memory leak (>50% growth from baseline)
                if self._baseline_memory_mb and memory_mb > self._baseline_memory_mb * 1.5:
                    issues.append(f"Possible memory leak: {memory_mb:.0f}MB (baseline: {self._baseline_memory_mb:.0f}MB)")

                if memory_mb > self.max_memory_mb:
                    issues.append(f"Memory usage critical: {memory_mb:.0f}MB")
                    is_healthy = False

                # CPU at 100% but no progress = likely stuck
                if cpu_percent > 95.0 and is_stuck:
                    issues.append(f"High CPU ({cpu_percent:.0f}%) with no progress - likely stuck")

            except psutil.NoSuchProcess:
                pass

        # Check 4: Error rate
        if cycles_completed > 10:
            error_rate = errors_last_hour / max(cycles_completed, 1)
            if error_rate > self.error_rate_threshold:
                issues.append(f"High error rate: {error_rate*100:.0f}% ({errors_last_hour} errors)")
                is_healthy = False

        status = HealthStatus(
            timestamp=datetime.now(),
            is_healthy=is_healthy,
            is_stuck=is_stuck,
            process_alive=process_alive,
            last_cycle_time=last_cycle_time,
            cycles_completed=cycles_completed,
            trades_last_hour=trades_last_hour,
            errors_last_hour=errors_last_hour,
            memory_mb=memory_mb,
            cpu_percent=cpu_percent,
            issues=issues
        )

        self._last_health_status = status

        # Track consecutive unhealthy
        if is_healthy:
            self._consecutive_unhealthy = 0
        else:
            self._consecutive_unhealthy += 1

        return status

    def should_restart(self) -> bool:
        """
        Determine if auto_trader should be restarted.

        Restart if:
        - Process dead
        - Stuck for 3+ consecutive checks
        - Memory leak detected
        """
        if self._last_health_status is None:
            return False

        # Process dead
        if not self._last_health_status.process_alive:
            logger.warning("Auto-trader process is dead - should restart")
            return True

        # Stuck for 3+ checks
        if self._consecutive_unhealthy >= 3 and self._last_health_status.is_stuck:
            logger.warning(f"Auto-trader stuck for {self._consecutive_unhealthy} checks - should restart")
            return True

        # Memory leak
        if self._last_health_status.memory_mb > self.max_memory_mb:
            logger.warning(f"Memory too high ({self._last_health_status.memory_mb:.0f}MB) - should restart")
            return True

        return False

    def get_status_summary(self) -> str:
        """Get a human-readable status summary."""
        if self._last_health_status is None:
            return "No health check performed yet"

        status = self._last_health_status
        
        if status.is_healthy:
            return f"HEALTHY - {status.cycles_completed} cycles, {status.trades_last_hour} trades/hr"
        else:
            return f"UNHEALTHY - Issues: {', '.join(status.issues)}"
