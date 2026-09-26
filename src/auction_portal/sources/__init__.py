"""Source adapters.

One module per auction data source. Each adapter knows how to discover and
parse exactly one source; nothing else in the codebase needs to know how
any of them work.
"""

from auction_portal.sources.baanknet import BaanknetAdapter
from auction_portal.sources.base import ParsedListing, SourceAdapter

#: Every adapter the pipeline can run, keyed by source_id.
REGISTRY: dict[str, type[SourceAdapter]] = {
    BaanknetAdapter.source_id: BaanknetAdapter,
}

__all__ = ["REGISTRY", "BaanknetAdapter", "ParsedListing", "SourceAdapter"]
