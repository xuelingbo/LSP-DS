from download_era5_hrldas import *
from create_forcing import *

import os
import shutil
import subprocess

start_year = 2020
end_year = 2020
months = ['08']
loop_start_date = '08-01'
loop_end_date = '08-31'
area = [55, 30, -50, 155]
levelists = ['136']
dir_raw = '../test/ERA5/raw/'
dir_hrldas = '../test/ERA5/'
geo_em_file = '../test/ERA5/geo/geo_em.d02.nc'
urbanParamTable = '../test/ERA5/tables/URBPARM.TBL'
nameList = '../test/ERA5/namelists/namelist.hrldas'
exe_directory = '../hrldas/hrldas/run/'
levelist = '136'
ZLVL = 30




# Download Data for HRLDAS
# Prerequisites to calculating Geopotential on model levels
download_files_for_compute_geopotential(dir_raw, area)

# Download ERA5 single layer data for setup file
download_era5_single_layer_for_setup(start_year, months[0], '01', dir_raw)

# Download ERA5 single layer data for forcing
download_era5_single_layer_ssrd_strd_sp_tp(start_year, end_year, months, area, dir_raw)

# Download ERA5 model level data for forcing
download_era5_model_levels_t_u_v_q(start_year, end_year, months, area, levelists, dir_raw)

# Calculate Geopotential on model levels
os.system(f"python compute_geopotential_on_ml.py {os.path.join(dir_raw, 'tq_ml.grib')} {os.path.join(dir_raw, 'zlnsp_ml.grib')} -o {os.path.join(dir_raw, 'z_out.grib')}")





# Create forcing files
if not os.path.exists(os.path.join(dir_hrldas, 'LDASIN')):
    os.makedirs(os.path.join(dir_hrldas, 'LDASIN'))

create_lai_vegfra(geo_em_file, dir_hrldas)

for year in range(start_year, end_year+1):

    create_setup_file(f'{str(year)}-{loop_start_date}', \
                        dir_raw, dir_hrldas, \
                        geo_em_file)

    create_LDASIN_files(f'{str(year)}-{loop_start_date}', f'{str(year)}-{loop_end_date}', \
                        dir_raw, dir_hrldas, \
                        geo_em_file, levelist, ZLVL)





# Run HRLDAS
if not os.path.exists(os.path.join(dir_hrldas, 'LDASOUT')):
    os.makedirs(os.path.join(dir_hrldas, 'LDASOUT'))

shutil.copy(urbanParamTable, exe_directory)
shutil.copy(nameList, exe_directory)

os.chdir(exe_directory)
subprocess.run(["./hrldas.exe"])
