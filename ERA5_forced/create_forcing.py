#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##############################################################################
# History:
#   2023.03.31  Created by DOAN Quang Van and XUE Lingbo (CCS, Tsukuba, Japan) 
##############################################################################

import numpy as np
import os
import pandas as pd
import xarray as xr
import rioxarray
import xesmf as xe
from scipy.interpolate import RectBivariateSpline
# import mpl_toolkits.basemap

def create_LDASIN_files(start_date, end_date, raw_data_dir, output_dir, geo_em_file, levelist, ZLVL, 
                        ahe_file=None, ahe_profile=None, utc_offset=None, urbfrc_table=1):
    
    if not os.path.exists(output_dir+"/LDASIN"):
        os.makedirs(output_dir+"/LDASIN")
    
    variables ={'t': {'name':'T2D', 'attrs':{'units':'K'}}, 
                'q': {'name':'Q2D', 'attrs':{'units':'kg/kg'}},
                'u': {'name':'U2D', 'attrs':{'units':'m/s'}},
                'v': {'name':'V2D', 'attrs':{'units':'m/s'}},
                'sp': {'name':'PSFC', 'attrs':{'units':'Pa'}},
                'strd': {'name':'LWDOWN', 'attrs':{'units':'W/m^2'}},
                'ssrd': {'name':'SWDOWN', 'attrs':{'units':'W/m^2'}},
                'tp': {'name':'RAINRATE', 'attrs':{'units':'kg/m^2/s'}},
                'ahe': {'name':'AHE', 'attrs':{'units':'W/m^2'}},
                'LAI12M':{'name':'LAI', 'attrs':{'units':'m^2/m^2'}},
                'GREENFRAC':{'name':'VEGFRA', 'attrs':{'units':'%'}},
               }
    
    geo_em = xr.open_dataset(geo_em_file)
    geo_lat, geo_lon = geo_em.XLAT_M.values[0], geo_em.XLONG_M.values[0]
    geo_lat_flat, geo_lon_flat = geo_lat.ravel(), geo_lon.ravel()
    
    z_file = xr.open_dataset(os.path.join(raw_data_dir, 'z_out.grib'), engine='cfgrib')
    z_file_domain = z_file.sel(latitude=slice(geo_lat.max()+0.5, geo_lat.min()-0.5), 
                              longitude=slice(geo_lon.min()-0.5, geo_lon.max()+0.5))
    
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

    def ahe (ahe_file, ahe_profile, geo_em_file):

        buffer = 0.2  # degrees, to avoid edge truncation in conservative remapping
        geo_em  = xr.open_dataset(geo_em_file)
        geo_lat = geo_em.XLAT_M.values[0]
        geo_lon = geo_em.XLONG_M.values[0]

        ahe = rioxarray.open_rasterio(ahe_file).squeeze()
        ahe = ahe.rio.reproject("EPSG:4326")
        ahe = ahe.rio.clip_box(minx=geo_lon.min()-buffer, miny=geo_lat.min()-buffer,
                               maxx=geo_lon.max()+buffer, maxy=geo_lat.max()+buffer)
        ahe_lat = ahe.y.values
        ahe_lon = ahe.x.values

        if ahe_lat[0] > ahe_lat[-1]:
            ahe_lat = ahe_lat[::-1]
            ahe_raw = ahe.values[::-1, :]
        else:
            ahe_raw = ahe.values
        ahe_raw = np.where(ahe_raw < -1e30, 0.0, ahe_raw)  # replace fill value
        ahe_vals = np.nan_to_num(ahe_raw, nan=0.0)

        ds_in = xr.Dataset({
            'lat':   (['lat'],   ahe_lat, {'units': 'degrees_north'}),
            'lon':   (['lon'],   ahe_lon, {'units': 'degrees_east'}),
            'lat_b': (['lat_b'], bounds_1d(ahe_lat)),
            'lon_b': (['lon_b'], bounds_1d(ahe_lon)),
        })
        ds_out = xr.Dataset({
            'lat':   (['y', 'x'], geo_lat,           {'units': 'degrees_north'}),
            'lon':   (['y', 'x'], geo_lon,           {'units': 'degrees_east'}),
            'lat_b': (['y_b', 'x_b'], bounds_2d(geo_lat)),
            'lon_b': (['y_b', 'x_b'], bounds_2d(geo_lon)),
        })
        regridder = xe.Regridder(ds_in, ds_out, method='conservative',
                                 unmapped_to_nan=True, ignore_degenerate=True)
        ahe_interp = np.nan_to_num(
            regridder(xr.DataArray(ahe_vals, dims=['lat', 'lon'])).values, nan=0.0)

        # normalize profile so hourly values integrate to daily mean
        # profile is in local time , shift to UTC
        profile_arr = np.roll(np.array(ahe_profile), -utc_offset)
        profile_norm = profile_arr / profile_arr.sum() * 24
        ahe_hourly_raw = np.array([ahe_interp * w for w in profile_norm])  # shape: (24, south_north, west_east), UTC

        # AHE in the dataset is the mean value over the grid, what we need is the value of impermeable surface (urban, for SLUCM)
        urblandusef = geo_em.LANDUSEF.sel(land_cat=12).values.squeeze()
        ahe_hourly = np.zeros_like(ahe_hourly_raw)
        for h in range(24):
            ahe_h = ahe_hourly_raw[h]
            # mean ratio where both ahe and urblandusef > 0
            mask_both = (ahe_h > 0) & (urblandusef > 0)
            mean_ratio = np.mean(ahe_h[mask_both] / urblandusef[mask_both]) if mask_both.any() else 0.0
            # urblandusef>0 but ahe==0 → fill with mean_ratio * urblandusef
            ahe_corrected = np.where((urblandusef > 0) & (ahe_h <= 0), mean_ratio * urblandusef, ahe_h)
            # divide by urblandusef to get AHE per unit urban area
            ahe_hourly[h] = np.where(urblandusef > 0, ahe_corrected / (urblandusef*urbfrc_table), 0.0)

        return ahe_hourly
    
    if ahe_file is not None and ahe_profile is not None and utc_offset is not None:
        ahe_hourly = ahe(ahe_file, ahe_profile, geo_em_file)
        # print(ahe_hourly[5, :, :])  # print AHE for hour 5 as a check
    else:
        ahe_hourly = np.zeros((24, geo_lat.shape[0], geo_lat.shape[1]))
    
    for date in pd.date_range(start_date, end_date, freq= 'D'):
        
        for time in pd.date_range(date, periods=24, freq='h'):
        
            LDASIN_file = xr.Dataset()
            
            for var in variables:
                
                if variables[var]['name'] in ['LWDOWN', 'SWDOWN']: 
                    filename = os.path.join(raw_data_dir, f"{date.strftime('%Y%m')}_accum_ssrd_strd_tp_era5_single_layer.nc")
                    raw_data_file = xr.open_dataset(filename)
                    data_vars_raw = raw_data_file.sel(
                        latitude=slice(geo_lat.max()+0.5, geo_lat.min()-0.5), 
                        longitude=slice(geo_lon.min()-0.5, geo_lon.max()+0.5))
                    raw_lat, raw_lon = data_vars_raw.latitude.values[::-1], data_vars_raw.longitude.values
                    data_var = data_vars_raw[var].sel(valid_time=time, method='nearest')[::-1].values / 3600

                elif variables[var]['name'] in ['RAINRATE']: 
                    filename = os.path.join(raw_data_dir, f"{date.strftime('%Y%m')}_accum_ssrd_strd_tp_era5_single_layer.nc")
                    raw_data_file = xr.open_dataset(filename)
                    data_vars_raw = raw_data_file.sel(
                        latitude=slice(geo_lat.max()+0.5, geo_lat.min()-0.5), 
                        longitude=slice(geo_lon.min()-0.5, geo_lon.max()+0.5))
                    raw_lat, raw_lon = data_vars_raw.latitude.values[::-1], data_vars_raw.longitude.values
                    data_var = data_vars_raw[var].sel(valid_time=time, method='nearest')[::-1].values / 3600 * 1000

                elif variables[var]['name'] in ['PSFC']:
                    filename = os.path.join(raw_data_dir, f"{date.strftime('%Y%m')}_instant_sp_era5_single_layer.nc")
                    raw_data_file = xr.open_dataset(filename)
                    data_vars_raw = raw_data_file.sel(
                        latitude=slice(geo_lat.max()+0.5, geo_lat.min()-0.5), 
                        longitude=slice(geo_lon.min()-0.5, geo_lon.max()+0.5))
                    raw_lat, raw_lon = data_vars_raw.latitude.values[::-1], data_vars_raw.longitude.values
                    data_var = data_vars_raw[var].sel(valid_time=time, method='nearest')[::-1].values

                elif variables[var]['name'] in ['T2D']:
                    filename = os.path.join(raw_data_dir, f"{date.strftime('%Y%m')}_t_u_v_q_{levelist}_era5_model_level.nc")
                    raw_data_file = xr.open_dataset(filename)
                    data_vars_raw = raw_data_file.sel(
                        latitude=slice(geo_lat.max()+0.5, geo_lat.min()-0.5), 
                        longitude=slice(geo_lon.min()-0.5, geo_lon.max()+0.5))
                    raw_lat, raw_lon = data_vars_raw.latitude.values[::-1], data_vars_raw.longitude.values
                    # data_var = data_vars_raw[var].sel(valid_time=time, model_level=levelist, method='nearest')
                    # data_var_correct_to_msl = (data_var - ( -0.0065 * z_file_domain.sel(hybrid=levelist)['z'].values / 9.80665 ))[::-1].values
                    t_raw = data_vars_raw[var].sel(valid_time=time, model_level=levelist, method='nearest').values[::-1, :]
                    z_raw = z_file_domain.sel(hybrid=levelist)['z'].values.squeeze()[::-1, :]
                    data_var_correct_to_msl = t_raw - (-0.0065 * z_raw / 9.80665)                

                elif variables[var]['name'] in ['LAI', 'VEGFRA']:
                    if date.is_leap_year:
                        raw_data_file = xr.open_dataset(os.path.join(output_dir,'LDASIN', f'{var}_leap.nc'))
                        data_var = [raw_data_file[var].sel(date='2020'+str(date.date())[-6:]).values]
                    else:
                        raw_data_file = xr.open_dataset(os.path.join(output_dir,'LDASIN', f'{var}.nc'))
                        data_var = [raw_data_file[var].sel(date='2021'+str(date.date())[-6:]).values]

                elif variables[var]['name'] in ['AHE']:
                    pass  # ahe_hourly already computed, no file reading needed

                else:
                    filename = os.path.join(raw_data_dir, f"{date.strftime('%Y%m')}_t_u_v_q_{levelist}_era5_model_level.nc")
                    raw_data_file = xr.open_dataset(filename)
                    data_vars_raw = raw_data_file.sel(
                        latitude=slice(geo_lat.max()+0.5, geo_lat.min()-0.5), 
                        longitude=slice(geo_lon.min()-0.5, geo_lon.max()+0.5))
                    raw_lat, raw_lon = data_vars_raw.latitude.values[::-1], data_vars_raw.longitude.values
                    data_var = data_vars_raw[var].sel(valid_time=time, model_level=levelist, method='nearest')[::-1].values

                if variables[var]['name'] in ['T2D']:
                    # data_var_interpolated = mpl_toolkits.basemap.interp(data_var_correct_to_msl, 
                    #                                                 raw_lon, raw_lat, 
                    #                                                 geo_lon, geo_lat, 
                    #                                                 checkbounds=False, masked=False, order=1)
                    interp_spline = RectBivariateSpline(raw_lat, raw_lon, data_var_correct_to_msl, kx=1, ky=1)
                    data_var_interpolated = interp_spline.ev(geo_lat_flat, geo_lon_flat).reshape(geo_lat.shape)
                    data_var_correct_to_HGT_M = data_var_interpolated + ( -0.0065 * (geo_em['HGT_M'].values.squeeze()+ZLVL))
                    LDASIN_file[variables[var]['name']] = (('Time','south_north','west_east'), [data_var_correct_to_HGT_M])
                    LDASIN_file[variables[var]['name']].attrs['units'] = variables[var]['attrs']['units']
                elif variables[var]['name'] in ['LAI', 'VEGFRA']:
                    LDASIN_file[variables[var]['name']] = (('Time','south_north','west_east'), data_var)
                    LDASIN_file[variables[var]['name']].attrs['units'] = variables[var]['attrs']['units']
                elif variables[var]['name'] in ['AHE']:
                    LDASIN_file[variables[var]['name']] = (('Time','south_north','west_east'), [ahe_hourly[time.hour, :, :]])
                    LDASIN_file[variables[var]['name']].attrs['units'] = variables[var]['attrs']['units']
                else:
                    # data_var_interpolated = mpl_toolkits.basemap.interp(data_var, 
                    #                                                 raw_lon, raw_lat, 
                    #                                                 geo_lon, geo_lat, 
                    #                                                 checkbounds=False, masked=False, order=1)
                    interp_spline = RectBivariateSpline(raw_lat, raw_lon, data_var, kx=1, ky=1)
                    data_var_interpolated = interp_spline.ev(geo_lat_flat, geo_lon_flat).reshape(geo_lat.shape)
                    LDASIN_file[variables[var]['name']] = (('Time','south_north','west_east'), [data_var_interpolated])
                    LDASIN_file[variables[var]['name']].attrs['units'] = variables[var]['attrs']['units']

            encoding=[{var: {'_FillValue': None}} for var in LDASIN_file.variables]    
            output_filename = f"{time.strftime('%Y%m%d%H')}.LDASIN_DOMAIN{geo_em_file[-4]}"
            LDASIN_file.to_netcdf(os.path.join(output_dir, 'LDASIN', output_filename), encoding=encoding[0])
            print(output_filename)
                        
def create_setup_file(start_date, raw_data_dir, output_dir, geo_em_file, lcz=0):
    
    if not os.path.exists(output_dir+"/LDASIN"):
        os.makedirs(output_dir+"/LDASIN")

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
    
    geo_em = xr.open_dataset(geo_em_file)
    geo_lat, geo_lon = geo_em.XLAT_M.values[0], geo_em.XLONG_M.values[0]
    geo_lat_flat, geo_lon_flat = geo_lat.ravel(), geo_lon.ravel()

    iswater = int(geo_em.attrs['ISWATER'])
    islake = int(geo_em.attrs['ISLAKE'])
    issoilwater = int(geo_em.attrs['ISOILWATER'])
    water_mask = (geo_em.LU_INDEX.values[0] == iswater) | (geo_em.LU_INDEX.values[0] == islake)

    if pd.Timestamp(start_date).is_leap_year:
        LAI = xr.open_dataset(os.path.join(output_dir, 'LDASIN', 'LAI12M_leap.nc'))
    else:
        LAI = xr.open_dataset(os.path.join(output_dir, 'LDASIN', 'LAI12M.nc'))

    raw_data_file = xr.open_dataset(os.path.join(raw_data_dir, pd.to_datetime(start_date).strftime('%Y%m%d')+'00_setup.nc'))
    data_vars_raw = raw_data_file.sel(
        latitude=slice(geo_lat.max(), geo_lat.min()), 
        longitude=slice(geo_lon.min(), geo_lon.max()))
    raw_lat, raw_lon = data_vars_raw.latitude.values[::-1], data_vars_raw.longitude.values     # lat, lon ascending order
    
    soil_data = []
    for var in ['skt', 'swvl1', 'swvl2', 'swvl3', 'swvl4', 'stl1', 'stl2', 'stl3', 'stl4', 'sd']:
        # data_var = data_vars_raw[var].rio.write_crs("epsg:4326",inplace=True).rio.interpolate_na()[0][::-1].values
        data_var = data_vars_raw[var].rio.write_crs("epsg:4326").rio.interpolate_na().squeeze().values[::-1, :]
        interp_spline = RectBivariateSpline(raw_lat, raw_lon, data_var, kx=1, ky=1)
        data_var_interpolated = interp_spline.ev(geo_lat_flat, geo_lon_flat).reshape(geo_lat.shape)
        # data_var_interpolated = xr.where((geo_em.LU_INDEX==iswater)|(geo_em.LU_INDEX==islake), np.nan, data_var_interpolated)
        data_var_interpolated_masked = np.where(water_mask, np.nan, data_var_interpolated)
        soil_data.append(data_var_interpolated_masked) 

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
            data_var, dims = [ [0.035, 0.175, 0.64, 1.945] ], dim2

        elif var == 'DZS': 
            data_var, dims = [ [0.07 , 0.21 , 0.72, 1.89 ] ], dim2

        elif var == 'SNOW': 
            data_var =  [ soil_data[-1] * 1000]

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

    output_filename = f"HRLDAS_setup_{pd.to_datetime(start_date).strftime('%Y%m%d')}00_d{geo_em_file[-4]}"
    
    setup_file.to_netcdf(os.path.join(output_dir, 'LDASIN', output_filename))

def create_lai_vegfra(geo_em_file, output_dir):

    if not os.path.exists(output_dir+"/LDASIN"):
        os.makedirs(output_dir+"/LDASIN")

    for var in ('LAI12M', 'GREENFRAC'):

        geo = xr.open_dataset(geo_em_file)
        LAI_geo = geo[var].sel(Time=0)

        LAI = xr.concat([LAI_geo, LAI_geo, LAI_geo, LAI_geo], dim="month")
        month = pd.date_range('2019-01-01', periods=48, freq='MS') + pd.DateOffset(days=14)
        LAI["month"] = ("month", month)

        date = pd.date_range('2019-01-15', '2022-12-15')
        LAI=LAI.rename({'month': 'date'})
        LAI=LAI.interp(date=date).to_dataset()
        
        # vegfra calibration
        if var=='GREENFRAC':
            LAI[var] = xr.where(LAI[var]<=0 ,0.01, LAI[var])
            LAI = LAI * 100  
        
        # (iswater || islake ) == 0
        iswater = int(geo.attrs['ISWATER'])
        islake = int(geo.attrs['ISLAKE'])
        LU_geo = geo['LU_INDEX'].sel(Time=0)
        mask = ((LU_geo==iswater)|(LU_geo==islake)).expand_dims(dim={"date": date}, axis=0)
        LAI[var] = xr.where(mask, 0, LAI[var])

        if var=='LAI12M':
            LAI.sel(date=slice('2020-01-01','2020-12-31')).to_netcdf(os.path.join(output_dir, 'LDASIN', 'LAI12M_leap.nc'))
            LAI.sel(date=slice('2021-01-01','2021-12-31')).to_netcdf(os.path.join(output_dir, 'LDASIN', 'LAI12M.nc'))
        else:
            LAI.sel(date=slice('2020-01-01','2020-12-31')).to_netcdf(os.path.join(output_dir, 'LDASIN', 'GREENFRAC_leap.nc'))
            LAI.sel(date=slice('2021-01-01','2021-12-31')).to_netcdf(os.path.join(output_dir, 'LDASIN', 'GREENFRAC.nc'))


if __name__ == '__main__':

    start_year = 2018
    end_year = 2018
    loop_start_date = '08-01'
    loop_end_date = '08-07'
    # raw_data_dir = '../hands-on/ERA5/YangtzeDelta/raw/'
    raw_data_dir = '/home/xuelingbo/NAS_ERA5_HRLDAS/'
    output_dir = '../hands-on/ERA5/YangtzeDelta/'
    geo_em_file = '../hands-on/ERA5/YangtzeDelta/geo/geo_em.d01.nc'
    ahe_file = f'/home/xuelingbo/data/AHF/AHF{start_year}.tif'
    ahe_profile = [0.4178056766, 0.3657308632, 0.3217844562, 0.2938594942, 
                   0.2806290301, 0.2889400697, 0.3065774127, 0.3619608281, 
                   0.5388410089, 0.7649379382, 0.9467296349, 1, 
                   0.9378828369, 0.9546770639, 0.9624970061, 0.9509591352, 
                   0.9787157012, 0.9972752017, 0.9995627881, 0.9669973445,
                   0.8745974733, 0.7576414942, 0.6162263020, 0.5046295022]      # local time, Ao, 2019
    levelist = '136'
    ZLVL = 30
    utc_offset = 8
    urbfrc_table = 0.9

    create_lai_vegfra(geo_em_file, output_dir)

    for year in range(start_year, end_year+1):

        create_setup_file(f'{str(year)}-{loop_start_date}', \
                          raw_data_dir, output_dir, \
                          geo_em_file, lcz=0)

        create_LDASIN_files(f'{str(year)}-{loop_start_date}', f'{str(year)}-{loop_end_date}', \
                            raw_data_dir, output_dir, \
                            geo_em_file, levelist, ZLVL, \
                            ahe_file, ahe_profile, utc_offset, urbfrc_table)
        
        
