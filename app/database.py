# Database module - kept minimal for compatibility
# All data is now stored on filesystem / env vars

def is_db_available() -> bool:
    """Database is not used."""
    return False
