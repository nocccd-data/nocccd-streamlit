from .fast_facts import render as fast_facts_render
from .coi_nhrdist_val import render as coi_nhrdist_val_render
from .mis_sp_submitted_scff import render as mis_sp_submitted_scff_render
from .mis_sp_current_scff import render as mis_sp_current_scff_render
from .mis_fa_submitted_scff import render as mis_fa_submitted_scff_render

# Registry of active tabs: (label, render_function)
# To add a tab: import its render function and append a tuple here.
# To retire a tab: remove its tuple (and optionally delete the module).
TABS = [
    ("Fast Facts", fast_facts_render),
    ("COI vs NHRDIST Validation", coi_nhrdist_val_render),
    ("MIS SP Submitted vs. SCFF", mis_sp_submitted_scff_render),
    ("MIS SP Current vs. SCFF", mis_sp_current_scff_render),
    ("MIS FA Submitted vs. SCFF", mis_fa_submitted_scff_render),
]
