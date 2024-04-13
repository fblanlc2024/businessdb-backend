import datetime
from datetime import datetime, timedelta
import logging

class RedisLayer:
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.MAX_LOGIN_ATTEMPTS = 5
        self.LOGIN_ATTEMPT_WINDOW = 900  # Time in seconds

    # Max 5 login attempts, refreshes after 15 minutes
    def increment_login_attempts(self, client_ip, username):
        key = f"login_attempts:{client_ip}:{username}"
        attempts = self.redis_client.incr(key)
        self.redis_client.expire(key, self.LOGIN_ATTEMPT_WINDOW)
        return attempts

    # see comment above for expiration
    def set_expiry_for_username(self, username):
        expiry_key = f"username_expiry:{username}"
        if not self.redis_client.exists(expiry_key):
            expiry_timestamp = datetime.utcnow() + timedelta(minutes=15)
            self.redis_client.set(expiry_key, expiry_timestamp.strftime('%Y-%m-%d %H:%M:%S'), ex=900)

    def get_remaining_attempts(self, client_ip, username):
        key = f"login_attempts:{client_ip}:{username}"
        attempts = self.redis_client.get(key)
        if not attempts:
            return self.MAX_LOGIN_ATTEMPTS
        return max(self.MAX_LOGIN_ATTEMPTS - int(attempts), 0)

    def get_remaining_minutes(self, username):
        expiry_key = f"username_expiry:{username}"
        expiry_timestamp = self.redis_client.get(expiry_key)
        if expiry_timestamp:
            expiry_time = datetime.strptime(expiry_timestamp.decode(), '%Y-%m-%d %H:%M:%S')
            remaining_time = expiry_time - datetime.utcnow()
            return max(0, int(remaining_time.total_seconds() / 60))
        return 0
    
    def is_ip_rate_limited(self, client_ip):
        ip_rate_limit_key = f"ip_rate_limit:{client_ip}"
        return self.redis_client.exists(ip_rate_limit_key)

    def set_ip_rate_limit(self, client_ip, lockout_duration=3600):
        ip_rate_limit_key = f"ip_rate_limit:{client_ip}"
        self.redis_client.set(ip_rate_limit_key, 1, ex=lockout_duration)
        logging.info(f"Set a {lockout_duration // 60} minute rate limit lockout for IP: {client_ip}")