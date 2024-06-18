#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##############################################################################
# History:
#   2022.12.05  Created by XUE Lingbo (CCS, Tsukuba, Japan) 
##############################################################################

import os
import cdsapi
from collections import namedtuple

def download_era5_land_SW_LW_PREP_SP(start_year, end_year, dir):

    c = cdsapi.Client()

    pair = namedtuple("pair", ["long", "short"])
    variables = [pair("surface_solar_radiation_downwards", "ssrd"), pair("surface_thermal_radiation_downwards", "strd"),\
         pair("surface_pressure", "sp"), pair("total_precipitation", "tp")]

    for year in range(start_year, end_year+1):
        for month in ['10', '11']:
            for var in variables:
                print(dir+str(year)+month+'_'+var.short+'_era5_land.nc')
                if not os.path.exists(dir+str(year)+month+'_'+var.short+'_era5_land.nc'):
                    c.retrieve(
                        'reanalysis-era5-land',
                        {
                            'variable': var.long,
                            'year': str(year),
                            'month': month,
                            'day': [
                                '01', '02', '03',
                                '04', '05', '06',
                                '07', '08', '09',
                                '10', '11', '12',
                                '13', '14', '15',
                                '16', '17', '18',
                                '19', '20', '21',
                                '22', '23', '24',
                                '25', '26', '27',
                                '28', '29', '30',
                                '31',
                            ],
                            'time': [
                                '00:00', '01:00', '02:00',
                                '03:00', '04:00', '05:00',
                                '06:00', '07:00', '08:00',
                                '09:00', '10:00', '11:00',
                                '12:00', '13:00', '14:00',
                                '15:00', '16:00', '17:00',
                                '18:00', '19:00', '20:00',
                                '21:00', '22:00', '23:00',
                            ],
                            'format': 'netcdf',
                        },
                        dir+str(year)+month+'_'+var.short+'_era5_land.nc')

def download_era5_model_levels_t_u_v_q(start_year, end_year, dir, levelists):

    c = cdsapi.Client()

    pair = namedtuple("pair", ["long", "short", "id"])
    variables = [pair("Temperature", "t","130"), pair("U component of wind", "u","131"),\
         pair("V component of wind", "v","132"), pair("Specific humidity", "q","133")]

    for year in range(start_year, end_year+1):
        for month in ['10', '11']:
            for var in variables:
                for levelist in levelists:
                # for levelist in ['136']:
                    print(dir+str(year)+month+'_'+var.short+'_'+levelist+'_era5.nc')
                    # print(str(year)+'-'+month+'-01'+'/to/'+str(year)+'-0'+str(int(month)+1)+'-01')
                    if not os.path.exists(dir+str(year)+month+'_'+var.short+'_'+levelist+'_era5.nc'):
                        c.retrieve('reanalysis-era5-complete', { # Requests follow MARS syntax
                                                                # Keywords 'expver' and 'class' can be dropped. They are obsolete
                                                                # since their values are imposed by 'reanalysis-era5-complete'
                            
                            'date'    : str(year)+'-'+month+'-01'+'/to/'+str(year)+'-'+str(int(month)+1)+'-01',
                            'levelist': levelist,               # 1 is top level, 137 the lowest model level in ERA5. Use '/' to separate values.
                            'levtype' : 'ml',
                            'param'   : var.id,                 # Full information at https://apps.ecmwf.int/codes/grib/param-db/
                                                                # The native representation for temperature is spherical harmonics
                            'stream'  : 'oper',                  # Denotes ERA5. Ensemble members are selected by 'enda'
                            'time'    : '00/to/23/by/1',         # You can drop :00:00 and use MARS short-hand notation, instead of '00/06/12/18'
                            'type'    : 'an',
                            'grid'    : '0.1/0.1',               # Latitude/longitude. Default: spherical harmonics or reduced Gaussian grid
                            'format'  : 'netcdf',                # Output needs to be regular lat-lon, so only works in combination with 'grid'!
                        }, 
                        dir+str(year)+month+'_'+var.short+'_'+levelist+'_era5.nc')            # Output file. Adapt as you wish.



if __name__ == '__main__':

    start_year = 2005
    end_year = 2014
    levelists = ['136']
    dir = '/share/ERA5/'

    download_era5_land_SW_LW_PREP_SP(start_year, end_year, dir)
    download_era5_model_levels_t_u_v_q(start_year, end_year, dir, levelists)
