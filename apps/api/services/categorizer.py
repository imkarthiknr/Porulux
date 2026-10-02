from __future__ import annotations

CATEGORIES = [
    "Salary", "Rent", "Food", "Travel", "Investments", "Utilities",
    "EMI", "Shopping", "Health", "Transfer", "Other",
]

# First match wins, so more specific categories come first.
_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Salary", ("salary", "sal cr", "payroll")),
    ("EMI", ("emi", "loan repay", "ach d- ", "nach")),
    ("Investments", (
        "zerodha", "groww", "upstox", "angel one", "icici direct", "kuvera", "coin by",
        "mutual fund", "sip", "nps", "ppf", "bse star", "nse clearing", "indian clearing",
        "ccil", "smallcase",
    )),
    ("Rent", ("rent", "nobroker", "housing.com")),
    ("Food", (
        "swiggy", "zomato", "restaurant", "cafe", "dominos", "mcdonald", "kfc", "starbucks",
        "bigbasket", "blinkit", "zepto", "instamart", "dmart", "grocer", "supermarket",
    )),
    ("Travel", (
        "uber", "ola ", "olacabs", "rapido", "irctc", "makemytrip", "redbus", "indigo",
        "air india", "vistara", "goibibo", "fastag", "petrol", "fuel", "hpcl", "bpcl", "iocl",
    )),
    ("Utilities", (
        "electricity", "bescom", "tneb", "bses", "water bill", "gas bill", "airtel", "jio",
        "vodafone", "vi prepaid", "act fibernet", "broadband", "recharge", "dth", "tata power",
    )),
    ("Health", ("pharmacy", "apollo", "hospital", "clinic", "medplus", "1mg", "pharmeasy", "practo")),
    ("Shopping", ("amazon", "flipkart", "myntra", "ajio", "nykaa", "meesho", "croma", "netflix", "spotify", "prime")),
    ("Transfer", ("upi", "neft", "imps", "rtgs", "self transfer", "atm")),
]


def categorize(description: str, amount: float) -> str:
    text = description.lower()
    for category, keywords in _RULES:
        if any(k in text for k in keywords):
            # Salary and similar only make sense as credits; EMI/Rent only as debits.
            if category == "Salary" and amount < 0:
                continue
            if category in ("EMI", "Rent") and amount > 0:
                continue
            return category
    return "Other"
