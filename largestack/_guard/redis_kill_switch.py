"""Redis-based kill switch for distributed deployments.

File-based (default) for single-node. Redis for multi-node clusters.
Cascade: killing parent halts all children via pub/sub.
"""
from __future__ import annotations
import time, logging
from largestack._guard import kill_switch as file_ks

log = logging.getLogger("largestack.kill_switch")

class RedisKillSwitch:
    """Distributed kill switch using Redis pub/sub."""
    
    def __init__(self, redis_url: str = "redis://localhost:6379", channel: str = "largestack:kill_switch"):
        self.channel = channel
        self._redis = None
        self._active = False
        
        try:
            import redis
            self._redis = redis.from_url(redis_url)
            self._redis.ping()
            log.info("Redis kill switch connected")
        except (ImportError, Exception):
            log.debug("Redis not available, using file-based kill switch")
            self._redis = None
    
    def activate(self, reason: str = "manual", by: str = "operator"):
        """Activate kill switch across all nodes."""
        if self._redis:
            self._redis.set("largestack:kill_active", f"{time.time()}|{reason}|{by}")
            self._redis.publish(self.channel, f"KILL|{reason}|{by}")
            log.critical(f"REDIS KILL SWITCH by {by}: {reason}")
        else:
            file_ks.activate(reason, by)
        self._active = True
    
    def deactivate(self):
        if self._redis:
            self._redis.delete("largestack:kill_active")
            self._redis.publish(self.channel, "RESUME")
        else:
            file_ks.deactivate()
        self._active = False
    
    def is_active(self) -> bool:
        if self._redis:
            return self._redis.exists("largestack:kill_active") > 0
        return file_ks.is_active()
    
    def check(self):
        from largestack.errors import KillSwitchActivatedError
        if self.is_active():
            raise KillSwitchActivatedError()
