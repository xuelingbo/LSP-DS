#!/usr/bin/env python3

import logging
from pathlib import Path

import numpy as np
import xarray as xr

# Variable list, periods and data directory are shared with the Amon download
from download_miroc6_pgw_hrldas import (
    SOURCE_ID, MEMBER_ID, HIST_EXPERIMENT, FUTURE_EXPERIMENT,
    AMON_VARIABLES, AMON_HIST_YEARS, AMON_FUTURE_YEARS, AMON_DIR,
)

_logger = logging.getLogger(__name__)

# ============================================================
# Configurable parameters
# ============================================================
HIST_YEAR_START,   HIST_YEAR_END    = AMON_HIST_YEARS      # 1995-2014
FUTURE_YEAR_START, FUTURE_YEAR_END  = AMON_FUTURE_YEARS    # 2080-2099

MONTHS             = [8]          # months to compute delta for

RAW_DIR            = AMON_DIR
OUTPUT_DIR         = Path("../hands-on/PGW/Tokyo/LDASIN-Common/")
GEO_EM_FILE        = Path("../hands-on/PGW/Tokyo/geo/geo_em.d03.nc")
# ============================================================


def get_domain_bounds(geo_em_file: Path) -> tuple[float, float, float, float]:
    """Return (lat_min, lat_max, lon_min, lon_max) from geo_em file."""
    geo_em = xr.open_dataset(geo_em_file)
    lat = geo_em.XLAT_M.values[0]
    lon = geo_em.XLONG_M.values[0]
    return lat.min(), lat.max(), lon.min(), lon.max()


def load_monthly_mean(
    raw_dir: Path,
    var_id: str,
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
    Load the Amon monthly climatology file (dims: month, [plev,] lat, lon) written by
    download_miroc6_pgw_hrldas.py, select the given month and subset to domain.
    """
    pattern = f"{var_id}_*.{SOURCE_ID}.{experiment_id}.Amon.*_{MEMBER_ID}_{year_start}_{year_end}.nc"
    files = sorted(raw_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files found for pattern: {pattern}")
    _logger.info(f"    reading {var_id} from {files[0].name}")

    ds = xr.open_dataset(files[0], decode_times=False)
    if month not in ds.month.values:
        raise ValueError(f"No data found for {var_id} {experiment_id} month={month}")

    # Subset to domain (with buffer)
    buf = 3.0
    ds = ds.sel(month=month).sel(
        lat=slice(lat_min - buf, lat_max + buf),
        lon=slice(lon_min - buf, lon_max + buf),
    )

    # drop scalar/aux coords (month, height, lat_bnds, ...) so variables merge cleanly
    return ds[var_id].reset_coords(drop=True)


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
    lat_min, lat_max, lon_min, lon_max = get_domain_bounds(geo_em_file)

    _logger.info(f"Domain: lat=[{lat_min:.2f}, {lat_max:.2f}], lon=[{lon_min:.2f}, {lon_max:.2f}]")

    for month in months:
        _logger.info(f"=== Month {month:02d} ===")
        delta_vars = {}

        for var_id in AMON_VARIABLES:
            _logger.info(f"  {var_id} (Amon)")

            try:
                hist_mean = load_monthly_mean(
                    raw_dir, var_id,
                    hist_experiment, hist_year_start, hist_year_end,
                    month, lat_min, lat_max, lon_min, lon_max,
                )
                future_mean = load_monthly_mean(
                    raw_dir, var_id,
                    future_experiment, future_year_start, future_year_end,
                    month, lat_min, lat_max, lon_min, lon_max,
                )
            except (FileNotFoundError, ValueError) as e:
                # ratio vars (pr) use 1 as "no change", others use 0
                no_change = 1.0 if var_id == "pr" else 0.0
                _logger.warning(f"  {var_id} not found, signal set to {no_change}: {e}")
                delta_vars[var_id] = xr.DataArray(no_change)
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

        # Replace scalar placeholders (missing files: 0.0, or 1.0 for pr) with proper lat/lon grids
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
                        np.full((len(lat_coord), len(lon_coord)), float(da.values)),
                        dims=[lat_dim, lon_dim],
                        coords={lat_dim: lat_coord, lon_dim: lon_coord},
                    )
                    _logger.info(f"  {var_id}: expanded scalar {float(da.values)} to ({lat_dim}, {lon_dim}) grid")

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
