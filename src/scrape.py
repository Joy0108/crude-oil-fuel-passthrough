"""Step 1 - Scrape the raw price data from official publishers.

  Brent crude   U.S. EIA, "Europe Brent Spot Price FOB", monthly average (USD/bbl)   HTML table
  USD/INR       Federal Reserve Board H.10 historical rates, daily (INR per USD)     HTML table
                (H.10 is the upstream source of FRED's DEXINUS / EXINUS series)
  Delhi petrol  PPAC, Ministry of Petroleum & Natural Gas
                  a) price revisions at Delhi up to 15-Jun-2017                    HTML table
                  b) daily prices in metro cities since 16-Jun-2017                PDF
                     (the PDF file name changes every day, so its link is discovered
                      from the PPAC page instead of being hard-coded)

Every raw response is archived in data/raw/ so each number can be traced back to the
page it came from. Tidy CSVs go to data/interim/ and are loaded into MySQL in step 2.

    python -m src.scrape             download + parse
    python -m src.scrape --offline   re-parse the archived raw files only
"""
import argparse
import io
import re
import time
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from config import INTERIM_DIR, RAW_DIR

URLS = {
    "brent": "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=RBRTE&f=M",
    "usdinr": "https://www.federalreserve.gov/releases/h10/hist/dat00_in.htm",
    "petrol_upto_2017": "https://ppac.gov.in/retail-selling-price-rsp-of-petrol-diesel-and-domestic-lpg/"
                        "rsp-of-petrol-and-diesel-at-delhi-up-to-15-6-2017",
    "petrol_daily_page": "https://ppac.gov.in/retail-selling-price-rsp-of-petrol-diesel-and-domestic-lpg/"
                         "rsp-of-petrol-and-diesel-in-metro-cities-since-16-6-2017",
}
RAW_FILES = {
    "brent": RAW_DIR / "eia_brent_monthly.html",
    "usdinr": RAW_DIR / "fed_h10_usdinr_daily.html",
    "petrol_upto_2017": RAW_DIR / "ppac_delhi_petrol_upto_2017.html",
    "petrol_daily_page": RAW_DIR / "ppac_metro_prices_page.html",
    "petrol_daily_pdf": RAW_DIR / "ppac_metro_prices_daily.pdf",
}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ----------------------------------------------------------------------------- download
def fetch(session: requests.Session, url: str, retries: int = 3) -> bytes:
    """GET with a timeout and a simple linear back-off (government sites can be slow)."""
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=90)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as exc:
            if attempt == retries:
                raise
            print(f"    retry {attempt}/{retries - 1} in {5 * attempt}s: {exc}")
            time.sleep(5 * attempt)


def find_daily_pdf_link(page_html: bytes, page_url: str) -> str:
    """PPAC re-uploads the daily price PDF under a new name each day: find it on the page."""
    soup = BeautifulSoup(page_html, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "DailyPrice" in href and href.lower().endswith(".pdf"):
            return urljoin(page_url, href)
    raise RuntimeError("Daily price PDF link not found - PPAC page layout may have changed")


def download_all() -> None:
    with requests.Session() as s:
        s.headers.update(HEADERS)
        for key, url in URLS.items():
            print(f"  GET {url}")
            RAW_FILES[key].write_bytes(fetch(s, url))
        pdf_url = find_daily_pdf_link(RAW_FILES["petrol_daily_page"].read_bytes(), URLS["petrol_daily_page"])
        print(f"  GET {pdf_url}")
        RAW_FILES["petrol_daily_pdf"].write_bytes(fetch(s, pdf_url))


# ----------------------------------------------------------------------------- parsers
def parse_brent(html: bytes) -> pd.DataFrame:
    """EIA leaf page: one row per year, one column per month -> long monthly series."""
    tables = pd.read_html(io.BytesIO(html), match="Jan")
    wide = next(t for t in tables if {"Year", "Jan", "Dec"} <= set(map(str, t.columns)))
    wide = wide.dropna(subset=["Year"])
    long = wide.melt(id_vars="Year", var_name="mon", value_name="brent_usd_bbl").dropna()
    long["month_start"] = pd.to_datetime(
        long["Year"].astype(int).astype(str) + "-" + long["mon"], format="%Y-%b")
    out = long[["month_start", "brent_usd_bbl"]].sort_values("month_start").reset_index(drop=True)
    return out.astype({"brent_usd_bbl": float})


def parse_usdinr(html: bytes) -> pd.DataFrame:
    """Fed H.10 page: Date | Rate, with 'ND' (no data) on US holidays."""
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for tr in soup.find_all("tr"):
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
        if len(cells) == 2 and re.fullmatch(r"\d{1,2}-[A-Z]{3}-\d{2}", cells[0]):
            rows.append(cells)
    df = pd.DataFrame(rows, columns=["obs_date", "inr_per_usd"])
    df["obs_date"] = pd.to_datetime(df["obs_date"].str.title(), format="%d-%b-%y")
    df["inr_per_usd"] = pd.to_numeric(df["inr_per_usd"], errors="coerce")   # 'ND' -> NaN
    return df.dropna().sort_values("obs_date").reset_index(drop=True)


DATE_DMY = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})")


def parse_petrol_upto_2017(html: bytes) -> pd.DataFrame:
    """PPAC revision table. Cells look like '16.1.17', 'As on 01.04.15',
    '21.06.06  (Reduction in VAT Rate)' and there are fiscal-year header rows ('2012-13')."""
    table = max(pd.read_html(io.BytesIO(html)), key=len)
    date_col, petrol_col = table.columns[0], table.columns[1]
    records = []
    for raw_date, price in zip(table[date_col].astype(str), table[petrol_col]):
        m = DATE_DMY.search(raw_date)
        price = pd.to_numeric(price, errors="coerce")
        if not m or pd.isna(price):
            continue                      # FY header row or footnote
        d, mth, y = (int(g) for g in m.groups())
        y = y + 2000 if y < 100 else y
        remark = DATE_DMY.sub("", raw_date).replace("As on", "").strip(" ()")
        records.append((pd.Timestamp(y, mth, d), float(price), remark or None))
    df = pd.DataFrame(records, columns=["effective_date", "rsp_inr_litre", "remark"])
    return df.drop_duplicates("effective_date", keep="last").sort_values("effective_date")


def parse_petrol_daily_pdf(pdf_bytes: bytes) -> pd.DataFrame:
    """Each text line: '13-Nov-26 102.12 111.21 107.77 113.51 13-Nov-26 95.20 ...'
    i.e. date, petrol for Delhi/Mumbai/Chennai/Kolkata, then the diesel block. Delhi petrol is
    the first number after the date."""
    line_pat = re.compile(r"^(\d{1,2}-[A-Za-z]{3}-\d{2})\s+(\d+\.\d+)\s")
    rows = []
    for page in PdfReader(io.BytesIO(pdf_bytes)).pages:
        for line in page.extract_text().splitlines():
            m = line_pat.match(line.strip())
            if m:
                rows.append(m.groups())
    df = pd.DataFrame(rows, columns=["effective_date", "rsp_inr_litre"])
    df["effective_date"] = pd.to_datetime(df["effective_date"], format="%d-%b-%y")
    df["rsp_inr_litre"] = df["rsp_inr_litre"].astype(float)
    df["remark"] = None
    return df.sort_values("effective_date").reset_index(drop=True)


# ----------------------------------------------------------------------------- validation
def validate(brent, fx, rev, daily) -> None:
    """Fail fast if a website changed its layout and the parser silently produced junk."""
    assert brent["brent_usd_bbl"].between(5, 250).all(), "Brent outside plausible range"
    assert fx["inr_per_usd"].between(30, 150).all(), "USD/INR outside plausible range"
    for name, d in (("revisions", rev), ("daily", daily)):
        assert d["rsp_inr_litre"].between(20, 200).all(), f"petrol {name} outside plausible range"
    assert not daily["effective_date"].duplicated().any(), "duplicate days in daily PDF"
    span = (daily["effective_date"].max() - daily["effective_date"].min()).days + 1
    assert span == len(daily), f"daily petrol series has gaps: {len(daily)} rows for {span} days"
    assert rev["effective_date"].max() < daily["effective_date"].min(), "petrol sources overlap"


def main(offline: bool = False) -> None:
    if offline:
        print("Offline mode: re-parsing archived files in data/raw/")
    else:
        print("Downloading raw sources ...")
        download_all()

    brent = parse_brent(RAW_FILES["brent"].read_bytes())
    fx = parse_usdinr(RAW_FILES["usdinr"].read_bytes())
    rev = parse_petrol_upto_2017(RAW_FILES["petrol_upto_2017"].read_bytes())
    daily = parse_petrol_daily_pdf(RAW_FILES["petrol_daily_pdf"].read_bytes())
    validate(brent, fx, rev, daily)

    rev["source"], daily["source"] = "PPAC_REVISION", "PPAC_DAILY"
    petrol = pd.concat([rev, daily], ignore_index=True)

    brent.to_csv(INTERIM_DIR / "brent_monthly.csv", index=False)
    fx.to_csv(INTERIM_DIR / "usdinr_daily.csv", index=False)
    petrol.to_csv(INTERIM_DIR / "petrol_delhi.csv", index=False)

    def rng(d, c):
        return f"{d[c].min():%Y-%m-%d} -> {d[c].max():%Y-%m-%d}"
    print(f"  Brent monthly      : {len(brent):>5} rows  {rng(brent, 'month_start')}")
    print(f"  USD/INR daily      : {len(fx):>5} rows  {rng(fx, 'obs_date')}")
    print(f"  Petrol revisions   : {len(rev):>5} rows  {rng(rev, 'effective_date')}")
    print(f"  Petrol daily (PDF) : {len(daily):>5} rows  {rng(daily, 'effective_date')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="parse archived raw files, no download")
    main(ap.parse_args().offline)
