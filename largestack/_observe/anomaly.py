"""Triple anomaly detection: Z-Score + CUSUM + Bollinger Bands.
Alert when ANY TWO agree.
"""

from __future__ import annotations
import math
from collections import deque


class AnomalyDetector:
    """Detect cost spikes, latency regression, error bursts."""

    def __init__(
        self,
        window: int = 100,
        z_threshold: float = 3.0,
        cusum_threshold: float = 5.0,
        bollinger_k: float = 2.0,
    ):
        self.window = window
        self.z_threshold = z_threshold
        self.cusum_threshold = cusum_threshold
        self.bollinger_k = bollinger_k
        self._values: deque[float] = deque(maxlen=window)
        self._cusum_high = 0.0
        self._cusum_low = 0.0

    def check(self, value: float) -> dict:
        """Check value for anomalies. Returns {is_anomaly, detectors, details}."""
        self._values.append(value)
        if len(self._values) < 10:
            return {"is_anomaly": False, "detectors": [], "value": value}

        vals = list(self._values)
        mean = sum(vals) / len(vals)
        std = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals)) or 0.001

        detectors = []

        # 1. Modified Z-Score
        median = sorted(vals)[len(vals) // 2]
        mad = sorted(abs(v - median) for v in vals)[len(vals) // 2]
        if mad < 0.001:
            mad = std if std > 0 else 0.001  # Handle constant sequences
        z_score = 0.6745 * (value - median) / mad
        if abs(z_score) > self.z_threshold:
            detectors.append("z_score")

        # 2. CUSUM
        target = mean
        allowance = std * 0.5
        self._cusum_high = max(0, self._cusum_high + value - target - allowance)
        self._cusum_low = max(0, self._cusum_low - value + target - allowance)
        if self._cusum_high > self.cusum_threshold or self._cusum_low > self.cusum_threshold:
            detectors.append("cusum")

        # 3. Bollinger Bands
        upper = mean + self.bollinger_k * std
        lower = mean - self.bollinger_k * std
        if value > upper or value < lower:
            detectors.append("bollinger")

        is_anomaly = len(detectors) >= 2  # Alert when 2/3 agree
        return {
            "is_anomaly": is_anomaly,
            "detectors": detectors,
            "value": value,
            "z_score": round(z_score, 2),
            "mean": round(mean, 4),
            "std": round(std, 4),
            "upper_band": round(upper, 4),
            "lower_band": round(lower, 4),
        }
