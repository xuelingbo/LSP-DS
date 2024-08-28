#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#######################################################################
# History:
#   2023.04.04  Created by XUE Lingbo (CCS, Tsukuba, Japan)
#   2024.08.08  Modified by XUE Lingbo (CCS, Tsukuba, Japan) for CDS-Beta
#######################################################################

#######################################################################
# 1. How to use the CDS API:
#    https://cds-beta.climate.copernicus.eu/how-to-api
#
# 2. Reference for ERA5 model levels data:
#    https://confluence.ecmwf.int/display/udoc/L137+model+level+definitions
#    https://confluence.ecmwf.int/display/CKB/ERA5%3A+compute+pressure+and+geopotential+on+model+levels%2C+geopotential+height+and+geometric+height 
#    https://rda.ucar.edu/datasets/ds633-6/
#######################################################################

import os
import cdsapi
from collections import namedtuple

# Prerequisites to calculating Geopotential on model levels
# Download ERA5 model level data for t, q and z, lnsp
# Dataset: Complete ERA5 global atmospheric reanalysis (reanalysis-era5-complete)
# Variables: Temperature (t), Specific humidity (q), Geopotential (z), Logarithm of surface pressure (lnsp)
def download_files_for_compute_geopotential(dir, area):

    c = cdsapi.Client()

    # data download specifications:
    cls     = "ea"         # do not change
    expver  = "1"          # do not change
    levtype = "ml"         # do not change
    stream  = "oper"       # do not change
    date    = "2020-08-01" # date: Specify a single date as "2018-01-01" or a period as "2018-08-01/to/2018-01-31". For periods > 1 month see https://confluence.ecmwf.int/x/l7GqB
    tp      = "an"         # type: Use "an" (analysis) unless you have a particular reason to use "fc" (forecast).
    time    = "00:00:00"   # time: ERA5 data is hourly. Specify a single time as "00:00:00", or a range as "00:00:00/01:00:00/02:00:00" or "00:00:00/to/23:00:00/by/1".
    
    c.retrieve('reanalysis-era5-complete', {
        'class'   : cls,
        'date'    : date,
        'expver'  : expver,
        'levelist': '130/131/132/133/134/135/136/137',         # For each of the 137 model levels
        'levtype' : 'ml',
        'param'   : '130/133', # Temperature (t) and specific humidity (q)
        'stream'  : stream,
        'time'    : time,
        'type'    : tp,
        'grid'    : [0.25, 0.25], # Latitude/longitude grid: east-west (longitude) and north-south resolution (latitude). Default: 0.25 x 0.25
        'area'    : area, #example: [60, -10, 50, 2], # North, West, South, East. Default: global
    }, dir+'tq_ml.grib')
    
    
    c.retrieve('reanalysis-era5-complete', {
        'class'   : cls,
        'date'    : date,
        'expver'  : expver,
        'levelist': '1',       # Geopotential (z) and Logarithm of surface pressure (lnsp) are 2D fields, archived as model level 1
        'levtype' : levtype,
        'param'   : '129/152', # Geopotential (z) and Logarithm of surface pressure (lnsp)
        'stream'  : stream,
        'time'    : time,
        'type'    : tp,
        'grid'    : [0.25, 0.25], # Latitude/longitude grid: east-west (longitude) and north-south resolution (latitude). Default: 0.25 x 0.25
        'area'    : area, #example: [60, -10, 50, 2], # North, West, South, East. Default: global
    }, dir+'zlnsp_ml.grib')

# Download ERA5 single layer data for setup
# Dataset: ERA5 hourly data on single levels from 1979 to present (reanalysis-era5-single-levels)
# Variables: Skin temperature, Snow depth, Soil temperature level 1-4, Volumetric soil water layer 1-4
def download_era5_single_layer_for_setup(year, month, day, area, dir):

    output_filename = f'{str(year)}{month}{day}00_setup.nc'
    print(os.path.join(dir, output_filename))

    if not os.path.exists(os.path.join(dir, output_filename)):
        dataset = "reanalysis-era5-single-levels"
        request = {
            'product_type': ['reanalysis'],
            'variable': ['skin_temperature', 'snow_depth', 
                         'soil_temperature_level_1', 'soil_temperature_level_2', 
                         'soil_temperature_level_3', 'soil_temperature_level_4', 
                         'volumetric_soil_water_layer_1', 'volumetric_soil_water_layer_2', 
                         'volumetric_soil_water_layer_3', 'volumetric_soil_water_layer_4'],
            'year': str(year),
            'month': month,
            'day': day,
            'time': ['00:00'],
            'data_format': 'netcdf',
            'download_format': 'unarchived',
            'area': area
        }

        client = cdsapi.Client()
        client.retrieve(dataset, request).download(os.path.join(dir, output_filename))

# Download ERA5 single layer data for ssrd, strd, sp, tp
# Dataset: ERA5 hourly data on single levels from 1979 to present (reanalysis-era5-single-levels)
# Variables: Surface solar radiation downwards (ssrd), Surface thermal radiation downwards (strd), 
#            Surface pressure (sp), Total precipitation (tp)
def download_era5_single_layer_ssrd_strd_sp_tp(start_year, end_year, months, area, dir):

    # pair = namedtuple("pair", ["long", "short"])
    # variables = [pair("surface_solar_radiation_downwards", "ssrd"), pair("surface_thermal_radiation_downwards", "strd"),\
    #      pair("surface_pressure", "sp"), pair("total_precipitation", "tp")]

    for year in range(start_year, end_year+1):
        for month in months:

            output_filename = f'{str(year)}{month}_ssrd_strd_sp_tp_era5_single_layer.nc'
            # output_filename = f'{str(year)}{month}_{var.short}_era5_single_layer.nc'
            print(os.path.join(dir, output_filename))

            if not os.path.exists(os.path.join(dir, output_filename)):

                dataset = "reanalysis-era5-single-levels"
                request = {
                    'product_type': ['reanalysis'],
                    'variable': ['surface_solar_radiation_downwards', 'surface_thermal_radiation_downwards',
                                 'surface_pressure', 'total_precipitation'],
                    'year': str(year),
                    'month': month,
                    'day': ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', 
                            '11', '12', '13', '14', '15', '16', '17', '18', '19', '20', 
                            '21', '22', '23', '24', '25', '26', '27', '28', '29', '30', 
                            '31'],
                    'time': ['00:00', '01:00', '02:00', '03:00', '04:00', '05:00', 
                                '06:00', '07:00', '08:00', '09:00', '10:00', '11:00', 
                                '12:00', '13:00', '14:00', '15:00', '16:00', '17:00', 
                                '18:00', '19:00', '20:00', '21:00', '22:00', '23:00'],
                    'data_format': 'netcdf',
                    'download_format': 'unarchived',
                    'area': area
                }

                client = cdsapi.Client()
                client.retrieve(dataset, request).download(os.path.join(dir, output_filename))

# Download ERA5 model level data for t, u, v, q
# Dataset: Complete ERA5 global atmospheric reanalysis (reanalysis-era5-complete)
# Variables: Temperature (t), U component of wind (u), V component of wind (v), Specific humidity (q)
def download_era5_model_levels_t_u_v_q(start_year, end_year, months, area, levelists, dir):

    c = cdsapi.Client()

    pair = namedtuple("pair", ["long", "short", "id"])
    variables = [
                    pair("Temperature", "t","130"), 
                    pair("U component of wind", "u","131"),
                    pair("V component of wind", "v","132"), 
                    pair("Specific humidity", "q","133")
                ]

    for year in range(start_year, end_year+1):
        for month in months:
            for levelist in levelists:

                output_filename = f'{str(year)}{month}_t_u_v_q_{levelist}_era5_model_level.nc'
                # output_filename = f'{str(year)}{month}_{var.short}_{levelist}_era5_model_level.nc'
                print(os.path.join(dir, output_filename))
                if not os.path.exists(os.path.join(dir, output_filename)):
                    c.retrieve('reanalysis-era5-complete', { # Requests follow MARS syntax
                                                            # Keywords 'expver' and 'class' can be dropped. They are obsolete
                                                            # since their values are imposed by 'reanalysis-era5-complete'
                        
                        'date'    : f'{str(year)}-{month}-01/to/{str(year)}-{int(month)+1:02}-01',
                        'levelist': levelist,               # 1 is top level, 137 the lowest model level in ERA5. Use '/' to separate values.
                        'levtype' : 'ml',
                        'param'   : '130/131/132/133',      # Full information at https://apps.ecmwf.int/codes/grib/param-db/
                                                            # The native representation for temperature is spherical harmonics
                        'stream'  : 'oper',                 # Denotes ERA5. Ensemble members are selected by 'enda'
                        'time'    : '00/to/23/by/1',        # You can drop :00:00 and use MARS short-hand notation, instead of '00/06/12/18'
                        'type'    : 'an',
                        'grid'    : '0.25/0.25',            # Latitude/longitude. Default: spherical harmonics or reduced Gaussian grid
                        'format'  : 'netcdf',               # Output needs to be regular lat-lon, so only works in combination with 'grid'!
                        'area'    : area,                   # North, West, South, East. Default: global
                    }, 
                    os.path.join(dir, output_filename))     # Output file. Adapt as you wish.



if __name__ == '__main__':

    start_year = 2020
    end_year = 2020
    months = ['08']                          # For example, ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']
    area = [55, 30, -50, 155]
    levelists = ['136']
    dir = '../test/ERA5/raw/'

    # Prerequisites to calculating Geopotential on model levels
    download_files_for_compute_geopotential(dir, area)

    # Download ERA5 single layer data for setup file
    for year in range(start_year, end_year+1):
        download_era5_single_layer_for_setup(start_year, months[0], '01', area, dir)

    # Download ERA5 single layer data for forcing
    download_era5_single_layer_ssrd_strd_sp_tp(start_year, end_year, months, area, dir)
    # Download ERA5 model level data for forcing
    download_era5_model_levels_t_u_v_q(start_year, end_year, months, area, levelists, dir)
