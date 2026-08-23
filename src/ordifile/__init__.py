# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Public package for Ordifile."""

from ordifile._version import __version__
from ordifile.core.models import ConversionExecutionMode
from ordifile.core.peak_mapping import (
    ColumnSelector,
    PeakMappingDriftCategory,
    PeakMappingDriftDiagnostic,
    PeakTableFormat,
    PeakTableImportSettings,
    PeakTableMapping,
    PeakTableMappingProfile,
    PeakTableMappingSet,
    PeakTablePreview,
    PeakTableTextEncoding,
    clone_peak_table_mapping_profile,
    load_peak_table_mapping,
    load_peak_table_mapping_set,
    save_peak_table_mapping,
    save_peak_table_mapping_set,
)
from ordifile.core.planning import (
    ConversionPlan,
    ConversionPlanEntry,
    ConversionPlanEntryStatus,
    ConversionPlanOutputDisposition,
    ConversionPlanProblem,
    ConversionPlanReadiness,
    ConversionPlanRoute,
    ConversionPlanSummary,
    PlanProgressEvent,
)
from ordifile.core.recipe import (
    CONVERSION_RECIPE_SCHEMA_VERSION,
    MAX_CONVERSION_RECIPE_BYTES,
    ConversionRecipe,
    load_conversion_recipe,
    save_conversion_recipe,
)
from ordifile.core.summary import (
    CONVERSION_RESULT_SUMMARY_SCHEMA_VERSION,
    ConversionResultSummary,
    summarize_conversion,
)

__all__ = [
    "ColumnSelector",
    "CONVERSION_RESULT_SUMMARY_SCHEMA_VERSION",
    "CONVERSION_RECIPE_SCHEMA_VERSION",
    "ConversionPlan",
    "ConversionPlanEntry",
    "ConversionPlanEntryStatus",
    "ConversionPlanOutputDisposition",
    "ConversionPlanProblem",
    "ConversionPlanReadiness",
    "ConversionPlanRoute",
    "ConversionPlanSummary",
    "ConversionExecutionMode",
    "ConversionResultSummary",
    "ConversionRecipe",
    "MAX_CONVERSION_RECIPE_BYTES",
    "PeakMappingDriftCategory",
    "PeakMappingDriftDiagnostic",
    "PeakTableFormat",
    "PeakTableImportSettings",
    "PeakTableMapping",
    "PeakTableMappingProfile",
    "PeakTableMappingSet",
    "PeakTablePreview",
    "PeakTableTextEncoding",
    "PlanProgressEvent",
    "__version__",
    "clone_peak_table_mapping_profile",
    "load_peak_table_mapping",
    "load_peak_table_mapping_set",
    "load_conversion_recipe",
    "save_peak_table_mapping",
    "save_peak_table_mapping_set",
    "save_conversion_recipe",
    "summarize_conversion",
]
