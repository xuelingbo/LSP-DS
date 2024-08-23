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
import mpl_toolkits.basemap

def create_LDASIN_files(start_date, end_date, raw_data_dir, output_dir, geo_em_file, levelist, ZLVL):
    
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
                'LAI12M':{'name':'LAI', 'attrs':{'units':'m^2/m^2'}},
                'GREENFRAC':{'name':'VEGFRA', 'attrs':{'units':'%'}},
               }
    
    geo_em = xr.open_dataset(geo_em_file)
    geo_lat, geo_lon = geo_em.XLAT_M.values[0], geo_em.XLONG_M.values[0]
    z_file = xr.open_dataset(os.path.join(raw_data_dir, 'z_out.grib'))
    
    for date in pd.date_range(start_date, end_date, freq= 'D'):
        
        for time in pd.date_range(date, periods=24, freq='H'):
        
            LDASIN_file = xr.Dataset()
            
            for var in variables:
                
                if variables[var]['name'] in ['LWDOWN', 'SWDOWN']: 
                    filename = os.path.join(raw_data_dir, f"{date.strftime('%Y%m')}_ssrd_strd_sp_tp_era5_single_layer.nc")
                    raw_data_file = xr.open_dataset(filename)
                    raw_lat, raw_lon = raw_data_file.latitude.values[::-1], raw_data_file.longitude.values
                    data_var = raw_data_file[var].sel(valid_time=time, method='nearest')[::-1].values / 3600

                elif variables[var]['name'] in ['RAINRATE']: 
                    filename = os.path.join(raw_data_dir, f"{date.strftime('%Y%m')}_ssrd_strd_sp_tp_era5_single_layer.nc")
                    raw_data_file = xr.open_dataset(filename)
                    raw_lat, raw_lon = raw_data_file.latitude.values[::-1], raw_data_file.longitude.values
                    data_var = raw_data_file[var].sel(valid_time=time, method='nearest')[::-1].values / 3600 * 1000

                elif variables[var]['name'] in ['PSFC']:
                    filename = os.path.join(raw_data_dir, f"{date.strftime('%Y%m')}_ssrd_strd_sp_tp_era5_single_layer.nc")
                    raw_data_file = xr.open_dataset(filename)
                    raw_lat, raw_lon = raw_data_file.latitude.values[::-1], raw_data_file.longitude.values
                    data_var = raw_data_file[var].sel(valid_time=time, method='nearest')[::-1].values

                elif variables[var]['name'] in ['T2D']:
                    filename = os.path.join(raw_data_dir, f"{date.strftime('%Y%m')}_t_u_v_q_{levelist}_era5_model_level.nc")
                    raw_data_file = xr.open_dataset(filename)
                    raw_lat, raw_lon = raw_data_file.latitude.values[::-1], raw_data_file.longitude.values
                    data_var = raw_data_file[var].sel(valid_time=time, model_level=levelist, method='nearest')
                    data_var_correct_to_msl = (data_var - ( -0.0065 * z_file.sel(hybrid=levelist)['z'].values / 9.80665 ))[::-1].values
                
                elif variables[var]['name'] in ['LAI', 'VEGFRA']:
                    if date.is_leap_year:
                        raw_data_file = xr.open_dataset(os.path.join(output_dir,'LDASIN', f'{var}_leap.nc'))
                        data_var = [raw_data_file[var].sel(date='2020'+str(date.date())[-6:]).values]
                    else:
                        raw_data_file = xr.open_dataset(os.path.join(output_dir,'LDASIN', f'{var}.nc'))
                        data_var = [raw_data_file[var].sel(date='2021'+str(date.date())[-6:]).values]

                else:
                    filename = os.path.join(raw_data_dir, f"{date.strftime('%Y%m')}_t_u_v_q_{levelist}_era5_model_level.nc")
                    raw_data_file = xr.open_dataset(filename)
                    raw_lat, raw_lon = raw_data_file.latitude.values[::-1], raw_data_file.longitude.values
                    data_var = raw_data_file[var].sel(valid_time=time, model_level=levelist, method='nearest')[::-1].values

                if variables[var]['name'] in ['T2D']:
                    data_var_interpolated = mpl_toolkits.basemap.interp(data_var_correct_to_msl, 
                                                                    raw_lon, raw_lat, 
                                                                    geo_lon, geo_lat, 
                                                                    checkbounds=False, masked=False, order=1)
                    data_var_correct_to_HGT_M = data_var_interpolated + ( -0.0065 * (geo_em['HGT_M'][::-1].values+ZLVL))
                    LDASIN_file[variables[var]['name']] = (('Time','south_north','west_east'), data_var_correct_to_HGT_M)
                    LDASIN_file[variables[var]['name']].attrs['units'] = variables[var]['attrs']['units']
                elif variables[var]['name'] in ['LAI', 'VEGFRA']:
                    LDASIN_file[variables[var]['name']] = (('Time','south_north','west_east'), data_var)
                    LDASIN_file[variables[var]['name']].attrs['units'] = variables[var]['attrs']['units']
                else:
                    data_var_interpolated = mpl_toolkits.basemap.interp(data_var, 
                                                                    raw_lon, raw_lat, 
                                                                    geo_lon, geo_lat, 
                                                                    checkbounds=False, masked=False, order=1)
                    LDASIN_file[variables[var]['name']] = (('Time','south_north','west_east'), [data_var_interpolated])
                    LDASIN_file[variables[var]['name']].attrs['units'] = variables[var]['attrs']['units']

            encoding=[{var: {'_FillValue': None}} for var in LDASIN_file.variables]    
            output_filename = f"{time.strftime('%Y%m%d%H')}.LDASIN_DOMAIN{geo_em_file[-4]}"
            LDASIN_file.to_netcdf(os.path.join(output_dir, 'LDASIN', output_filename), encoding=encoding[0])
            print(output_filename)
                        
def create_setup_file(start_date, raw_data_dir, output_dir, geo_em_file):
    
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
        "IVGTYP": {'units': '', 'geoname': 'LU_INDEX'} , 

        # edit from geo_em file
        "TMN": {'units': 'K', 'geoname': 'SOILTEMP'} ,  # adjust to elevation
        "SHDMAX": {'units': '%'} ,  # max(100*GREENFRAC) 
        "SHDMIN": {'units': '%'} ,  # min(100*GREENFRAC) 
        "LAI": {'units': 'm^2/m^2'} , # LAI12M after interpolated
        "XLAND": {'units': '', 'geoname': 'LU_INDEX'} ,  # if LU_INDEX==iswater or islake,2; else 1.  
        "ISLTYP": {'units': '', 'geoname': 'SOILCTOP'} ,

        # from raw data file
        "TSK": {'units': 'K'} ,  # skin temperature from ERA5 
        "TSLB": {'units': 'K'} ,  # soil layer temp 
        "SMOIS": {'units': 'm^3/m^3'},  # layer volumetric total water content [m3/m3] !!!
        "DZS": {'units': 'm'} ,  # each soil layer depth
        "ZS": {'units': 'm'} ,   # soil layer 
        "SNOW": {'units': 'kg/m^2'} , #snow depth
        # 'SNODEP':{'units': 'kg/m^2'} , #snow depth

        # add
        "SEAICE": {'units': ''} ,       # sea ice fraction (=0 for a land point)
        "CANWAT": {'units': 'kg/m^2'} , # set CANWAT = 0
    }
    
    geo_em = xr.open_dataset(geo_em_file)
    geo_lat, geo_lon = geo_em.XLAT_M.values[0], geo_em.XLONG_M.values[0]
    iswater = int(geo_em.attrs['ISWATER'])
    islake = int(geo_em.attrs['ISLAKE'])
    issoilwater = int(geo_em.attrs['ISOILWATER'])

    if pd.Timestamp(start_date).is_leap_year:
        LAI = xr.open_dataset(os.path.join(output_dir, 'LDASIN', 'LAI12M_leap.nc'))
    else:
        LAI = xr.open_dataset(os.path.join(output_dir, 'LDASIN', 'LAI12M.nc'))

    # get skin temperature, soil temperature, soil moisture and snow depth from raw data files
    # raw_data_file = xr.open_dataset(raw_data_dir+'/'+pd.to_datetime(start_date).strftime('%Y')
    #                                     +'/ERA5-'+pd.to_datetime(start_date).strftime('%Y%m%d')+'-sl.nc')

    raw_data_file = xr.open_dataset(os.path.join(raw_data_dir, pd.to_datetime(start_date).strftime('%Y%m%d')+'00_setup.nc'))
    data_var_raw = raw_data_file.sel(latitude=slice(geo_lat.max(), geo_lat.min()), \
                                          longitude=slice(geo_lon.min(), geo_lon.max()))
    raw_lat, raw_lon = data_var_raw.latitude.values[::-1], data_var_raw.longitude.values
    soil_data = []
    for var in ['skt', 'swvl1', 'swvl2', 'swvl3', 'swvl4', 'stl1', 'stl2', 'stl3', 'stl4', 'sd']:
        data_var = data_var_raw[var].rio.write_crs("epsg:4326",inplace=True).rio.interpolate_na()[0][::-1].values
        data_var_interpolated = mpl_toolkits.basemap.interp(data_var, 
                                                            raw_lon, raw_lat, 
                                                            geo_lon, geo_lat,  
                                                            checkbounds=False, masked=False, order=1)
        data_var_interpolated = xr.where((geo_em.LU_INDEX==iswater)|(geo_em.LU_INDEX==islake), np.NaN, data_var_interpolated)
        soil_data.append(data_var_interpolated[0].values) 


    # raw_data_file = xr.open_dataset(raw_data_dir+'/'+pd.to_datetime(start_date).strftime('%Y%m%d')+'00_setup.nc')
    # raw_lat, raw_lon = raw_data_file.latitude.values[::-1], raw_data_file.longitude.values
    # soil_data = []
    # for var in ['skt', 'swvl1', 'swvl2', 'swvl3', 'swvl4', 'stl1', 'stl2', 'stl3', 'stl4', 'sd']:
    #     data_var = raw_data_file[var][0][::-1].values
    #     data_var_interpolated = mpl_toolkits.basemap.interp(data_var, 
    #                                                         raw_lon, raw_lat, 
    #                                                         geo_lon, geo_lat,  
    #                                                         checkbounds=False, masked=False, order=1)
    #     data_var_interpolated = xr.where((geo_em.LU_INDEX==iswater)|(geo_em.LU_INDEX==islake), np.NaN, data_var_interpolated)
    #     soil_data.append(data_var_interpolated[0].values) 


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
        elif var in ['XLAT', 'XLONG', 'HGT', "MAPFAC_MX", "MAPFAC_MY", "IVGTYP"]: 
            data_var = geo_em[variables[var]['geoname']].values
        
        #######################
        # edit from geo_em file
        #######################
        # adjust to elevation
        elif var == 'TMN':
            data_var = geo_em[variables[var]['geoname']].values - 0.0065 * geo_em['HGT_M'].values
            data_var = xr.where((geo_em.LU_INDEX==iswater)|(geo_em.LU_INDEX==islake), -1.e36, data_var).values

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
            data_var = xr.where((LU_data==iswater)|(LU_data==islake), 2, 1).values
        
        elif var == 'ISLTYP':
            dominant_index = geo_em['SOILCTOP'].argmax(dim='soil_cat') + 1
            dominant_value = geo_em['SOILCTOP'].max(dim='soil_cat')
            dominant_index_corrected = xr.where(dominant_value<0.01, 8, dominant_index)
            data_var = xr.where(setup_file['XLAND']==2, issoilwater, dominant_index_corrected)
            data_var = xr.where((setup_file['XLAND']!=2)&(data_var==14), 8, data_var).values

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

    start_year = 2020
    end_year = 2020
    loop_start_date = '08-01'
    loop_end_date = '08-02'
    raw_data_dir = '../test/ERA5/raw/'
    output_dir = '../test/ERA5/'
    geo_em_file = '../test/ERA5/geo/geo_em.d02.nc'
    levelist = '136'
    ZLVL = 30

    create_lai_vegfra(geo_em_file, output_dir)

    for year in range(start_year, end_year+1):

        create_setup_file(f'{str(year)}-{loop_start_date}', \
                          raw_data_dir, output_dir, \
                          geo_em_file)

        create_LDASIN_files(f'{str(year)}-{loop_start_date}', f'{str(year)}-{loop_end_date}', \
                            raw_data_dir, output_dir, \
                            geo_em_file, levelist, ZLVL)
        
        
