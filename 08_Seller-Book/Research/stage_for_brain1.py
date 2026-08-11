#!/usr/bin/env python3
"""
Stage the listing-price research corpus for Brain 1 ingestion.

Prepends a CLAIM STATUS header to each paper's extracted text so that the
effect size, the verification status, and — critically — what the paper does
NOT prove travel in the same retrieval chunk as the finding itself.

Rationale: chunk-and-embed retrieval returns claims, not the refutations that
live in other documents. Without this, a query like "how much do bidding wars
add?" returns Han & Strange's 17.89% premium with no indication that the same
authors call the underprice->war->premium chain "folklore".

Output: sources/brain1_staged/  (upload this to the Drive Research root)
Papers only. Analysis documents and Fields measurements route to Brain 3.
"""
import hashlib
import shutil
from pathlib import Path

SRC = Path(__file__).parent / "sources" / "papers"
OUT = Path(__file__).parent / "sources" / "brain1_staged"

# Files that are byte-identical or superseded duplicates of another entry.
SKIP = {"hs_asking.txt", "wc.txt", "frino.txt"}

H = {}

H["bk96.txt"] = dict(
    cite="Bulow, J. & Klemperer, P. (1996). 'Auctions Versus Negotiations.' American Economic Review 86(1):180-194.",
    sample="Theoretical. No empirical sample.",
    finding="An absolute English auction with N+1 bidders is more profitable in expectation than ANY negotiation with N bidders. Worked example (seller value 0, buyer values U[0,1]): one bidder plus a perfectly optimal take-it-or-leave-it price yields expected revenue 0.25; two bidders in an open auction with no reserve yields 0.333. One extra serious bidder is worth +33% against perfect monopoly bargaining power. Authors: 'No amount of bargaining power is as valuable to the seller as attracting one extra bidder.'",
    status="VERIFIED to full text (JSTOR). Theorem 1 p.187, Corollary p.189, worked example pp.182-183.",
    notproof="This is a theorem about asset sales under stated conditions, NOT a housing measurement. The conditions are load-bearing and routinely dropped: every extra bidder must be 'serious' (value the asset at least as much as the seller does); values and strategies must be symmetric; bidders risk-neutral; no reserve in the (N+1) auction; and the negotiation benchmark assumes the seller has FULL bargaining power and commitment, which no real seller has. Cite as the principle, never as a magnitude. Measured housing magnitudes are far smaller - see stockholm.txt (+4% for the second bidder) and merlo.txt (+0.64% per bidder).",
)

H["merlo.txt"] = dict(
    cite="Merlo, A. & Ortalo-Magne, F. (2004). 'Bargaining over residential real estate: evidence from England.' Journal of Urban Economics 56(2):192-216.",
    sample="n=780 complete transaction histories, Halifax Estate Agencies, three Greater London branches plus one South Yorkshire, June 1995 - April 1998. Every listing-price change and every offer recorded. Viewings sub-sample n=199.",
    finding="THREE findings, all central. (1) All 30 above-list sales out of 780 were de facto auctions: 'such de facto auctions account for ALL instances in the data where the sale price is above the listing price.' In a private-treaty market, selling above asking happens ONLY when two or more buyers bid simultaneously - about 3.8% of sales. (2) Listing price coefficient on weekly viewing arrivals -0.395 (SE 0.154), significant at 5%: a lower listing price raises the arrival rate of viewings, which raises the arrival rate of offers. (3) THE BRACKET TEST: a price cut that moves a property into a LOWER GBP5,000 segment significantly raises the probability of a first offer; a cut that leaves it in the SAME segment has no effect at all. Robust to controlling for the size of the reduction, which is itself insignificant. About half of all initial listing prices sat within GBP50 of a segment boundary. Additional buyer making an offer adds GBP430 (SE 153) on a mean GBP66,964 = +0.64%.",
    status="VERIFIED to full text (CESifo WP 778).",
    notproof="Does NOT show that underpricing raises the sale price - it shows underpricing raises TRAFFIC. The same paper finds NO relation between viewings and the probability of a sale agreement. Traffic predicts offers, not completions. Also: viewing arrival decays monotonically from listing with no discrete drop after weeks 1-2, so this supports 'interest is a flow, not a stock' but does NOT support any specific 'X% of buyers arrive in week one' claim.",
)

H["Asking_Price_8-14-2014.txt"] = dict(
    cite="Han, L. & Strange, W.C. (2016). 'What is the role of the asking price for a house?' Journal of Urban Economics 93:115-130. (Working paper version, 14 Aug 2014. Published version: hs_askingprice.txt)",
    sample="3,193 valid homebuyer interviews (1,722 mail + 1,467 phone, 19.2% response) in a large North American metro, matched to 89,891 MLS transactions, 2006-2009. Over one third of surveyed buyers reported facing competing bidders.",
    finding="The only direct measurement anywhere of asking price -> number of bidders. Elasticity -0.22 with district/period/attribute controls (10% lower ask = +2.2% bidders); -0.40 with tax-assessment controls proxying unobserved quality (+4%); -0.24 with a crisis interaction of -0.16 (+2.4% normal times, +4% in busts). Atypicality interaction -0.018: +7.8% at the 10th percentile of atypicality, +69% at the 90th.",
    status="VERIFIED to full working-paper text.",
    notproof="CRITICAL: the RAW relationship is POSITIVE. Columns 1-3, without district dummies, give +0.08, +0.09, +0.14 - higher asking price, MORE bidders - because expensive suburbs have both higher prices and more buyers. The sign only flips negative once location is controlled. Anyone can run the naive regression and get the opposite answer. The authors also state the mechanism has a bound: 'A lower asking price is shown to encourage more potential buyers to visit, BUT ONLY UP TO A POINT. Past this bound, a lower asking price leads to more bidding wars, and buyer recognition of this means that more cannot be encouraged to search.' Note also a sign typo in the working-paper prose on p.3 that contradicts its own tables; the tables are correct.",
)

H["hs_askingprice.txt"] = dict(
    cite="Han, L. & Strange, W.C. (2016). 'What is the role of the asking price for a house?' Journal of Urban Economics 93:115-130. (Published version; working paper is Asking_Price_8-14-2014.txt)",
    sample="As above: 3,193 buyer interviews matched to 89,891 MLS transactions, 2006-2009.",
    finding="See Asking_Price_8-14-2014.txt. Asking-price elasticity of bidder count -0.22 to -0.40.",
    status="VERIFIED.",
    notproof="Same caveat: the raw relationship is positive before location controls. See Asking_Price_8-14-2014.txt.",
)

H["BiddingWar.txt"] = dict(
    cite="Han, L. & Strange, W.C. (2014). 'Bidding Wars for Houses.' Real Estate Economics 42(1):1-32.",
    sample="92,700 NAR micro survey responses aggregated to 334 US metropolitan areas, 15 surveys 1987-2010. Response rates never exceed 19%.",
    finding="Bidding-war incidence rose from ~3.5% in 1986 to 12.46% (2003) - 15.52% (2005), then 13.78% in 2003-06 vs 8.70% in 2007-10. Metro peaks: Washington DC ~29.1%, LA ~26%. Bidding-war premium over list price: 10.01% in the 2003-06 boom and 17.89% in the 2007-10 bust. Time on market for bidding-war sales 5.84 weeks (boom) / 9.46 (bust) vs 11.84 / 16.20 for below-list sales.",
    status="VERIFIED to full working-paper text.",
    notproof="*** THE 17.89% IS THE MOST DANGEROUS NUMBER IN THIS CORPUS. *** It is a premium over LIST PRICE, not over value, and the authors' own explanation is that it was HIGHER in the bust precisely because SELLERS CHOSE LOWER LIST PRICES: 'The bust is identified by a decrease in sales price. That bidding wars showed a higher premium during the bust must therefore require that sellers have chosen lower list prices.' It measures how low the list price was set, not how much competition added. This paper estimates NO causal price effect and does NOT test whether low list prices cause bidding wars. The same authors call the underprice->bidding-war->high-price idea 'FOLKLORE' (Handbook 2015, p.33 - see hs_handbook.txt). Three studies that DID test it found underpricing lowers the final price: see stockholm.txt, kopsch.txt, and Hammervold et al. (2025). Never quote 10.01% or 17.89% as the value of competition.",
)

H["hs_handbook.txt"] = dict(
    cite="Han, L. & Strange, W.C. (2015). 'The Microstructure of Housing Markets: Search, Bargaining, and Brokerage.' Handbook of Regional and Urban Economics Vol 5B, ch.13, pp.813-886.",
    sample="Survey article. No original sample.",
    finding="The standard survey of the field. Key statements: 'a lower asking price increases the number of bidders on a house (a subset of the number of visitors)'; 'asking price has a stronger negative relationship with search activity in a bust than in a boom'; and on agency, 'a seller does not typically decide between auction and sequential search. The decision is made by the market.' Reports Genesove & Han (2012b): doubling the number of bidders increases the sales price by 2.4%; spread of bidders' valuations for the same house is 4-5% of home value.",
    status="VERIFIED to full text.",
    notproof="The authors describe the underprice-to-bidding-war strategy as 'folklore': 'popular discussions of bidding wars, with folklore suggesting that a low listing price to bring people to the table can result in a high sales price as bidders throw caution to the wind.' They also flag the auction-vs-private-treaty literature as producing 'DISPARATE' results - the sign of the auction effect is not settled. And they state the theory is explicitly open: 'how can one rationalize in a fully specified equilibrium model how asking price can direct search even though it is neither a posted price nor a ceiling?' The 2.4%-per-doubling figure is from a WORKING PAPER (Genesove & Han 2012b), not peer-reviewed.",
)

H["Search_and_Matching_in_the_Housing_Market.txt"] = dict(
    cite="Genesove, D. & Han, L. (2012). 'Search and matching in the housing market.' Journal of Urban Economics 72(1):31-45.",
    sample="NAR buyer and seller surveys aggregated to MSA-year, 1987-2007/08. Buyer sample n=2,372 MSA-years; seller n=1,894; joint n=1,636.",
    finding="First estimate of the housing matching function: elasticity of the seller contact hazard with respect to the buyer-seller ratio is 0.84 (constant returns assumed) - i.e. near-proportional. More buyers per seller means proportionally more contacts for the seller. Buyers visit a mean of 9.96 homes (SD 4.34). Weighted-average median seller time on market 7.3 weeks; buyer 8.2 weeks.",
    status="VERIFIED to full text.",
    notproof="Identifies DEMAND shocks, not list-price effects. This is not a listing-price elasticity and must not be cited as one. It establishes that buyer volume translates into seller contacts roughly one-for-one; it says nothing about how the asking price changes buyer volume.",
)

H["genesove.txt"] = dict(
    cite="Genesove, D. & Han, L. (2012). 'Search and matching in the housing market.' Journal of Urban Economics 72(1):31-45. (Alternate extraction.)",
    sample="See Search_and_Matching_in_the_Housing_Market.txt.",
    finding="Matching-function elasticity 0.84; 9.9 homes visited per buyer.",
    status="VERIFIED.",
    notproof="Not a listing-price elasticity. See Search_and_Matching_in_the_Housing_Market.txt.",
)

H["rba_hansen.txt"] = dict(
    cite="Genesove, D. & Hansen, J. (2025). 'Auctions and Negotiations in Housing Price Dynamics.' Review of Economics and Statistics 107(4):1074-1085. (Draft: gh.txt)",
    sample="CENSUS of all Sydney and Melbourne sales 1993:Q1-2016:Q4 - approximately 4 million transactions, price recorded for all but 0.2%; attributes for 35%. Sydney plus Melbourne is roughly 40% of Australian transaction volume.",
    finding="THE BEST AUSTRALIAN EVIDENCE IN THIS CORPUS. Auction prices weight BUYER values heavily; negotiated prices are close to an equally weighted average of buyer and seller values; and LIST PRICES REFLECT ONLY SELLER VALUES. 'Absent seller reserves, auction prices are solely determined by the distribution of buyers' values; even with seller reserves, theory predicts the weight on the seller's value to approach zero as the number of bidders increases' - their calibration puts that threshold at about six bidders. Buyers incorporate ~60% of a common market shock within a quarter and 95% within three; sellers manage under 15% and under 40% respectively.",
    status="VERIFIED to full 2019 draft.",
    notproof="Does NOT measure bidder count against price - the authors state outright, 'We have no data on the number of bidders at individual auctions.' If a ~4-million-transaction Australian census could not obtain bidder counts, that relationship has never been estimated in Australia and no one should claim otherwise. Footnote 5 also warns that negotiated prices following informal bidding wars are misclassified auctions, so the paper UNDERSTATES the auction-negotiation gap.",
)

H["gh.txt"] = dict(
    cite="Genesove, D. & Hansen, J. 'The Role of Auctions and Negotiation in Housing Prices.' Draft, 13 December 2019. Published as Review of Economics and Statistics 107(4):1074-1085 (2025).",
    sample="~4 million matched Sydney and Melbourne sales, 1993-2016.",
    finding="See rba_hansen.txt. List prices reflect only seller values.",
    status="VERIFIED. This is the working draft; rba_hansen.txt is the fuller extraction.",
    notproof="No bidder-count data. See rba_hansen.txt.",
)

H["guren.txt"] = dict(
    cite="Guren, A.M. (2018). 'House Price Momentum and Strategic Complementarity.' Journal of Political Economy 126(3):1172-1218.",
    sample="Altos Research weekly MLS matched to DataQuick; San Francisco Bay Area, Los Angeles and San Diego, April 2008 - February 2013. 663,976 listings resulting in 480,258 transactions; IV sample 416,373 -> 310,758. First-stage joint F = 206.",
    finding="THE STRONGEST EVIDENCE ON THE REAL COST OF OVERPRICING. Instrumented: a 1% higher list price reduces the probability of sale within 13 weeks by 2.7 percentage points against a base of 48pp - a 5.6% relative fall. A 5% higher list price costs 21.5pp, a 45% relative fall. Demand is strongly CONCAVE: overpricing destroys sale probability fast while underpricing barely improves it. Guren's own first-listed mechanism: 'buyers may avoid visiting homes that appear to be overpriced.'",
    status="VERIFIED to author's PDF.",
    notproof="This is a PROBABILITY OF SALE result, not a sale-price result. It does not say an overpriced home sells for less; it says it is much less likely to sell at all within the window. Do NOT convert these percentages into dollar figures. Also: the OLS estimates in the same paper are badly biased by unobserved quality - use only the IV specification, never the OLS shape.",
)

H["repetto.txt"] = dict(
    cite="Repetto, L. & Solis, A. (2020). 'The Price of Inattention: Evidence from the Swedish Housing Market.' Journal of the European Economic Association 18(6):3261-3304.",
    sample="n=349,476 Swedish apartment sales 2010-2015 (Maklarstatistik, ~90% of broker sales); 27,173 with bidder-level auction data. Mean asking price 1.514m SEK; mean final price 10.4% above asking; mean 2.7 bidders.",
    finding="An asking price set just BELOW a round million attracts +0.72 more bidders and +2.7 more bids (+25% and +30%), producing a 3-5% higher final price, identified by regression discontinuity. Around 5m SEK, roughly 7x more apartments transact at 5.00-5.19m than at 4.80-4.99m.",
    status="VERIFIED to full working-paper text.",
    notproof="*** DO NOT MERGE THIS WITH THE PRICE-BRACKET / SEARCH-FILTER ARGUMENT. *** The authors explicitly REJECT the search-filter explanation, twice: (1) on Hemnet, an apartment listed exactly at a bracket boundary appears in BOTH brackets, so round-number listings are if anything MORE visible; (2) when Hemnet replaced a manual slider with pre-set price brackets on 12 March 2011, difference-in-differences (Appendix Table 18) shows the price discontinuity was present before AND after. Their mechanism is LEFT-DIGIT INATTENTION - buyers reading 1,995,000 as 'one-nine' rather than 'two' - not portal filtering. Bracket reach (merlo.txt, Rightmove, Qld Reg s10) and left-digit inattention are SEPARATE mechanisms with separate evidence. Conflating them makes both easier to attack.",
)

H["kopsch.txt"] = dict(
    cite="Kopsch, F., Helgason, Hansson & Johansson (2021). Nordic Journal of Surveying and Real Estate Research 16(1):7-24. DOI 10.30672/njsr.102913.",
    sample="n=31,671 estimation sample (36,310 baseline), Capital Region of Iceland, 2014-2020.",
    finding="Tests deliberate underpricing directly. Degree-of-underpricing coefficient 0.9047 (SE 0.00249), squared term -0.0827. Verbatim: 'a property under-priced with 10% will result in a sales price reduction of 9.047%.' 11.4% sold above list, ~16% at list, 73% below.",
    status="VERIFIED to full PDF.",
    notproof="Methodological caveat the reader should know: 'degree of underpricing' is constructed as (list - model-predicted value) / predicted value, so it absorbs the hedonic model's own prediction error and partly regresses price on price. The tell is R-squared jumping from 0.80 to 0.97 on adding the variable, and the authors concede it 'does contain information about estimated prices.' Han & Strange's design (outcome = number of BIDDERS, not price) is immune to this and is the cleaner test. That said, three independent teams in three countries reach the same sign - see stockholm.txt and Hammervold et al. (2025), Real Estate Economics 53:1284-1308, n=15,288 Norway.",
)

H["stockholm.txt"] = dict(
    cite="Hungria-Gunnelin, R. (2013). 'Impact of Number of Bidders on Sale Price of Auctioned Condominium Apartments in Stockholm.' International Real Estate Review 16(3):274-295. Note: the SAME author's later paper (Hungria-Gunnelin, Kopsch & Enegren 2021, IJHMA 14(3):481-497, n=11,658 Gothenburg 2012-2016) REJECTS the underpricing hypothesis - 1% of underpricing costs ~0.85% of sale price, and 86% of those transactions sold above list averaging ~10% above.",
    sample="n=512 inner-city Stockholm condominium sales, January-November 2010, e-bud auction platform. Log-linear hedonic plus spatial error/spatial lag models.",
    finding="Bidder coefficient 0.038-0.039 (z = 5.27-5.47); bidder-squared -0.0018 (z = -2.6 to -2.8). 'The average price per square meter paid by every extra bidder has an increasing but decelerating growth, starting with an approximate 4 percent increase when going from one to two bidders.'",
    status="VERIFIED to full PDF.",
    notproof="Author's own caveat: NO controls for building age, maintenance or refurbishment. 'It may be that high-quality apartments on average attract more bidders.' Direction of bias unknown - the bidder effect may be partly a quality effect. And note the decelerating term: the second bidder is worth ~4%, each subsequent one less. This does NOT support a claim that many bidders produce a large premium.",
)

H["cardella.txt"] = dict(
    cite="Cardella, E. & Seiler, M.J. (2016). 'The effect of listing price strategy on real estate negotiations.' JOURNAL OF ECONOMIC PSYCHOLOGY 52:71-90.",
    sample="LABORATORY EXPERIMENT. 132 subjects in 66 pairs, University of Arizona. Buyer reservation value held at $205,000. Four conditions: Rounded $200,000 / Just Below $199,000 / High Precise $201,326 / Low Precise $198,674.",
    finding="A HIGH PRECISE list price - a precise figure slightly ABOVE the nearest round number - yields the highest final sale price and the largest seller share of surplus. 'Just below' pricing yields the LOWEST. ANOVA p=.012; Jonckheere-Terpstra p=.003.",
    status="VERIFIED. *** CITATION CORRECTION: 'Before You List' cites this to Journal of Real Estate Finance and Economics 52(4):434-461. That is WRONG. The paper is in the Journal of Economic Psychology 52:71-90. ***",
    notproof="Much weaker than it is usually presented. It is a 132-subject lab experiment, not field data, and the price manipulation is only +/-0.7% - it cannot support claims about 'several percent of the sale price'. Effects attenuate with negotiating experience. And it is CONTRADICTED on field data by Beracha & Seiler (2014), JREFE 49(2):237-255, which finds just-below pricing nets +2.5% to +3% versus round pricing because the higher embedded overprice more than offsets the larger negotiated discount. Treat precise pricing as a cheap, plausible, low-risk refinement - not a proven lever.",
)

H["nn87.txt"] = dict(
    cite="Northcraft, G.B. & Neale, M.A. (1987). 'Experts, amateurs, and real estate: An anchoring-and-adjustment perspective on property pricing decisions.' Organizational Behavior and Human Decision Processes 39(1):84-97.",
    sample="Tucson, Arizona. Real property tour plus a full MLS comparables packet. Experiment 1: true appraisal $74,900, $18,000 anchor spread, amateurs n=48, experts n=21. Experiment 2: experts n=47, amateurs n=54, +/-11% anchors.",
    finding="Listing-price anchors passed through at 48% for amateurs and 41% for experienced real estate agents. Exp.1 F=4.85 p<.01, planned comparison F=14.26 p<.001, omega-squared 0.22. Exp.2 all four measures significant for both groups, omega-squared 0.23-0.40. THE MEMORABLE FINDING: 'the decision checklists and descriptions of the expert subjects flatly denied their use of listing price.' Only 14.3% (Exp.1) and 8% (Exp.2) of experts listed it among their top three considerations. Agents are anchored by the list price and do not know it.",
    status="VERIFIED to full text.",
    notproof="Hypothetical judgements with no money at stake, tiny expert cells (n=21, n=47), and 1987. Hypothesis 2 - that anchor credibility limits the effect - received only weak support in Exp.1 and NONE in Exp.2. This establishes that anchoring operates on professionals; it does NOT establish that a higher list price produces a higher sale price in the field. For that, see Bucchianeri & Minson (2013), where the field effect is +$117 to $163 on a 10-20% overprice - about 0.05-0.07% of sale price.",
)

H["haurin.txt"] = dict(
    cite="Haurin, D., Haurin, J., Nadauld, T. & Sanders, A. (2010). 'List Prices, Sale Prices and Marketing Time: An Application to U.S. Housing Markets.' Real Estate Economics 38(4):659-685.",
    sample="See paper.",
    finding="Held in the Fields evidence base for one result: THE LIST PRICE FUNCTIONS AS AN UPPER BOUND ON OFFERS. In a private-treaty market this is the most important qualification to any 'the listing price is just an attraction tool' framing - whatever else it is doing, it is capping the outcome.",
    status="PDF on file; the one-line result above is all that has been extracted and verified. NO effect size, sample size or verbatim quotation has been confirmed.",
    notproof="DO NOT QUOTE A NUMBER FROM THIS PAPER. Only the directional result is held. Anyone needing a magnitude must read the PDF first.",
)

H["rust_howtosell.txt"] = dict(
    cite="Merlo, A., Ortalo-Magne, F. & Rust, J. (2015). 'The Home Selling Problem: Theory and Evidence.' International Economic Review 56(2):457-484.",
    sample="Halifax Estate Agencies transaction histories (as Merlo & Ortalo-Magne 2004).",
    finding="'The estimated relationship between the list price and the expected rate of arrival of potential buyers is RELATIVELY INELASTIC. More precisely, relatively small adjustments in the list price hardly affect the expected sale probability while impacting the expected sale price.' A menu cost below 0.006% of house value (about GBP12 on GBP200,000) is enough to explain observed list-price stickiness, precisely BECAUSE the arrival response is weak.",
    status="VERIFIED to working-paper text.",
    notproof="*** THIS PAPER CONTRADICTS THE REACH-ELASTICITY ARGUMENT. *** It is in direct conflict with Vandenbergh (2024), Journal of Housing Economics 64:101997, which finds a 1% increase in listing price reduces search activity by 6.7% using property fixed effects on Belgian portal data. Different countries, decades and outcome variables (offers vs portal clicks), so both may be locally right - but the reach elasticity is NOT SETTLED and no single number should be quoted for it. Any Fields claim about how much traffic a price change buys must acknowledge this conflict.",
)

H["vandijk.txt"] = dict(
    cite="van Dijk, D.W. & Francke, M.K. (2018). 'Internet Search Behavior, Liquidity and Prices in the Housing Market.' Real Estate Economics 46(2):368-403.",
    sample="See paper.",
    finding="Internet search behaviour, liquidity and housing prices.",
    status="*** UNVERIFIED. *** A figure circulating in Fields material - '1% higher price -> 0.66% fewer clicks' - DOES NOT APPEAR in the PDF retrieved here. Do not cite that number to this paper.",
    notproof="Nothing from this paper should be quoted until the specific result has been located in the text.",
)

H["mayer.txt"] = dict(
    cite="Mayer, C. (1998). 'Assessing the Performance of Real Estate Auctions.' Real Estate Economics 26(1):41-66. (Boston Fed WP 93-1.)",
    sample="Los Angeles (mid-1980s boom) and Dallas (late-1980s bust).",
    finding="Auction DISCOUNTS of 0-9% in Los Angeles and 9-21% in Dallas. Discounts are larger in weaker markets.",
    status="VERIFIED to Boston Fed working paper.",
    notproof="This is the counterweight to any claim that auctions or competitive bidding produce a premium. The sign of the auction effect is NOT settled anywhere in the literature: Ashenfelter & Genesove (1992) found identical New Jersey condos sold face-to-face for 13% LESS than at auction; Quan (2002) and Chow et al. (2014) found premiums; Gan (2013) found discounts; Mayer finds discounts. Han & Strange (2015) call the results 'disparate'. For Australia specifically, Cortes & Singh (2026, Review of Finance, 480,000+ NSW/VIC sales) find a successful-auction premium of only +0.7% and a net expected advantage of +0.3% once the ~1-in-5 failure rate and the -1.3% failed-auction penalty are accounted for.",
)

H["aabfj_auction.txt"] = dict(
    cite="Frino, A., Lepone, A., Mollica, V. & Vassallo, A. (2010). 'The Impact of Auctions on Residential Sale Prices: Australian Evidence.' Australasian Accounting, Business and Finance Journal 4(3).",
    sample="RP Data, five Australian capital cities, more than 536,000 transactions, January 2005 - June 2009.",
    finding="ListType coefficients for houses: Melbourne 0.1223 (t=12.37), Sydney 0.0153 (2.39), Brisbane 0.0678 (7.16), Perth 0.1778 (9.15), Adelaide 0.2425 (37.31). The auction premium survives a two-stage Heckman self-selection correction (all lambda significant). For UNITS it is significant only in Perth and Adelaide. Median time on market: auction ~25 days vs private treaty ~37.",
    status="VERIFIED to full PDF.",
    notproof="*** DO NOT QUOTE THOSE COEFFICIENTS AS 'THE AUCTION PREMIUM'. *** The model includes ListType x sub-division interactions ranging from -0.23 to +0.26, so each coefficient is the effect in that city's REFERENCE SUB-DIVISION ONLY, not a city-wide premium. Reading Adelaide's 0.2425 as 'a 24% auction premium in Adelaide' is wrong. The best-identified Australian estimate is Cortes & Singh (2026): +0.7% for a successful auction, +0.3% net of failure risk.",
)

H["bestkleven.txt"] = dict(
    cite="Best, M.C. & Kleven, H.J. (2018). 'Housing Market Responses to Transaction Taxes: Evidence From Notches and Stimulus in the U.K.' Review of Economic Studies 85(1):157-193.",
    sample="Universe of UK property transactions 2004-2012, approximately 10 million.",
    finding="Hard evidence that price thresholds bend real market behaviour. At the GBP250,000 and GBP500,000 stamp duty notches, excess bunching is 1.85x and 1.64x the counterfactual density, and the HOLE above each notch spans GBP25,000. The most responsive agents cut transacted value by 5x the GBP5,000 tax jump; the average house-price response is GBP10,000, twice the size of the tax jump.",
    status="VERIFIED to September 2016 working paper.",
    notproof="This is about TRANSACTION TAX notches, not portal search brackets. It proves that buyers and sellers cluster at salient price thresholds and that the effect is large - a useful analogue for the search-bracket argument, but NOT direct evidence for it. Do not present it as evidence about portal filtering.",
)

H["kopczuk.txt"] = dict(
    cite="Kopczuk, W. & Munroe, D. (2015). 'Mansion Tax: The Effect of Transfer Taxes on the Residential Real Estate Market.' American Economic Journal: Economic Policy 7(2):214-257.",
    sample="New York City 380,629 taxable sales 2003-2011; New York State 1,172,708; New Jersey 1,703,260. Plus 71,875 REBNY Manhattan LISTINGS 2003-2010.",
    finding="At the $1,000,000 'mansion tax' notch, 'about $20,000 worth of transactions shift to the threshold in response to the $10,000 tax'. Roughly 2,800 missing transactions out of 380,000 in NYC - a 1% tax eliminated 0.7% of transactions through unravelling. CRUCIALLY, on the listings data they find bunching IN ASKING PRICES (median initial ask $899,000): the distortion is present when the property is FIRST ADVERTISED, not just at settlement.",
    status="VERIFIED.",
    notproof="A tax-notch result, not a search-bracket result. Its value here is the asking-price bunching finding - evidence that sellers set asking prices at salient thresholds - not as proof that portals filter by bracket.",
)

H["besley.txt"] = dict(
    cite="Besley, T., Meads, N. & Surico, P. 'The incidence of transaction taxes: evidence from a stamp duty holiday.' Journal of Public Economics.",
    sample="UK stamp duty holiday.",
    finding="Incidence of transaction taxes around a price threshold. Supporting material for the price-threshold/notch literature.",
    status="Extracted but not independently verified for this project. No figure from this paper has been used in any Fields document.",
    notproof="Do not quote without reading. Held as context for the threshold literature only.",
)

H["winners_curse.txt"] = dict(
    cite="Choi, S.H., Nowak, A., Smith, P. & Tchistyi, A. (March 2025 draft). 'The Winner's Curse in Housing Markets.' WORKING PAPER - the draft is marked DO NOT CIRCULATE.",
    sample="CoreLogic MLS matched to deeds and HMDA. 14.2 million transactions, 136 counties, 30 states, 2000-2018.",
    finding="Bidding-war incidence: 15-25% in 2000-07, ~10% in 2008-11, ~30% in 2020, just under 50% in 2021, ~35% in H1 2023. BIDDING-WAR WINNERS EARN 1.3 PERCENTAGE POINTS LOWER ANNUALISED UNLEVERED RETURNS against a sample mean of 5.1pp - 10.5pp lower total return over a 6.3-year hold, equivalent to overpaying by 8.2pp - and are 1.9pp more likely to default. Effects concentrate among 'socioeconomically vulnerable homebuyers'.",
    status="WORKING PAPER, marked do-not-circulate. Treat as indicative.",
    notproof="Read this before writing anything that celebrates bidding wars. It is evidence that the winner of a bidding war SYSTEMATICALLY OVERPAYS. That is not an argument against seeking competition, but it constrains the tone: Fields' editorial position is buyer-first, and framing a bidding war as extracting more than a home is worth sits badly against this. The defensible framing is that competition REVEALS what the market will bear.",
)

# Compact banner repeated every REPEAT_WORDS so that EVERY 600-word retrieval chunk
# carries the caveat, not just the first one. Without this the header lands in chunk 1
# and chunks 2..N (15-100+ per paper) return the finding with nothing attached.
SHORT = {
    "BiddingWar.txt": "Han & Strange 2014. The 10.01%/17.89% bidding-war premium is over LIST PRICE, not value, and was HIGHER in the bust because sellers listed LOWER. Not a measure of what competition adds. Same authors call underprice->war->premium 'folklore'.",
    "stockholm.txt": "Hungria-Gunnelin 2013, n=512. ~+4% for the 2nd bidder, decelerating. NO controls for building age/condition - may be a quality effect. The same author's 2021 paper (n=11,658) REJECTS the underpricing hypothesis.",
    "kopsch.txt": "Kopsch et al 2021, n=31,671 Iceland. Underpricing 10% -> sale price -9.047%. Underpricing LOWERS the final price. Caveat: the DOP variable absorbs hedonic prediction error (R2 0.80->0.97).",
    "repetto.txt": "Repetto & Solis 2020. Just-below-round asking -> +25% bidders, 3-5% higher price. The authors EXPLICITLY REJECT the portal search-filter explanation - the mechanism is LEFT-DIGIT INATTENTION. Do not cite as bracket-reach evidence.",
    "cardella.txt": "Cardella & Seiler 2016, J ECONOMIC PSYCHOLOGY (not JREFE - the seller book cites it wrongly). LAB EXPERIMENT, 132 subjects, manipulation only +/-0.7%. Contradicted on field data by Beracha & Seiler 2014.",
    "Asking_Price_8-14-2014.txt": "Han & Strange 2016. 10% lower ask -> +2.2% to +4% bidders. WARNING: the RAW relationship is POSITIVE (+0.08 to +0.14); it only turns negative once location is controlled. Effect is bounded - 'only up to a point'.",
    "hs_askingprice.txt": "Han & Strange 2016 (published). Asking-price elasticity of bidder count -0.22 to -0.40. The RAW relationship is POSITIVE before location controls.",
    "guren.txt": "Guren 2018. +1% list price -> -5.6% RELATIVE PROBABILITY OF SALE in 13 weeks; +5% -> -45%. This is a probability-of-sale result, NOT a sale-price result. Do not convert to dollars. Use the IV, never the OLS.",
    "merlo.txt": "Merlo & Ortalo-Magne 2004, n=780. ALL 30 above-list sales were de facto auctions - in private treaty you only clear list when 2+ buyers bid at once. Bracket test: a cut into a LOWER segment moves offers, a same-segment cut does nothing. Traffic predicts OFFERS, not completions.",
    "bk96.txt": "Bulow & Klemperer 1996. One extra SERIOUS bidder beats any bargaining power (+33% in their example). A THEOREM with strict conditions, not a housing measurement. Measured housing effects are far smaller (+0.64% to +4% per bidder).",
    "rust_howtosell.txt": "Merlo, Ortalo-Magne & Rust 2015. Buyer arrival is 'RELATIVELY INELASTIC' to list price. DIRECTLY CONTRADICTS Vandenbergh 2024 (-6.7% search per +1% price). The reach elasticity is NOT settled - quote no single number.",
    "vandijk.txt": "van Dijk & Francke 2018. UNVERIFIED - the '0.66% fewer clicks per 1% price' figure circulating in Fields material DOES NOT APPEAR in this text. Do not cite it to this paper.",
    "aabfj_auction.txt": "Frino et al 2010, >536k AU transactions. DO NOT quote the ListType coefficients as 'the auction premium' - they are reference-sub-division effects only. Best AU estimate is Cortes & Singh 2026: +0.7%, +0.3% net of failure risk.",
    "haurin.txt": "Haurin et al 2010. Held for ONE result: the list price is an UPPER BOUND ON OFFERS. No effect size has been verified - DO NOT QUOTE A NUMBER from this paper.",
    "winners_curse.txt": "Choi et al 2025 WORKING DRAFT (do-not-circulate), 14.2m transactions. Bidding-war WINNERS earn 1.3pp lower annual returns and default 1.9pp more. Evidence the winner OVERPAYS - constrains any tone that celebrates bidding wars.",
    "nn87.txt": "Northcraft & Neale 1987. List-price anchors moved EXPERT agents' appraisals by 41%, and the experts denied using them (only 8-14% acknowledged). Hypothetical judgements, tiny expert cells. Field anchoring effect is ~0.05-0.07% (Bucchianeri & Minson).",
    "rba_hansen.txt": "Genesove & Hansen 2025, ~4m Sydney+Melbourne sales. LIST PRICES REFLECT ONLY SELLER VALUES; auction prices reflect buyers'. Authors state they have NO bidder-count data - that relationship has never been estimated in Australia.",
    "gh.txt": "Genesove & Hansen draft. List prices reflect only seller values. No bidder-count data exists in Australia.",
    "mayer.txt": "Mayer 1998. Auction DISCOUNTS of 0-9% (LA) and 9-21% (Dallas). The sign of the auction effect is NOT settled anywhere; Han & Strange call the literature 'disparate'.",
    "bestkleven.txt": "Best & Kleven 2018. Stamp-duty NOTCH bunching, ~10m UK transactions. Evidence that markets cluster at salient price thresholds - an ANALOGUE for search brackets, NOT direct evidence of portal filtering.",
    "kopczuk.txt": "Kopczuk & Munroe 2015. Mansion-tax notch; bunching appears in ASKING prices. A tax result, not a search-bracket result.",
    "hs_handbook.txt": "Han & Strange 2015 survey. Calls the underprice->bidding-war->high-price idea 'FOLKLORE'. Auction literature results are 'disparate'. The 2.4%-per-doubling bidder figure is from an unpublished working paper.",
    "Search_and_Matching_in_the_Housing_Market.txt": "Genesove & Han 2012. Matching-function elasticity 0.84. Identifies DEMAND shocks - this is NOT a listing-price elasticity and must not be cited as one.",
    "genesove.txt": "Genesove & Han 2012. Matching elasticity 0.84. NOT a listing-price elasticity.",
    "besley.txt": "Besley, Meads & Surico. Stamp-duty holiday incidence. Context only - no figure from this paper has been used in any Fields document. Do not quote without reading.",
}
REPEAT_WORDS = 500  # < the ingester's 600-word chunk, so every chunk gets a banner


def header(meta):
    return (
        "=" * 78 + "\n"
        "DOCUMENT TYPE: EXTERNAL PUBLISHED ACADEMIC LITERATURE - PUBLIC / NON-CONFIDENTIAL\n"
        "This file is the text of a published, peer-reviewed academic paper by\n"
        "third-party authors. It contains no Fields Estate client data, financial\n"
        "records, or internal strategy. ROUTE: BRAIN 1 (external knowledge pool).\n"
        "Only the bracketed CLAIM STATUS block below was added by Fields Estate.\n"
        + "=" * 78 + "\n"
        "CLAIM STATUS (added by Fields Estate at ingest, 2026-08-11)\n"
        "Read this before quoting anything below. The 'DOES NOT PROVE' line is\n"
        "not a disclaimer - it is the part most likely to be needed and least\n"
        "likely to survive retrieval on its own.\n"
        + "=" * 78 + "\n\n"
        f"CITATION:      {meta['cite']}\n\n"
        f"SAMPLE:        {meta['sample']}\n\n"
        f"KEY FINDING:   {meta['finding']}\n\n"
        f"STATUS:        {meta['status']}\n\n"
        f"DOES NOT PROVE / HANDLE WITH CARE:\n               {meta['notproof']}\n\n"
        + "=" * 78 + "\n"
        "END CLAIM STATUS HEADER - original document text follows\n"
        + "=" * 78 + "\n\n\n"
    )


def interleave(body, short):
    """Repeat a compact caveat banner through the document body.

    The ingester chunks at WORDS_PER_CHUNK=600 with a naive word split, so a header
    placed only at the top of the file reaches chunk 1 and nothing else. Papers here
    run to 15-100+ chunks. Spacing the banner every REPEAT_WORDS(500) < 600 guarantees
    every retrieval chunk contains at least one complete banner.
    """
    banner = f"\n\n[FIELDS CLAIM-STATUS -- {short}]\n\n"
    w = body.split()
    if len(w) <= REPEAT_WORDS:
        return body + banner
    out = []
    for i in range(0, len(w), REPEAT_WORDS):
        out.append(" ".join(w[i:i + REPEAT_WORDS]))
    return banner.join(out) + banner


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    written, skipped, unheadered = 0, [], []
    seen_hashes = {}

    for f in sorted(SRC.iterdir()):
        if not f.is_file() or f.suffix != ".txt":
            continue
        if f.name in SKIP:
            skipped.append(f.name)
            continue

        digest = hashlib.md5(f.read_bytes()).hexdigest()
        if digest in seen_hashes:
            skipped.append(f"{f.name} (duplicate of {seen_hashes[digest]})")
            continue
        seen_hashes[digest] = f.name

        meta = H.get(f.name)
        body = f.read_text(errors="replace")
        if meta:
            short = SHORT.get(
                f.name,
                f"{meta['cite'][:110]} - see the CLAIM STATUS header at the top of this file "
                f"before quoting any figure.",
            )
            (OUT / f.name).write_text(header(meta) + interleave(body, short))
            written += 1
        else:
            (OUT / f.name).write_text(body)
            unheadered.append(f.name)

    print(f"staged   : {written} file(s) with claim-status headers")
    print(f"no header: {len(unheadered)} -> {unheadered}")
    print(f"skipped  : {len(skipped)} -> {skipped}")
    print(f"output   : {OUT}")


if __name__ == "__main__":
    main()
