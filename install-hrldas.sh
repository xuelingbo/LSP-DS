#!/bin/bash

wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh

bash Miniconda3-latest-Linux-x86_64.sh

source ~/.bashrc

conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

conda create -n hrldas python=3.12 -y

conda activate hrldas

conda install -c conda-forge cmake make -y 

conda install -c conda-forge git -y

conda install -c conda-forge numpy scipy matplotlib pandas xarray rioxarray -y

conda install -c conda-forge netcdf4 h5py -y

conda install -c conda-forge netcdf-fortran -y

conda install -c conda-forge fortran-compiler -y

conda install -c conda-forge gfortran openmpi -y

conda install -c conda-forge cfgrib eccodes

conda install -c conda-forge cdsapi

git clone --recurse-submodules https://github.com/xuelingbo/LSP-DS