#!/usr/bin/env python3

import logging
import subprocess
import csv
from pathlib import Path

import pandas as pd

from get_6h_url import get_download_urls

# ============================================================
# Configurable parameters
# ============================================================
SOURCE_ID   = "MIROC6"
MEMBER_ID   = "r1i1p1f1"
CSV_FILE    = Path(__file__).parent / "MIROC6.csv"

HIST_EXPERIMENT     = "historical"
HIST_START_DATE     = "2009-01-02"
HIST_END_DATE       = "2010-12-31"

FUTURE_EXPERIMENT   = "ssp585"          # ssp126, ssp245, ssp370, ssp585
FUTURE_START_DATE   = "2099-01-02"
FUTURE_END_DATE     = "2100-12-31"

DATA_DIR = Path("/home/xuelingbo/LSP-DS-HiClimaX/hands-on/MIROC6/Tokyo/raw")
EXCLUDE_NODES: list[str] = []
# EXCLUDE_NODES = ["esgf-node.llnl.gov", "esgf.ceda.ac.uk"]
EXCLUDE_NODES = ["esgf-data02.diasjp.net"]
# ============================================================

_logger = logging.getLogger(__name__)


def read_variables(csv_file: Path) -> list[dict]:
    """Read variable list from CSV, skip rows with empty table_id."""
    variables = []
    with open(csv_file, newline="") as f:
        for row in csv.DictReader(f):
            if row["table_id"]:
                variables.append(row)
    return variables


def node_from_url(url: str) -> str:
    """Extract data node hostname from a URL, e.g. 'esgf-data1.llnl.gov'."""
    return url.split("/")[2]


CYAN  = "\033[96m"
RED   = "\033[91m"
RESET = "\033[0m"


def wget_download(url: str, output_dir: Path) -> bool:
    """Download a file with wget. Returns True if successful or file already exists."""
    filename = url.split("/")[-1].split("|")[0]
    output_path = output_dir / filename
    if output_path.exists():
        print(f"{CYAN}  Already exists, skipping: {filename}{RESET}")
        return True
    result = subprocess.run(
        ["wget", "--no-clobber", "--tries=3", "--timeout=60",
         "-P", str(output_dir), url],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _logger.error(f"wget failed for {url}\n{result.stderr.strip()}")
        return False
    print(f"{CYAN}  Downloaded: {filename}{RESET}")
    return True


def check_missing(
    experiment_id: str,
    variables: list[dict],
    output_dir: Path,
    year_start: int,
    year_end: int,
) -> list[dict]:
    """Return variable rows that have no files covering the requested year range."""
    import re
    missing = []
    for var in variables:
        if var["table_id"] == "fx":
            # fx files are experiment-independent; just check if any exist
            pattern = f"{var['var_id']}_{var['table_id']}_{SOURCE_ID}_*.nc"
            covered = len(list(output_dir.glob(pattern))) > 0
            if not covered:
                missing.append(var)
            continue
        pattern = f"{var['var_id']}_{var['table_id']}_{SOURCE_ID}_{experiment_id}_*.nc"
        files = list(output_dir.glob(pattern))
        covered = False
        for f in files:
            m = re.search(r"_(\d{4})\d{2,8}-(\d{4})\d{2,8}\.nc$", f.name)
            if m:
                file_year_start, file_year_end = int(m.group(1)), int(m.group(2))
                if file_year_start <= year_end and file_year_end >= year_start:
                    covered = True
                    break
        if not covered:
            missing.append(var)
    return missing


def save_missing_csv(missing_vars: list[dict], output_path: Path) -> None:
    """Save missing variables to a CSV with the same format as MIROC6.csv."""
    if not missing_vars:
        return
    fieldnames = list(missing_vars[0].keys())
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(missing_vars)


def download_miroc6(
    experiment_id: str,
    start_date: str,
    end_date: str,
    variables: list[dict],
    output_dir: Path,
) -> None:
    """Fetch URLs and download all files for one experiment."""
    _logger.info(f"=== {experiment_id}: {start_date} ~ {end_date} ===")

    for var in variables:
        _logger.info(f"  Fetching URLs: {var['var_id']} ({var['table_id']})")
        urls = None
        for attempt in range(1, 4):
            try:
                urls = get_download_urls(
                    variable_id=var["var_id"],
                    table_id=var["table_id"],
                    frequency=var["frequency"],
                    source_id=SOURCE_ID,
                    member_id=MEMBER_ID,
                    experiment_id=experiment_id,
                    start_date=pd.Timestamp(start_date),
                    end_date=pd.Timestamp(end_date),
                    exclude_nodes=EXCLUDE_NODES,
                )
                break
            except Exception as e:
                _logger.warning(f"  Attempt {attempt}/3 failed for {var['var_id']}: {e}")
                if attempt == 3:
                    _logger.error(f"  Giving up on {var['var_id']} after 3 attempts.")
        if urls is None:
            continue

        for url in urls:
            exclude_nodes = list(EXCLUDE_NODES)
            _logger.info(f"  Downloading: {url}")
            if wget_download(url, output_dir):
                continue
            # wget failed — try a different node
            bad_node = node_from_url(url)
            exclude_nodes.append(bad_node)
            _logger.warning(f"  Retrying with node {bad_node!r} excluded ...")
            try:
                alt_urls = get_download_urls(
                    variable_id=var["var_id"],
                    table_id=var["table_id"],
                    frequency=var["frequency"],
                    source_id=SOURCE_ID,
                    member_id=MEMBER_ID,
                    experiment_id=experiment_id,
                    start_date=pd.Timestamp(start_date),
                    end_date=pd.Timestamp(end_date),
                    exclude_nodes=exclude_nodes,
                )
            except Exception as e:
                _logger.error(f"  Could not find alternative node: {e}")
                continue
            failed_filename = url.split("/")[-1].split("|")[0]
            alt_url = next(
                (u for u in alt_urls if u.split("/")[-1].split("|")[0] == failed_filename),
                None,
            )
            if alt_url:
                _logger.info(f"  Retrying: {alt_url}")
                if not wget_download(alt_url, output_dir):
                    print(f"{RED}  Failed (both nodes): {alt_url.split('/')[-1].split('|')[0]}{RESET}")
            else:
                print(f"{RED}  Failed (no alternative node): {url.split('/')[-1].split('|')[0]}{RESET}")


def main():
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        force=True,
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # If a CSV is passed as argument, download only those variables
    if len(sys.argv) > 1:
        csv_path = DATA_DIR / sys.argv[1]
        variables = read_variables(csv_path)
        _logger.info(f"Using variable list from: {csv_path}")
        download_miroc6(HIST_EXPERIMENT, HIST_START_DATE, HIST_END_DATE, variables, DATA_DIR)
        download_miroc6(FUTURE_EXPERIMENT, FUTURE_START_DATE, FUTURE_END_DATE, variables, DATA_DIR)
        return

    # Default: check first, then download only missing variables.
    # Comment/uncomment entries in `experiments` to control which are processed.
    experiments = [
        (HIST_EXPERIMENT,   HIST_START_DATE,   HIST_END_DATE),
        # (FUTURE_EXPERIMENT, FUTURE_START_DATE, FUTURE_END_DATE),
    ]

    variables = read_variables(CSV_FILE)

    for exp_id, s_date, e_date in experiments:
        missing_vars = check_missing(exp_id, variables, DATA_DIR,
                                     int(s_date[:4]), int(e_date[:4]))
        if not missing_vars:
            print(f"\n=== {exp_id}: all variables present, skipping download. ===")
            continue
        print(f"\n=== {exp_id}: {len(missing_vars)} variable(s) missing, downloading... ===")
        for v in missing_vars:
            print(f"  {v['var_id']} ({v['table_id']})")
        download_miroc6(exp_id, s_date, e_date, missing_vars, DATA_DIR)

    # Final check across all experiments
    all_missing = []
    for exp_id, s_date, e_date in experiments:
        all_missing += check_missing(exp_id, variables, DATA_DIR,
                                     int(s_date[:4]), int(e_date[:4]))

    seen = set()
    missing_unique = []
    for v in all_missing:
        key = (v["var_id"], v["table_id"])
        if key not in seen:
            seen.add(key)
            missing_unique.append(v)

    if missing_unique:
        missing_csv = DATA_DIR / "MIROC6_missing.csv"
        save_missing_csv(missing_unique, missing_csv)
        print("\n=== Still missing after download ===")
        for v in missing_unique:
            print(f"  {v['var_id']} ({v['table_id']})")
        print(f"Saved to: {missing_csv}")
        print(f"Re-run with: python {Path(__file__).name} {missing_csv.name}")
    else:
        print("\n=== All variables downloaded successfully ===")


if __name__ == "__main__":
    main()
