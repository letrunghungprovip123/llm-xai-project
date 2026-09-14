"""Release-47 SFLLD raw file schema used by the 2024 vintage export.

The 2024 files supplied in July 2026 use the Release-47 naming/layout.  The
constants here describe raw positional columns only.  Semantic normalization
belongs to the preparation adapter, not the raw intake stage.
"""

from __future__ import annotations

ORIGINATION_COLUMNS: tuple[str, ...] = (
    "classic_fico",
    "first_payment_date",
    "first_time_homebuyer_indicator",
    "maturity_date",
    "msa_or_metropolitan_division",
    "mortgage_insurance_percentage",
    "number_of_units",
    "occupancy_status",
    "original_cltv",
    "original_dti",
    "original_upb",
    "original_ltv",
    "original_interest_rate",
    "channel",
    "prepayment_penalty_indicator",
    "amortization_type",
    "property_state",
    "property_type",
    "postal_code",
    "loan_identifier",
    "loan_purpose",
    "original_loan_term",
    "number_of_borrowers",
    "seller_name",
    "super_conforming_flag",
    "pre_harp_loan_identifier",
    "special_eligibility_program",
    "harp_indicator",
    "property_valuation_method",
    "interest_only_indicator",
    "vantagescore_4_0",
)

PERFORMANCE_COLUMNS: tuple[str, ...] = (
    "loan_identifier",
    "monthly_reporting_period",
    "current_actual_upb",
    "current_loan_delinquency_status",
    "loan_age",
    "remaining_months_to_legal_maturity",
    "defect_settlement_date",
    "modification_flag",
    "zero_balance_code",
    "zero_balance_effective_date",
    "current_interest_rate",
    "current_non_interest_bearing_upb",
    "ddlpi",
    "mi_recoveries",
    "net_sales_proceeds",
    "non_mi_recoveries",
    "total_expenses",
    "legal_costs",
    "maintenance_and_preservation_costs",
    "taxes_and_insurance",
    "miscellaneous_expenses",
    "actual_loss",
    "cumulative_modification_costs",
    "interest_rate_step_indicator",
    "payment_deferral_flag",
    "estimated_ltv",
    "zero_balance_removal_upb",
    "delinquent_accrued_interest",
    "delinquency_due_to_disaster",
    "borrower_assistance_plan",
    "current_period_modification_costs",
    "current_interest_bearing_upb",
    "mortgage_insurance_cancellation_indicator",
    "servicer_name",
    "bankruptcy_cramdown_costs",
)

ORIGINATION_WIDTH = len(ORIGINATION_COLUMNS)
PERFORMANCE_WIDTH = len(PERFORMANCE_COLUMNS)
LOAN_ID_ORIG_INDEX = ORIGINATION_COLUMNS.index("loan_identifier")
LOAN_ID_PERF_INDEX = PERFORMANCE_COLUMNS.index("loan_identifier")
PERIOD_INDEX = PERFORMANCE_COLUMNS.index("monthly_reporting_period")
LOAN_AGE_INDEX = PERFORMANCE_COLUMNS.index("loan_age")
DELINQUENCY_INDEX = PERFORMANCE_COLUMNS.index("current_loan_delinquency_status")
ZERO_BALANCE_CODE_INDEX = PERFORMANCE_COLUMNS.index("zero_balance_code")
