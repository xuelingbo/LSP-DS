#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##############################################################################
# History:
#   2026.03.26  Created by XUE Lingbo (CCS, Tsukuba, Japan)
##############################################################################

##############################################################################
# Create HRLDAS forcing files (LDASIN) from downloaded GFS forecast data.
# Variable list:
#   https://www.nco.ncep.noaa.gov/pmb/products/gfs/gfs.t00z.pgrb2.0p25.f000.shtml
##############################################################################

import numpy as np
import os
import pandas as pd
import xarray as xr
import rioxarray
from scipy.interpolate import RectBivariateSpline
import sys
import matplotlib.pyplot as plot

def create_LDASIN_files(start_date, cycle_hour, fhour, raw_data_dir, output_dir, geo_em, upper_level_m, geo_em_file):

    if not os.path.exists(output_dir+"/LDASIN/"+start_date.replace("-", "")):
        os.makedirs(output_dir+"/LDASIN/"+start_date.replace("-", ""))

    time = pd.to_datetime(start_date) + pd.Timedelta(hours=fhour)

    filename = f"gfs.t{cycle_hour}z.pgrb2.0p25.f{fhour:03d}.grb2"
    # sp     :  surface pressure
    # orog   :  surface geopotential height
    # prate  :  precipitation rate
    ds_sfc_instant = xr.open_dataset(os.path.join(raw_data_dir, filename), engine='cfgrib',
                           filter_by_keys={'stepType': 'instant', 'typeOfLevel': 'surface'})
    # prate  :  precipitation rate (accumulated over the forecast step)
    # sdswrf :  downward short-wave radiation flux (accumulated over the forecast step)
    # sdlwrf :  downward long-wave radiation flux (accumulated over the forecast step)
    ds_sfc_avg = xr.open_dataset(os.path.join(raw_data_dir, filename), engine='cfgrib',
                           filter_by_keys={'stepType': 'avg', 'typeOfLevel': 'surface'})
    # t      :  temperature
    # q      :  specific humidity
    # u      :  u-component of wind
    # v      :  v-component of wind
    # gh     :  geopotential height
    ds_pres_instant = xr.open_dataset(os.path.join(raw_data_dir, filename), engine='cfgrib',
                           filter_by_keys={'stepType': 'instant', 'typeOfLevel': 'isobaricInhPa'})

    geo_lat, geo_lon = geo_em.XLAT_M.values[0], geo_em.XLONG_M.values[0]
    geo_lat_flat, geo_lon_flat = geo_lat.ravel(), geo_lon.ravel()
    # pad by more than one GFS grid spacing (0.25 deg) so the subset always
    # keeps enough surrounding points to interpolate, even for domains
    # smaller than the GFS grid spacing
    GFS_PAD = 0.5
    def subset(ds):
        return ds.sel(latitude=slice(geo_lat.min() - GFS_PAD, geo_lat.max() + GFS_PAD),
                      longitude=slice(geo_lon.min() - GFS_PAD, geo_lon.max() + GFS_PAD))
    ds_sfc_instant_sub, ds_sfc_avg_sub, ds_pres_instant_sub = subset(ds_sfc_instant), subset(ds_sfc_avg), subset(ds_pres_instant)
    raw_lat, raw_lon = ds_sfc_instant_sub.latitude.values, ds_sfc_instant_sub.longitude.values

    vars = {
        't':        {'ds': ds_pres_instant_sub, 'name': 'T2D',      'attrs': {'units': 'K'}},
        'q':        {'ds': ds_pres_instant_sub, 'name': 'Q2D',      'attrs': {'units': 'kg/kg'}},
        'u':        {'ds': ds_pres_instant_sub, 'name': 'U2D',      'attrs': {'units': 'm/s'}},
        'v':        {'ds': ds_pres_instant_sub, 'name': 'V2D',      'attrs': {'units': 'm/s'}},
        'sp':       {'ds': ds_sfc_instant_sub,  'name': 'PSFC',     'attrs': {'units': 'Pa'}},
        'sdlwrf':   {'ds': ds_sfc_avg_sub,      'name': 'LWDOWN',   'attrs': {'units': 'W/m^2'}},
        'sdswrf':   {'ds': ds_sfc_avg_sub,      'name': 'SWDOWN',   'attrs': {'units': 'W/m^2'}},
        'prate':    {'ds': ds_sfc_avg_sub,      'name': 'RAINRATE', 'attrs': {'units': 'kg/m^2/s'}},
        'LAI12M':   {'ds': None,            'name':'LAI',       'attrs': {'units': 'm^2/m^2'}},
        'GREENFRAC':{'ds': None,            'name':'VEGFRA',    'attrs': {'units': '%'}},
    }


    LDASIN_file = xr.Dataset()
    
    for var in vars:

        if vars[var]['ds'] is not None:
            data_var = vars[var]['ds'][var].values

        if var not in ['t', 'LAI12M', 'GREENFRAC']:
            interp_spline = RectBivariateSpline(raw_lat, raw_lon, data_var, kx=1, ky=1)
            data_var_interpolated = interp_spline.ev(geo_lat_flat, geo_lon_flat).reshape(geo_lat.shape)
            LDASIN_file[vars[var]['name']] = (('Time','south_north','west_east'), [data_var_interpolated])
            LDASIN_file[vars[var]['name']].attrs['units'] = vars[var]['attrs']['units']
        elif var == 't':
            gh = ds_pres_instant_sub['gh']
            data_var_correct_to_msl = data_var - (-0.0065 * gh / 9.80665)  
            interp_spline = RectBivariateSpline(raw_lat, raw_lon, data_var_correct_to_msl, kx=1, ky=1)
            data_var_interpolated = interp_spline.ev(geo_lat_flat, geo_lon_flat).reshape(geo_lat.shape)
            data_var_correct_to_HGT_M = data_var_interpolated + ( -0.0065 * (geo_em['HGT_M'].values.squeeze()+upper_level_m))
            LDASIN_file[vars[var]['name']] = (('Time','south_north','west_east'), [data_var_correct_to_HGT_M])
            LDASIN_file[vars[var]['name']].attrs['units'] = vars[var]['attrs']['units']
        elif vars[var]['name'] in ['LAI', 'VEGFRA']:
            if pd.to_datetime(start_date).is_leap_year:
                raw_data_file = xr.open_dataset(os.path.join(output_dir,'LDASIN', start_date.replace("-", ""), f'{var}_leap.nc'))
                data_var = [raw_data_file[var].sel(date='2020'+start_date[-6:]).values]
            else:
                raw_data_file = xr.open_dataset(os.path.join(output_dir,'LDASIN', start_date.replace("-", ""), f'{var}.nc'))
                data_var = [raw_data_file[var].sel(date='2021'+start_date[-6:]).values]
            raw_data_file.close()
            LDASIN_file[vars[var]['name']] = (('Time','south_north','west_east'), data_var)
            LDASIN_file[vars[var]['name']].attrs['units'] = vars[var]['attrs']['units']

    ds_sfc_instant.close()
    ds_sfc_avg.close()
    ds_pres_instant.close()

    encoding=[{var: {'_FillValue': None}} for var in LDASIN_file.variables]
    output_filename = f"{time.strftime('%Y%m%d%H')}.LDASIN_DOMAIN{geo_em_file[-4]}"
    LDASIN_file.to_netcdf(os.path.join(output_dir, 'LDASIN', start_date.replace("-", ""), output_filename), encoding=encoding[0])
    LDASIN_file.close()
    print(output_filename)
                        
def create_setup_file(start_date, cycle_hour, raw_data_dir, output_dir, geo_em, geo_em_file, lcz=0):
    
    if not os.path.exists(output_dir+"/LDASIN/"+start_date.replace("-", "")):
        os.makedirs(output_dir+"/LDASIN/"+start_date.replace("-", ""))

    variables = {
    
        "Times": {'units':''} ,

        # from geo_em file
        "XLAT": {'units': 'degree_north', 'geoname': 'XLAT_M'} , 
        "XLONG": {'units': 'degree_east', 'geoname': 'XLONG_M'} , 
        "HGT": {'units': 'm', 'geoname': 'HGT_M'} , 
        "MAPFAC_MX": {'units': '', 'geoname': 'MAPFAC_MX'} , 
        "MAPFAC_MY": {'units': '', 'geoname': 'MAPFAC_MY'} ,  
        "URBLANDUSEF": {'units': '', 'geoname': 'LANDUSEF'} ,      # for 2D urban fraction

        # edit from geo_em file
        "TMN": {'units': 'K', 'geoname': 'SOILTEMP'} ,  # adjust to elevation
        "SHDMAX": {'units': '%'} ,  # max(100*GREENFRAC) 
        "SHDMIN": {'units': '%'} ,  # min(100*GREENFRAC) 
        "LAI": {'units': 'm^2/m^2'} , # LAI12M after interpolated
        "XLAND": {'units': '', 'geoname': 'LU_INDEX'} ,  # if LU_INDEX==iswater or islake,2; else 1.  
        "ISLTYP": {'units': '', 'geoname': 'SOILCTOP'} ,
        "IVGTYP": {'units': '', 'geoname': 'LU_INDEX'} ,

        # from raw data file
        "TSK": {'units': 'K'} ,  # skin temperature from ERA5 
        "TSLB": {'units': 'K'} ,  # soil layer temp 
        "SMOIS": {'units': 'm^3/m^3'},  # layer volumetric total water content [m3/m3] !!!
        "DZS": {'units': 'm'} ,  # each soil layer depth
        "ZS": {'units': 'm'} ,   # soil layer 
        "SNOW": {'units': 'kg/m^2'} , #snow depth

        # add
        "SEAICE": {'units': ''} ,       # sea ice fraction (=0 for a land point)
        "CANWAT": {'units': 'kg/m^2'} , # set CANWAT = 0
    }
    
    geo_lat, geo_lon = geo_em.XLAT_M.values[0], geo_em.XLONG_M.values[0]
    geo_lat_flat, geo_lon_flat = geo_lat.ravel(), geo_lon.ravel()

    iswater = int(geo_em.attrs['ISWATER'])
    islake = int(geo_em.attrs['ISLAKE'])
    issoilwater = int(geo_em.attrs['ISOILWATER'])
    water_mask = (geo_em.LU_INDEX.values[0] == iswater) | (geo_em.LU_INDEX.values[0] == islake)

    if pd.Timestamp(start_date).is_leap_year:
        LAI = xr.open_dataset(os.path.join(output_dir, 'LDASIN', start_date.replace("-", ""), 'LAI12M_leap.nc'))
    else:
        LAI = xr.open_dataset(os.path.join(output_dir, 'LDASIN', start_date.replace("-", ""), 'LAI12M.nc'))


    raw_data_path = os.path.join(raw_data_dir, f'gfs.t{cycle_hour}z.pgrb2.0p25.setup.grb2')
    ds_sfc  = xr.open_dataset(raw_data_path, engine='cfgrib',
                               backend_kwargs={'filter_by_keys': {'typeOfLevel': 'surface'}})
    ds_soil = xr.open_dataset(raw_data_path, engine='cfgrib',
                               backend_kwargs={'filter_by_keys': {'typeOfLevel': 'depthBelowLandLayer'}})

    # pad by more than one GFS grid spacing (0.25 deg) so the subset always
    # keeps enough surrounding points to interpolate, even for domains
    # smaller than the GFS grid spacing
    GFS_PAD = 0.5
    def subset(ds):
        return ds.sel(latitude=slice(geo_lat.min() - GFS_PAD, geo_lat.max() + GFS_PAD),
                      longitude=slice(geo_lon.min() - GFS_PAD, geo_lon.max() + GFS_PAD))

    ds_sfc_sub  = subset(ds_sfc)
    ds_soil_sub = subset(ds_soil)
    raw_lat, raw_lon = ds_sfc_sub.latitude.values, ds_sfc_sub.longitude.values

    # GFS cfgrib shortNames: t=TMP, sdwe=WEASD, st=TSOIL, soilw=SOILW
    gfs_vars = [
        (ds_sfc_sub,  't',   None),     # [0] skin temperature (TMP surface)
        (ds_soil_sub, 'soilw', 0),      # [1] soil moisture layer 1
        (ds_soil_sub, 'soilw', 1),      # [2] soil moisture layer 2
        (ds_soil_sub, 'soilw', 2),      # [3] soil moisture layer 3
        (ds_soil_sub, 'soilw', 3),      # [4] soil moisture layer 4
        (ds_soil_sub, 'st',  0),        # [5] soil temperature layer 1
        (ds_soil_sub, 'st',  1),        # [6] soil temperature layer 2
        (ds_soil_sub, 'st',  2),        # [7] soil temperature layer 3
        (ds_soil_sub, 'st',  3),        # [8] soil temperature layer 4
        (ds_sfc_sub,  'sdwe', None),    # [9] snow depth (WEASD)
    ]

    def var_interpolate(data_var):
        data_var = data_var.squeeze() \
                       .rio.set_spatial_dims(x_dim="longitude", y_dim="latitude") \
                       .rio.write_crs("epsg:4326") \
                       .rio.write_nodata(np.nan) \
                       .rio.interpolate_na().values
        interp_spline = RectBivariateSpline(raw_lat, raw_lon, data_var, kx=1, ky=1)
        data_var_interpolated = interp_spline.ev(geo_lat_flat, geo_lon_flat).reshape(geo_lat.shape)
        data_var_interpolated_masked = np.where(water_mask, np.nan, data_var_interpolated)
        return data_var_interpolated_masked
    
    soil_data = []
    for ds, varname, level_idx in gfs_vars:
        data_var = ds[varname].isel(depthBelowLandLayer=level_idx) if level_idx is not None else ds[varname]
        soil_data.append(var_interpolate(data_var)) 

    setup_file = xr.Dataset()
    
    for var in variables:
        
        dims = ('Time', 'south_north', 'west_east')
        dim4 = ('Time', 'soil_layers_stag', 'south_north', 'west_east')
        dim2 = ('Time', 'soil_layers_stag')
        
        if var == 'Times': 
            data_var, dims =  [pd.to_datetime(start_date).strftime('%Y-%m-%d_%H:%M:%S')], ( 'Time' )
            
        ##################
        # from geo_em file
        ##################
        elif var in ['XLAT', 'XLONG', 'HGT', "MAPFAC_MX", "MAPFAC_MY"]: 
            data_var = geo_em[variables[var]['geoname']].values
        
        elif var == 'URBLANDUSEF':
            if lcz==0:
                data_var = geo_em[variables[var]['geoname']].sel(land_cat=12).values       # urban
                # if unresonable values appear, set them to 0
                data_var[data_var < 0] = 0              
                data_var[data_var > 1] = 0
            else:
                data_var = np.ones_like(geo_em[variables[var]['geoname']].sel(land_cat=0).values)
        
        #######################
        # edit from geo_em file
        #######################
        # adjust to elevation
        elif var == 'TMN':
            data_var = geo_em[variables[var]['geoname']].values[0] - 0.0065 * geo_em['HGT_M'].values[0]
            # data_var = xr.where((geo_em.LU_INDEX==iswater)|(geo_em.LU_INDEX==islake), -1.e36, data_var).values
            data_var = [np.where(water_mask, -1.e36, data_var)]

        # gvfmax%field(:,:) = maxval(geo_em%veg,3)
        elif var == 'SHDMAX': 
            data_var = geo_em.GREENFRAC.max(axis=1).values*100
        
        # gvfmin%field(:,:) = minval(geo_em%veg,3)
        elif var == 'SHDMIN': 
            data_var = geo_em.GREENFRAC.min(axis=1).values*100
            
        elif var == 'LAI':
            if pd.Timestamp(start_date).is_leap_year:
                data_var = [LAI.sel(date='2020'+start_date[-6:])['LAI12M'].values]
            else:
                data_var = [LAI.sel(date='2021'+start_date[-6:])['LAI12M'].values]
        
        # if LU_INDEX==iswater or islake,2; else 1.  
        elif var == 'XLAND':
            LU_data = geo_em[variables[var]['geoname']]
            # data_var = xr.where((LU_data==iswater)|(LU_data==islake), 2, 1).values
            data_var = [np.where(water_mask, 2, 1)]
        
        elif var == 'ISLTYP':
            dominant_index = geo_em['SOILCTOP'].argmax(dim='soil_cat') + 1
            dominant_value = geo_em['SOILCTOP'].max(dim='soil_cat')
            dominant_index_corrected = xr.where(
                (dominant_value < 0.01) | (dominant_value > 1.0), 8, dominant_index)
            data_var = xr.where(setup_file['XLAND']==2, issoilwater, dominant_index_corrected)
            data_var = xr.where((setup_file['XLAND']!=2)&(data_var==14), 8, data_var).values

        # if urbanlandusef exist and resonable, set IVGTYP=13(urban)
        elif var == 'IVGTYP':
            LU = xr.where(((geo_em.LANDUSEF).sel(land_cat=12)<=1)&((geo_em.LANDUSEF).sel(land_cat=12)>0), 13, geo_em.LU_INDEX)  
            data_var = LU.values

        ####################
        # from raw data file
        ####################
        elif var == 'TSK':  
            data_var = [soil_data[0]]

        elif var == 'TSLB': 
            data_var, dims = [ np.array(soil_data[5:9]) ], dim4

        elif var == 'SMOIS': 
            data_var, dims = [ np.array(soil_data[1:5]) ], dim4

        elif var == 'ZS': 
            data_var, dims = [ [0.05, 0.25, 0.7, 1.5] ], dim2

        elif var == 'DZS': 
            data_var, dims = [ [0.1 , 0.3 , 0.6, 1 ] ], dim2

        elif var == 'SNOW': 
            data_var =  [ soil_data[-1] ]
        
        ########################
        # add SEAICE and CANWAT
        ########################
        elif var == 'SEAICE':
            data_var = np.zeros(geo_em.LU_INDEX.shape)

        elif var == 'CANWAT': 
            data_var = np.zeros(geo_em.LU_INDEX.shape)

        print(var)
        print(dims, np.array(data_var).shape)
        
        setup_file[var] = ( dims, data_var )

        setup_file[var].attrs['units'] = variables[var]['units']
    
    setup_file = setup_file.fillna({'SNOW': -999})

    setup_file.attrs = geo_em.attrs

    output_filename = f"HRLDAS_setup_{pd.to_datetime(start_date).strftime('%Y%m%d')}01_d{geo_em_file[-4]}"

    setup_file.to_netcdf(os.path.join(output_dir, 'LDASIN', start_date.replace("-", ""), output_filename))
    setup_file.close()
    LAI.close()
    ds_sfc.close()
    ds_soil.close()

def create_lai_vegfra(geo_em, output_dir, start_date):

    if not os.path.exists(output_dir+"/LDASIN/"+start_date.replace("-", "")):
        os.makedirs(output_dir+"/LDASIN/"+start_date.replace("-", ""))

    iswater = int(geo_em.attrs['ISWATER'])
    islake = int(geo_em.attrs['ISLAKE'])
    LU_geo = geo_em['LU_INDEX'].sel(Time=0)

    for var in ('LAI12M', 'GREENFRAC'):

        LAI_geo = geo_em[var].sel(Time=0)

        LAI_month = xr.concat([LAI_geo, LAI_geo, LAI_geo, LAI_geo], dim="month")
        month = pd.date_range('2019-01-01', periods=48, freq='MS') + pd.DateOffset(days=14)
        LAI_month["month"] = ("month", month)
        LAI_month = LAI_month.rename({'month': 'date'})

        # interpolate one target year at a time instead of a full 4-year daily
        # series (900x900x1461 days ~= 9.5GB per var was OOM-killing the box)
        for year, suffix in ((2020, '_leap'), (2021, '')):

            date = pd.date_range(f'{year}-01-01', f'{year}-12-31')
            LAI = LAI_month.interp(date=date).to_dataset()

            # vegfra calibration
            if var == 'GREENFRAC':
                LAI[var] = xr.where(LAI[var] <= 0, 0.01, LAI[var])
                LAI = LAI * 100

            # (iswater || islake) == 0
            mask = ((LU_geo == iswater) | (LU_geo == islake)).expand_dims(dim={"date": date}, axis=0)
            LAI[var] = xr.where(mask, 0, LAI[var])

            LAI.to_netcdf(os.path.join(output_dir, 'LDASIN', start_date.replace("-", ""), f'{var}{suffix}.nc'))
            LAI.close()


if __name__ == '__main__':

    start_date = '2026-07-20'
    n_days = 5
    cycle_hour    = '00'
    upper_level_m = 50

    raw_data_dir = f'../hands-on/GFS/Tokyo/raw/{start_date.replace("-","")}'
    output_dir = '../hands-on/GFS/Tokyo/'
    geo_em_file = '../hands-on/GFS/Tokyo/geo/geo_em.d01.nc'

    geo_em = xr.open_dataset(geo_em_file)

    create_lai_vegfra(geo_em, output_dir, start_date)
    create_setup_file(start_date, cycle_hour, raw_data_dir, output_dir, geo_em, geo_em_file, lcz=0)

    for fhour in range(1, n_days*24+1, 1):
        create_LDASIN_files(start_date, cycle_hour, fhour, raw_data_dir, output_dir, geo_em, upper_level_m, geo_em_file)

    geo_em.close()
        
        
