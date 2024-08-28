import pandas as pd
import os
import xarray as xr
import numpy as np
import sys
import concurrent.futures
from wrf import ll_to_xy, xy_to_ll
from netCDF4 import Dataset

def find_valid_obs_stations(geo_em_path, obs_ls_path, output_dir):

    geo = Dataset(geo_em_path)

    ls = pd.read_csv(obs_ls_path, index_col=0)
    ls_valid = ls[ls['End_year']==9999]

    [ls_valid['i'], ls_valid['j']] = ll_to_xy(geo, ls_valid['latitude'], ls_valid['longitude'])
    [ls_valid['geo_lat'], ls_valid['geo_lon']] = xy_to_ll(geo, ls_valid['i'], ls_valid['j'])

    # print(geo.dimensions['west_east'], geo.dimensions['south_north'])
    
    ls_valid = ls_valid.where((ls_valid['i']<geo.dimensions['west_east'].size)&
                              (ls_valid['i']>0)&
                              (ls_valid['j']<geo.dimensions['south_north'].size)&
                              (ls_valid['j']>0)).dropna(how="all")
    
    # ls_valid = ls_valid.where(ls_valid['f_tem']=='Y').dropna(how="all")

    ls_valid['i'] = ls_valid['i'].astype('int')
    ls_valid['j'] = ls_valid['j'].astype('int')
    ls_valid['station_id'] = ls_valid['station_id'].astype('int')

    ls_valid['LU_INDEX'] = ls_valid.apply(lambda x: geo.variables['LU_INDEX'][0, x['j'], x['i']], axis=1, result_type='expand').astype('int')

    ls_valid.to_csv(os.path.join(output_dir, 'valid_stations.csv'))

    return ls_valid

def extract_hrldas(hrldas_dir, output_dir, start_date, end_date, station, i, j, utc=0, vars=None):

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    ofile = f'{station:04d}.csv'

    if not os.path.exists(os.path.join(output_dir, ofile)):

        time_period = pd.date_range(start=start_date, end=end_date, freq="1H")

        extracted_data = []

        for time in time_period:

            ifile = time.strftime("%Y%m%d%H.LDASOUT_DOMAIN2")

            try:
                ds = xr.open_dataset(os.path.join(hrldas_dir, 'LDASOUT', ifile))
                data_dict = {'time': time}

                for var_name, var_data in ds.variables.items():
                    if vars is not None and var_name not in vars:
                        continue
                    if var_name not in ['south_north', 'west_east', 'Times']:
                        if 'soil_layers_stag' in var_data.dims:
                            for layer in range(ds.dims['soil_layers_stag']):
                                new_var_name = f"{var_name}_{layer}"
                                data_dict[new_var_name] = var_data.isel(
                                    south_north=j, west_east=i, soil_layers_stag=layer).item()
                        elif 'snow_layers' in var_data.dims:
                            for layer in range(ds.dims['snow_layers']):
                                new_var_name = f"{var_name}_{layer}"
                                data_dict[new_var_name] = var_data.isel(
                                    south_north=j, west_east=i, snow_layers=layer).item()
                        elif any(dim not in ['Time', 'south_north', 'west_east', 'soil_layers_stag', 'snow_layers'] for dim in var_data.dims):
                            # Skip processing for variables with other dimensions
                            continue
                        else:
                            data_dict[var_name] = var_data.isel(
                                south_north=j, west_east=i).item()

                extracted_data.append(data_dict)

                ds.close()

                print(f'{station:04d} {ifile}')
            
            except Exception as e:
                print(f"Error processing {ifile}: {e}")
        
        df = pd.DataFrame(extracted_data)

        df = df.set_index('time')
        df.index = df.index + pd.DateOffset(hours=utc)

        # df.columns = [col + '_hrldas' for col in df.columns]

        print(ofile)

        df.to_csv(os.path.join(output_dir, ofile))
    
    else:

        print(f"{ofile} exists!")

def process_station(station_info):

    station, i, j, kwargs = station_info

    extract_hrldas(hrldas_dir, output_dir, start_date, end_date, station, i, j, **kwargs)



if __name__ == '__main__':

    geo_em = '../test/ERA5/geo/geo_em.d02.nc'

    hrldas_dir = '../test/ERA5/'

    output_dir = '../test/ERA5/results/'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    start_date = '2020-08-01'
    end_date = '2020-08-31'

    # option 1: read stations information from a csv file
    obs_ls_path = '../test/ERA5/tables/Amedas_list.csv'
    ls = find_valid_obs_stations(geo_em, obs_ls_path, output_dir)

    # 'utc':0, -> UTC time
    # 'vars': None -> extract all variables
    # 'vars': ['T2', 'Q2'] -> extract only T2 and Q2
    station_info_list = [(station, i, j, {'utc':9, 'vars': ['T2', 'Q2', 'RH2']}) for station, i, j in zip(ls['station_id'], ls['i'], ls['j'])]

    # process stations in parallel
    max_workers = 4   # number of parallel processes
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        executor.map(process_station, station_info_list)


    # option 2: write stations information manually
    # ls = {
    # 'longitude': ['46.71667', '46.72517'],
    # 'latitude': ['24.93333', '24.70983'],
    # 'station_name': ['OERK', 'OERY']
    # }
    # ls = pd.DataFrame(ls)
    # geo = Dataset(geo_em)
    # ls['i'], ls['j'] = ll_to_xy(geo, ls['latitude'], ls['longitude']) 
    # ls['geo_lat'], ls['geo_lon'] = xy_to_ll(geo, ls['i'], ls['j'])
    # for station, i, j in zip(ls['station_name'], ls['i'], ls['j']):
    #     extract_hrldas(hrldas_dir, output_dir, start_date, end_date, station, i, j)
    