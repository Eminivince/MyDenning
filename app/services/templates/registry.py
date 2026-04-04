"""Pre-built playbook templates for compliance frameworks and common contract types.

Each template is a dict with the same shape as a PlaybookCreate request,
ready to be instantiated into any organization's playbook library.
"""

from app.services.templates.gdpr import GDPR_DPA_PLAYBOOK
from app.services.templates.ndpr import NDPR_PLAYBOOK
from app.services.templates.ccpa import CCPA_PLAYBOOK
from app.services.templates.nda import NDA_PLAYBOOK
from app.services.templates.saas import SAAS_AGREEMENT_PLAYBOOK
from app.services.templates.employment import EMPLOYMENT_AGREEMENT_PLAYBOOK

# Master registry of all templates
PLAYBOOK_TEMPLATES: dict[str, dict] = {
    "gdpr_dpa": GDPR_DPA_PLAYBOOK,
    "ndpr_compliance": NDPR_PLAYBOOK,
    "ccpa_compliance": CCPA_PLAYBOOK,
    "nda_standard": NDA_PLAYBOOK,
    "saas_agreement": SAAS_AGREEMENT_PLAYBOOK,
    "employment_agreement": EMPLOYMENT_AGREEMENT_PLAYBOOK,
}
