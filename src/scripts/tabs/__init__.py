from .coi_nhrdist_val import render as coi_nhrdist_val_render

# Registry of active tabs: (label, render_function)
# To add a tab: import its render function and append a tuple here.
# To retire a tab: remove its tuple (and optionally delete the module).
TABS = [
    ("COI vs NHRDIST Validation", coi_nhrdist_val_render),
]
