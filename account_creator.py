import os
import random
import concurrent.futures
import requests
import bs4
import re

BASE_URL = "https://opengoon.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
}

DEFAULT_PASSWORD = "Shanucom101@"

FREE_PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=2500&country=all&ssl=all&anonymity=all",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
]

def fetch_fresh_proxy_candidates():
    """Fetches a list of public HTTP proxies from multiple sources."""
    proxies = set()
    for source in FREE_PROXY_SOURCES:
        try:
            r = requests.get(source, timeout=4)
            if r.status_code == 200:
                lines = r.text.strip().splitlines()
                for line in lines:
                    line = line.strip()
                    if ":" in line and not line.startswith("#"):
                        proxies.add(f"http://{line}")
        except Exception:
            continue
    proxy_list = list(proxies)
    random.shuffle(proxy_list)
    return proxy_list

def test_single_proxy(proxy_url: str):
    """Tests a single proxy against ipify API."""
    s = requests.Session()
    s.headers.update(HEADERS)
    s.proxies = {"http": proxy_url, "https": proxy_url}
    try:
        r = s.get("https://api.ipify.org?format=json", timeout=2.5)
        if r.status_code == 200:
            ip = r.json().get("ip")
            if ip:
                return s, ip, proxy_url
    except Exception:
        pass
    return None

def get_working_proxy_session() -> tuple[requests.Session, str]:
    """Multithreaded Fast Free Proxy Auto-Fetcher."""
    candidates = fetch_fresh_proxy_candidates()

    if candidates:
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            futures = [executor.submit(test_single_proxy, p) for p in candidates[:30]]
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    session, out_ip, proxy_url = result
                    print(f"✅ Fast working free proxy found: {out_ip} ({proxy_url})")
                    return session, out_ip

    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        my_ip = session.get("https://api.ipify.org?format=json", timeout=3).json().get("ip", "Direct-IP")
    except Exception:
        my_ip = "Direct-IP"
    return session, my_ip

def get_csrf_token(session: requests.Session, url: str = BASE_URL) -> str:
    """Fetches target page and extracts CSRF token."""
    resp = session.get(url)
    soup = bs4.BeautifulSoup(resp.text, "html.parser")
    meta = soup.find("meta", {"name": "csrf-token"})
    if meta and meta.get("content"):
        return meta["content"]
    match = re.search(r'name="csrf-token"\s+content="([^"]+)"', resp.text)
    if match:
        return match.group(1)
    raise ValueError("Failed to obtain CSRF Token from Opengoon.")

def register_opengoon_account(email: str, password: str = DEFAULT_PASSWORD, invite_url: str = None):
    """Submits new account signup to POST /users."""
    session, outgoing_ip = get_working_proxy_session()

    target_url = invite_url if invite_url else BASE_URL
    try:
        csrf_token = get_csrf_token(session, target_url)
    except Exception as e:
        return False, 500, f"Failed to connect via IP {outgoing_ip}: {str(e)}", outgoing_ip

    signup_url = f"{BASE_URL}/users"
    payload = {
        "authenticity_token": csrf_token,
        "user[email_address]": email,
        "user[password]": password,
        "user[password_confirmation]": password,
        "commit": "Create account",
    }
    signup_headers = {
        **HEADERS,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRF-Token": csrf_token,
        "X-Requested-With": "XMLHttpRequest",
    }

    try:
        reg_resp = session.post(signup_url, data=payload, headers=signup_headers)

        if reg_resp.status_code in (200, 302):
            return True, reg_resp.status_code, "Registration submitted successfully! Check inbox for verification link.", outgoing_ip
        else:
            soup = bs4.BeautifulSoup(reg_resp.text, "html.parser")
            alerts = [el.text.strip() for el in soup.find_all(class_=lambda x: x and "alert" in str(x))]
            msg = " ".join(alerts) if alerts else reg_resp.text[:200]
            return False, reg_resp.status_code, f"Registration failed ({reg_resp.status_code}): {msg}", outgoing_ip
    except Exception as e:
        return False, 500, f"Error sending signup via IP {outgoing_ip}: {str(e)}", outgoing_ip

def login_opengoon_account(email: str, password: str = DEFAULT_PASSWORD):
    """
    Submits POST /session with email and password (default Shanucom101@).
    Returns (success: bool, cookie_str or error_msg).
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        csrf_token = get_csrf_token(session, BASE_URL)
    except Exception as e:
        return False, f"Connection error: {str(e)}"

    login_url = f"{BASE_URL}/session"
    payload = {
        "authenticity_token": csrf_token,
        "email_address": email,
        "password": password,
    }
    login_headers = {
        **HEADERS,
        "X-CSRF-Token": csrf_token,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json, text/html, */*",
    }

    try:
        r = session.post(login_url, data=payload, headers=login_headers)
        cookie_header = "; ".join([f"{k}={v}" for k, v in session.cookies.items()])

        if "_opengoon_session" in session.cookies or "session_id" in session.cookies:
            return True, cookie_header

        soup = bs4.BeautifulSoup(r.text, "html.parser")
        alerts = [el.text.strip() for el in soup.find_all(class_=lambda x: x and "alert" in str(x))]
        err_msg = " ".join(alerts) if alerts else "Login failed. Please ensure the email is verified."
        return False, err_msg
    except Exception as e:
        return False, f"Login exception: {str(e)}"

def fetch_opengoon_balance(cookie_str: str) -> int:
    """Fetches available balance/credits from logged-in Opengoon session."""
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        for item in cookie_str.split(";"):
            if "=" in item:
                k, v = item.strip().split("=", 1)
                session.cookies.set(k, v, domain="opengoon.com")
        r = session.get(BASE_URL, timeout=5)
        if r.status_code == 200:
            m = re.search(r'(\d+)\s*(?:credits?|points?|generations?)', r.text, re.IGNORECASE)
            if m:
                return int(m.group(1))
    except Exception:
        pass
    return 5
