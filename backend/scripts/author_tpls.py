"""Author the correspondence-template (TPL-01..42) bodies.

Writes one HTML file per TPL under ``app/templates/library/`` with real letter
content: ``{{merge_token}}`` where an Airtable field maps, and ``[bracketed]``
blanks where the value isn't captured anywhere (agent fills it in the editor).

The catalog in ``services/document_library.py`` promotes each TPL from a
placeholder to ``library_file`` automatically once its ``{doc_id}.html`` exists.

Does NOT touch the three big contracts (pg_tcs_2026 / apt_pet_abnb /
common_law_ta). Re-run any time to regenerate.

    python -m scripts.author_tpls
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app" / "templates" / "library"

# Recipient address + salutation blocks (merge tokens; [brackets] for non-data).
ADDR = {
    "landlord": "{{landlord_full_name}}<br>{{landlord_address}}<br>{{landlord_post_code}}",
    "tenant":   "{{tenant_full_name}}<br>{{property_address}}, {{property_post_code}}",
    "guarantor": "{{guarantor_name}}<br>{{guarantor_address}}",
    "contractor": "[Contractor name]<br>[Contractor address]",
    "both":     "{{landlord_full_name}} &amp; {{tenant_full_name}}",
}
SAL = {
    "landlord": "{{landlord_full_name}}",
    "tenant": "{{tenant_full_name}}",
    "guarantor": "{{guarantor_name}}",
    "contractor": "[Contractor name]",
    "both": "{{landlord_full_name}} and {{tenant_full_name}}",
}
FOOTER = (
    "<p>Yours sincerely,</p>"
    "<p><strong>{{brand_name}}</strong><br>{{agent_office_address}}"
    "<br>{{agent_phone}} &middot; {{agent_email}}</p>"
)


def letter(title: str, recipient: str, body: str, *, re_line: bool = True, footer: str = FOOTER) -> str:
    parts = [
        "<h2>" + title + "</h2>",
        "<p>{{today}}</p>",
        "<p>" + ADDR[recipient] + "</p>",
    ]
    if re_line:
        parts.append("<p><strong>Re: {{property_address}}, {{property_post_code}}</strong></p>")
    parts.append("<p>Dear " + SAL[recipient] + ",</p>")
    parts.append(body)
    parts.append(footer)
    return "".join(parts)


# (doc_id, recipient, title, body_html)
TPLS: list[tuple[str, str, str, str]] = [
    # ------------------------------------------------------------------ Stage 1
    ("tpl_01", "landlord", "TPL-01 — Introductory Valuation Letter",
     "<p>Thank you for the opportunity to advise on the letting of your property. "
     "Following our assessment we are pleased to provide our recommendation below.</p>"
     "<p>Based on comparable evidence and current demand we would recommend marketing "
     "{{property_address}} ({{property_type}}) at a guide rent of <strong>[recommended rent]</strong>, "
     "against a current figure on file of {{annual_rent}} per annum ({{rent_frequency}}).</p>"
     "<p>We would propose a <strong>{{service_level}}</strong> service. A summary of the local market "
     "and our marketing strategy is set out below:</p><p>[Market commentary and strategy]</p>"
     "<p>We would be delighted to act for you and look forward to your instructions.</p>"),

    ("tpl_02", "landlord", "TPL-02 — Instruction Letter",
     "<p>Thank you for instructing {{brand_name}} in connection with the letting of "
     "{{property_address}}. This letter confirms your instruction on a <strong>{{service_level}}</strong> "
     "basis at our agreed commission of <strong>[commission rate]</strong>.</p>"
     "<p>Our full Terms &amp; Conditions of Business accompany this letter and form part of our "
     "agreement. Please sign below to confirm your instruction.</p>"
     "<table><tr><td><p><strong>Signed by the Landlord</strong></p><p>/sig1/</p>"
     "<p>Name: {{landlord_full_name}}</p><p>Date: ____________________</p></td></tr></table>",
     ),

    ("tpl_04", "landlord", "TPL-04 — Terms &amp; Conditions Reminder",
     "<p>We are looking forward to progressing the letting of {{property_address}}. Our records show "
     "that our Terms &amp; Conditions of Business are not yet signed.</p>"
     "<p>So that we can proceed without delay, please review and sign the Terms &amp; Conditions we sent "
     "you. We are unable to market the property or release funds until these are in place.</p>"),

    # ------------------------------------------------------------------ Stage 2
    ("tpl_03", "landlord", "TPL-03 — Know Your Client (KYC) &amp; AML Request",
     "<p>Under the Money Laundering Regulations 2017 we are required to verify your identity before "
     "acting for you. Our records show your residency status as <strong>{{landlord_resident_status}}</strong>.</p>"
     "<p>Please provide the following:</p><ul>"
     "<li>Photographic ID (passport or driving licence)</li>"
     "<li>Proof of address dated within the last three months</li>"
     "<li>Proof of ownership of {{property_address}}</li>"
     "<li>For company landlords ({{landlord_company_name}}): certificate of incorporation, and ID for "
     "director {{landlord_director_name}}</li></ul>"
     "<p>You can upload these securely via the link we have sent to {{landlord_email}}.</p>"),

    ("tpl_07", "landlord", "TPL-07 — Legal Requirements &amp; Pre-Tenancy Checklist",
     "<p>Before we can let {{property_address}}, the following legal requirements must be satisfied. "
     "Our current records are shown alongside each item.</p><ul>"
     "<li>Gas Safety Certificate — expiry on file: {{gas_cert_expiry}}</li>"
     "<li>Electrical Installation Condition Report (EICR) — expiry on file: {{eicr_expiry}}</li>"
     "<li>Energy Performance Certificate — current rating: {{epc_rating}} (minimum E to let)</li>"
     "<li>Smoke and carbon-monoxide alarms — [confirm fitted and tested]</li>"
     "<li>HMO licence required: {{hmo_flag}}</li></ul>"
     "<p>Please arrange any outstanding items at your earliest convenience so we can proceed to market.</p>"),

    ("tpl_08", "landlord", "TPL-08 — Pre-Tenancy Works Sign-Off",
     "<p>Following our inspection of {{property_address}}, the works below are recommended before the "
     "tenancy commences:</p><p>[List of works and estimated costs]</p>"
     "<p>Please confirm your approval to instruct these works. We will obtain [number] quotes where the "
     "cost is expected to exceed [threshold].</p>"),

    # ------------------------------------------------------------------ Stage 4
    ("tpl_05", "landlord", "TPL-05 — Offer Confirmation",
     "<p>We are pleased to confirm that we have received an offer for {{property_address}} on the "
     "following terms:</p><ul>"
     "<li>Proposed tenant: {{tenant_full_name}}</li>"
     "<li>Rent: {{monthly_rent}} ({{rent_frequency}})</li>"
     "<li>Deposit: {{deposit_amount}}</li>"
     "<li>Holding deposit received: {{holding_deposit}}</li>"
     "<li>Proposed start date: {{tenancy_start_date}}</li>"
     "<li>Term: {{tenancy_term}} months</li>"
     "<li>Rent in advance: {{rent_in_advance_months}} month(s)</li>"
     "<li>Break clause: {{break_clause}}</li></ul>"
     "<p>Any special conditions: [special conditions]. Please confirm your acceptance so we can proceed "
     "to referencing and prepare the tenancy agreement.</p>"),

    ("tpl_06", "tenant", "TPL-06 — Referencing Request",
     "<p>Thank you for your offer on {{property_address}}. To progress your application we now need to "
     "complete referencing through our provider, Paragon.</p>"
     "<p>You will shortly receive an email from Paragon at {{tenant_email}} with a secure link. Please "
     "complete it within [number] working days. Where a guarantor is required, "
     "{{guarantor_name}} will also be referenced.</p>"
     "<p>Your current referencing status is: {{referencing_status}}.</p>"),

    # ------------------------------------------------------------------ Stage 7
    ("tpl_09", "tenant", "TPL-09 — Bank Details &amp; Standing Order Instruction",
     "<p>Please set up a standing order for your rent on {{property_address}} as follows:</p><ul>"
     "<li>Amount: {{monthly_rent}} ({{rent_frequency}})</li>"
     "<li>Payee: {{landlord_account_name}}</li>"
     "<li>Bank: {{landlord_bank_name}}</li>"
     "<li>Sort code: {{landlord_sort_code}}</li>"
     "<li>Account number: {{landlord_account_number}}</li>"
     "<li>First payment date: [first rent due date]</li>"
     "<li>Reference: {{property_post_code}}</li></ul>"
     "<p>Please ensure the standing order is active before your tenancy start date of "
     "{{tenancy_start_date}}.</p>"),

    ("tpl_10", "tenant", "TPL-10 — Check-In Confirmation",
     "<p>We are pleased to confirm your check-in at {{property_address}}.</p><ul>"
     "<li>Check-in date: {{checkin_date}}</li>"
     "<li>Inventory clerk: {{inventory_clerk}}</li>"
     "<li>Meeting time and place: [time / place]</li></ul>"
     "<p>The independent inventory will be carried out at check-in. Please bring photographic ID.</p>"),

    ("tpl_11", "tenant", "TPL-11 — Welcome Letter &amp; Tenant Pack",
     "<p>Welcome to your new home at {{property_address}}. Your tenancy begins on "
     "{{tenancy_start_date}} for a term of {{tenancy_term}} months.</p>"
     "<p>Your deposit of {{deposit_amount}} has been protected with [deposit scheme] under certificate "
     "[scheme reference]. Your prescribed documents (How to Rent, gas safety, EPC, EICR and deposit "
     "prescribed information) are attached.</p>"
     "<p>If you have any questions during your tenancy please contact us at {{agent_email}}.</p>"),

    ("tpl_12", "landlord", "TPL-12 — Move-In Confirmation",
     "<p>We are pleased to confirm that {{tenant_full_name}} has moved into {{property_address}} on "
     "{{tenancy_start_date}}.</p>"
     "<p>Rent of {{monthly_rent}} ({{rent_frequency}}) is now in place. The signed tenancy agreement, "
     "inventory and check-in report will follow under separate cover.</p>"),

    ("tpl_13", "tenant", "TPL-13 — Utility Transfer Instruction",
     "<p>Now that your tenancy at {{property_address}} has begun on {{tenancy_start_date}}, please "
     "arrange to transfer the following into your name from that date:</p><ul>"
     "<li>Gas and electricity — [supplier]</li>"
     "<li>Water — [supplier]</li>"
     "<li>Council tax — borough: [council borough]</li>"
     "<li>Broadband / media — [supplier]</li></ul>"
     "<p>Opening meter readings: [readings]. Please notify each supplier promptly to avoid being billed "
     "for the previous occupier.</p>"),

    # ------------------------------------------------------------------ Stage 8
    ("tpl_14", "tenant", "TPL-14 — Friendly Rent Reminder",
     "<p>This is a friendly reminder that your rent of {{monthly_rent}} for {{property_address}} is due "
     "on [due date]. No action is needed if your standing order is set up.</p>"),

    ("tpl_15", "tenant", "TPL-15 — First Arrears Notice",
     "<p>Our records show that your rent of {{monthly_rent}} for {{property_address}} has not been "
     "received and is now [days] days overdue. The balance outstanding is [amount].</p>"
     "<p>Please make payment immediately or contact us to discuss.</p>"),

    ("tpl_16", "tenant", "TPL-16 — Second Arrears Notice",
     "<p>Further to our previous reminder, the rent on {{property_address}} remains unpaid. The amount "
     "now outstanding is [amount], being [days] days in arrears.</p>"
     "<p>Please arrange payment within [number] days to avoid further action.</p>"),

    ("tpl_17", "tenant", "TPL-17 — Final Arrears Warning",
     "<p>Despite our previous notices, rent of [amount] for {{property_address}} remains outstanding. "
     "This is a final request before we refer the matter to the landlord and consider possession "
     "proceedings.</p><p>Please contact us urgently on {{agent_phone}}.</p>"),

    ("tpl_18", "tenant", "TPL-18 — Maintenance Acknowledgement",
     "<p>Thank you for reporting the following issue at {{property_address}}:</p><p>[Reported issue]</p>"
     "<p>We have logged your report and will arrange for it to be attended to. We will be in touch with "
     "an appointment shortly.</p>"),

    ("tpl_19", "landlord", "TPL-19 — Maintenance Notification",
     "<p>A maintenance issue has been reported at {{property_address}}:</p><p>[Reported issue]</p>"
     "<p>Our recommended action is [action], at an estimated cost of [cost]. Please confirm your "
     "authorisation to proceed.</p>"),

    ("tpl_20", "contractor", "TPL-20 — Works Instruction to Contractor",
     "<p>We instruct you to attend {{property_address}} to carry out the following works:</p>"
     "<p>[Scope of works]</p><ul>"
     "<li>Access arrangements: [access]</li>"
     "<li>Agreed cost: [cost]</li>"
     "<li>Target completion: [date]</li></ul>"
     "<p>Please confirm receipt and your attendance date.</p>"),

    ("tpl_21", "contractor", "TPL-21 — Contractor Chase",
     "<p>We are following up on the works instructed at {{property_address}} ([scope]). Please provide "
     "an update on progress and your expected completion date.</p>"),

    ("tpl_22", "tenant", "TPL-22 — Works Completion Notice",
     "<p>We are pleased to confirm that the works at {{property_address}} ([scope]) have now been "
     "completed. Please let us know if you have any concerns.</p>"),

    ("tpl_23", "landlord", "TPL-23 — Works Completion Report",
     "<p>The works at {{property_address}} have been completed.</p><ul>"
     "<li>Works carried out: [scope]</li><li>Contractor: [contractor]</li>"
     "<li>Final cost: [cost]</li></ul>"
     "<p>The invoice [will be deducted from rent received / is attached]. Photographs are enclosed.</p>"),

    ("tpl_24", "landlord", "TPL-24 — Inspection Report Cover Letter",
     "<p>We have carried out a periodic inspection of {{property_address}} on [inspection date]. The "
     "full report is attached.</p><p>Summary of findings: [summary]. We recommend [recommendations].</p>"),

    ("tpl_25", "tenant", "TPL-25 — Settling-In Check (Month 1)",
     "<p>You have now been at {{property_address}} for a month and we wanted to check that everything is "
     "as it should be. If there is anything that needs attention, please let us know.</p>"),

    ("tpl_26", "tenant", "TPL-26 — Six-Month Check-In",
     "<p>We hope you are continuing to enjoy living at {{property_address}}. As you reach the half-way "
     "point of your tenancy, please let us know if there is anything we can help with.</p>"),

    ("tpl_27", "landlord", "TPL-27 — Market Update",
     "<p>We thought you would find a brief update on the local lettings market useful in relation to "
     "{{property_address}}.</p><p>[Market commentary]</p>"),

    ("tpl_28", "tenant", "TPL-28 — Introduction to {{brand_name}} Services",
     "<p>As your managing agent for {{property_address}}, we wanted to introduce the services available "
     "to you during your tenancy, including maintenance reporting and our out-of-hours line.</p>"
     "<p>[Services overview]</p>"),

    ("tpl_29", "tenant", "TPL-29 — Tenancy Anniversary Note",
     "<p>It has been a year since you moved into {{property_address}} on {{tenancy_start_date}}. Thank "
     "you for being a valued tenant — we hope the home continues to serve you well.</p>"),

    ("tpl_30", "landlord", "TPL-30 — Landlord Market Update",
     "<p>A periodic update on your investment at {{property_address}} and the wider market.</p>"
     "<p>[Market and portfolio commentary]</p>"),

    ("tpl_31", "landlord", "TPL-31 — Property Health Summary",
     "<p>A proactive compliance and health summary for {{property_address}}:</p><ul>"
     "<li>Gas safety certificate expiry: {{gas_cert_expiry}}</li>"
     "<li>EICR expiry: {{eicr_expiry}}</li>"
     "<li>EPC rating: {{epc_rating}}</li>"
     "<li>Tenancy expiry: {{tenancy_expiry_date}}</li></ul>"
     "<p>We will arrange renewals of any expiring certificates in good time.</p>"),

    # ------------------------------------------------------------------ Stage 9
    ("tpl_32", "landlord", "TPL-32 — Renewal Prompt",
     "<p>The current tenancy of {{property_address}} is due to end on {{tenancy_expiry_date}}. The "
     "tenant, {{tenant_full_name}}, [has expressed an interest in / we recommend offering] a renewal.</p>"
     "<p>We would suggest a renewal at [proposed rent] for [proposed term]. Please let us know your "
     "wishes.</p>"),

    ("tpl_33", "tenant", "TPL-33 — Renewal Prompt",
     "<p>Your tenancy at {{property_address}} is due to end on {{tenancy_end_date}}. We would be "
     "delighted to offer you a renewal.</p>"
     "<p>Proposed terms: rent [proposed rent], term [proposed term]. Please let us know if you would "
     "like to proceed.</p>"),

    ("tpl_34", "both", "TPL-34 — Renewal Confirmation",
     "<p>We are pleased to confirm the renewal of the tenancy at {{property_address}} on the following "
     "terms:</p><ul><li>New rent: [new rent]</li><li>New term: [new term]</li>"
     "<li>Commencing: [renewal start date]</li></ul>"
     "<p>A renewal memorandum / new agreement will follow for signature.</p>"),

    ("tpl_35a", "tenant", "TPL-35a — Acknowledgement of Notice to Quit (APT)",
     "<p>We acknowledge receipt of your notice to end the assured periodic tenancy at "
     "{{property_address}}.</p><ul><li>Notice received: [date received]</li>"
     "<li>Tenancy end date: [end date]</li></ul>"
     "<p>We will be in touch to arrange the check-out and the return of your deposit "
     "({{deposit_amount}}).</p>"),

    ("tpl_35b", "tenant", "TPL-35b — Section 8 Notice (APT)",
     "<p>Please take notice that the landlord of {{property_address}} intends to seek possession under "
     "the following grounds of the Housing Act 1988:</p><p>[Grounds relied upon]</p><ul>"
     "<li>Date notice served: [date]</li><li>Earliest possession date: [date]</li></ul>"
     "<p>This notice is served in respect of [reason, e.g. rent arrears of (amount)].</p>"),

    ("tpl_35c", "tenant", "TPL-35c — Notice to Vacate (Common Law)",
     "<p>Please take notice that you are required to give up vacant possession of {{property_address}} "
     "by [vacate date], in accordance with the terms of your common-law tenancy.</p>"
     "<p>Please contact us to arrange the check-out and the return of your deposit "
     "({{deposit_amount}}).</p>"),

    ("tpl_36", "tenant", "TPL-36 — End of Tenancy Information Pack",
     "<p>As your tenancy at {{property_address}} approaches its end on {{tenancy_end_date}}, this pack "
     "explains the check-out process, your responsibilities and how your deposit will be returned.</p>"
     "<p>[Check-out process and cleaning standards]</p>"),

    ("tpl_37", "tenant", "TPL-37 — Check-Out Reminder &amp; Cleaning Guidance",
     "<p>Your check-out at {{property_address}} is scheduled for {{checkout_date}}. To help ensure the "
     "full return of your deposit, please note the cleaning and condition standards below.</p>"
     "<p>[Cleaning guidance]</p>"),

    ("tpl_38", "landlord", "TPL-38 — Check-Out Cover Letter",
     "<p>The check-out of {{property_address}} took place on {{checkout_date}}. The check-out report is "
     "attached for your review, together with any recommended deductions.</p><p>[Summary]</p>"),

    ("tpl_39", "tenant", "TPL-39 — Check-Out Cover Letter",
     "<p>Thank you for returning the keys to {{property_address}}. The check-out report from "
     "{{checkout_date}} is attached. We will be in touch regarding the return of your deposit.</p>"),

    ("tpl_40", "tenant", "TPL-40 — Deposit Release Confirmation",
     "<p>We are pleased to confirm the release of your deposit for {{property_address}}.</p><ul>"
     "<li>Deposit held: {{deposit_amount}}</li><li>Agreed deductions: [deductions]</li>"
     "<li>Amount returned: [amount returned]</li><li>Scheme: [deposit scheme]</li></ul>"
     "<p>Funds will be returned to [account] within [number] working days.</p>"),

    ("tpl_41", "tenant", "TPL-41 — Deposit Dispute Notification",
     "<p>We were unable to reach agreement on the proposed deductions from your deposit "
     "({{deposit_amount}}) for {{property_address}}.</p>"
     "<p>The matter has been referred to the deposit scheme's dispute resolution service. The amount in "
     "dispute is [amount]; the undisputed sum of [amount] will be released to you.</p>"),

    ("tpl_42", "tenant", "TPL-42 — Farewell Note",
     "<p>Thank you for renting {{property_address}} through {{brand_name}}. It has been a pleasure "
     "having you as a tenant and we wish you well in your new home.</p>"
     "<p>Should you need a reference or be looking for your next home, we would be glad to help.</p>"),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    for doc_id, recipient, title, body in TPLS:
        html = letter(title, recipient, body)
        (OUT / f"{doc_id}.html").write_text(html, encoding="utf-8")
        written += 1
    print(f"[ok] authored {written} TPL files -> {OUT}")


if __name__ == "__main__":
    main()
