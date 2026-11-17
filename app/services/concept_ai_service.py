"""AI Concept Engine for Open Nepali Image.
Generates structured Devanagari captions and high-converting English search queries
tailored for low-resource Nepali administrative, legal, academic, and cultural document acquisition.
"""
import random
from typing import Dict, List, Optional, Any

DOCUMENT_LEXICON: Dict[str, Dict[str, Any]] = {
    "citizenship": {
        "title": "नेपाली नागरिकता प्रमाण-पत्र",
        "doc_type": "citizenship",
        "caption": "नेपाल सरकार जिल्ला प्रशासन कार्यालयद्वारा जारी गरिएको नेपाली नागरिकताको प्रमाणपत्र",
        "primary_query": "Nepal citizenship certificate nagarikta document",
        "alt_queries": [
            "Nepali nagarikta certificate format",
            "Nepal citizenship card official sample",
            "Nepal district administration citizenship paper"
        ],
        "tags": ["citizenship", "nagarikta", "moha", "official_id"]
    },
    "lalpurja": {
        "title": "जग्गाधनी दर्ता प्रमाणपूर्जा (लालपुर्जा)",
        "doc_type": "lalpurja",
        "caption": "नेपाल सरकार भूमि व्यवस्था, सहकारी तथा गरिबी निवारण मन्त्रालय अन्तर्गत मालपोत कार्यालयद्वारा जारी जग्गाधनी दर्ता प्रमाणपूर्जा",
        "primary_query": "Nepal land ownership deed lalpurja document",
        "alt_queries": [
            "Nepal malpot lalpurja scanned page",
            "Nepal land revenue certificate deed",
            "Nepal jagga dhani praman purja"
        ],
        "tags": ["lalpurja", "land_deed", "malpot", "property"]
    },
    "gazette": {
        "title": "नेपाल राजपत्र (Nepal Gazette)",
        "doc_type": "gazette",
        "caption": "नेपाल सरकार मुद्रण विभागद्वारा प्रकाशित नेपाल राजपत्रको आधिकारिक सूचना पृष्ठ",
        "primary_query": "Nepal gazette rajpatra official document page",
        "alt_queries": [
            "Nepal rajpatra scanned notice",
            "Nepal government printing press gazette",
            "Nepal law gazette circular"
        ],
        "tags": ["gazette", "rajpatra", "law", "circular"]
    },
    "license": {
        "title": "सवारी चालक अनुमतिपत्र (Smart Driving License)",
        "doc_type": "license",
        "caption": "यातायात व्यवस्था विभागद्वारा जारी गरिएको विद्युतीय सवारी चालक अनुमतिपत्र (स्मार्ट लाइसेन्स)",
        "primary_query": "Nepal smart driving license DOTM card",
        "alt_queries": [
            "Nepal driving permit official format",
            "Nepal transport management license card",
            "Nepal smart license sample"
        ],
        "tags": ["license", "driving_permit", "dotm", "card"]
    },
    "passport": {
        "title": "विद्युतीय राहदानी (e-Passport)",
        "doc_type": "passport",
        "caption": "नेपाल सरकार परराष्ट्र मन्त्रालय राहदानी विभागद्वारा जारी विद्युतीय राहदानीको व्यक्तिगत विवरण पृष्ठ",
        "primary_query": "Nepal passport e-passport bio-page document",
        "alt_queries": [
            "Nepal electronic passport bio data page",
            "Nepal passport sample format official",
            "Department of Passports Nepal document"
        ],
        "tags": ["passport", "epassport", "mofa", "travel_document"]
    },
    "revenue_receipt": {
        "title": "आन्तरिक राजस्व कर दाखिला रसिद",
        "doc_type": "receipt",
        "caption": "नेपाल सरकार आन्तरिक राजस्व विभाग अन्तर्गत करदाता सेवा कार्यालयद्वारा जारी राजस्व दाखिला भौचर तथा रसिद",
        "primary_query": "Nepal internal revenue tax receipt voucher IRD",
        "alt_queries": [
            "Nepal Inland Revenue Department tax bill",
            "Nepal government revenue receipt format",
            "Nepal PAN tax clearance receipt"
        ],
        "tags": ["receipt", "tax", "ird", "revenue"]
    },
    "court_verdict": {
        "title": "अदालतको फैसला तथा आदेश मिसिल",
        "doc_type": "letter",
        "caption": "सर्वोच्च वा उच्च अदालत नेपालद्वारा जारी गरिएको मिसिल, फैसला तथा न्यायिक आदेशको प्रतिलिपि",
        "primary_query": "Nepal Supreme Court verdict order document",
        "alt_queries": [
            "Nepal court decision scanned page",
            "High Court Nepal official ruling paper",
            "Nepal judicial misil order format"
        ],
        "tags": ["court", "verdict", "judiciary", "legal"]
    },
    "academic_marksheet": {
        "title": "एस.ई.ई. / त्रि.वि. लब्धाङ्क पत्र (Transcript / Marksheet)",
        "doc_type": "certificate",
        "caption": "राष्ट्रिय परीक्षा बोर्ड वा त्रिभुवन विश्वविद्यालयद्वारा जारी गरिएको आधिकारिक शैक्षिक लब्धाङ्क पत्र तथा ट्रान्सक्रिप्ट",
        "primary_query": "Tribhuvan University transcript marksheet certificate Nepal",
        "alt_queries": [
            "Nepal NEB SEE transcript certificate",
            "Nepal board academic marksheet format",
            "TU examination controller office certificate"
        ],
        "tags": ["certificate", "transcript", "academic", "university"]
    },
    "vital_registration": {
        "title": "जन्म / विवाह दर्ता प्रमाण-पत्र",
        "doc_type": "certificate",
        "caption": "स्थानीय वडा कार्यालय तथा पञ्जिकाधिकारीद्वारा जारी व्यक्तिगत घटना (जन्म, विवाह वा मृत्यु) दर्ता प्रमाणपत्र",
        "primary_query": "Nepal birth registration certificate ward office",
        "alt_queries": [
            "Nepal marriage registration certificate official",
            "Nepal vital event registration document",
            "Nepal ward office panjika certificate"
        ],
        "tags": ["vital_registration", "birth_certificate", "ward", "certificate"]
    },
    "company_registration": {
        "title": "कम्पनी दर्ता प्रमाण-पत्र",
        "doc_type": "certificate",
        "caption": "नेपाल सरकार उद्योग, वाणिज्य तथा आपूर्ति मन्त्रालय कम्पनी रजिष्ट्रारको कार्यालयद्वारा जारी कम्पनी दर्ता प्रमाणपत्र",
        "primary_query": "Office of Company Registrar Nepal registration certificate",
        "alt_queries": [
            "Nepal company incorporation certificate format",
            "OCR Nepal business registration deed",
            "Nepal commercial certificate sample"
        ],
        "tags": ["company", "registration", "ocr_nepal", "business"]
    },
    "postal_stamp": {
        "title": "नेपाल हुलाक टिकट तथा फिलाटेलिक कभर",
        "doc_type": "photo",
        "caption": "नेपाल सरकार हुलाक सेवा विभाग फिलाटेलिक तथा टिकट व्यवस्थापन कार्यालयद्वारा प्रकाशित स्मारक हुलाक टिकट",
        "primary_query": "Nepal postage stamp first day cover philatelic",
        "alt_queries": [
            "Nepal postal department commemorative stamp",
            "Vintage Nepal stamps document philately",
            "Nepal postal stamp scanned envelope"
        ],
        "tags": ["postal", "stamp", "philatelic", "heritage"]
    },
    "voter_id": {
        "title": "निर्वाचन आयोग मतदाता परिचयपत्र",
        "doc_type": "identity_card",
        "caption": "निर्वाचन आयोग नेपालद्वारा जारी फोटो सहितको मतदाता परिचयपत्र",
        "primary_query": "Nepal Election Commission voter ID card sample",
        "alt_queries": [
            "Nepal voter identification card photo",
            "Election Commission of Nepal matadata parichayapatra",
            "Nepal voter identity card format"
        ],
        "tags": ["voter_id", "election", "identity_card", "official"]
    },
}


class ConceptAiService:
    """Service generating targeted Devanagari captions and English search queries."""

    def suggest_concept(self, topic: Optional[str] = None) -> Dict[str, Any]:
        """
        Suggest caption, search terms, and metadata given a seed topic or returning a curated one.
        """
        if not topic or not topic.strip():
            # Pick a random high-value category from lexicon
            key = random.choice(list(DOCUMENT_LEXICON.keys()))
            item = DOCUMENT_LEXICON[key]
            return {
                "topic": item["title"],
                "document_type": item["doc_type"],
                "caption_nepali": item["caption"],
                "search_query_en": item["primary_query"],
                "alternative_queries": item["alt_queries"],
                "tags": item["tags"],
            }

        t = topic.strip()
        # Check if topic matches any known category
        for key, item in DOCUMENT_LEXICON.items():
            if key in t.lower() or item["title"] in t or any(w in t for w in ["नागरिकता", "लालपुर्जा", "राजपत्र", "लाइसेन्स", "राहदानी", "कर", "अदालत", "प्रमाणपत्र"]):
                if any(w in t for w in ["नागरिकता"]) and key == "citizenship":
                    return self._build_from_item(item, t)
                if any(w in t for w in ["लालपुर्जा", "जग्गाधनी"]) and key == "lalpurja":
                    return self._build_from_item(item, t)
                if any(w in t for w in ["राजपत्र"]) and key == "gazette":
                    return self._build_from_item(item, t)
                if any(w in t for w in ["लाइसेन्स", "सवारी चालक"]) and key == "license":
                    return self._build_from_item(item, t)
                if any(w in t for w in ["राहदानी", "पासपोर्ट"]) and key == "passport":
                    return self._build_from_item(item, t)
                if any(w in t for w in ["अदालत", "फैसला", "आदेश"]) and key == "court_verdict":
                    return self._build_from_item(item, t)
                if any(w in t for w in ["कर", "रसिद", "राजस्व"]) and key == "revenue_receipt":
                    return self._build_from_item(item, t)

        # Generative heuristic synthesis for custom user topic
        clean_name = t.replace("Nepal", "").replace("नेपाल", "").strip()
        return {
            "topic": t,
            "document_type": "other",
            "caption_nepali": f"नेपाल सरकार वा आधिकारिक निकायद्वारा जारी गरिएको दस्तावेज: {t} — अभिलेख तथा विवरण पृष्ठ",
            "search_query_en": f"Nepal {clean_name} official document scanned",
            "alternative_queries": [
                f"Nepal {clean_name} certificate notice",
                f"Government of Nepal {clean_name} paper",
                f"Nepal {clean_name} archive file"
            ],
            "tags": ["nepal_document", clean_name.lower().replace(" ", "_"), "official"]
        }

    def generate_batch_concepts(self, count: int = 5) -> List[Dict[str, Any]]:
        """Generate batch of diverse, high-value Nepali document concepts."""
        keys = list(DOCUMENT_LEXICON.keys())
        random.shuffle(keys)
        selected_keys = keys[:min(count, len(keys))]

        results = []
        for k in selected_keys:
            item = DOCUMENT_LEXICON[k]
            results.append({
                "topic": item["title"],
                "document_type": item["doc_type"],
                "caption_nepali": item["caption"],
                "search_query_en": item["primary_query"],
                "alternative_queries": item["alt_queries"],
                "tags": item["tags"],
            })
        return results

    def _build_from_item(self, item: dict, user_topic: str) -> dict:
        return {
            "topic": item["title"] if len(user_topic) < 4 else user_topic,
            "document_type": item["doc_type"],
            "caption_nepali": item["caption"],
            "search_query_en": item["primary_query"],
            "alternative_queries": item["alt_queries"],
            "tags": item["tags"],
        }


concept_ai_service = ConceptAiService()
