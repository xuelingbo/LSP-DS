# HRLDAS (High Resolution Land Data Assimilation System) 
The High-Resolution Land Data Assimilation System (HRLDAS) is a widely-used open-source offline community framework/driver of land surface models (LSMs). HRLDAS uses a combination of observed and analyzed meterological forcing (precipitation, shortwave and longwave radiation, surface wind, specific humidity, temperature, surface pressure) to drive a LSM to simulate the evolution of land surface states. The system has been developed to leverage the WRF pre-processed input data (e.g., WPS geo_em* file) and conduct computationally-efficient model run to generate more accurate initial land state conditions and/or produce the offline LSM simulations alone for scientific studies.
HRLDAS model website: [https://ral.ucar.edu/solutions/products/high-resolution-land-data-assimilation-system-hrldas](https://ral.ucar.edu/solutions/products/high-resolution-land-data-assimilation-system-hrldas)
HRLDAS Community Model Repository: [https://github.com/NCAR/hrldas](https://github.com/NCAR/hrldas)

# Noah-MP<sup>®</sup>

Noah-MP<sup>®</sup> is a widely-used state-of-the-art land surface model used in many research and operational weather/climate models (e.g., HRLDAS, WRF, MPAS, WRF-Hydro/NWM, NOAA/UFS, NASA/LIS, etc.). Noah-MP is a community open-source model developed with the contributions from the entire scientific community. 
Noah-MP model website: https://ral.ucar.edu/solutions/products/noah-multiparameterization-land-surface-model-noah-mp-lsm
Noah-MP Community Model Repository: https://github.com/NCAR/noahmp/blob/master/README.md

# Download the LSP-DS code

To download the LSP-DS code, use the following command:

git clone --recurse-submodules https://github.com/xuelingbo/LSP-DS

If the "--recurse-submodules" is not specified, the HRLDAS/Noah-MP source code will not be downloaded.

HRLDAS model website: https://ral.ucar.edu/solutions/products/high-resolution-land-data-assimilation-system-hrldas

Noah-MP model GitHub repository: https://github.com/NCAR/noahmp

# Modify the Source Code

To modify the original HRLDAS/Noah-MP code, please use the following command:

`./modify.sh`

This command will copy the modified files and cover the original one.

# Compile HRLDAS

Please follow `hrldas_manual.ipynb` to install the necessary libraries and compile the HRLDAS.

# Download ERA5 Data

To download the ERA5 data, please modify as your need and run the script:

 `python download_era5_hrldas.py`

 # Create Forcing

 To create forcing from ERA5 data, please modify as your need and run the script:

 `python create_forcing.py`

 # Run HRLDAS

To run hrldas, please use the following command:

`cd hrldas/hrldas/run/`

`./hrldas.exe`



