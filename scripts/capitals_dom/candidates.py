"""Candidate suburb lists for the Gold-Coast-vs-capitals days-on-market comparison.

These are WIDE candidate pools — middle-ring suburbs likely to fall in the
Gold-Coast-like price band (house median ~$1.2-1.7M, unit median ~$0.78-1.15M)
with real mixed house+unit turnover. `screen_panel.py` calls PropRadar per
candidate and keeps only those that actually fall in-band with enough sales
volume; do NOT treat this list as the final panel.

Each entry: (suburb, postcode, state). Slug is built as f"{suburb-hyphenated}-{postcode}".
"""

# Greater Sydney — mid-market only. Sydney's whole-city house median (~$1.49M)
# already sits at Robina's level, so the GC-matching band is the OUTER-MIDDLE ring
# (Sutherland Shire, St George, Ryde/Northern, Inner-West south, Northern Beaches
# fringe), NOT the $3M eastern suburbs / lower north shore.
SYDNEY = [
    # Sutherland Shire (coastal-ish, family — closest in character to the GC)
    ("Gymea", "2227"), ("Miranda", "2228"), ("Caringbah", "2229"),
    ("Sutherland", "2232"), ("Kirrawee", "2232"), ("Engadine", "2233"),
    ("Jannali", "2226"), ("Como", "2226"), ("Woolooware", "2230"),
    ("Cronulla", "2230"), ("Gymea Bay", "2227"), ("Sylvania", "2224"),
    # St George
    ("Penshurst", "2222"), ("Mortdale", "2223"), ("Oatley", "2223"),
    ("Hurstville", "2220"), ("Beverly Hills", "2209"), ("Kogarah", "2217"),
    ("Carlton", "2218"), ("Allawah", "2218"), ("Ramsgate", "2217"),
    # Inner-West south / Canterbury
    ("Earlwood", "2206"), ("Dulwich Hill", "2203"), ("Ashfield", "2131"),
    ("Croydon", "2132"), ("Campsie", "2194"), ("Canterbury", "2193"),
    # Ryde / Northern
    ("Ryde", "2112"), ("West Ryde", "2114"), ("Meadowbank", "2114"),
    ("Eastwood", "2122"), ("Carlingford", "2118"), ("Gladesville", "2111"),
    ("Dundas", "2117"), ("Denistone", "2114"),
    # Northern Beaches fringe (coastal lifestyle)
    ("Dee Why", "2099"), ("Narraweena", "2099"), ("Cromer", "2099"),
    ("Manly Vale", "2093"), ("Brookvale", "2100"),
    # Canada Bay
    ("Concord", "2137"), ("Five Dock", "2046"), ("Rhodes", "2138"),
    # Hills
    ("Baulkham Hills", "2153"), ("Kellyville", "2155"), ("Winston Hills", "2153"),
    # Mid-market house belt (Sydney's whole-city median is ~$1.49M, so the GC-price
    # band lands in the Canterbury-Bankstown / outer St George / western middle ring,
    # NOT the affluent Shire above — added after a first screen left only 1 house suburb).
    ("Revesby", "2212"), ("Padstow", "2211"), ("Panania", "2213"),
    ("East Hills", "2213"), ("Riverwood", "2210"), ("Peakhurst", "2210"),
    ("Kingsgrove", "2208"), ("Bexley", "2207"), ("Bexley North", "2207"),
    ("Arncliffe", "2205"), ("Rockdale", "2216"), ("Sans Souci", "2219"),
    ("Narwee", "2209"), ("Bankstown", "2200"), ("Yagoona", "2199"),
    ("Greenacre", "2190"), ("Chester Hill", "2162"), ("Sefton", "2162"),
    ("Guildford", "2161"), ("Merrylands", "2160"), ("Granville", "2142"),
    ("Northmead", "2152"), ("Wentworthville", "2145"), ("Toongabbie", "2146"),
    ("Seven Hills", "2147"), ("Kings Langley", "2147"), ("Lakemba", "2195"),
    ("Belmore", "2192"), ("Punchbowl", "2196"), ("Roselands", "2196"),
]

# Greater Melbourne — GC-matching suburbs sit ABOVE the city median ($850k):
# bayside SE, inner-east, and the eastern middle ring.
MELBOURNE = [
    # Bayside / SE
    ("Bentleigh", "3204"), ("Bentleigh East", "3165"), ("Ormond", "3204"),
    ("McKinnon", "3204"), ("Hampton East", "3188"), ("Highett", "3190"),
    ("Cheltenham", "3192"), ("Mentone", "3194"), ("Parkdale", "3195"),
    # Inner east
    ("Ashburton", "3147"), ("Surrey Hills", "3127"), ("Mont Albert", "3127"),
    ("Box Hill", "3128"), ("Box Hill South", "3128"), ("Blackburn", "3130"),
    ("Blackburn South", "3130"), ("Mitcham", "3132"), ("Nunawading", "3131"),
    # SE middle
    ("Mount Waverley", "3149"), ("Glen Waverley", "3150"), ("Wheelers Hill", "3150"),
    ("Oakleigh", "3166"), ("Oakleigh East", "3166"), ("Huntingdale", "3166"),
    # Manningham
    ("Doncaster", "3108"), ("Doncaster East", "3109"), ("Templestowe Lower", "3107"),
    ("Bulleen", "3105"),
    # Inner north
    ("Essendon", "3040"), ("Moonee Ponds", "3039"), ("Strathmore", "3041"),
    ("Pascoe Vale", "3044"), ("Coburg", "3058"), ("Northcote", "3070"),
    ("Thornbury", "3071"), ("Preston", "3072"), ("Brunswick", "3056"),
    # West (bay-adjacent, gentrifying)
    ("Yarraville", "3013"), ("Newport", "3015"), ("Williamstown", "3016"),
    ("Seddon", "3011"),
]

# Greater Brisbane — inner-middle ring (same metro as the GC; a natural anchor).
BRISBANE = [
    # Inner north
    ("Ashgrove", "4060"), ("The Gap", "4061"), ("Wilston", "4051"),
    ("Windsor", "4030"), ("Grange", "4051"), ("Newmarket", "4051"),
    ("Alderley", "4051"), ("Wavell Heights", "4012"), ("Kedron", "4031"),
    ("Gordon Park", "4031"), ("Stafford", "4053"), ("Everton Park", "4053"),
    ("Nundah", "4012"), ("Chermside", "4032"),
    # Inner east
    ("Camp Hill", "4152"), ("Carina", "4152"), ("Carina Heights", "4152"),
    ("Coorparoo", "4151"), ("Holland Park", "4121"), ("Holland Park West", "4121"),
    ("Cannon Hill", "4170"), ("Morningside", "4170"), ("Balmoral", "4171"),
    ("Norman Park", "4170"), ("Seven Hills", "4170"),
    # Inner west
    ("Kenmore", "4069"), ("Chapel Hill", "4069"), ("Indooroopilly", "4068"),
    ("Toowong", "4066"), ("Taringa", "4068"), ("Sherwood", "4075"),
    ("Graceville", "4075"), ("Corinda", "4075"),
    # Inner south
    ("Tarragindi", "4121"), ("Yeronga", "4104"), ("Fairfield", "4103"),
    ("Annerley", "4103"), ("Mount Gravatt", "4122"), ("Mount Gravatt East", "4122"),
    ("Wishart", "4122"), ("Mansfield", "4122"),
]

CITIES = {"NSW": SYDNEY, "VIC": MELBOURNE, "QLD": BRISBANE}
CITY_LABEL = {"NSW": "Greater Sydney", "VIC": "Greater Melbourne", "QLD": "Greater Brisbane"}


def slug_for(suburb: str, postcode: str) -> str:
    return suburb.lower().replace(" ", "-") + "-" + postcode


def all_candidates():
    """Yield {suburb, slug, state, postcode, city} for every candidate."""
    for state, subs in CITIES.items():
        for suburb, pc in subs:
            yield {"suburb": suburb.lower(), "slug": slug_for(suburb, pc),
                   "state": state, "postcode": pc, "city": state}
