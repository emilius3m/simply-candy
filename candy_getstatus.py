import os
import requests

CANDY_IP = '192.168.1.235'
TIMEOUT = 10

# stringa nota usata per ricavare la chiave di cifratura
KNOWN_RESPONSE = '{"response":"SUCCESS"}'

# prefisso noto della risposta di stato (per fallback + validazione chiave)
KNOWN_STATUS_PREFIX = '{\r\n\t"statusLavatrice":{\r\n\t\t"WiFiStatus":"'

# file di cache della chiave (la chiave e' fissa per dispositivo)
_KEY_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'candy_key.cache')


def getkey():
    """Recupera la chiave in modo robusto:
    1) cache su disco (se valida)
    2) estrazione da BM=1 + validazione
    3) fallback known-plaintext sul read endpoint
    La prima chiave valida trovata viene cachata per gli usi successivi."""
    # 1) cache
    cached = _load_cache()
    if cached and _key_valid(cached):
        return cached

    # 2) BM=1
    try:
        hex_in = requests.get(
            "http://" + CANDY_IP + "/http-write.json?encrypted=1&BM=1",
            timeout=TIMEOUT).text
        key = "".join(
            chr(ord(KNOWN_RESPONSE[i]) ^ int(hex_in[i * 2:i * 2 + 2], 16))
            for i in range(0, min(16, len(KNOWN_RESPONSE))))[:16]
        if _key_valid(key):
            _save_cache(key)
            return key
    except Exception:
        pass

    # 3) fallback known-plaintext
    key = _key_from_read()
    if key:
        _save_cache(key)
        return key

    # best-effort
    return key


def _key_valid(key):
    """Verifica che la chiave decodifichi correttamente lo stato corrente."""
    try:
        status = requests.get(
            "http://" + CANDY_IP + "/http-read.json?encrypted=1",
            timeout=TIMEOUT).text
        return '"statusLavatrice"' in decode_raw(status, key)
    except Exception:
        return False


def _key_from_read():
    """Recupera la chiave dal read endpoint via attacco known-plaintext."""
    try:
        raw = requests.get("http://" + CANDY_IP + "/http-read.json?encrypted=1",
                           timeout=TIMEOUT).text
    except Exception:
        return None
    known = KNOWN_STATUS_PREFIX
    partial = {}
    for i in range(len(known)):
        k = chr(int(raw[i * 2:i * 2 + 2], 16) ^ ord(known[i]))
        pos = i % 16
        if pos in partial and partial[pos] != k:
            return None  # incoerente
        partial[pos] = k
    if len(partial) == 16:
        return "".join(partial[i] for i in range(16))
    return None


def _save_cache(key):
    try:
        with open(_KEY_CACHE, "w") as f:
            f.write(key)
    except Exception:
        pass


def _load_cache():
    try:
        with open(_KEY_CACHE) as f:
            return f.read().strip()
    except Exception:
        return None


def decode_raw(status, key):
    """Decifra una risposta esadecimale in testo."""
    return "".join([chr(ord(key[idx % len(key)]) ^ int(status[i:i+2], 16))
                    for idx, i in enumerate(range(0, len(status), 2))])


def decode(uri):
    """Legge e decifra un endpoint della lavatrice."""
    status = requests.get("http://" + CANDY_IP + "/" + uri,
                          timeout=TIMEOUT).text
    return decode_raw(status, key)


key = getkey()

print(key)
print(decode("http-read.json?encrypted=1"))
print(decode("http-getStatistics.json?encrypted=1"))
