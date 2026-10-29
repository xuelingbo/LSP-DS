#!/usr/bin/env python3

import logging
import subprocess
import csv
from pathlib import Path

import pandas as pd
import xarray as xr

from util import PANGEO_CATALOG_URL

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

# --- Amon monthly climatology from Pangeo (Google Cloud zarr) ---
AMON_VARIABLES = [
    # surface only, one per LDASIN variable:
    # T2D, Q2D (via dRH), U2D, V2D, PSFC, SWDOWN, LWDOWN, RAINRATE
    "tas", "hurs", "uas", "vas", "ps", "rsds", "rlds", "pr",
]
AMON_HIST_YEARS     = (1995, 2014)
AMON_FUTURE_YEARS   = (2080, 2099)
AMON_DIR = Path("/home/xuelingbo/NAS_CMIP6/MIROC6")
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
        pattern = f"{var['var_id']}_{var['table_id']}_{SOURCE_ID}_{experiment_id}_*.nc"
        files = list(output_dir.glob(pattern))
        covered = False
        for f in files:
            m = re.search(r"_(\d{4})\d{8}-(\d{4})\d{8}\.nc$", f.name)
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
    from get_6h_url import get_download_urls   # needs pyesgf, only for the ESGF (6h) workflow
    _logger.info(f"=== {experiment_id}: {start_date} ~ {end_date} ===")

    for var in variables:
        _logger.info(f"  Fetching URLs: {var['var_id']} ({var['table_id']})")
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
        except Exception as e:
            _logger.error(f"  Failed to get URLs for {var['var_id']}: {e}")
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


def download_amon_climatology(
    experiment_id: str,
    year_start: int,
    year_end: int,
    variables: list[str],
    output_dir: Path,
) -> list[str]:
    """
    Open Amon data from the Pangeo CMIP6 catalog, average each calendar month over
    year_start~year_end, and save one file per variable with dims (month, [plev,] lat, lon).
    Returns the variables that could not be found.
    """
    _logger.info(f"=== Amon {experiment_id}: {year_start} ~ {year_end} ===")
    catalog = pd.read_csv(PANGEO_CATALOG_URL.replace(".json", ".csv"))
    catalog = catalog[
        (catalog.source_id == SOURCE_ID)
        & (catalog.member_id == MEMBER_ID)
        & (catalog.experiment_id == experiment_id)
        & (catalog.table_id == "Amon")
    ]

    missing = []
    for var_id in variables:
        rows = catalog[catalog.variable_id == var_id]
        if rows.empty:
            _logger.error(f"  {var_id}: not found in Pangeo catalog")
            missing.append(var_id)
            continue
        row = rows.sort_values("version").iloc[-1]   # latest version

        filename = (
            f"{var_id}_{row.activity_id}.{row.institution_id}.{row.source_id}."
            f"{row.experiment_id}.{row.table_id}.{row.grid_label}"
            f"_{row.member_id}_{year_start}_{year_end}.nc"
        )
        output_path = output_dir / filename
        if output_path.exists():
            print(f"{CYAN}  Already exists, skipping: {filename}{RESET}")
            continue

        _logger.info(f"  Opening: {row.zstore}")
        ds = xr.open_zarr(row.zstore, consolidated=True, storage_options={"token": "anon"})
        ds = ds.sel(time=slice(str(year_start), str(year_end)))
        n_years = len(set(ds.time.dt.year.values))
        if n_years != year_end - year_start + 1:
            _logger.warning(f"  {var_id}: only {n_years} years available in {year_start}-{year_end}")

        clim = ds[[var_id]].groupby("time.month").mean("time", keep_attrs=True)
        for bnds in ("lat_bnds", "lon_bnds"):
            if bnds in ds:
                clim = clim.assign_coords({bnds: ds[bnds]})
        clim.attrs = ds.attrs
        clim.attrs["climatology"] = f"monthly mean over {year_start}-{year_end}"
        clim.load().to_netcdf(output_path)
        print(f"{CYAN}  Saved: {filename}{RESET}")

    return missing


def main():
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        force=True,
    )

    # Default: Amon monthly climatology from Pangeo
    if len(sys.argv) == 1 or sys.argv[1] == "amon":
        AMON_DIR.mkdir(parents=True, exist_ok=True)
        missing = (
            download_amon_climatology(HIST_EXPERIMENT, *AMON_HIST_YEARS, AMON_VARIABLES, AMON_DIR)
            + download_amon_climatology(FUTURE_EXPERIMENT, *AMON_FUTURE_YEARS, AMON_VARIABLES, AMON_DIR)
        )
        if missing:
            print(f"\n{RED}=== Missing Amon variables: {sorted(set(missing))} ==={RESET}")
        else:
            print("\n=== All Amon variables downloaded successfully ===")
        return

    # "6h": high-frequency files from ESGF (original workflow)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # If a CSV is passed as argument, download only those variables
    if len(sys.argv) > 2:
        csv_path = DATA_DIR / sys.argv[2]
        variables = read_variables(csv_path)
        _logger.info(f"Using variable list from: {csv_path}")
        download_miroc6(HIST_EXPERIMENT, HIST_START_DATE, HIST_END_DATE, variables, DATA_DIR)
        download_miroc6(FUTURE_EXPERIMENT, FUTURE_START_DATE, FUTURE_END_DATE, variables, DATA_DIR)
        return

    # Default: download all variables, then check and save missing
    variables = read_variables(CSV_FILE)
    # download_miroc6(HIST_EXPERIMENT, HIST_START_DATE, HIST_END_DATE, variables, DATA_DIR)
    # download_miroc6(FUTURE_EXPERIMENT, FUTURE_START_DATE, FUTURE_END_DATE, variables, DATA_DIR)

    missing = (
        check_missing(HIST_EXPERIMENT, variables, DATA_DIR,
                      int(HIST_START_DATE[:4]), int(HIST_END_DATE[:4]))
        + check_missing(FUTURE_EXPERIMENT, variables, DATA_DIR,
                        int(FUTURE_START_DATE[:4]), int(FUTURE_END_DATE[:4]))
    )

    # Deduplicate missing vars by var_id+table_id
    seen = set()
    missing_unique = []
    for v in missing:
        key = (v["var_id"], v["table_id"])
        if key not in seen:
            seen.add(key)
            missing_unique.append(v)

    if missing_unique:
        missing_csv = DATA_DIR / "MIROC6_missing.csv"
        save_missing_csv(missing_unique, missing_csv)
        print("\n=== Missing variables ===")
        for v in missing_unique:
            print(f"  {v['var_id']} ({v['table_id']})")
        print(f"Saved to: {missing_csv}")
        print(f"Re-run with: python {Path(__file__).name} 6h {missing_csv.name}")
    else:
        print("\n=== All variables downloaded successfully ===")


if __name__ == "__main__":
    main()
