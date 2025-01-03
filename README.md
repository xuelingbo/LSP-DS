[![DOI](https://zenodo.org/badge/806566110.svg)](https://zenodo.org/doi/10.5281/zenodo.13291568)
# Land-Surface-Physics-Based Downscaling Approach (LSP-DS)

This is the offical LSP-DS Github repository for code downloading and contribution.

**LSP-DS description paper**: 

Xue, L., Doan, Q.‐V., Kusaka, H., He, C., & Chen, F. (2024). Insights into urban heat island and heat waves synergies revealed by a Land‐Surface‐Physics‐Based Downscaling method. Journal of Geophysical Research: Atmospheres, 129, e2023JD040531. https://doi.org/10.1029/2023JD040531

Xue, L., Doan, Q. V., Kusaka, H., He, C., & Chen, F. (2025). Land-surface-physics-based downscaling versus conventional dynamical downscaling for high-resolution urban climate change information: The case study of two cities. Urban Climate, 59, 102228. https://doi.org/10.1016/j.uclim.2024.102228

## 1. Download the LSP-DS code

To download the LSP-DS code, use the following command:

git clone --recurse-submodules https://github.com/xuelingbo/LSP-DS

If the "--recurse-submodules" is not specified, the HRLDAS/Noah-MP source code will not be downloaded.

HRLDAS model website: https://ral.ucar.edu/solutions/products/high-resolution-land-data-assimilation-system-hrldas

Noah-MP model GitHub repository: https://github.com/NCAR/noahmp

## 2. Modify the Source Code

To modify the original HRLDAS/Noah-MP code, please use the following command:

[`./modify.sh`](https://github.com/xuelingbo/LSP-DS/blob/main/modify.sh)

This command will copy the modified files and cover the original one.

## 3. Compile HRLDAS

Please follow [`hrldas_manual.ipynb`](https://github.com/xuelingbo/LSP-DS/blob/main/hrldas_manual.ipynb) to install the necessary libraries and compile the HRLDAS.

## 4. Run HRLDAS

A script for using ERA5 data as forcing is provided here [`run_HRLDAS_era5.py`](https://github.com/xuelingbo/LSP-DS/blob/main/ERA5_forced/run_HRLDAS_era5.py). The necessary [`geo_em file`](https://github.com/xuelingbo/LSP-DS/blob/main/test/ERA5/geo/geo_em.d02.nc), [`namelist.hrldas`](https://github.com/xuelingbo/LSP-DS/blob/main/test/ERA5/namelists/namelist.hrldas), and [`URBPARM.TBL`](https://github.com/xuelingbo/LSP-DS/blob/main/test/ERA5/tables/URBPARM.TBL) are provided. After running the script, the output files will be generated in `/test/ERA5/LDASOUT`.

## 5. Postprocessing

A script for extracting data based on observational stations is provided in [`extract_data_based_on_stations.py`](https://github.com/xuelingbo/LSP-DS/blob/main/postprocessing_scripts/extract_data_based_on_stations.py). An example of the necessary staions information file is provided here [Amedas_list.csv](https://github.com/xuelingbo/LSP-DS/blob/main/test/ERA5/tables/Amedas_list.csv). After running the script, the output csv files will be generated in [`results/`](https://github.com/xuelingbo/LSP-DS/tree/main/test/ERA5/results).


# HRLDAS (High Resolution Land Data Assimilation System) 
The High-Resolution Land Data Assimilation System (HRLDAS) is a widely-used open-source offline community framework/driver of land surface models (LSMs). HRLDAS uses a combination of observed and analyzed meterological forcing (precipitation, shortwave and longwave radiation, surface wind, specific humidity, temperature, surface pressure) to drive a LSM to simulate the evolution of land surface states. The system has been developed to leverage the WRF pre-processed input data (e.g., WPS geo_em* file) and conduct computationally-efficient model run to generate more accurate initial land state conditions and/or produce the offline LSM simulations alone for scientific studies.

HRLDAS model website: [https://ral.ucar.edu/solutions/products/high-resolution-land-data-assimilation-system-hrldas](https://ral.ucar.edu/solutions/products/high-resolution-land-data-assimilation-system-hrldas)

HRLDAS Community Model Repository: [https://github.com/NCAR/hrldas](https://github.com/NCAR/hrldas)

**HRLDAS/Noah-MP technical documentation and model description papers:**

Technical documentation freely available at http://dx.doi.org/10.5065/ew8g-yr95

**To cite the technical documentation**:  He, C., P. Valayamkunnath, M. Barlage, F. Chen, D. Gochis, R. Cabell, T. Schneider, R. Rasmussen, G.-Y. Niu, Z.-L. Yang, D. Niyogi, and M. Ek (2023): The Community Noah-MP Land Surface Modeling System Technical Description Version 5.0, (No. NCAR/TN-575+STR). doi:10.5065/ew8g-yr95

**Original HRLDAS model description paper**: Fei Chen, Kevin W. Manning, Margaret A. LeMone, Stanley B. Trier, Joseph G. Alfieri, Rita Roberts, Mukul Tewari, Dev Niyogi, Thomas W. Horst, Steven P. Oncley, Jeffrey B. Basara, and Peter D. Blanken, 2007: Description and Evaluation of the Characteristics of the NCAR High-Resolution Land Data Assimilation System. J. Appl. Meteor. Climatol., 46, 694–713.
doi: http://dx.doi.org/10.1175/JAM2463.1

**HRLDAS/Noah-MP version 5.0 model description paper**:  He, C., Valayamkunnath, P., Barlage, M., Chen, F., Gochis, D., Cabell, R., Schneider, T., Rasmussen, R., Niu, G.-Y., Yang, Z.-L., Niyogi, D., and Ek, M.: Modernizing the open-source community Noah with multi-parameterization options (Noah-MP) land surface model (version 5.0) with enhanced modularity, interoperability, and applicability, Geosci. Model Dev., 16, 5131–5151, https://doi.org/10.5194/gmd-16-5131-2023, 2023.

# Noah-MP<sup>®</sup>

Noah-MP<sup>®</sup> is a widely-used state-of-the-art land surface model used in many research and operational weather/climate models (e.g., HRLDAS, WRF, MPAS, WRF-Hydro/NWM, NOAA/UFS, NASA/LIS, etc.). Noah-MP is a community open-source model developed with the contributions from the entire scientific community. 

Noah-MP model website: https://ral.ucar.edu/solutions/products/noah-multiparameterization-land-surface-model-noah-mp-lsm

Noah-MP Community Model Repository: https://github.com/NCAR/noahmp/blob/master/README.md

**Noah-MP technical documentation and model description papers:**

Technical documentation freely available at http://dx.doi.org/10.5065/ew8g-yr95

**To cite the technical documentation**:  He, C., P. Valayamkunnath, M. Barlage, F. Chen, D. Gochis, R. Cabell, T. Schneider, R. Rasmussen, G.-Y. Niu, Z.-L. Yang, D. Niyogi, and M. Ek (2023): The Community Noah-MP Land Surface Modeling System Technical Description Version 5.0, (No. NCAR/TN-575+STR). doi:10.5065/ew8g-yr95

**Original Noah-MP model description paper**:   Niu, G. Y., Yang, Z. L., Mitchell, K. E., Chen, F., Ek, M. B., Barlage, M., ... & Xia, Y. (2011). The community Noah land surface model with multiparameterization options (Noah‐MP): 1. Model description and evaluation with local‐scale measurements. Journal of Geophysical Research: Atmospheres, 116(D12).

**Noah-MP version 5.0 model description paper**:  He, C., Valayamkunnath, P., Barlage, M., Chen, F., Gochis, D., Cabell, R., Schneider, T., Rasmussen, R., Niu, G.-Y., Yang, Z.-L., Niyogi, D., and Ek, M.: Modernizing the open-source community Noah with multi-parameterization options (Noah-MP) land surface model (version 5.0) with enhanced modularity, interoperability, and applicability, Geosci. Model Dev., 16, 5131–5151, https://doi.org/10.5194/gmd-16-5131-2023, 2023.

**Noah-MP development future priority paper**: He, C., Chen, F., Barlage, M., Yang, Z.-L., Wegiel, J. W., Niu, G.-Y., Gochis, D., Mocko, D. M., Abolafia-Rosenzweig, R., Zhang, Z., Lin, T.-S., Valayamkunnath, P., Ek, M., and Niyogi, D. (2023): Enhancing the community Noah-MP land model capabilities for Earth sciences and applications, Bull. Amer. Meteor. Soc., E2023–E2029, https://doi.org/10.1175/BAMS-D-23-0249.1
