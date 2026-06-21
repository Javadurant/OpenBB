import pandas as pd
import numpy as np
from typing import Dict, List, Optional

# SELIVANOV: Robust import handling for the Risk Module
try:
    from engine.risk.risk_management import calculate_position_size, get_dynamic_risk_params
except ImportError:
    # NILSSON: Fallback safety to prevent runtime crashes if risk module is not yet deployed
    def get_dynamic_risk_params(df, side): 
        # Default 5% Stop / 10% Target for compliance fallback
        current_price = df['close'].iloc[-1]
        if side == "BUY":
            return {'stop_loss': current_price * 0.95, 'take_profit': current_price * 1.10}
        return {'stop_loss': current_price * 1.05, 'take_profit': current_price * 0.90}

def run_backtest(df: pd.DataFrame, signals_output: dict, initial_cap: float = 10000.0):
    """
    Simulates trading performance. 
    Standardized for OpenBB Architecture to prevent ChainedAssignmentErrors and ensure 
    numerical stability in equity growth calculations.
    """
    # SELIVANOV: Initial state validation
    if df is None or df.empty:
        return {"results": pd.DataFrame(), "equity_curve": []}

    # PAEZ: Use a copy to avoid SettingWithCopyWarning in Pandas
    df = df.copy()
    current_signal = signals_output.get('signal', 'NEUTRAL')
    
    # Initialize signals column
    if 'trade_signal' not in df.columns:
        df['trade_signal'] = 0
        
    # Map current execution signal to the terminal bar for "Last-Bar Validation"
    if current_signal == "BUY": 
        df.loc[df.index[-1], 'trade_signal'] = 1
    elif current_signal == "SELL": 
        df.loc[df.index[-1], 'trade_signal'] = -1

    # KARPATHY: Use np.float64 for equity tracking to maintain precision across thousands of iterations
    equity = np.full(len(df), float(initial_cap), dtype=np.float64)
    trades = []
    active_pos: Optional[Dict] = None

    # Performance Loop: Sequential Simulation
    for i in range(1, len(df)):
        equity[i] = equity[i-1]
        current_price = float(df['close'].iloc[i])
        
        # 1. MANAGE ACTIVE POSITION
        if active_pos:
            closed = False
            # PAEZ: Logic for checking Stop Loss / Take Profit
            if active_pos['side'] == 'BUY':
                if current_price <= active_pos['sl']:
                    # Exit at Stop Loss
                    equity[i] -= active_pos['risk_amt']
                    closed = True
                elif current_price >= active_pos['tp']:
                    # Exit at Take Profit (2R Reward standard)
                    equity[i] += (active_pos['risk_amt'] * 2.0)
                    closed = True
            elif active_pos['side'] == 'SELL':
                if current_price >= active_pos['sl']:
                    equity[i] -= active_pos['risk_amt']
                    closed = True
                elif current_price <= active_pos['tp']:
                    equity[i] += (active_pos['risk_amt'] * 2.0)
                    closed = True
            
            if closed:
                trades.append({
                    "res": 1 if equity[i] > equity[i-1] else -1,
                    "exit_price": current_price,
                    "profit": equity[i] - equity[i-1]
                })
                active_pos = None
        
        # 2. OPEN NEW POSITION
        # Logic: Only open if neutral and a signal exists at index i
        elif df['trade_signal'].iloc[i] != 0:
            side = "BUY" if df['trade_signal'].iloc[i] == 1 else "SELL"
            
            # NILSSON: Risk 2% of CURRENT equity per trade (Compound Risking)
            risk_amt = equity[i] * 0.02 
            
            params = get_dynamic_risk_params(df.iloc[:i+1], side)
            
            # PAEZ: Fallback SL/TP if risk engine returns 0 or None
            sl = params.get('stop_loss') or (current_price * 0.95 if side == "BUY" else current_price * 1.05)
            tp = params.get('take_profit') or (current_price * 1.10 if side == "BUY" else current_price * 0.90)
            
            active_pos = {
                "side": side, 
                "sl": float(sl), 
                "tp": float(tp),
                "risk_amt": float(risk_amt),
                "entry_price": current_price
            }
    
    # KARPATHY: Final metric computation
    wins = [t for t in trades if t['res'] > 0]
    win_rate = len(wins) / len(trades) if trades else 0.0
    
    # PAEZ: Drawdown Calculation
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    max_dd = np.min(drawdown)

    return {
        "results": pd.DataFrame({
            "Metric": ["Final Equity", "Total Trades", "Win Rate", "Max Drawdown"],
            "Value": [
                f"${equity[-1]:.2f}", 
                str(len(trades)), 
                f"{win_rate:.2%}",
                f"{max_dd:.2%}"
            ]
        }),
        "equity_curve": equity.tolist(),
        "trade_log": trades
    }