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



