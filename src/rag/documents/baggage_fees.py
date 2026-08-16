"""Checked-baggage policy documents for the RAG knowledge base.

Content is sourced from third-party baggage-fee aggregators (not scraped
directly from the airlines' own fare pages), since airline fee pages change
frequently and are not reliably machine-readable. Each document cites its
source so the figures can be verified or refreshed. Treat these as
representative ranges for a portfolio/demo project, not live pricing —
real fees vary by route, season, and booking channel.

Airlines covered: Ryanair, EasyJet, Wizz Air (three major European low-cost
carriers), matching the "Low-Cost Airline Baggage Policies" category in
README.md's RAG strategy.
"""

from typing import TypedDict


class BaggageDocument(TypedDict):
    airline: str
    text: str
    source_url: str


BAGGAGE_DOCUMENTS: list[BaggageDocument] = [
    {
        "airline": "Ryanair",
        "text": (
            "Ryanair checked baggage: up to 3 bags per person, each up to 20kg "
            "(max single bag 32kg, max dimensions 80x120x120cm). A 20kg checked "
            "bag booked online costs roughly EUR/GBP 19.99 to 59.99 per leg, "
            "depending on route and date; the same bag added at airport bag-drop "
            "costs roughly EUR 35-75. A 10kg checked bag online costs roughly "
            "EUR 10-45 per leg. Excess baggage beyond the pre-booked allowance is "
            "charged at EUR/GBP 13 per kilogram. Booking baggage online in advance "
            "is significantly cheaper than adding it at the airport."
        ),
        "source_url": "https://www.moneyguideireland.com/ryanair-increased-baggage-allowance-of-20kg.html",
    },
    {
        "airline": "EasyJet",
        "text": (
            "EasyJet checked (hold) baggage: standard allowance is 23kg per bag, "
            "with a smaller 15kg option purchasable online from GBP 6.99. Up to 3 "
            "bags may be checked, each no more than 275cm total (length + width + "
            "depth). A 23kg checked bag costs roughly GBP 9.49 to 50.00 one way "
            "online, or up to GBP 50 if paid at the airport. Checked baggage is "
            "not included in any EasyJet fare and must be purchased separately. "
            "Excess weight beyond the pre-paid allowance is charged at GBP 12 per "
            "kilogram; bags checked at the airport without pre-purchase can incur "
            "an airport bag fee of up to GBP 55."
        ),
        "source_url": "https://www.sendmybag.com/airlines/easyjet-baggage-allowance/",
    },
    {
        "airline": "Wizz Air",
        "text": (
            "Wizz Air checked baggage: purchasable in 10kg, 20kg, 26kg, or 32kg "
            "tiers, up to 6 pieces per passenger (10kg tier limited to one per "
            "passenger). Prices range roughly EUR 15-120 per bag per flight "
            "depending on season, booking channel (online cheapest, call centre "
            "pricier, airport most expensive), and weight tier -- a 20kg "
            "allowance costs roughly EUR 20-164 and a 32kg allowance roughly "
            "EUR 32-198 depending on season and channel. Checked baggage is not "
            "included in Wizz Air's basic fare unless the passenger holds "
            "Priority or Plus status. Excess weight beyond the purchased "
            "allowance is charged at EUR 13 per kilogram per flight."
        ),
        "source_url": "https://wise.com/us/blog/lp-wizz-air-baggage-policy",
    },
]
