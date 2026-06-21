# engine/portfolio_optimizer.py
import pandas as pd
import numpy as np
from typing import Dict, List, Any
import logging

# SELIVANOV: High-performance numerical imports
# KARPATHY: Ensure float64 precision for covariance matrix inversion
logger = logging.getLogger(__name__)

class PortfolioOptimizer:
    """
    Institutional Portfolio Optimizer.
    Combines Technical Evidence Scores with Mean-Variance Optimization constraints.
    """
    
    def __init__(self, max_exposure_per_asset: float = 0.25, total_gross_limit: float = 1.0):
        self.max_exposure = max_exposure_per_asset
        self.total_limit = total_gross_limit
        
    def calculate_weights(self, assets_data: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
        """
        Calculates optimal weights based on Institutional Scores and Volatility.
        
        Args:
            assets_data: { 'BTC': {'score': 0.85, 'returns': pd.Series(...)}, ... }
        """
        symbols = list(assets_data.keys())
        if not symbols:
            return pd.DataFrame()

        # 1. SCORE AGGREGATION (PAEZ LOGIC)
        scores = np.array([assets_data[s]['score'] for s in symbols])
        
        # 2. VOLATILITY ESTIMATION (KARPATHY NUMERICAL STABILITY)
        returns_df = pd.DataFrame({s: assets_data[s]['returns'] for s in symbols}).dropna()
        
        if returns_df.empty or len(returns_df) < 10:
            # Fallback to score-weighted if no return history
            norm_scores = scores / np.sum(scores) if np.sum(scores) > 0 else np.full(len(symbols), 1/len(symbols))
            return pd.DataFrame({"Symbol": symbols, "Weight": norm_scores})

        # Calculate Covariance Matrix
        cov_matrix = returns_df.cov().values
        inv_cov = np.linalg.pinv(cov_matrix) # Pseudo-inverse for stability
        
        # 3. OPTIMIZATION: Black-Litterman Inspired Weighting
        # We blend Inverse Volatility with the Institutional Alpha Score
        ones = np.ones(len(symbols))
        min_var_weights = dot_product_inv = inv_cov @ ones
        min_var_weights /= np.sum(min_var_weights)
        
        # NILSSON: Enforce Exposure Constraints
        # Combine Score (Alpha) and Min-Var (Risk)
        raw_weights = min_var_weights * (1 + scores) 
        
        # Final Normalization and Clipping
        final_weights = raw_weights / np.sum(raw_weights)
        final_weights = np.clip(final_weights, 0, self.max_exposure)
        
        # Re-normalize to satisfy Nilsson's total limit
        final_weights = (final_weights / np.sum(final_weights)) * self.total_limit

        return pd.DataFrame({
            "Symbol": symbols,
            "Institutional_Score": scores,
            "Optimal_Weight": np.round(final_weights, 4),
            "Allocation_USD": np.round(final_weights * 10000, 2) # Example $10k portfolio
        }).sort_values(by="Optimal_Weight", ascending=False)

    def check_compliance(self, weights_df: pd.DataFrame) -> bool:
        """
        NILSSON: Mandatory Risk Audit.
        Ensures no single asset exceeds the mandate and sum equals total limit.
        """
        if weights_df.empty: return False
        
        total_weight = weights_df['Optimal_Weight'].sum()
        max_asset_weight = weights_df['Optimal_Weight'].max()
        
        # Allow 0.1% tolerance for float precision errors (Karpathy standard)
        is_total_valid = np.isclose(total_weight, self.total_limit, atol=1e-3)
        is_exposure_valid = max_asset_weight <= (self.max_exposure + 1e-3)
        
        if not (is_total_valid and is_exposure_valid):
            logger.error(f"Compliance Violation: Total={total_weight}, Max={max_asset_weight}")
            return False
            
        return True



def get_portfolio_summary(weights_df: pd.DataFrame):
    """
    PAEZ: Formats the optimizer output for the OpenBB Workspace UI.
    """
    if weights_df.empty:
        return "Insufficient data for portfolio optimization."
    
    top_asset = weights_df.iloc[0]['Symbol']
    return f"Optimization complete. Lead allocation: {top_asset} at {weights_df.iloc[0]['Optimal_Weight']:.2%}."