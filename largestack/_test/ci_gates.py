"""CI/CD quality gates — block deployment on quality regression."""
from __future__ import annotations
from typing import Any

class QualityGate:
    """Define and check quality thresholds for CI/CD.
    
    Default gates:
        task_completion >= 0.85
        tool_correctness >= 0.90
        hallucination_rate <= 0.02
        cost_regression <= 20%
        p99_latency <= 30s
    """
    def __init__(self, thresholds: dict = None):
        self.thresholds = thresholds or {
            "task_completion": (">=", 0.85),
            "tool_correctness": (">=", 0.90),
            "hallucination_rate": ("<=", 0.02),
            "cost_per_run": ("<=", 1.00),
            "p99_latency_s": ("<=", 30.0),
            "test_pass_rate": (">=", 0.95),
        }
    
    def check(self, metrics: dict) -> dict:
        """Check metrics against thresholds. Returns pass/fail per gate."""
        results = {"passed": True, "gates": {}}
        for name, (op, threshold) in self.thresholds.items():
            value = metrics.get(name)
            if value is None:
                results["gates"][name] = {"status": "skipped", "reason": "no data"}
                continue
            
            if op == ">=" and value >= threshold:
                results["gates"][name] = {"status": "pass", "value": value, "threshold": threshold}
            elif op == "<=" and value <= threshold:
                results["gates"][name] = {"status": "pass", "value": value, "threshold": threshold}
            else:
                results["gates"][name] = {"status": "FAIL", "value": value, "threshold": threshold}
                results["passed"] = False
        
        return results
    
    def format_report(self, results: dict) -> str:
        lines = [f"Quality Gate: {'PASSED ✅' if results['passed'] else 'FAILED ❌'}"]
        for name, gate in results["gates"].items():
            icon = "✅" if gate["status"] == "pass" else "❌" if gate["status"] == "FAIL" else "⏭️"
            lines.append(f"  {icon} {name}: {gate.get('value', 'N/A')} (threshold: {gate.get('threshold', 'N/A')})")
        return "\n".join(lines)
