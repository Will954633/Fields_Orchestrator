#!/usr/bin/env python3
"""Generate Google Ads API design document for Basic Access application."""

from fpdf import FPDF


class DesignDoc(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 8, "Fields Estate - Google Ads API Tool Design Document", align="C", new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title):
        self.set_font("Helvetica", "B", 12)
        self.set_fill_color(230, 230, 230)
        self.cell(0, 8, title, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 5, text)
        self.ln(2)

    def bullet_list(self, items):
        self.set_font("Helvetica", "", 10)
        for item in items:
            self.cell(3, 5, "")
            self.multi_cell(0, 5, "- " + item)
            self.ln(1)


pdf = DesignDoc()
pdf.alias_nb_pages()
pdf.set_auto_page_break(auto=True, margin=20)
pdf.add_page()

# Title
pdf.set_font("Helvetica", "B", 16)
pdf.cell(0, 12, "Fields Estate", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "", 12)
pdf.cell(0, 8, "Google Ads API Internal Campaign Management Tool", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(4)

pdf.set_font("Helvetica", "", 10)
pdf.cell(0, 5, "Company: Fields Estate  |  Website: https://fieldsestate.com.au", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 5, "Contact: Will Simpson  |  Email: will@fieldsestate.com.au", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 5, "Date: March 2026  |  Version: 1.0", new_x="LMARGIN", new_y="NEXT")
pdf.ln(6)

# 1. Overview
pdf.section_title("1. Overview")
pdf.body_text(
    "Fields Estate is a property intelligence platform based on the Gold Coast, Queensland, "
    "Australia. We provide property valuations, market analysis, suburb intelligence, and sales "
    "data to home buyers and sellers in targeted suburbs (Robina, Burleigh Waters, Varsity Lakes)."
)
pdf.body_text(
    "We are building an internal-only tool to manage Google Ads campaigns programmatically via "
    "the Google Ads API. This tool will be used exclusively by Fields Estate staff (currently a "
    "single operator/founder) to create, manage, and optimise Search and Display campaigns that "
    "drive traffic to our property data content at fieldsestate.com.au."
)

# 2. Tool Purpose
pdf.section_title("2. Tool Purpose and Functionality")
pdf.body_text("The tool is designed to:")
pdf.bullet_list([
    "Create and manage Google Ads Search campaigns targeting property-related keywords in specific Gold Coast suburbs",
    "Create and manage Display campaigns to reach home buyers and sellers with property data content",
    "Set geo-targeting to specific suburbs (Robina, Burleigh Waters, Varsity Lakes and surrounding areas)",
    "Generate and update responsive search ad copy based on current property data",
    "Set and monitor daily/monthly budgets with configurable safety caps",
    "Pull campaign performance reports (clicks, impressions, conversions, cost) for analysis",
    "Pause/enable campaigns and adjust bids based on performance data",
])

# 3. Architecture
pdf.section_title("3. Technical Architecture")
pdf.body_text(
    "The tool runs on a Google Cloud VM (e2-medium, australia-southeast1-b) alongside our "
    "existing data pipeline infrastructure. It is a Python-based command-line application that "
    "interacts with the Google Ads API via the official google-ads Python client library."
)
pdf.body_text("Architecture components:")
pdf.bullet_list([
    "Runtime: Python 3.11 on Google Cloud Compute Engine VM",
    "API client: google-ads Python library (official Google client)",
    "Authentication: OAuth2 (Desktop app flow) with stored refresh token",
    "Credential storage: Environment variables in .env file on the VM (never in source code)",
    "Execution: Manual command-line invocation by the operator, or scheduled via cron for reporting",
    "Data source: Azure Cosmos DB (MongoDB API) containing live property data used to generate ad copy",
])

pdf.body_text(
    "Data flow:\n"
    "1. Operator triggers the tool via command line\n"
    "2. Tool reads current property data from our database\n"
    "3. Tool generates campaign/ad group/ad configurations\n"
    "4. Tool sends API requests to Google Ads via the official Python client\n"
    "5. Performance reports are pulled back and stored locally for analysis"
)

# 4. API Features Used
pdf.section_title("4. Google Ads API Features Used")
pdf.body_text("The tool will use the following API services:")
pdf.bullet_list([
    "CampaignService - Create, update, pause/enable campaigns",
    "AdGroupService - Create and manage ad groups within campaigns",
    "AdGroupAdService - Create responsive search ads",
    "AdGroupCriterionService - Set keyword targeting",
    "CampaignBudgetService - Set and manage daily budgets",
    "GeoTargetConstantService - Set geographic targeting",
    "GoogleAdsService (SearchStream) - Pull performance reports",
])
pdf.body_text(
    "The tool will NOT use: Remarketing, App Conversion Tracking, Offline Conversion Import, "
    "Customer Match, or any features involving user data upload."
)

# 5. Access and Users
pdf.section_title("5. Access Control and Users")
pdf.body_text(
    "This is an internal-only tool. Access is restricted to Fields Estate staff."
)
pdf.body_text(
    "Current users: 1 (Will Simpson, founder and sole operator)"
)
pdf.body_text(
    "The tool runs on a private VM accessible only via SSH. There is no web interface or "
    "external access point for the Google Ads management functionality. OAuth2 credentials "
    "are stored in environment variables on the VM and are not shared or exposed."
)
pdf.body_text(
    "The tool will only manage campaigns in the Fields Estate Google Ads account. It will "
    "not access, manage, or interact with any third-party Google Ads accounts."
)

# 6. Rate Limiting
pdf.section_title("6. Rate Limiting and API Usage")
pdf.body_text("Expected API usage is very low:")
pdf.bullet_list([
    "Campaign creation: 1-5 campaigns per week",
    "Ad creation/updates: 5-20 ads per week",
    "Performance reporting: 1-2 report pulls per day",
    "Total estimated API calls: Under 200 per day",
])
pdf.body_text(
    "The tool implements exponential backoff for rate limit errors and respects all API "
    "quotas. No bulk operations or high-frequency polling is planned."
)

# 7. Compliance
pdf.section_title("7. Compliance and Policies")
pdf.body_text("The tool complies with all Google Ads API Terms and Conditions:")
pdf.bullet_list([
    "No user data is collected, stored, or uploaded via the API",
    "No automated bidding strategies beyond standard Google Ads smart bidding",
    "All ad content complies with Google Ads advertising policies",
    "OAuth2 credentials are stored securely and never shared",
    "The developer token will only be used for Fields Estate's own account",
    "API contact email (will@fieldsestate.com.au) will be kept up to date",
    "The tool does not scrape, cache, or redistribute Google Ads data",
])

# 8. Budget Safety
pdf.section_title("8. Budget Safety Controls")
pdf.body_text("To prevent accidental overspend, the tool includes built-in safety controls:")
pdf.bullet_list([
    "Configurable maximum daily budget cap (default: $50 AUD per campaign)",
    "Configurable maximum monthly spend cap across all campaigns",
    "All campaign creations require explicit operator confirmation before submission",
    "No campaigns are created in ENABLED state by default - they start as PAUSED for review",
    "Budget changes above a configurable threshold require manual confirmation",
])

pdf.ln(6)
pdf.set_font("Helvetica", "I", 9)
pdf.cell(0, 5, "Document prepared by Fields Estate, March 2026", align="C")

# Save
output_path = "/home/fields/Fields_Orchestrator/google_ads_api_design_document.pdf"
pdf.output(output_path)
print(f"PDF saved to: {output_path}")
