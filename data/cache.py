import os
import pickle
from datetime import datetime, timedelta
from config import DATA_CACHE_DIR, CACHE_EXPIRY_HOURS

os.makedirs(DATA_CACHE_DIR, exist_ok=True)


def _cache_path(key):
    safe = key.replace("/", "_").replace("^", "").replace(" ", "_")
    return os.path.join(DATA_CACHE_DIR, f"{safe}.pkl")


def get_cache(key):
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            entry = pickle.load(f)
        if datetime.now() - entry["ts"] > timedelta(hours=CACHE_EXPIRY_HOURS):
            return None
        return entry["data"]
    except Exception:
        return None


def set_cache(key, data):
    path = _cache_path(key)
    try:
        with open(path, "wb") as f:
            pickle.dump({"data": data, "ts": datetime.now()}, f)
    except Exception:
        pass


def clear_cache():
    for fname in os.listdir(DATA_CACHE_DIR):
        if fname.endswith(".pkl"):
            os.remove(os.path.join(DATA_CACHE_DIR, fname))
