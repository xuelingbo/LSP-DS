#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#######################################################################
# History:
#   2026.03.26  Created by XUE Lingbo (CCS, Tsukuba, Japan)
#######################################################################

#######################################################################
# Download GFS 0.25-degree forecast data from NOMADS NCEP for HRLDAS forcing.
#
# Two requests are made per forecast hour and merged into one GRIB2 file:
#   1. Surface level  : DSWRF, DLWRF, PRATE, PRES
#   2. 50 m above ground: TMP, SPFH, UGRD, VGRD
#
# NOMADS filter service:
#   https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl
#   https://nomads.ncep.noaa.gov/gribfilter.php?ds=gfs_0p25
# Variable list:
#   https://www.nco.ncep.noaa.gov/pmb/products/gfs/gfs.t00z.pgrb2.0p25.f000.shtml
#######################################################################

import os
import re
import requests
import boto3
from botocore import UNSIGNED
from botocore.config import Config

NOMADS_BASE    = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
GFS_S3_BUCKET  = "noaa-gfs-bdp-pds"


def get_available_fhours(date, cycle_hour, n_days, interval):
    """
    Query the NOAA GFS S3 bucket and return the leading continuous list of
    forecast hours (step=interval) that exist for the given date/cycle.
    Stops at the first missing hour.

    File naming:
      gfs.YYYYMMDD/HH/atmos/gfs.tHHz.pgrb2.0p25.fNNN
    """
    s3     = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    prefix = f"gfs.{date}/{cycle_hour}/atmos/gfs.t{cycle_hour}z.pgrb2.0p25."

    available = set()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=GFS_S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            filename = obj["Key"].split("/")[-1]
            m = re.search(r"\.f(\d{3})$", filename)
            if m:
                available.add(int(m.group(1)))

    fhours = []
    for h in range(1, n_days * 24 + 1, interval):
        if h in available:
            fhours.append(h)
        else:
            print(f"[info] Continuous sequence ends at f{fhours[-1]:03d} (f{h:03d} not available)")
            break
    return fhours


def build_url(date, cycle_hour, fhour, variables, level_param, subregion=None):
    """
    Build a NOMADS filter URL for GFS 0.25-degree data.

    Parameters
    ----------
    date        : str   e.g. "20260326"
    cycle_hour  : str   e.g. "00", "06", "12", "18"
    fhour       : int   forecast hour (0 = analysis)
    variables   : list  e.g. ["DSWRF", "DLWRF", "PRATE", "PRES"]
    level_param : str or list  NOMADS level token(s), e.g. "lev_surface" or
                               ["lev_0-0.1_m_below_ground", "lev_0.1-0.4_m_below_ground"]
    subregion   : dict  optional keys: toplat, leftlon, rightlon, bottomlat
    """
    filename = f"gfs.t{cycle_hour}z.pgrb2.0p25.f{fhour:03d}"

    params = {
        "dir": f"/gfs.{date}/{cycle_hour}/atmos",
        "file": filename,
    }
    for var in variables:
        params[f"var_{var}"] = "on"
    for lp in ([level_param] if isinstance(level_param, str) else level_param):
        params[lp] = "on"

    if subregion:
        params["subregion"] = ""
        params["toplat"]    = subregion["toplat"]
        params["leftlon"]   = subregion["leftlon"]
        params["rightlon"]  = subregion["rightlon"]
        params["bottomlat"] = subregion["bottomlat"]

    query = "&".join(
        f"{k}={v}" for k, v in params.items()
    )
    return f"{NOMADS_BASE}?{query}"


def download_bytes(url):
    """Download URL and return raw bytes. Raises on HTTP error."""
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()
    return resp.content


def download_gfs_setup(date, cycle_hour, output_dir, subregion=None):
    """
    Download GFS analysis (anl) fields for model initialization:
      - Soil temperature layers 1-4 (TSOIL)
      - Soil moisture layers 1-4 (SOILW)
      - Skin temperature (TMP at surface)
      - Snow depth (WEASD: Water Equivalent of Accumulated Snow Depth [kg/m^2] )

    Parameters
    ----------
    date       : str   e.g. "20260326"
    cycle_hour : str   e.g. "00"
    output_dir : str   directory where the GRIB2 file is saved
    subregion  : dict or None
    """
    os.makedirs(output_dir, exist_ok=True)

    out_file = os.path.join(
        output_dir,
        f"gfs.t{cycle_hour}z.pgrb2.0p25.setup.grb2"
    )
    if os.path.exists(out_file):
        print(f"[skip] {out_file} already exists")
        return

    soil_levels = [
        "lev_0-0.1_m_below_ground",
        "lev_0.1-0.4_m_below_ground",
        "lev_0.4-1_m_below_ground",
        "lev_1-2_m_below_ground",
    ]

    # TSOIL + SOILW at all four soil layers
    url_soil = build_url(
        date, cycle_hour, 1,
        ["TSOIL", "SOILW"], soil_levels,
        subregion=subregion
    )
    print(f"[download] setup TSOIL+SOILW  {url_soil}")
    data_soil = download_bytes(url_soil)

    # Skin temperature + snow depth at surface
    url_sfc = build_url(
        date, cycle_hour, 1,
        ["TMP", "WEASD"], "lev_surface",
        subregion=subregion
    )
    print(f"[download] setup TMP+WEASD  {url_sfc}")
    data_sfc = download_bytes(url_sfc)

    combined = data_soil + data_sfc
    with open(out_file, "wb") as f:
        f.write(combined)
    print(f"[saved]    {out_file}  ({len(combined)/1024:.1f} KB)")


def download_gfs_forcing(date, cycle_hour, fhours, output_dir,
                         upper_level="1000_mb", subregion=None):
    """
    Download GFS surface + upper-level forcing fields and save each
    forecast hour as a single combined GRIB2 file.

    Parameters
    ----------
    date        : str        e.g. "20260326"
    cycle_hour  : str        e.g. "00"
    fhours      : list[int]  forecast hours to download, e.g. [0, 3, 6, ...]
    output_dir  : str        directory where GRIB2 files are saved
    upper_level : str        NOMADS level for upper-layer winds/T/q,
                             e.g. "1000_mb"
    subregion   : dict or None
                  {"toplat": 55, "leftlon": 50, "rightlon": 200, "bottomlat": 10}
    """
    os.makedirs(output_dir, exist_ok=True)

    surface_vars    = ["DSWRF", "DLWRF", "PRATE", "PRES", "HGT"]
    upper_vars      = ["TMP", "SPFH", "UGRD", "VGRD", "HGT"]
    upper_lev_param = f"lev_{upper_level}"

    for fhour in fhours:
        tag = f"f{fhour:03d}"
        out_file = os.path.join(
            output_dir,
            f"gfs.t{cycle_hour}z.pgrb2.0p25.{tag}.grb2"
        )

        if os.path.exists(out_file):
            print(f"[skip] {out_file} already exists")
            continue

        # --- surface fields ---
        url_sfc = build_url(
            date, cycle_hour, fhour,
            surface_vars, "lev_surface",
            subregion=subregion
        )
        print(f"[download] surface  fhour={fhour:03d}  {url_sfc}")
        data_sfc = download_bytes(url_sfc)

        # --- upper-level fields (default: 50 m above ground, configurable via upper_level) ---
        url_upper = build_url(
            date, cycle_hour, fhour,
            upper_vars, upper_lev_param,
            subregion=subregion
        )
        print(f"[download] {upper_level}  fhour={fhour:03d}  {url_upper}")
        data_upper = download_bytes(url_upper)

        # GRIB2 messages are self-contained; concatenation produces a valid file
        combined = data_sfc + data_upper
        with open(out_file, "wb") as f:
            f.write(combined)
        print(f"[saved]    {out_file}  ({len(combined)/1024:.1f} KB)")


if __name__ == "__main__":

    # ------------------------------------------------------------------ #
    # User settings
    # ------------------------------------------------------------------ #
    date       = "20260720"        # YYYYMMDD
    cycle_hour = "00"              # GFS cycle: "00", "06", "12", "18"
    n_days     = 7                         # number of forecast days
    interval   = 1                         # forecast hour interval (1 or 3)

    print(f"[check] Querying available forecast hours from S3 ...")
    fhours = get_available_fhours(date, cycle_hour, n_days, interval)

    # Spatial subset (set to None to download global)
    subregion  = {
        "toplat"   : 55,
        "leftlon"  : 30,
        "rightlon" : 155,
        "bottomlat": -50,
    }

    upper_level = "1000_mb"  # e.g. "1000_mb"
    output_dir  = f'../hands-on/GFS/Tokyo/raw/{date}'
    # ------------------------------------------------------------------ #

    download_gfs_setup(date, cycle_hour, output_dir, subregion=subregion)
    download_gfs_forcing(date, cycle_hour, fhours, output_dir,
                         upper_level=upper_level, subregion=subregion)
