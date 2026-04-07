# Data Model Analysis Notes

This file records the empirical basis for the storage model.

## Source material

The subtype property analysis was collected from current Sreality listings and stored under:

- `Data/analysis/byty_property_map.json`
- `Data/analysis/domy_property_map.json`
- `Data/analysis/pozemky_property_map.json`
- `Data/analysis/komercni_property_map.json`
- `Data/analysis/ostatni_property_map.json`
- `Data/analysis/property_matrix_summary.json`

These files are working analysis artifacts and do not need to be committed.

## Observed conclusion

The property model is:

- broad,
- subtype-variant,
- only partially shared even inside one main category,
- unsuitable for a persistence design based mainly on subtype-specific child tables.

## Storage consequence

The specification therefore chooses:

- shared entity table for identity,
- typed attribute storage for variable fields,
- attribute-level event history,
- browse-friendly exports for manual inspection.
