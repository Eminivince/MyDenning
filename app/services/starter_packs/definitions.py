"""Jurisdiction starter pack definitions.

Each pack defines key authorities to search for and import via the legal source adapters.
These are the foundational statutes, landmark cases, and regulations that any legal
professional working in that jurisdiction would need in their knowledge base.
"""

STARTER_PACKS: dict[str, dict] = {
    "NG": {
        "name": "Nigeria Starter Pack",
        "jurisdiction": "NG",
        "jurisdiction_name": "Nigeria",
        "description": "Key Nigerian statutes, landmark Supreme Court decisions, and foundational regulations.",
        "sources": [
            # --- Key Statutes (via Laws.Africa) ---
            {"query": "Companies and Allied Matters Act 2020", "type": "statute", "description": "CAMA 2020 — primary company law"},
            {"query": "Nigerian Labour Act", "type": "statute", "description": "Labour Act — employment law"},
            {"query": "Nigeria Data Protection Act 2023", "type": "statute", "description": "NDP Act 2023 — data protection"},
            {"query": "Investment and Securities Act", "type": "statute", "description": "ISA — capital markets regulation"},
            {"query": "Banks and Other Financial Institutions Act", "type": "statute", "description": "BOFIA — banking regulation"},
            {"query": "Arbitration and Mediation Act 2023", "type": "statute", "description": "Arbitration law reform"},
            {"query": "Evidence Act 2011", "type": "statute", "description": "Law of evidence"},
            {"query": "Land Use Act", "type": "statute", "description": "Land tenure and use"},
            {"query": "Constitution of the Federal Republic of Nigeria", "type": "statute", "description": "1999 Constitution (as amended)"},
            {"query": "Nigerian Minerals and Mining Act", "type": "statute", "description": "Mining and solid minerals regulation"},
            # --- Landmark Cases (via NigeriaLII) ---
            {"query": "Ariori v Elemo", "type": "case_law", "description": "Supreme Court — land law"},
            {"query": "Tukur v Government of Gongola State", "type": "case_law", "description": "Supreme Court — constitutional law"},
            {"query": "Attorney General of Ondo State v Attorney General of the Federation", "type": "case_law", "description": "Federalism and legislative competence"},
            {"query": "Madukolu v Nkemdilim", "type": "case_law", "description": "Supreme Court — jurisdiction requirements"},
            {"query": "Adetona v Igele General Enterprises", "type": "case_law", "description": "Supreme Court — contract law"},
        ],
    },
    "GB": {
        "name": "United Kingdom Starter Pack",
        "jurisdiction": "GB",
        "jurisdiction_name": "United Kingdom",
        "description": "Key UK statutes and landmark Supreme Court / House of Lords decisions.",
        "sources": [
            # --- Key Statutes (via legislation.gov.uk) ---
            {"query": "Companies Act 2006", "type": "statute", "description": "UK company law"},
            {"query": "Employment Rights Act 1996", "type": "statute", "description": "Employment rights"},
            {"query": "Data Protection Act 2018", "type": "statute", "description": "UK GDPR implementation"},
            {"query": "Arbitration Act 1996", "type": "statute", "description": "Arbitration law"},
            {"query": "Sale of Goods Act 1979", "type": "statute", "description": "Commercial law"},
            {"query": "Limitation Act 1980", "type": "statute", "description": "Limitation periods"},
            {"query": "Bribery Act 2010", "type": "statute", "description": "Anti-corruption"},
            {"query": "Financial Services and Markets Act 2000", "type": "statute", "description": "Financial regulation"},
            {"query": "Insolvency Act 1986", "type": "statute", "description": "Insolvency and restructuring"},
            # --- Landmark Cases (via UK Find Case Law) ---
            {"query": "Donoghue v Stevenson", "type": "case_law", "description": "Duty of care — tort law foundation"},
            {"query": "Salomon v Salomon", "type": "case_law", "description": "Corporate personality / veil of incorporation"},
            {"query": "Caparo Industries v Dickman", "type": "case_law", "description": "Three-part test for duty of care"},
            {"query": "Arnold v Britton", "type": "case_law", "description": "Contract interpretation principles"},
        ],
    },
    "US": {
        "name": "United States Starter Pack",
        "jurisdiction": "US",
        "jurisdiction_name": "United States",
        "description": "Key federal regulations and landmark Supreme Court decisions.",
        "sources": [
            # --- Key Regulations (via eCFR) ---
            {"query": "Securities Exchange Act Rule 10b-5", "type": "regulation", "description": "Securities fraud"},
            {"query": "HIPAA Privacy Rule", "type": "regulation", "description": "Health data privacy"},
            {"query": "FCPA Foreign Corrupt Practices", "type": "regulation", "description": "Anti-bribery"},
            # --- Landmark Cases (via CourtListener) ---
            {"query": "Chevron v Natural Resources Defense Council", "type": "case_law", "description": "Administrative law — agency deference"},
            {"query": "International Shoe v Washington", "type": "case_law", "description": "Personal jurisdiction — minimum contacts"},
            {"query": "Erie Railroad v Tompkins", "type": "case_law", "description": "Federal courts apply state substantive law"},
            {"query": "Ashcroft v Iqbal", "type": "case_law", "description": "Pleading standards — plausibility"},
            {"query": "Alice Corp v CLS Bank", "type": "case_law", "description": "Patent eligibility — abstract ideas"},
            {"query": "Carpenter v United States insider trading", "type": "case_law", "description": "Insider trading — misappropriation theory"},
        ],
    },
    "EU": {
        "name": "European Union Starter Pack",
        "jurisdiction": "EU",
        "jurisdiction_name": "European Union",
        "description": "Key EU regulations, directives, and CJEU decisions.",
        "sources": [
            {"query": "General Data Protection Regulation 2016/679", "type": "regulation", "description": "GDPR"},
            {"query": "Digital Services Act", "type": "regulation", "description": "DSA — platform regulation"},
            {"query": "Digital Markets Act", "type": "regulation", "description": "DMA — gatekeeper regulation"},
            {"query": "AI Act artificial intelligence", "type": "regulation", "description": "EU AI Act"},
            {"query": "MiCA Markets in Crypto Assets Regulation", "type": "regulation", "description": "Crypto asset regulation"},
            {"query": "NIS2 Directive cybersecurity", "type": "regulation", "description": "Network and information security"},
        ],
    },
    "KE": {
        "name": "Kenya Starter Pack",
        "jurisdiction": "KE",
        "jurisdiction_name": "Kenya",
        "description": "Key Kenyan statutes and landmark Court of Appeal / Supreme Court decisions.",
        "sources": [
            {"query": "Constitution of Kenya 2010", "type": "statute", "description": "2010 Constitution"},
            {"query": "Companies Act Kenya 2015", "type": "statute", "description": "Company law"},
            {"query": "Data Protection Act Kenya 2019", "type": "statute", "description": "Data protection"},
            {"query": "Employment Act Kenya 2007", "type": "statute", "description": "Employment law"},
            {"query": "Nairobi Centre for International Arbitration Act", "type": "statute", "description": "Arbitration"},
        ],
    },
    "ZA": {
        "name": "South Africa Starter Pack",
        "jurisdiction": "ZA",
        "jurisdiction_name": "South Africa",
        "description": "Key South African statutes including POPIA, Companies Act, and constitutional law.",
        "sources": [
            {"query": "Protection of Personal Information Act POPIA", "type": "statute", "description": "POPIA — data protection"},
            {"query": "Companies Act South Africa 2008", "type": "statute", "description": "Company law"},
            {"query": "Constitution of South Africa 1996", "type": "statute", "description": "Constitutional framework"},
            {"query": "Labour Relations Act South Africa", "type": "statute", "description": "Labour law"},
            {"query": "Consumer Protection Act South Africa", "type": "statute", "description": "Consumer protection"},
        ],
    },
}
