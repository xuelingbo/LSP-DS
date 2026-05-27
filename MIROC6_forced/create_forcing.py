#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##############################################################################
# History:
#   2026.05.27  Rewritten for direct MIROC6 forcing (XUE Lingbo, CCS, Tsukuba)
#   2026.04.08  Add URBLANDUSEF and AHE (XUE Lingbo, CCS, Tsukuba, Japan)
#   2023.03.31  Created by DOAN Quang Van and XUE Lingbo (CCS, Tsukuba, Japan)
##############################################################################

import numpy as np
import os
import pandas as pd
import xarray as xr
import rioxarray
import xesmf as xe
from scipy.interpolate import RectBivariateSpline
from pathlib import Path

SOURCE_ID = "MIROC6"

# ─────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────

def _open_miroc6(raw_data_dir, var_id, table_id, experiment_id, member_id):
    """Open all MIROC6 files for a variable as a single dataset (no dask required)."""
    pattern = f"{var_id}_{table_id}_{SOURCE_ID}_{experiment_id}_{member_id}_gn_*.nc"
    files = sorted(Path(raw_data_dir).glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files found: {raw_data_dir}/{pattern}")
    if len(files) == 1:
        return xr.open_dataset(str(files[0]))
    return xr.concat([xr.open_dataset(str(f)) for f in files], dim='time')


def _latlon_dims(ds):
    lat = 'lat' if 'lat' in ds.dims else 'latitude'
    lon = 'lon' if 'lon' in ds.dims else 'longitude'
    return lat, lon


def _subset(ds, lat_min, lat_max, lon_min, lon_max):
    ld, od = _latlon_dims(ds)
    lats = ds[ld].values
    if lats[0] <= lats[-1]:  # ascending (CMIP6 standard)
        return ds.sel({ld: slice(lat_min, lat_max), od: slice(lon_min, lon_max)})
    else:                     # descending
        return ds.sel({ld: slice(lat_max, lat_min), od: slice(lon_min, lon_max)})


def _to_ascending(raw_lat, data):
    """Flip lat/data so lat is ascending (required by RectBivariateSpline)."""
    if raw_lat[0] > raw_lat[-1]:
        return raw_lat[::-1], data[::-1, :]
    return raw_lat, data


def _cos_sza(geo_lat, geo_lon, t):
    """Per-cell cosine of solar zenith angle (>=0) at UTC time t."""
    doy  = t.day_of_year
    h    = t.hour + 0.5       # mid-hour UTC
    B    = np.radians(360 / 365 * (doy - 81))
    decl = np.radians(23.45 * np.sin(B))
    eot  = (9.87 * np.sin(2*B) - 7.53 * np.cos(B) - 1.5 * np.sin(B)) / 60.0
    lst  = h + geo_lon / 15.0 + eot
    ha   = np.radians(15.0 * (lst - 12.0))
    cos_z = (np.sin(np.radians(geo_lat)) * np.sin(decl) +
             np.cos(np.radians(geo_lat)) * np.cos(decl) * np.cos(ha))
    return np.maximum(cos_z, 0.0)


def _swdown_hourly(rsds_daily_grid, geo_lat, geo_lon, date):
    """Disaggregate daily mean SWDOWN to 24 hourly values using solar geometry."""
    weights = np.stack(
        [_cos_sza(geo_lat, geo_lon, pd.Timestamp(date) + pd.Timedelta(hours=h))
         for h in range(24)], axis=0)           # (24, ny, nx)
    w_sum = weights.sum(axis=0, keepdims=True)
    w_sum = np.where(w_sum > 0, w_sum, 1.0)
    return rsds_daily_grid[np.newaxis] * 24.0 * weights / w_sum   # (24, ny, nx)


def bounds_1d(c):
    b = np.empty(len(c) + 1)
    b[1:-1] = 0.5 * (c[:-1] + c[1:])
    b[0]    = c[0]  - (c[1]  - c[0])  / 2
    b[-1]   = c[-1] + (c[-1] - c[-2]) / 2
    return b


def bounds_2d(c):
    ny, nx = c.shape
    b = np.zeros((ny + 1, nx + 1))
    b[1:-1, 1:-1] = 0.25 * (c[:-1, :-1] + c[:-1, 1:] + c[1:, :-1] + c[1:, 1:])
    b[0,   1:-1]  = 2*b[1,   1:-1] - b[2,   1:-1]
    b[-1,  1:-1]  = 2*b[-2,  1:-1] - b[-3,  1:-1]
    b[1:-1, 0]    = 2*b[1:-1, 1]   - b[1:-1, 2]
    b[1:-1, -1]   = 2*b[1:-1, -2]  - b[1:-1, -3]
    b[0,   0]     = b[1,  1]   + (b[1,  1]  - b[2,  2])
    b[0,   -1]    = b[1,  -2]  + (b[1, -2]  - b[2, -3])
    b[-1,  0]     = b[-2, 1]   + (b[-2, 1]  - b[-3, 2])
    b[-1,  -1]    = b[-2, -2]  + (b[-2, -2] - b[-3, -3])
    return b


# ─────────────────────────────────────────────
# Main functions
# ─────────────────────────────────────────────

def create_LDASIN_files(start_date, end_date, raw_data_dir, output_dir, geo_em_file,
                        experiment_id, member_id, plev, ZLVL,
                        ahe_file=None, ahe_profile=None, utc_offset=None):
    """
    Create hourly HRLDAS LDASIN forcing files from MIROC6 data directly.

    Parameters
    ----------
    plev : int
        Target pressure level in Pa (e.g. 92500 for 925 hPa).
        ta/ua/va/hus/zg are selected at this level.
    experiment_id : str
        MIROC6 experiment (e.g. 'historical', 'ssp585').
    member_id : str
        MIROC6 member (e.g. 'r1i1p1f1').
    """

    os.makedirs(os.path.join(output_dir, "LDASIN"), exist_ok=True)

    UNITS = {
        'T2D': 'K', 'Q2D': 'kg/kg', 'U2D': 'm/s', 'V2D': 'm/s',
        'PSFC': 'Pa', 'LWDOWN': 'W/m^2', 'SWDOWN': 'W/m^2',
        'RAINRATE': 'kg/m^2/s', 'AHE': 'W/m^2',
        'LAI': 'm^2/m^2', 'VEGFRA': '%',
    }

    geo_em       = xr.open_dataset(geo_em_file)
    geo_lat      = geo_em.XLAT_M.values[0]
    geo_lon      = geo_em.XLONG_M.values[0]
    geo_lat_flat = geo_lat.ravel()
    geo_lon_flat = geo_lon.ravel()
    HGT_M        = geo_em['HGT_M'].values.squeeze()

    buf = 2.0
    lat_min, lat_max = geo_lat.min() - buf, geo_lat.max() + buf
    lon_min, lon_max = geo_lon.min() - buf, geo_lon.max() + buf

    def open_sub(var_id, table_id):
        return _subset(
            _open_miroc6(raw_data_dir, var_id, table_id, experiment_id, member_id),
            lat_min, lat_max, lon_min, lon_max)

    # Open MIROC6 datasets (xarray is lazy — no data loaded until .values)
    ds_ta   = open_sub('ta',   '6hrPlevPt')
    ds_ua   = open_sub('ua',   '6hrPlevPt')
    ds_va   = open_sub('va',   '6hrPlevPt')
    ds_hus  = open_sub('hus',  '6hrPlevPt')
    ds_zg   = open_sub('zg',   '6hrPlevPt')
    ds_ps   = open_sub('ps',   '6hrLev')
    ds_rlds = open_sub('rlds', 'day')
    ds_rsds = open_sub('rsds', 'day')
    ds_pr   = open_sub('pr',   '6hrPlev')

    # Select target pressure level (ta/ua/va/hus/zg are 3-D: time × plev × lat × lon)
    ta_da  = ds_ta['ta'].sel(plev=plev)
    ua_da  = ds_ua['ua'].sel(plev=plev)
    va_da  = ds_va['va'].sel(plev=plev)
    hus_da = ds_hus['hus'].sel(plev=plev)
    zg_da  = ds_zg['zg'].sel(plev=plev)   # geopotential height [m]

    # Extract lat/lon arrays for spatial interpolation
    ld3,  od3  = _latlon_dims(ds_ta)
    ldps, odps = _latlon_dims(ds_ps)
    ldpr, odpr = _latlon_dims(ds_pr)
    ldrd, odrd = _latlon_dims(ds_rlds)

    raw_lat_3d  = ds_ta[ld3].values;   raw_lon_3d  = ds_ta[od3].values
    raw_lat_ps  = ds_ps[ldps].values;  raw_lon_ps  = ds_ps[odps].values
    raw_lat_pr  = ds_pr[ldpr].values;  raw_lon_pr  = ds_pr[odpr].values
    raw_lat_rad = ds_rlds[ldrd].values; raw_lon_rad = ds_rlds[odrd].values

    def regrid(raw_lat, raw_lon, data):
        lat, dat = _to_ascending(raw_lat, data)
        dat = np.where(np.isnan(dat), np.nanmean(dat), dat)
        spl = RectBivariateSpline(lat, raw_lon, dat, kx=1, ky=1)
        return spl.ev(geo_lat_flat, geo_lon_flat).reshape(geo_lat.shape)

    # ── AHE ──────────────────────────────────────────────────────────────────
    def ahe_raster_hourly(ahe_file, ahe_profile, geo_em_file):
        buffer  = 0.2
        geo_em_ = xr.open_dataset(geo_em_file)
        glat    = geo_em_.XLAT_M.values[0]
        glon    = geo_em_.XLONG_M.values[0]
        ahe = rioxarray.open_rasterio(ahe_file).squeeze()
        ahe = ahe.rio.reproject("EPSG:4326")
        ahe = ahe.rio.clip_box(minx=glon.min()-buffer, miny=glat.min()-buffer,
                               maxx=glon.max()+buffer, maxy=glat.max()+buffer)
        ahe_lat = ahe.y.values; ahe_lon = ahe.x.values
        if ahe_lat[0] > ahe_lat[-1]:
            ahe_lat = ahe_lat[::-1]; ahe_raw = ahe.values[::-1, :]
        else:
            ahe_raw = ahe.values
        ahe_raw  = np.where(ahe_raw < -1e30, 0.0, ahe_raw)
        ahe_vals = np.nan_to_num(ahe_raw, nan=0.0)
        ds_in  = xr.Dataset({'lat':   (['lat'],   ahe_lat, {'units': 'degrees_north'}),
                              'lon':   (['lon'],   ahe_lon, {'units': 'degrees_east'}),
                              'lat_b': (['lat_b'], bounds_1d(ahe_lat)),
                              'lon_b': (['lon_b'], bounds_1d(ahe_lon))})
        ds_out = xr.Dataset({'lat':   (['y', 'x'], glat,           {'units': 'degrees_north'}),
                              'lon':   (['y', 'x'], glon,           {'units': 'degrees_east'}),
                              'lat_b': (['y_b', 'x_b'], bounds_2d(glat)),
                              'lon_b': (['y_b', 'x_b'], bounds_2d(glon))})
        rg = xe.Regridder(ds_in, ds_out, method='conservative',
                          unmapped_to_nan=True, ignore_degenerate=True)
        ahe_interp    = np.nan_to_num(rg(xr.DataArray(ahe_vals, dims=['lat', 'lon'])).values, nan=0.0)
        urblandusef   = geo_em_.LANDUSEF.sel(land_cat=12).values.squeeze()
        valid_urban   = urblandusef[urblandusef > 0]
        if valid_urban.size > 0:
            ub = np.arange(0, valid_urban.max() + 0.1, 0.1)
            uc, ue = np.histogram(valid_urban, bins=ub)
            modal_urban = (ue[np.argmax(uc)] + ue[np.argmax(uc) + 1]) / 2.0
        else:
            modal_urban = 0.7
        valid_ahe  = ahe_interp[(ahe_interp > 0) & (urblandusef > 0)]
        median_ahe = np.median(valid_ahe) if valid_ahe.size > 0 else 10
        print(f"Modal urban fraction: {modal_urban:.2f}, Median AHE: {median_ahe:.2f} W/m^2")
        fill_ahe   = np.where(urblandusef > 0, median_ahe / modal_urban * urblandusef, 0.0)
        ahe_interp = np.where((urblandusef > 0) & (ahe_interp <= 0), fill_ahe, ahe_interp)
        ahe_interp = np.where(urblandusef > 0, ahe_interp, 0.0)
        profile_arr  = np.roll(np.array(ahe_profile), -utc_offset)
        profile_norm = profile_arr / profile_arr.sum() * 24
        return np.array([ahe_interp * w for w in profile_norm])

    if ahe_file is not None and ahe_profile is not None and utc_offset is not None:
        ahe_hourly = ahe_raster_hourly(ahe_file, ahe_profile, geo_em_file)
    else:
        ahe_hourly = np.zeros((24, geo_lat.shape[0], geo_lat.shape[1]))

    # ── Main loop ─────────────────────────────────────────────────────────────
    for date in pd.date_range(start_date, end_date, freq='D'):

        # Daily radiation: regrid once per day
        date_str  = str(date.date())
        rlds_grid = regrid(raw_lat_rad, raw_lon_rad,
                           ds_rlds['rlds'].sel(time=date_str, method='nearest').values.squeeze())
        rsds_grid = regrid(raw_lat_rad, raw_lon_rad,
                           ds_rsds['rsds'].sel(time=date_str, method='nearest').values.squeeze())

        # Disaggregate SWDOWN to hourly using solar geometry
        swdown_h = _swdown_hourly(rsds_grid, geo_lat, geo_lon, date)   # (24, ny, nx)

        for time in pd.date_range(date, periods=24, freq='h'):

            t = pd.Timestamp(time)

            # Interpolate 6-hourly / 3-hourly variables to this hour
            ta_h  = ta_da.interp(time=t,  method='linear').values
            ua_h  = ua_da.interp(time=t,  method='linear').values
            va_h  = va_da.interp(time=t,  method='linear').values
            hus_h = hus_da.interp(time=t, method='linear').values
            zg_h  = zg_da.interp(time=t,  method='linear').values   # geopotential height [m]
            ps_h  = ds_ps['ps'].interp(time=t, method='linear').values.squeeze()
            pr_h  = ds_pr['pr'].interp(time=t, method='linear').values.squeeze()

            # Regrid to WRF domain
            ta_grid  = regrid(raw_lat_3d, raw_lon_3d, ta_h)
            ua_grid  = regrid(raw_lat_3d, raw_lon_3d, ua_h)
            va_grid  = regrid(raw_lat_3d, raw_lon_3d, va_h)
            hus_grid = regrid(raw_lat_3d, raw_lon_3d, hus_h)
            zg_grid  = regrid(raw_lat_3d, raw_lon_3d, zg_h)
            ps_grid  = regrid(raw_lat_ps, raw_lon_ps, ps_h)
            pr_grid  = regrid(raw_lat_pr, raw_lon_pr, pr_h)

            # T2D: correct from pressure-level height to WRF grid elevation
            # T_wrf = T_plev + Γ*(zg_plev − (HGT_M + ZLVL)),   Γ = −0.0065 K/m
            T2D = ta_grid + (-0.0065) * (HGT_M + ZLVL - zg_grid)

            LDASIN = xr.Dataset()

            def put(lname, data):
                LDASIN[lname] = (('Time', 'south_north', 'west_east'), [data])
                LDASIN[lname].attrs['units'] = UNITS[lname]

            put('T2D',      T2D)
            put('Q2D',      hus_grid)
            put('U2D',      ua_grid)
            put('V2D',      va_grid)
            put('PSFC',     ps_grid)
            put('LWDOWN',   rlds_grid)          # daily mean held constant across 24 h
            put('SWDOWN',   swdown_h[time.hour])
            put('RAINRATE', pr_grid)
            put('AHE',      ahe_hourly[time.hour])

            # LAI and VEGFRA: interpolated from geo_em climatology (same as ERA5 version)
            for var, lname in [('LAI12M', 'LAI'), ('GREENFRAC', 'VEGFRA')]:
                suffix = '_leap' if date.is_leap_year else ''
                ref_yr = '2020' if date.is_leap_year else '2021'
                raw_ds = xr.open_dataset(os.path.join(output_dir, 'LDASIN', f'{var}{suffix}.nc'))
                LDASIN[lname] = (('Time', 'south_north', 'west_east'),
                                 [raw_ds[var].sel(date=ref_yr + str(date.date())[-6:]).values])
                LDASIN[lname].attrs['units'] = UNITS[lname]

            encoding   = [{v: {'_FillValue': None}} for v in LDASIN.variables]
            out_name   = f"{time.strftime('%Y%m%d%H')}.LDASIN_DOMAIN{geo_em_file[-4]}"
            LDASIN.to_netcdf(os.path.join(output_dir, 'LDASIN', out_name), encoding=encoding[0])
            print(out_name)


def create_setup_file(start_date, raw_data_dir, output_dir, geo_em_file,
                      experiment_id, member_id, lcz=0):
    """
    Create HRLDAS setup file using MIROC6 initial soil/surface conditions.

    Soil moisture (mrsos) is only available for the top 10 cm layer;
    it is used for all 4 HRLDAS soil layers as an approximation.
    Soil temperature (tsl) is selected at the 4 depths nearest to
    HRLDAS ZS = [0.035, 0.175, 0.64, 1.945] m.
    """

    os.makedirs(os.path.join(output_dir, "LDASIN"), exist_ok=True)

    variables = {
        "Times":       {'units': ''},
        "XLAT":        {'units': 'degree_north',  'geoname': 'XLAT_M'},
        "XLONG":       {'units': 'degree_east',   'geoname': 'XLONG_M'},
        "HGT":         {'units': 'm',             'geoname': 'HGT_M'},
        "MAPFAC_MX":   {'units': '',              'geoname': 'MAPFAC_MX'},
        "MAPFAC_MY":   {'units': '',              'geoname': 'MAPFAC_MY'},
        "URBLANDUSEF": {'units': '',              'geoname': 'LANDUSEF'},
        "TMN":         {'units': 'K',             'geoname': 'SOILTEMP'},
        "SHDMAX":      {'units': '%'},
        "SHDMIN":      {'units': '%'},
        "LAI":         {'units': 'm^2/m^2'},
        "XLAND":       {'units': '',              'geoname': 'LU_INDEX'},
        "ISLTYP":      {'units': '',              'geoname': 'SOILCTOP'},
        "IVGTYP":      {'units': '',              'geoname': 'LU_INDEX'},
        "TSK":         {'units': 'K'},
        "TSLB":        {'units': 'K'},
        "SMOIS":       {'units': 'm^3/m^3'},
        "DZS":         {'units': 'm'},
        "ZS":          {'units': 'm'},
        "SNOW":        {'units': 'kg/m^2'},
        "SEAICE":      {'units': ''},
        "CANWAT":      {'units': 'kg/m^2'},
    }

    geo_em       = xr.open_dataset(geo_em_file)
    geo_lat      = geo_em.XLAT_M.values[0]
    geo_lon      = geo_em.XLONG_M.values[0]
    geo_lat_flat = geo_lat.ravel()
    geo_lon_flat = geo_lon.ravel()

    iswater    = int(geo_em.attrs['ISWATER'])
    islake     = int(geo_em.attrs['ISLAKE'])
    issoilwater = int(geo_em.attrs['ISOILWATER'])
    water_mask = (geo_em.LU_INDEX.values[0] == iswater) | (geo_em.LU_INDEX.values[0] == islake)

    if pd.Timestamp(start_date).is_leap_year:
        LAI = xr.open_dataset(os.path.join(output_dir, 'LDASIN', 'LAI12M_leap.nc'))
    else:
        LAI = xr.open_dataset(os.path.join(output_dir, 'LDASIN', 'LAI12M.nc'))

    buf = 2.0
    lat_min, lat_max = geo_lat.min() - buf, geo_lat.max() + buf
    lon_min, lon_max = geo_lon.min() - buf, geo_lon.max() + buf

    def open_sub(var_id, table_id):
        return _subset(
            _open_miroc6(raw_data_dir, var_id, table_id, experiment_id, member_id),
            lat_min, lat_max, lon_min, lon_max)

    t_ref = pd.Timestamp(start_date)

    ds_ts    = open_sub('ts',    '6hrPlevPt')
    ds_mrsos = open_sub('mrsos', '3hr')
    ds_tsl   = open_sub('tsl',   '6hrPlevPt')
    ds_snw   = open_sub('snw',   'LImon')

    def regrid_masked(raw_lat, raw_lon, data):
        lat, dat = _to_ascending(raw_lat, data)
        # RectBivariateSpline cannot handle NaN; fill ocean/missing cells with land mean
        dat = np.where(np.isnan(dat), np.nanmean(dat), dat)
        spl = RectBivariateSpline(lat, raw_lon, dat, kx=1, ky=1)
        interp = spl.ev(geo_lat_flat, geo_lon_flat).reshape(geo_lat.shape)
        return np.where(water_mask, np.nan, interp)

    ld_ts,  od_ts  = _latlon_dims(ds_ts)
    ld_sm,  od_sm  = _latlon_dims(ds_mrsos)
    ld_tsl, od_tsl = _latlon_dims(ds_tsl)
    ld_snw, od_snw = _latlon_dims(ds_snw)

    raw_lat_ts  = ds_ts[ld_ts].values;   raw_lon_ts  = ds_ts[od_ts].values
    raw_lat_sm  = ds_mrsos[ld_sm].values; raw_lon_sm  = ds_mrsos[od_sm].values
    raw_lat_tsl = ds_tsl[ld_tsl].values; raw_lon_tsl = ds_tsl[od_tsl].values
    raw_lat_snw = ds_snw[ld_snw].values; raw_lon_snw = ds_snw[od_snw].values

    # TSK: skin temperature
    ts_val  = ds_ts['ts'].sel(time=t_ref, method='nearest').values.squeeze()
    TSK     = regrid_masked(raw_lat_ts, raw_lon_ts, ts_val)

    # SMOIS: top 0-10 cm only; apply 0.01 scale (kg/m² → m³/m³) and use for all 4 layers
    mrsos_val = ds_mrsos['mrsos'].sel(time=t_ref, method='nearest').values.squeeze()
    smois_1   = regrid_masked(raw_lat_sm, raw_lon_sm, mrsos_val) * 0.01
    SMOIS     = np.stack([smois_1, smois_1, smois_1, smois_1], axis=0)   # (4, ny, nx)

    # TSLB: tsl in 6hrPlevPt has a scalar depth coordinate (single layer).
    # Use the same value for all 4 HRLDAS soil layers as an approximation.
    tsl_val = ds_tsl['tsl'].sel(time=t_ref, method='nearest').values.squeeze()
    tsl_grid = regrid_masked(raw_lat_tsl, raw_lon_tsl, tsl_val)
    TSLB = np.stack([tsl_grid] * 4, axis=0)                             # (4, ny, nx)

    # SNOW: snow water equivalent (kg/m²) — monthly, no unit conversion needed
    snw_val = ds_snw['snw'].sel(time=t_ref, method='nearest').values.squeeze()
    SNOW    = regrid_masked(raw_lat_snw, raw_lon_snw, snw_val)
    SNOW    = np.where(np.isnan(SNOW), -999, SNOW)

    setup_file = xr.Dataset()

    for var in variables:
        dims = ('Time', 'south_north', 'west_east')
        dim4 = ('Time', 'soil_layers_stag', 'south_north', 'west_east')
        dim2 = ('Time', 'soil_layers_stag')

        if var == 'Times':
            data_var, dims = [pd.to_datetime(start_date).strftime('%Y-%m-%d_%H:%M:%S')], ('Time',)

        elif var in ['XLAT', 'XLONG', 'HGT', 'MAPFAC_MX', 'MAPFAC_MY']:
            data_var = geo_em[variables[var]['geoname']].values

        elif var == 'URBLANDUSEF':
            if lcz == 0:
                data_var = geo_em[variables[var]['geoname']].sel(land_cat=12).values
                data_var[data_var < 0] = 0
                data_var[data_var > 1] = 0
            else:
                data_var = np.ones_like(geo_em[variables[var]['geoname']].sel(land_cat=0).values)

        elif var == 'TMN':
            data_var = geo_em[variables[var]['geoname']].values[0] - 0.0065 * geo_em['HGT_M'].values[0]
            data_var = [np.where(water_mask, -1.e36, data_var)]

        elif var == 'SHDMAX':
            data_var = geo_em.GREENFRAC.max(axis=1).values * 100

        elif var == 'SHDMIN':
            data_var = geo_em.GREENFRAC.min(axis=1).values * 100

        elif var == 'LAI':
            ref_yr = '2020' if pd.Timestamp(start_date).is_leap_year else '2021'
            data_var = [LAI.sel(date=ref_yr + start_date[-6:])['LAI12M'].values]

        elif var == 'XLAND':
            data_var = [np.where(water_mask, 2, 1)]

        elif var == 'ISLTYP':
            dominant_index = geo_em['SOILCTOP'].argmax(dim='soil_cat') + 1
            dominant_value = geo_em['SOILCTOP'].max(dim='soil_cat')
            dominant_index_corrected = xr.where(
                (dominant_value < 0.01) | (dominant_value > 1.0), 8, dominant_index)
            data_var = xr.where(setup_file['XLAND'] == 2, issoilwater, dominant_index_corrected)
            data_var = xr.where((setup_file['XLAND'] != 2) & (data_var == 14), 8, data_var).values

        elif var == 'IVGTYP':
            LU = xr.where(((geo_em.LANDUSEF).sel(land_cat=12) <= 1) &
                          ((geo_em.LANDUSEF).sel(land_cat=12) > 0), 13, geo_em.LU_INDEX)
            data_var = LU.values

        elif var == 'TSK':
            data_var = [TSK]

        elif var == 'TSLB':
            data_var, dims = [TSLB], dim4

        elif var == 'SMOIS':
            data_var, dims = [SMOIS], dim4

        elif var == 'ZS':
            data_var, dims = [[0.035, 0.175, 0.64, 1.945]], dim2

        elif var == 'DZS':
            data_var, dims = [[0.07,  0.21,  0.72, 1.89]], dim2

        elif var == 'SNOW':
            data_var = [SNOW]

        elif var == 'SEAICE':
            data_var = np.zeros(geo_em.LU_INDEX.shape)

        elif var == 'CANWAT':
            data_var = np.zeros(geo_em.LU_INDEX.shape)

        print(var, dims, np.array(data_var).shape)
        setup_file[var] = (dims, data_var)
        setup_file[var].attrs['units'] = variables[var]['units']

    setup_file.attrs = geo_em.attrs
    out_name = f"HRLDAS_setup_{pd.to_datetime(start_date).strftime('%Y%m%d')}00_d{geo_em_file[-4]}"
    setup_file.to_netcdf(os.path.join(output_dir, 'LDASIN', out_name))


def create_lai_vegfra(geo_em_file, output_dir):

    os.makedirs(os.path.join(output_dir, "LDASIN"), exist_ok=True)

    for var in ('LAI12M', 'GREENFRAC'):

        geo     = xr.open_dataset(geo_em_file)
        LAI_geo = geo[var].sel(Time=0)

        LAI   = xr.concat([LAI_geo, LAI_geo, LAI_geo, LAI_geo], dim="month")
        month = pd.date_range('2019-01-01', periods=48, freq='MS') + pd.DateOffset(days=14)
        LAI["month"] = ("month", month)

        date = pd.date_range('2019-01-15', '2022-12-15')
        LAI  = LAI.rename({'month': 'date'})
        LAI  = LAI.interp(date=date).to_dataset()

        if var == 'GREENFRAC':
            LAI[var] = xr.where(LAI[var] <= 0, 0.01, LAI[var])
            LAI = LAI * 100

        iswater = int(geo.attrs['ISWATER'])
        islake  = int(geo.attrs['ISLAKE'])
        LU_geo  = geo['LU_INDEX'].sel(Time=0)
        mask    = ((LU_geo == iswater) | (LU_geo == islake)).expand_dims(dim={"date": date}, axis=0)
        LAI[var] = xr.where(mask, 0, LAI[var])

        if var == 'LAI12M':
            LAI.sel(date=slice('2020-01-01', '2020-12-31')).to_netcdf(
                os.path.join(output_dir, 'LDASIN', 'LAI12M_leap.nc'))
            LAI.sel(date=slice('2021-01-01', '2021-12-31')).to_netcdf(
                os.path.join(output_dir, 'LDASIN', 'LAI12M.nc'))
        else:
            LAI.sel(date=slice('2020-01-01', '2020-12-31')).to_netcdf(
                os.path.join(output_dir, 'LDASIN', 'GREENFRAC_leap.nc'))
            LAI.sel(date=slice('2021-01-01', '2021-12-31')).to_netcdf(
                os.path.join(output_dir, 'LDASIN', 'GREENFRAC.nc'))


if __name__ == '__main__':

    start_year      = 2009
    end_year        = 2009
    loop_start_date = '08-01'
    loop_end_date   = '08-15'

    raw_data_dir    = '../hands-on/MIROC6/Tokyo/raw/'
    output_dir      = '../hands-on/MIROC6/Tokyo/'
    geo_em_file     = '../hands-on/MIROC6/Tokyo/geo/geo_em.d03.nc'

    experiment_id   = 'historical'
    member_id       = 'r1i1p1f1'
    plev            = 92500    # Pa — select 925 hPa as the near-surface level
    ZLVL            = 50       # m — reference height for T2D

    create_lai_vegfra(geo_em_file, output_dir)

    for year in range(start_year, end_year + 1):

        create_setup_file(f'{year}-{loop_start_date}',
                          raw_data_dir, output_dir,
                          geo_em_file, experiment_id, member_id, lcz=0)

        create_LDASIN_files(f'{year}-{loop_start_date}', f'{year}-{loop_end_date}',
                            raw_data_dir, output_dir,
                            geo_em_file, experiment_id, member_id, plev, ZLVL)
