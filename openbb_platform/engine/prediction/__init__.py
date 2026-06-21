"""
Prediction package public API.
Only export what actually exists.
"""

from engine.prediction.engine import predict_scenarios

__all__ = ["predict_scenarios"]
