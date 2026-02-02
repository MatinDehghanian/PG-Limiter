"""
Smart Punishment System for Limiter
This module provides an escalating punishment system based on violation history.

The system tracks violations within a configurable time window and applies
progressively harsher punishments based on the violation count.

Example configuration:
{
    "punishment": {
        "enabled": true,
        "window_hours": 72,  // 3 days
        "steps": [
            {"type": "warning", "duration": 0},
            {"type": "disable", "duration": 15},  // 15 minutes
            {"type": "disable", "duration": 60},  // 1 hour
            {"type": "disable", "duration": 240}, // 4 hours
            {"type": "disable", "duration": 0}    // unlimited (0 = permanent until manual)
        ]
    }
}
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Optional

from utils.logs import get_logger

punishment_logger = get_logger("punishment")


@dataclass
class PunishmentStep:
    """Represents a single punishment step"""
    step_type: str  # "warning", "disable", or "revoke"
    duration_minutes: int  # 0 = unlimited/permanent for disable, ignored for warning/revoke
    
    def is_warning(self) -> bool:
        """Check if this step is a warning only"""
        return self.step_type == "warning"
    
    def is_unlimited_disable(self) -> bool:
        """Check if this step is an unlimited/permanent disable"""
        return self.step_type == "disable" and self.duration_minutes == 0
    
    def is_revoke(self) -> bool:
        """Check if this step revokes the subscription (changes UUID)"""
        return self.step_type == "revoke"
    
    def get_duration_seconds(self) -> int:
        """Get duration in seconds"""
        return self.duration_minutes * 60
    
    def get_display_text(self) -> str:
        """Get human-readable text for this step"""
        if self.is_warning():
            return "⚠️ Warning only"
        if self.is_revoke():
            return "🔄 Revoke subscription + Disable"
        if self.is_unlimited_disable():
            return "🚫 Unlimited disable"
        # Format duration nicely
        minutes = self.duration_minutes
        if minutes < 60:
            return f"🔒 {minutes} minute{'s' if minutes != 1 else ''} disable"
        hours = minutes // 60
        remaining_mins = minutes % 60
        if remaining_mins == 0:
            return f"🔒 {hours} hour{'s' if hours != 1 else ''} disable"
        return f"🔒 {hours}h {remaining_mins}m disable"


@dataclass
class ViolationRecord:
    """Represents a single violation record"""
    username: str
    timestamp: float
    step_applied: int  # Which step was applied (0-indexed)
    disable_duration: int  # Duration in minutes (0 = unlimited or warning)
    enabled_at: Optional[float] = None  # When user was re-enabled (for timed disables)


class PunishmentSystem:
    """
    Smart punishment system with escalating penalties.
    
    Tracks user violations within a configurable time window and applies
    progressively harsher punishments based on violation count.
    """
    
    DEFAULT_STEPS = [
        PunishmentStep("warning", 0),
        PunishmentStep("disable", 10),
        PunishmentStep("disable", 30),
        PunishmentStep("disable", 60),
        PunishmentStep("disable", 0),  # Unlimited
    ]
    
    DEFAULT_WINDOW_HOURS = 168  # 7 days
    
    def __init__(self, filename=".violation_history.json"):
        self.filename = filename
        self.violations: dict[str, list[ViolationRecord]] = {}  # username -> list of violations
        self.steps: list[PunishmentStep] = self.DEFAULT_STEPS.copy()
        self.window_hours: int = self.DEFAULT_WINDOW_HOURS
        self.enabled: bool = True
        self.load_violations()
    
    def load_violations(self):
        """Load violation history from file"""
        try:
            if os.path.exists(self.filename):
                punishment_logger.debug(f"📂 Loading violation history from {self.filename}")
                with open(self.filename, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    
                    for username, records in data.get("violations", {}).items():
                        self.violations[username] = []
                        for record in records:
                            self.violations[username].append(ViolationRecord(
                                username=record["username"],
                                timestamp=record["timestamp"],
                                step_applied=record["step_applied"],
                                disable_duration=record["disable_duration"],
                                enabled_at=record.get("enabled_at")
                            ))
                    
                    # Clean up old violations
                    self.cleanup_old_violations()
                    
                    punishment_logger.info(f"✅ Loaded violation history for {len(self.violations)} users")
        except Exception as e:
            punishment_logger.error(f"❌ Error loading violation history: {e}")
            self.violations = {}
    
    async def save_violations(self):
        """Save violation history to file"""
        try:
            data = {"violations": {}}
            
            for username, records in self.violations.items():
                data["violations"][username] = []
                for record in records:
                    data["violations"][username].append({
                        "username": record.username,
                        "timestamp": record.timestamp,
                        "step_applied": record.step_applied,
                        "disable_duration": record.disable_duration,
                        "enabled_at": record.enabled_at
                    })
            
            with open(self.filename, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2)
                
            punishment_logger.debug(f"💾 Saved violation history for {len(self.violations)} users")
        except Exception as e:
            punishment_logger.error(f"❌ Error saving violation history: {e}")
    
    def load_config(self, config_data: dict):
        """
        Load punishment configuration from config data.
        
        Args:
            config_data: Configuration dictionary with optional 'punishment' key
        """
        punishment_config = config_data.get("punishment", {})
        
        self.enabled = punishment_config.get("enabled", True)
        self.window_hours = punishment_config.get("window_hours", self.DEFAULT_WINDOW_HOURS)
        
        # Load steps from config
        steps_config = punishment_config.get("steps", None)
        if steps_config and isinstance(steps_config, list) and len(steps_config) > 0:
            self.steps = []
            for step in steps_config:
                step_type = step.get("type", "disable")
                duration = step.get("duration", 0)
                self.steps.append(PunishmentStep(step_type, duration))
            punishment_logger.info(f"📋 Loaded {len(self.steps)} punishment steps from config (window: {self.window_hours}h)")
        else:
            self.steps = self.DEFAULT_STEPS.copy()
            punishment_logger.debug("📋 Using default punishment steps")
    
    def cleanup_old_violations(self):
        """Remove violations older than the time window"""
        current_time = time.time()
        window_seconds = self.window_hours * 60 * 60
        cutoff_time = current_time - window_seconds
        
        for username in list(self.violations.keys()):
            # Filter out old violations
            self.violations[username] = [
                v for v in self.violations[username]
                if v.timestamp > cutoff_time
            ]
            # Remove user if no recent violations
            if not self.violations[username]:
                del self.violations[username]
    
    def get_violation_count(self, username: str) -> int:
        """
        Get the number of violations for a user within the time window.
        
        Args:
            username: The username to check
            
        Returns:
            Number of violations in the time window
        """
        self.cleanup_old_violations()
        return len(self.violations.get(username, []))
    
    def get_next_step_index(self, username: str) -> int:
        """
        Get the index of the next punishment step for a user.
        
        Args:
            username: The username to check
            
        Returns:
            Step index (0-indexed), capped at max step
        """
        violation_count = self.get_violation_count(username)
        # Cap at the last step
        return min(violation_count, len(self.steps) - 1)
    
    def get_next_punishment(self, username: str) -> PunishmentStep:
        """
        Get the next punishment step for a user.
        
        Args:
            username: The username to check
            
        Returns:
            The PunishmentStep to apply
        """
        step_index = self.get_next_step_index(username)
        return self.steps[step_index]
    
    async def record_violation(self, username: str, step_applied: int, duration_minutes: int):
        """
        Record a new violation for a user.
        
        Args:
            username: The username
            step_applied: Which step was applied (0-indexed)
            duration_minutes: Duration of disable in minutes (0 for warning or unlimited)
        """
        if username not in self.violations:
            self.violations[username] = []
        
        record = ViolationRecord(
            username=username,
            timestamp=time.time(),
            step_applied=step_applied,
            disable_duration=duration_minutes
        )
        
        self.violations[username].append(record)
        await self.save_violations()
        
        punishment_logger.info(f"📝 Recorded violation #{len(self.violations[username])} for {username} (step {step_applied}, duration: {duration_minutes}min)")
    
    async def clear_user_history(self, username: str):
        """Clear all violation history for a user"""
        if username in self.violations:
            del self.violations[username]
            await self.save_violations()
            punishment_logger.info(f"🗑️ Cleared violation history for {username}")
    
    async def clear_all_history(self):
        """Clear all violation history"""
        self.violations = {}
        await self.save_violations()
        punishment_logger.info("🗑️ Cleared all violation history")
    
    def get_user_status(self, username: str) -> dict:
        """
        Get detailed status for a user.
        
        Args:
            username: The username to check
            
        Returns:
            Dict with violation_count, next_step, history details
        """
        self.cleanup_old_violations()
        
        violations = self.violations.get(username, [])
        next_step_idx = self.get_next_step_index(username)
        next_step = self.steps[next_step_idx]
        
        return {
            "username": username,
            "violation_count": len(violations),
            "window_hours": self.window_hours,
            "next_step_index": next_step_idx,
            "next_punishment": next_step.get_display_text(),
            "is_warning_next": next_step.is_warning(),
            "is_unlimited_next": next_step.is_unlimited_disable(),
            "recent_violations": [
                {
                    "timestamp": v.timestamp,
                    "time_ago": self._format_time_ago(v.timestamp),
                    "step": v.step_applied,
                    "duration": v.disable_duration
                }
                for v in violations[-5:]  # Last 5 violations
            ]
        }
    
    def _format_time_ago(self, timestamp: float) -> str:
        """Format timestamp as 'X ago' string"""
        diff = time.time() - timestamp
        if diff < 60:
            return f"{int(diff)}s ago"
        if diff < 3600:
            return f"{int(diff / 60)}m ago"
        if diff < 86400:
            return f"{int(diff / 3600)}h ago"
        return f"{int(diff / 86400)}d ago"
    
    def get_steps_summary(self) -> str:
        """Get a formatted summary of all punishment steps"""
        lines = [f"📋 <b>Punishment Steps</b> (window: {self.window_hours}h):\n"]
        for i, step in enumerate(self.steps, 1):
            lines.append(f"  {i}. {step.get_display_text()}")
        return "\n".join(lines)


# Global instance
_punishment_system: Optional[PunishmentSystem] = None


def get_punishment_system() -> PunishmentSystem:
    """Get or create the global punishment system instance"""
    global _punishment_system
    if _punishment_system is None:
        _punishment_system = PunishmentSystem()
    return _punishment_system


async def get_punishment_for_user(username: str, config_data: dict) -> tuple[PunishmentStep, int, int]:
    """
    Get the punishment to apply for a user.
    
    Args:
        username: The username
        config_data: Configuration data with punishment settings
        
    Returns:
        Tuple of (PunishmentStep, step_index, violation_count)
    """
    system = get_punishment_system()
    system.load_config(config_data)
    
    if not system.enabled:
        # Punishment system disabled - use unlimited disable as default
        return PunishmentStep("disable", 0), 0, 0
    
    violation_count = system.get_violation_count(username)
    step_index = system.get_next_step_index(username)
    punishment = system.get_next_punishment(username)
    
    return punishment, step_index, violation_count


async def record_user_violation(username: str, step_index: int, duration_minutes: int):
    """Record a violation for a user"""
    system = get_punishment_system()
    await system.record_violation(username, step_index, duration_minutes)
