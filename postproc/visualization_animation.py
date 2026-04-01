#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#######################################################################
# History:
#   2026.04.01  Created by XUE Lingbo (CCS, Tsukuba, Japan)
#######################################################################

#######################################################################
# Plot a HRLDAS LDASOUT variable and export as GIF or MP4.
#
# File naming: YYYYMMDDHH.LDASOUT_DOMAIN3
# Coordinates: read from geo_em.d01.nc (XLAT_M / XLONG_M)
#######################################################################

import os
import glob
import subprocess
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import cartopy
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import cartopy.mpl.gridliner
from netCDF4 import Dataset
from datetime import datetime, timedelta

# ------------------------------------------------------------------ #
# Configuration                                                        #
# ------------------------------------------------------------------ #

# Date range to plot (None = use all available files)
start_dt = datetime(2026, 3, 31,  1)
end_dt   = datetime(2026, 4, 5,  0)

ldasout_dir = f"/home/xuelingbo/LSP-DS/hands-on/GFS/Tokyo/LDASOUT/{start_dt.strftime('%Y%m%d')}"
geo_file    = "/home/xuelingbo/LSP-DS/hands-on/GFS/Tokyo/geo/geo_em.d03.nc"
output_dir  = "/home/xuelingbo/LSP-DS/hands-on/GFS/Tokyo/figures/"
var_name    = "RH2"       # HRLDAS variable name (e.g. T2, RH2)
output_fmt  = "mp4"      # "gif" or "mp4"
output_name = f"HRLDAS_{var_name}"

# Colormap and value range (None = auto)
cmap = 'Blues' if var_name in ['RH2'] else "RdYlBu_r"
vmin = None
vmax = None

# Time zone: UTC offset in hours (e.g. 9 for JST)
utc_offset = 9

# Figure settings
dpi     = 100
figsize = (8, 7)
fps     = 4

# For 3-D variables (e.g. SOIL_T, SOIL_M), specify the level index
level_idx = 0   # 0 = top soil layer

# ------------------------------------------------------------------ #


def get_ldasout_files(ldasout_dir, start_dt, end_dt):
    """Return sorted LDASOUT files within the date range."""
    files = sorted(glob.glob(os.path.join(ldasout_dir, "*.LDASOUT_DOMAIN3")))
    if not (start_dt or end_dt):
        return files
    filtered = []
    for f in files:
        tag = os.path.basename(f).replace(".LDASOUT_DOMAIN3", "")
        try:
            dt = datetime.strptime(tag, "%Y%m%d%H")
        except ValueError:
            continue
        if start_dt and dt < start_dt:
            continue
        if end_dt and dt > end_dt:
            continue
        filtered.append(f)
    return filtered


def get_latlon(geo_file):
    """Read 2-D lat/lon grids from geo_em.d01.nc."""
    nc  = Dataset(geo_file)
    lats = nc.variables['XLAT_M'][0]   # (south_north, west_east)
    lons = nc.variables['XLONG_M'][0]
    nc.close()
    return np.array(lats), np.array(lons)


def read_var(nc, var_name, level_idx=0):
    """Read 2-D slice from LDASOUT file."""
    v = nc.variables[var_name]
    units = getattr(v, 'units', '')
    data  = v[0]   # Time dim = 1 per file
    if data.ndim == 3:
        data = data[level_idx]
    data = np.array(data, dtype=float)
    data[np.abs(data) > 1e30] = np.nan
    return data, units


def plot_frame(lats, lons, data, units, convert_K_to_C,
               v_lo, v_hi, cmap, time_str, figsize, dpi):
    """Plot one time step and return a matplotlib Figure."""
    if convert_K_to_C:
        data = data - 273.15

    proj_lcc = ccrs.LambertConformal(
        central_longitude=float(lons.mean()),
        central_latitude=float(lats.mean()),
        standard_parallels=(30, 40)
    )

    fig, ax = plt.subplots(1, 1, figsize=figsize, dpi=dpi,
                           subplot_kw={"projection": proj_lcc})
    ax.set_extent([lons.min(), lons.max(), lats.min(), lats.max()],
                  crs=ccrs.PlateCarree())

    import matplotlib.ticker as mticker
    gl = ax.gridlines(draw_labels=True, linewidth=0.4, color='gray',
                      alpha=0.6, linestyle='--',
                      x_inline=False, y_inline=False)
    gl.top_labels   = False
    gl.right_labels = False
    gl.xformatter   = cartopy.mpl.gridliner.LongitudeFormatter()
    gl.yformatter   = cartopy.mpl.gridliner.LatitudeFormatter()
    gl.xlabel_style = {'rotation': 0}
    gl.xlocator     = mticker.MultipleLocator(0.5)
    gl.ylocator     = mticker.MultipleLocator(0.25)

    cf = ax.pcolormesh(lons, lats, data,
                       transform=ccrs.PlateCarree(),
                       cmap=cmap, vmin=v_lo, vmax=v_hi)
    cb_label = "°C" if convert_K_to_C else units
    plt.colorbar(cf, ax=ax, shrink=0.8, pad=0.02, label=cb_label)
    ax.set_title(f"{var_name}  {time_str}", fontsize=11)

    return fig


def save_as_gif(frames_dir, output_path, fps):
    pattern = os.path.join(frames_dir, "frame_%04d.png")
    palette_path = os.path.join(frames_dir, "palette.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-start_number", "1",
                    "-framerate", str(fps), "-i", pattern,
                    "-vf", "palettegen", palette_path], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-start_number", "1",
                    "-framerate", str(fps), "-i", pattern,
                    "-i", palette_path, "-lavfi", "paletteuse",
                    "-loop", "0", output_path], check=True)
    print(f"[saved] {output_path}")


def save_as_mp4(frames_dir, output_path, fps):
    pattern = os.path.join(frames_dir, "frame_%04d.png")
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-start_number", "1",
           "-framerate", str(fps), "-i", pattern,
           "-c:v", "libx264", "-crf", "18",
           "-preset", "slow", "-pix_fmt", "yuv420p", output_path]
    subprocess.run(cmd, check=True)
    print(f"[saved] {output_path}")


def main():
    os.makedirs(output_dir, exist_ok=True)
    frames_dir = os.path.join(output_dir, f"_frames_{output_name}")
    os.makedirs(frames_dir, exist_ok=True)

    files = get_ldasout_files(ldasout_dir, start_dt, end_dt)
    if not files:
        print("No LDASOUT files found in the specified date range.")
        return
    print(f"Found {len(files)} files.")

    # Get lat/lon from geo_em file (same grid for all LDASOUT files)
    lats, lons = get_latlon(geo_file)

    nc0 = Dataset(files[0])
    _, units0 = read_var(nc0, var_name, level_idx)
    nc0.close()

    convert_K_to_C = (units0 == 'K' or var_name.upper().startswith("T"))
    if convert_K_to_C:
        print("  Unit is K, converting to °C")

    # First pass: auto-detect vmin/vmax
    v_lo, v_hi = vmin, vmax
    if v_lo is None or v_hi is None:
        print("Auto-detecting value range ...")
        all_vals = []
        for f in files:
            nc = Dataset(f)
            data, _ = read_var(nc, var_name, level_idx)
            if convert_K_to_C:
                data = data - 273.15
            all_vals.append(data.ravel())
            nc.close()
        arr = np.concatenate(all_vals)
        v_lo = v_lo if v_lo is not None else float(np.nanpercentile(arr, 2))
        v_hi = v_hi if v_hi is not None else float(np.nanpercentile(arr, 98))
        print(f"  vmin={v_lo:.2f}  vmax={v_hi:.2f}")

    # Second pass: plot each file (skip first time point)
    for i, f in enumerate(files):
        if i == 0:
            continue
        print(f"  [{i+1}/{len(files)}] {os.path.basename(f)}")
        tag    = os.path.basename(f).replace(".LDASOUT_DOMAIN3", "")
        utc_dt = datetime.strptime(tag, "%Y%m%d%H")
        loc_dt = utc_dt + timedelta(hours=utc_offset)
        tz_label = f"UTC+{utc_offset}" if utc_offset >= 0 else f"UTC{utc_offset}"
        time_str = f"{loc_dt.strftime('%Y-%m-%d %H:%M')} ({tz_label})"

        nc   = Dataset(f)
        data, _ = read_var(nc, var_name, level_idx)
        nc.close()

        fig = plot_frame(lats, lons, data, units0, convert_K_to_C,
                         v_lo, v_hi, cmap, time_str, figsize, dpi)
        fig.savefig(os.path.join(frames_dir, f"frame_{i:04d}.png"))
        plt.close(fig)

    # Export animation
    out_path = os.path.join(output_dir, f"{output_name}.{output_fmt}")
    if output_fmt == "gif":
        save_as_gif(frames_dir, out_path, fps)
    else:
        save_as_mp4(frames_dir, out_path, fps)

    import shutil
    shutil.rmtree(frames_dir)
    print(f"[cleaned] {frames_dir}")


if __name__ == "__main__":
    main()
