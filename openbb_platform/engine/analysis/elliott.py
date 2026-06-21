from core.TRADING_DOMAIN_KNOWLEDGE_REFERENCE import ELLIOTT_RULES

def validate_motive_wave(w1, w2, w3, w4, w5):
    """
    Hedge-Fund Grade: Validates the 3 Absolute Rules of Elliott Waves.
    1. Wave 2 never retraces more than 100% of Wave 1.
    2. Wave 3 is never the shortest.
    3. Wave 4 never overlaps Wave 1 (except in diagonals).
    """
    # Rule 1
    if w2 >= w1: return False
    
    # Rule 2: Wave 3 cannot be the shortest
    lens = [abs(w1), abs(w3), abs(w5)]
    if abs(w3) == min(lens): return False
    
    # Rule 3: Overlap check
    if w4 <= w1: return False # Simplified for Bullish
    
    return True
