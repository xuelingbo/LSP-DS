# !/bin/bash
# 2024.06.18  Created by XUE Lingbo (CCS, Tsukuba, Japan) 

cp ./modified/NoahmpIOVarType.F90 ./hrldas/noahmp/drivers/hrldas/NoahmpIOVarType.F90
cp ./modified/NoahmpIOVarInitMod.F90 ./hrldas/noahmp/drivers/hrldas/NoahmpIOVarInitMod.F90
cp ./modified/module_NoahMP_hrldas_driver.F ./hrldas/hrldas/IO_code/module_NoahMP_hrldas_driver.F
cp ./modified/NoahmpUrbanDriverMainMod.F ./hrldas/urban/wrf/NoahmpUrbanDriverMainMod.F
cp ./modified/module_sf_urban.F ./hrldas/urban/wrf/module_sf_urban.F
cp ./modified/module_sf_bem.F ./hrldas/urban/wrf/module_sf_bem.F
