"""Shared helpers for the expired-domain-finder pipeline.

Standard library only, so the skill runs on any machine with Python 3.9+.
Every stage reads and writes one table, <run>/domains.csv, keyed by domain.
"""
from __future__ import annotations

import base64
import csv
import json
import math
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS = SKILL_DIR / "assets"
UA = ("Mozilla/5.0 (compatible; expired-domain-finder/1.0; "
      "+https://github.com/muhiussunnah/domainfinder)")

csv.field_size_limit(10_000_000)


def setup_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- domains

DOMAIN_RE = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}$")
MULTI_SUFFIXES = {
    "co.uk", "org.uk", "me.uk", "ltd.uk", "plc.uk", "com.au", "net.au", "org.au", "co.nz",
    "net.nz", "org.nz", "co.in", "net.in", "org.in", "com.br", "co.za", "com.sg", "com.my",
    "co.jp", "com.mx", "com.ar", "com.tr", "com.cn", "com.hk", "com.tw", "co.kr", "com.ph",
    "com.pk", "com.bd", "com.ng", "co.id", "com.vn", "com.ua", "com.pl", "com.es", "com.co",
}


def normalize_domain(value: str) -> str | None:
    """Turn a URL, host or messy string into a bare registrable domain."""
    if not value:
        return None
    s = value.strip().strip('"\'').lower()
    s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", s)
    s = s.split("/")[0].split("?")[0].split("#")[0].split("@")[-1].split(":")[0].strip(".")
    if s.startswith("www."):
        s = s[4:]
    try:
        s = s.encode("idna").decode("ascii")
    except Exception:
        return None
    if not DOMAIN_RE.match(s):
        return None
    return registrable(s)


def registrable(host: str) -> str:
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in MULTI_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def suffix_of(domain: str) -> str:
    parts = domain.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in MULTI_SUFFIXES:
        return ".".join(parts[-2:])
    return parts[-1]


def label_of(domain: str) -> str:
    return domain[: -(len(suffix_of(domain)) + 1)]


def parse_tlds(value: str | None) -> set[str]:
    if not value:
        return {"com", "net", "org"}
    return {t.strip().lstrip(".").lower() for t in value.split(",") if t.strip()}


# --------------------------------------------------------------------------- table I/O

def table_path(run_dir: Path) -> Path:
    return Path(run_dir) / "domains.csv"


def load_table(run_dir: Path) -> dict[str, dict]:
    path = table_path(run_dir)
    table: dict[str, dict] = {}
    if not path.exists():
        return table
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            d = row.get("domain")
            if d:
                table[d] = row
    return table


def save_table(run_dir: Path, table: dict[str, dict]) -> Path:
    path = table_path(run_dir)
    cols: list[str] = ["domain"]
    seen = {"domain"}
    for row in table.values():
        for k in row:
            if k not in seen:
                seen.add(k)
                cols.append(k)
    tmp = path.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in table.values():
            w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in cols})
    os.replace(tmp, path)
    return path


def upsert(table: dict[str, dict], domain: str, fields: dict, source: str | None = None) -> dict:
    row = table.get(domain)
    if row is None:
        row = {"domain": domain}
        table[domain] = row
    if source:
        sources = set(filter(None, (row.get("sources") or "").split("|")))
        sources.add(source)
        row["sources"] = "|".join(sorted(sources))
    for k, v in fields.items():
        if v is None or v == "":
            continue
        row[k] = v
    return row


def num(row: dict, key: str, default: float | None = None) -> float | None:
    v = row.get(key)
    if v in (None, ""):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def truthy(v) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y"}


# --------------------------------------------------------------------------- niche

def load_lines(path: Path) -> list[str]:
    out = []
    if not Path(path).exists():
        return out
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def load_niche(run_dir: Path) -> dict:
    path = Path(run_dir) / "niche.json"
    if not path.exists():
        raise SystemExit(f"{path} not found. Run init_run.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


def token_regex(tokens: list[str]) -> re.Pattern:
    toks = sorted({t.lower() for t in tokens if t}, key=len, reverse=True)
    return re.compile("|".join(re.escape(t) for t in toks)) if toks else re.compile(r"(?!x)x")


_segmenter = None


def segment(label: str) -> list[str]:
    """Split a domain label into words. Uses wordninja when installed."""
    global _segmenter
    if _segmenter is None:
        try:
            import wordninja  # type: ignore
            _segmenter = wordninja.split
        except Exception:
            _segmenter = False
    parts = [p for p in re.split(r"[-0-9]+", label) if p]
    if not _segmenter:
        return parts
    words: list[str] = []
    for p in parts:
        words.extend(w.lower() for w in _segmenter(p))
    return words


def has_segmenter() -> bool:
    segment("probe")
    return bool(_segmenter)


def name_match(label: str, tokens: list[str], negative: list[str]) -> tuple[list[str], str]:
    """Return (matched tokens, strength): 'word' when a token is a real word in the name,
    'substring' for a long token or one at the edge of the name, '' for no usable match.
    Short tokens buried inside other words ('reef' in 'freefonts') do not count."""
    low = label.lower()
    if any(n and n.lower() in low for n in negative):
        return [], ""
    hits = sorted({t.lower() for t in tokens if t and t.lower() in low}, key=len, reverse=True)
    if not hits:
        return [], ""
    if has_segmenter():
        words = set(segment(low))
        parts = [p for p in re.split(r"[-0-9]+", low) if p]
        for t in hits:
            if len(t) < 4 and not any(p == t or p.startswith(t) or p.endswith(t) for p in parts):
                continue  # 3-letter tokens ('koi', 'bbq') only at the edge of a name part
            if t in words or t + "s" in words or t + "es" in words or (t.endswith("s") and t[:-1] in words):
                return hits, "word"
        return (hits, "substring") if any(len(t) >= 6 for t in hits) else ([], "")
    parts = [p for p in re.split(r"[-0-9]+", low) if p]
    for t in hits:
        if len(t) >= 6 or (len(t) >= 4 and any(p.startswith(t) or p.endswith(t) or p.endswith(t + "s") for p in parts)):
            return hits, "substring"
    return [], ""


# --------------------------------------------------------------------------- word lists

def load_asset_terms(name: str) -> list[str]:
    return [t.lower() for t in load_lines(ASSETS / name)]


def find_terms(text: str, terms: list[str]) -> list[str]:
    low = text.lower()
    hits = []
    for t in terms:
        if re.search(r"(?<![a-z])" + re.escape(t) + r"(?![a-z])", low):
            hits.append(t)
    return hits


FOREIGN_SCRIPT_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯Ѐ-ӿ฀-๿؀-ۿ]")


def foreign_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return len(FOREIGN_SCRIPT_RE.findall(text)) / len(letters)


# --------------------------------------------------------------------------- HTTP

class _HostThrottle:
    def __init__(self):
        self.lock = threading.Lock()
        self.next_ok: dict[str, float] = {}

    def wait(self, host: str, interval: float) -> None:
        if interval <= 0:
            return
        with self.lock:
            t = time.monotonic()
            slot = max(t, self.next_ok.get(host, 0.0))
            self.next_ok[host] = slot + interval
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)


THROTTLE = _HostThrottle()


def http_request(url: str, data: bytes | None = None, headers: dict | None = None,
                 method: str | None = None, timeout: float = 30, retries: int = 3,
                 min_interval: float = 0.0, max_bytes: int | None = None) -> tuple[int, bytes, dict]:
    """HTTP with retries on 429/5xx/network errors. Returns (status, body, headers); status 0 = failed."""
    hdrs = {"User-Agent": UA, "Accept-Encoding": "identity"}
    if headers:
        hdrs.update(headers)
    host = urllib.parse.urlsplit(url).netloc
    last_err = ""
    for attempt in range(retries + 1):
        THROTTLE.wait(host, min_interval)
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read(max_bytes) if max_bytes else resp.read()
                return resp.status, body, dict(resp.headers)
        except urllib.error.HTTPError as e:
            status = e.code
            try:
                body = e.read(max_bytes or 200_000)
            except Exception:
                body = b""
            if status in (429, 500, 502, 503, 504, 520, 522, 524) and attempt < retries:
                retry_after = e.headers.get("Retry-After") if e.headers else None
                wait = float(retry_after) if retry_after and retry_after.isdigit() else (2 ** attempt) * 2
                time.sleep(min(wait, 60))
                continue
            return status, body, dict(e.headers or {})
        except Exception as e:  # URLError, timeouts, resets
            last_err = str(e)
            if attempt < retries:
                time.sleep((2 ** attempt) * 1.5)
                continue
    return 0, last_err.encode("utf-8", "replace"), {}


def get_json(url: str, **kw) -> tuple[int, object]:
    status, body, _ = http_request(url, **kw)
    if status != 200:
        return status, None
    try:
        return status, json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return status, None


def parallel_map(fn, items, workers: int = 8, desc: str = "", every: int = 50):
    """Run fn over items in threads; yields (item, result, error)."""
    items = list(items)
    total = len(items)
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futs = {pool.submit(fn, it): it for it in items}
        for fut in as_completed(futs):
            it = futs[fut]
            done += 1
            if desc and (done % every == 0 or done == total):
                log(f"{desc}: {done}/{total}")
            try:
                yield it, fut.result(), None
            except Exception as e:  # keep the batch going
                yield it, None, e


# --------------------------------------------------------------------------- HTML text

class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self.h1: list[str] = []
        self.meta_desc = ""
        self.lang = ""
        self.links: list[str] = []
        self._skip = 0
        self._in_title = False
        self._in_h1 = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True
            self.h1.append("")
        elif tag == "html" and a.get("lang"):
            self.lang = (a.get("lang") or "").lower()
        elif tag == "meta" and (a.get("name") or "").lower() == "description":
            self.meta_desc = a.get("content") or ""
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        if self._in_h1 and self.h1:
            self.h1[-1] += data
        self.parts.append(data)


def parse_html(raw: bytes) -> dict:
    text = raw.decode("utf-8", "replace")
    p = _TextExtractor()
    try:
        p.feed(text)
    except Exception:
        pass
    body = re.sub(r"\s+", " ", " ".join(p.parts)).strip()
    return {
        "title": re.sub(r"\s+", " ", p.title).strip()[:200],
        "h1": [re.sub(r"\s+", " ", h).strip()[:150] for h in p.h1 if h.strip()][:3],
        "meta": p.meta_desc.strip()[:300],
        "lang": p.lang,
        "text": body,
        "links": p.links,
    }


# --------------------------------------------------------------------------- DataForSEO

class DataForSEOError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(f"DataForSEO {code}: {message}")
        self.code = code
        self.message = str(message)

    @property
    def is_access_problem(self) -> bool:
        m = self.message.lower()
        code = self.code if isinstance(self.code, int) else 0
        return 40100 <= code < 40300 or any(
            w in m for w in ("subscription", "access denied", "not enough", "payment", "balance", "unauthorized"))


class BudgetExceeded(RuntimeError):
    pass


def _read_env_file(path: Path) -> dict:
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"\'')
    return out


def dataforseo_credentials() -> tuple[str, str] | None:
    env = dict(os.environ)
    for p in (Path.cwd() / ".env", SKILL_DIR / ".env", Path.home() / ".dataforseo.env"):
        for k, v in _read_env_file(p).items():
            env.setdefault(k, v)
    login = env.get("DATAFORSEO_LOGIN") or env.get("DATAFORSEO_USERNAME")
    password = env.get("DATAFORSEO_PASSWORD")
    if login and password:
        return login, password
    if sys.platform == "win32":  # user env vars set after the app started are still in the registry
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                def rd(name):
                    try:
                        return winreg.QueryValueEx(k, name)[0]
                    except OSError:
                        return None
                login = rd("DATAFORSEO_LOGIN") or rd("DATAFORSEO_USERNAME")
                password = rd("DATAFORSEO_PASSWORD")
                if login and password:
                    return login, password
        except Exception:
            pass
    return None


class DataForSEO:
    BASE = "https://api.dataforseo.com/v3/"

    def __init__(self, run_dir: Path | None = None, max_cost: float | None = None):
        creds = dataforseo_credentials()
        if not creds:
            raise SystemExit(
                "DataForSEO credentials not found. Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD "
                "(run scripts/setup_credentials.ps1 on Windows), or skip the paid stages with --free-only.")
        token = base64.b64encode(f"{creds[0]}:{creds[1]}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}
        self.run_dir = Path(run_dir) if run_dir else None
        self.max_cost = max_cost
        self.lock = threading.Lock()
        self.spent = self._ledger_total()

    def _ledger(self) -> Path | None:
        return self.run_dir / "cost_log.csv" if self.run_dir else None

    def _ledger_total(self) -> float:
        p = self._ledger()
        if not p or not p.exists():
            return 0.0
        total = 0.0
        with p.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    total += float(row.get("cost") or 0)
                except ValueError:
                    pass
        return total

    def _record(self, endpoint: str, cost: float, label: str) -> None:
        with self.lock:
            self.spent += cost
            p = self._ledger()
            if not p:
                return
            new = not p.exists()
            with p.open("a", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                if new:
                    w.writerow(["time", "endpoint", "label", "cost"])
                w.writerow([now_utc().isoformat(timespec="seconds"), endpoint, label, f"{cost:.6f}"])

    def ensure_budget(self, estimate: float) -> None:
        if self.max_cost is None:
            return
        with self.lock:
            if self.spent + estimate > self.max_cost + 1e-9:
                raise BudgetExceeded(
                    f"Budget ${self.max_cost:.2f} would be exceeded (spent ${self.spent:.2f}, "
                    f"next call ~${estimate:.3f}). Raise --max-cost to continue.")

    def post(self, endpoint: str, task: dict, label: str = "", estimate: float = 0.0) -> dict:
        self.ensure_budget(estimate)
        body = json.dumps([task]).encode("utf-8")
        status, raw, _ = http_request(self.BASE + endpoint, data=body, headers=self.headers,
                                      method="POST", timeout=180, retries=4)
        return self._handle(endpoint, status, raw, label)

    def get(self, endpoint: str, label: str = "") -> dict:
        status, raw, _ = http_request(self.BASE + endpoint, headers=self.headers, timeout=60, retries=3)
        return self._handle(endpoint, status, raw, label)

    def _handle(self, endpoint: str, status: int, raw: bytes, label: str) -> dict:
        if status == 401:
            raise DataForSEOError(40100, "Unauthorized: check DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD (API Access tab, not your website password)")
        try:
            resp = json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            raise DataForSEOError(status, f"HTTP {status}: {raw[:200]!r}")
        if resp.get("status_code") != 20000:
            raise DataForSEOError(resp.get("status_code"), resp.get("status_message"))
        tasks = resp.get("tasks") or [{}]
        task = tasks[0]
        cost = float(task.get("cost") or resp.get("cost") or 0)
        self._record(endpoint, cost, label)
        if task.get("status_code") not in (20000, None):
            raise DataForSEOError(task.get("status_code"), task.get("status_message"))
        return task


def first_result(task: dict) -> dict:
    res = task.get("result") or []
    return res[0] if res and isinstance(res[0], dict) else {}


def chunks(seq, n):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def log10p(x: float | None) -> float:
    return math.log10(1 + max(0.0, x or 0.0))
