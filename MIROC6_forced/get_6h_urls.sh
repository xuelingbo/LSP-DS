#!/bin/bash

set -eou pipefail

# Sometimes some nodes are not working, so we can exclude them
exclude_nodes=()
# Example
# exclude_nodes+=(esgf-node.llnl.gov)
# exclude_nodes+=(esgf.ceda.ac.uk)
# exclude_nodes+=(esgf-data02.diasjp.net)

options=()

if [ ${#exclude_nodes[@]} -gt 0 ]; then
	options+=(--exclude_nodes "${exclude_nodes[@]}")
fi

data_dir=./6hr_data
mkdir -p "$data_dir"

source_id=MIROC6
member_id=r1i1p1f1

awk -F, '(NR > 1) && $2' model_conf/"$source_id".csv |
	parallel -j 4 --delay 3 --lb --colsep=, python get_6h_url.py \
		"${options[@]+"${options[@]}"}" --variable_id '{1}' --table_id '{2}' --frequency '{3}' \
		--source_id "$source_id" --member_id "$member_id" --experiment_id historical \
		--start_date "2010-01-02" --end_date "2010-01-30" |
	tee "$data_dir/urls.txt"

awk -F, '(NR > 1) && $2' model_conf/"$source_id".csv |
	parallel -j 4 --delay 3 --lb --colsep=, python get_6h_url.py \
		"${options[@]+"${options[@]}"}" --variable_id '{1}' --table_id '{2}' --frequency '{3}' \
		--source_id "$source_id" --member_id "$member_id" --experiment_id ssp370 \
		--start_date "2050-01-02" --end_date "2050-01-30" |
	tee -a "$data_dir/urls.txt"
