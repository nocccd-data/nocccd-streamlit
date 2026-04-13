from .fast_facts import render as fast_facts_render
from .class_schedule_heatmap import render as class_schedule_heatmap_render
from .persistence_by_styp import render as persistence_by_styp_render
from .coi_nhrdist_val import render as coi_nhrdist_val_render
from .mis_sp_submitted_scff import render as mis_sp_submitted_scff_render
from .mis_sp_current_scff import render as mis_sp_current_scff_render
from .mis_fa_submitted_scff import render as mis_fa_submitted_scff_render
from .cte_sx_submitted_scff import render as cte_sx_submitted_scff_render
from .seat_count_report import render as seat_count_report_render
from .bot_goal1_students import render as bot_goal1_students_render
from .bot_goal2_cert import render as bot_goal2_cert_render
from .bot_goal2_cert_nc import render as bot_goal2_cert_nc_render
from .bot_goal2_assoc import render as bot_goal2_assoc_render
from .bot_goal2_adt import render as bot_goal2_adt_render
from .bot_goal2_bac import render as bot_goal2_bac_render
from .bot_goal2_xfer import render as bot_goal2_xfer_render
from .bot_goal2_wage import render as bot_goal2_wage_render
from .bot_goal3_finaid import render as bot_goal3_finaid_render
from .mail_admin import render as mail_admin_render

# Registry of active tabs: (label, render_function)
# To add a tab: import its render function and append a tuple here.
# To retire a tab: remove its tuple (and optionally delete the module).
TABS = [
    ("Fast Facts", fast_facts_render),
    ("Seat Count Report", seat_count_report_render),
    ("Class Schedule Heatmap", class_schedule_heatmap_render),
    ("Persistence by Student Type", persistence_by_styp_render),
    ("COI vs NHRDIST Validation", coi_nhrdist_val_render),
    ("SCFF Degrees - MIS SP Submitted", mis_sp_submitted_scff_render),
    ("SCFF Degrees - MIS SP Current", mis_sp_current_scff_render),
    ("SCFF Awards - MIS FA Submitted", mis_fa_submitted_scff_render),
    ("SCFF CTE - MIS SX Submitted", cte_sx_submitted_scff_render),
    ("BOT Goal 1 - Students", bot_goal1_students_render),
    ("BOT Goal 2 - Certificates", bot_goal2_cert_render),
    ("BOT Goal 2 - Noncredit Certificates", bot_goal2_cert_nc_render),
    ("BOT Goal 2 - Associate Degrees", bot_goal2_assoc_render),
    ("BOT Goal 2 - ADT", bot_goal2_adt_render),
    ("BOT Goal 2 - Bachelor's Degrees", bot_goal2_bac_render),
    ("BOT Goal 2 - Transfers", bot_goal2_xfer_render),
    ("BOT Goal 2 - Living Wage", bot_goal2_wage_render),
    ("BOT Goal 3 - Financial Aid", bot_goal3_finaid_render),
    ("Mail Admin", mail_admin_render),
]
