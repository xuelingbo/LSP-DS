#!/usr/bin/env python3

import csv
import logging
from pathlib import Path

import numpy as np
import xarray as xr

_logger = logging.getLogger(__name__)

# ============================================================
# Configurable parameters
# ============================================================
SOURCE_ID          = "MIROC6"
MEMBER_ID          = "r1i1p1f1"
CSV_FILE           = Path(__file__).parent / "MIROC6.csv"

HIST_EXPERIMENT    = "historical"
HIST_YEAR_START    = 2009
HIST_YEAR_END      = 2010

FUTURE_EXPERIMENT  = "ssp585"
FUTURE_YEAR_START  = 2099
FUTURE_YEAR_END    = 2100

MONTHS             = [8]          # months to compute delta for

RAW_DIR            = Path("../hands-on/MIROC6/Tokyo/raw/")
OUTPUT_DIR         = Path("../hands-on/MIROC6/Tokyo/LDASIN/")
GEO_EM_FILE        = Path("../hands-on/MIROC6/Tokyo/geo/geo_em.d03.nc")
# ============================================================


def read_variables(csv_file: Path) -> list[dict]:
    """Read variable list from CSV, skip rows with empty table_id."""
    variables = []
    with open(csv_file, newline="") as f:
        for row in csv.DictReader(f):
            if row["table_id"]:
                variables.append(row)
    return variables


def get_domain_bounds(geo_em_file: Path) -> tuple[float, float, float, float]:
    """Return (lat_min, lat_max, lon_min, lon_max) from geo_em file."""
    geo_em = xr.open_dataset(geo_em_file)
    lat = geo_em.XLAT_M.values[0]
    lon = geo_em.XLONG_M.values[0]
    return lat.min(), lat.max(), lon.min(), lon.max()


def load_monthly_mean(
    raw_dir: Path,
    var_id: str,
    table_id: str,
    experiment_id: str,
    year_start: int,
    year_end: int,
    month: int,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
) -> xr.DataArray:
    """
    Load all nc files for a variable/experiment, select the given month
    across year_start~year_end, subset to domain, and return the time mean.
    """
    pattern = f"{var_id}_{table_id}_{SOURCE_ID}_{experiment_id}_*.nc"
    files = sorted(raw_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files found for pattern: {pattern}")

    time_coder = xr.coders.CFDatetimeCoder(use_cftime=True)
    ds = xr.concat(
        [xr.open_dataset(f, decode_times=time_coder) for f in files],
        dim="time",
        data_vars=None,
    )

    # Select years and month
    ds = ds.sel(time=ds.time.dt.year.isin(range(year_start, year_end + 1)))
    ds = ds.sel(time=ds.time.dt.month == month)

    if len(ds.time) == 0:
        raise ValueError(
            f"No data found for {var_id} {experiment_id} "
            f"years={year_start}-{year_end} month={month}"
        )

    # Subset to domain (with buffer)
    buf = 3.0
    lat_dim = "lat" if "lat" in ds.dims else "latitude"
    lon_dim = "lon" if "lon" in ds.dims else "longitude"

    ds = ds.sel(
        {lat_dim: slice(lat_min - buf, lat_max + buf),
         lon_dim: slice(lon_min - buf, lon_max + buf)}
    )

    da = ds[var_id]
    return da.mean(dim="time")


def compute_pgw_delta(
    raw_dir: Path,
    output_dir: Path,
    geo_em_file: Path,
    hist_experiment: str,
    hist_year_start: int,
    hist_year_end: int,
    future_experiment: str,
    future_year_start: int,
    future_year_end: int,
    months: list[int],
):
    output_dir.mkdir(parents=True, exist_ok=True)
    variables = read_variables(CSV_FILE)
    lat_min, lat_max, lon_min, lon_max = get_domain_bounds(geo_em_file)

    _logger.info(f"Domain: lat=[{lat_min:.2f}, {lat_max:.2f}], lon=[{lon_min:.2f}, {lon_max:.2f}]")

    for month in months:
        _logger.info(f"=== Month {month:02d} ===")
        delta_vars = {}

        for var in variables:
            var_id    = var["var_id"]
            table_id  = var["table_id"]
            _logger.info(f"  {var_id} ({table_id})")

            try:
                hist_mean = load_monthly_mean(
                    raw_dir, var_id, table_id,
                    hist_experiment, hist_year_start, hist_year_end,
                    month, lat_min, lat_max, lon_min, lon_max,
                )
                future_mean = load_monthly_mean(
                    raw_dir, var_id, table_id,
                    future_experiment, future_year_start, future_year_end,
                    month, lat_min, lat_max, lon_min, lon_max,
                )
            except (FileNotFoundError, ValueError) as e:
                _logger.warning(f"  {var_id} not found, delta set to 0: {e}")
                delta_vars[var_id] = xr.DataArray(0.0)
                continue

            if var_id == "pr":
                # Use ratio to avoid negative precipitation
                MIN_PR = 1e-9  # avoid division by zero
                signal = future_mean / hist_mean.clip(min=MIN_PR)
                _logger.info(f"  ratio {var_id}: mean={float(signal.mean()):.4f}")
            else:
                signal = future_mean - hist_mean
                _logger.info(f"  delta {var_id}: mean={float(signal.mean()):.4f}")
            delta_vars[var_id] = signal

        if not delta_vars:
            _logger.warning(f"No variables computed for month {month:02d}, skipping.")
            continue

        # Replace scalar placeholders (missing files set to 0.0) with proper lat/lon grids
        ref_2d = next(
            (da for da in delta_vars.values() if da.dims and ("lat" in da.dims or "latitude" in da.dims)),
            None,
        )
        if ref_2d is not None:
            lat_dim = "lat" if "lat" in ref_2d.dims else "latitude"
            lon_dim = "lon" if "lon" in ref_2d.dims else "longitude"
            lat_coord = ref_2d[lat_dim]
            lon_coord = ref_2d[lon_dim]
            for var_id, da in delta_vars.items():
                if da.dims == ():
                    delta_vars[var_id] = xr.DataArray(
                        np.zeros((len(lat_coord), len(lon_coord))),
                        dims=[lat_dim, lon_dim],
                        coords={lat_dim: lat_coord, lon_dim: lon_coord},
                    )
                    _logger.info(f"  {var_id}: expanded scalar 0 to ({lat_dim}, {lon_dim}) grid")

        ds_out = xr.Dataset(delta_vars)
        ds_out.attrs.update({
            "hist_experiment":  hist_experiment,
            "hist_years":       f"{hist_year_start}-{hist_year_end}",
            "future_experiment": future_experiment,
            "future_years":     f"{future_year_start}-{future_year_end}",
            "month":            month,
            "source_id":        SOURCE_ID,
        })

        fname = (
            f"delta_{hist_experiment}_{hist_year_start}-{hist_year_end}"
            f"_{future_experiment}_{future_year_start}-{future_year_end}"
            f"_{month:02d}.nc"
        )
        out_path = output_dir / fname
        ds_out.to_netcdf(out_path)
        _logger.info(f"  Saved: {out_path}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        force=True,
    )
    compute_pgw_delta(
        raw_dir=RAW_DIR,
        output_dir=OUTPUT_DIR,
        geo_em_file=GEO_EM_FILE,
        hist_experiment=HIST_EXPERIMENT,
        hist_year_start=HIST_YEAR_START,
        hist_year_end=HIST_YEAR_END,
        future_experiment=FUTURE_EXPERIMENT,
        future_year_start=FUTURE_YEAR_START,
        future_year_end=FUTURE_YEAR_END,
        months=MONTHS,
    )
