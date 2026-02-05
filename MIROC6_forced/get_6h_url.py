# %%
import logging
import re

import numpy as np
import pandas as pd
import pyesgf.search
from pyesgf.search import SearchConnection
from tap import tapify

import util

# %%
_logger = logging.getLogger(__name__)


# %%
def get_download_urls(
    variable_id: str,
    table_id: str,
    frequency: str,
    source_id: str,
    experiment_id: str,
    member_id: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    exclude_nodes: list[str] = [],
    esgf_url: str = "http://esgf-node.llnl.gov/esg-search",
) -> list[str]:
    """
    Reference: https://esgf.github.io/esg-search/ESGF_Search_RESTful_API.html
    """

    def filter_node(results):
        return [
            result
            for result in results
            if result.json["data_node"] not in exclude_nodes_set
        ]

    exclude_nodes_set = frozenset(exclude_nodes)
    conn = SearchConnection(esgf_url, distrib=True)
    facets = "project,experiment_id,variable_id,source_id,member_id,table_id,frequency,data_node"

    ctx = conn.new_context(
        project="CMIP6",
        experiment_id=experiment_id,
        variable=variable_id,
        table_id=table_id,
        frequency=frequency,
        facets=facets,
        latest=True,
        source_id=source_id,
        member_id=member_id,
    )
    search_results = filter_node(ctx.search())
    members = util.natural_sort(
        np.unique([result.json["member_id"][0] for result in search_results])
    )
    _logger.info(f"Found {len(members)} members: {list(map(str, members))}")

    if len(members) == 0:
        _logger.critical(
            f"Found no data source for the requested variable {variable_id}"
        )
        raise RuntimeError("Found no data source for the requested variable")

    ctx_first = ctx.constrain(member_id=members[0])
    search_results_first_member = filter_node(ctx_first.search())
    result = search_results_first_member[0]

    file_context: pyesgf.search.context.FileSearchContext = result.file_context()
    file_context.facets = facets
    files: list[pyesgf.search.results.FileResult] = file_context.search()

    _logger.info(f"Found {len(files)} files for member {members[0]}")

    if table_id == "fx":
        # fixed files (i.e., not changing with time)
        return [file.download_url for file in files]

    download_urls = []
    for file in files:
        regex = r".*_(\d{12})-(\d{12}).nc\|.*"
        file_stime, file_etime = pd.to_datetime(re.match(regex, file.file_id).groups())
        if max(file_stime, start_date) <= min(file_etime, end_date):
            download_urls.append(file.download_url)

    return download_urls


# %%
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        force=True,
    )
    print("\n".join(tapify(get_download_urls)))
