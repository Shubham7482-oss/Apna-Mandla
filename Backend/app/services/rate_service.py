
# Placeholder for configuration values
BASE_DELIVERY_FEE = 50.0  # Base fee for any delivery
PER_KILOMETER_RATE = 7.0    # Rate per kilometer

def calculate_delivery_fee(distance_km: float) -> float:
    """
    Calculates the delivery fee based on the distance.
    
    Args:
        distance_km: The total distance of the delivery in kilometers.
        
    Returns:
        The calculated delivery fee.
    """
    if distance_km < 0:
        raise ValueError("Distance cannot be negative.")
        
    # Simple calculation: Base fee + (distance * rate per km)
    fee = BASE_DELIVERY_FEE + (distance_km * PER_KILOMETER_RATE)
    
    # Round to 2 decimal places for currency
    return round(fee, 2)
