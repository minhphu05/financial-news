"""Inactive Prefect flows kept for future reuse."""

from importlib import import_module


_FLOW_EXPORTS = {
	"eval_flow": "src.flows.future_use.eval_flow",
	"full_pipeline_flow": "src.flows.future_use.full_pipeline_flow",
	"ingest_flow": "src.flows.future_use.ingest_flow",
	"medallion_flow": "src.flows.future_use.medallion_flow",
	"reindex_flow": "src.flows.future_use.reindex_flow",
	"scrape_quality_flow": "src.flows.future_use.scrape_quality_flow",
}


def __getattr__(name: str):
	if name not in _FLOW_EXPORTS:
		raise AttributeError(name)
	module = import_module(_FLOW_EXPORTS[name])
	globals()[name] = module
	return module


__all__ = sorted(_FLOW_EXPORTS)
