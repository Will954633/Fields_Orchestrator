# Comparing Median House Prices — September 2026 · Walkthrough Transcript

Source: `/walkthrough/median-house-prices_2026-09b.mp4` (live on [/articles/comparing-median-house-prices](https://fieldsestate.com.au/articles/comparing-median-house-prices) and the /news pillar cards). Verbatim, timecoded. Derived from the page-rendered caption segments (`WALK_SEGMENTS_MEDIAN` in `MarketFlowProto.engine.ts`) — the same text the /news walkthrough draws on screen; these ARE Will's captions, not a separate ASR pass.

> Note: a spoken "2026" after "December" was cut from the video (Will meant Dec **2025**); timecodes here follow the original authored timeline, so they run ~1s ahead of the final cut after the ~13:32 mark. Chapter titles are the walkthrough's own film markers.

---


### 0:00 — Why the median gets misread

**[0:00]** Okay I really wanted to do a video on median house prices because this is a number that gets thrown around quite a lot and it's easily presented in such a way that could be misleading if you didn't understand a bit

**[0:14]** more about the numbers behind it.

**[0:16]** So let's take a look at how it's calculated and four different traps that you can fall into that can make a median house price misleading.

**[0:24]** So let's get started.


### 0:26 — How a median is calculated

**[0:26]** So first of all let's work out how it's calculated.

**[0:28]** This is pretty simple.

**[0:30]** So we've got a series of eight numbers here and the median house price is simply the middle number.

**[0:36]** In this case the middle numbers between two numbers there.

**[0:40]** So when that happens we just add those two up and divide by two we get 1.49 million easy.

**[0:47]** So just take a closer look at that data set there I've included a 12 million dollar sale as like an extreme outlier because I want to show you how median is really good at accounting for that effect so with that 12

**[0:59]** million dollar included we get that median price of 1.49 if we pull it out and recalculate the median price now it's 1.48 million so just a difference of $10,000 and that's because

**[1:13]** that one number got pulled out the middle then became 1.48 instead of in between 1.48 1.55 hopefully that makes sense so you can see how a median really adjusts well for extreme

**[1:27]** outliers it doesn't get distorted by them too much and that'll be highlighted in this next example if we have a look at that same data set and use an average instead of a median what we get is a really

**[1:41]** different story there so with that 12 million dollars sale included we get an average price of two point seven five so the median was one point four nine and the average is two point seven five

**[1:54]** if we then pull out that 12 million and recalculate the average one point four three million so it moves radically the average moves radically when we leave outliers in our data sets and that's why median

**[2:08]** median price is really a good measure to use for property data sets.

**[2:13]** Right.

**[2:13]** So now that we've got the math out of the way, let's jump into the core issue.

**[2:16]** And there are four different ways that we can easily get tricked up when it comes to median prices.


### 2:22 — Trap 1 — the mix of homes changes

**[2:22]** So let's jump into the first one.

**[2:25]** And this is the mix, the mix of homes that sells changes and the median will change with it.

**[2:32]** So let's jump down now to this first chart.

**[2:35]** So this is a chart of attached dwellings.

**[2:38]** So units and duplexes, et cetera, in Robina and how their prices change over time.

**[2:45]** So we've got two bedroom units and three bedroom units and all attached dwellings across that data set.

**[2:53]** And what's striking there is you can see that all attached dwellings is higher than both three bedrooms and two bedrooms.

**[2:59]** So how could that be?

**[3:01]** How could it be higher than those two underlying data points within it?

**[3:06]** And the answer is that it's because of the mix of homes that sold over that time.

**[3:13]** So what actually happened was, was that in 2026, there was a far greater portion of larger, more expensive properties that sold than in the years before.

**[3:24]** So that median price jumped up simply because there was more properties at that high number or higher frequency of those properties in the data set in the row of sequential numbers when the medians found

**[3:37]** it moved up simply because there's more of them in there.

**[3:41]** So that explains in part why that where that 30% came from.

**[3:47]** And there's another way to explain it here below.

**[3:50]** If I actually show you the numbers, we can lay them out and use them as an example to see how this comes to be.

**[3:57]** So here's a simplified example using 13 attached property sales from 2024 arranged from lowest to highest.

**[4:06]** So nine of the 13 sales were two bedroom properties and only three were three bedroom properties and then one had four or more bedrooms.

**[4:14]** So that middle sale there, the seventh property in the row, that was a two bedroom home selling for $860,000.

**[4:22]** So that became the median price.

**[4:24]** Now let's take a look at 2026 so we still have 13 sales but the mix really changed there so there's only five two bedroom properties while eight have three or more

**[4:38]** bedrooms so the mix changed to larger sized properties and we were arranged those sales from lowest to highest.

**[4:46]** The middle property is now the three bedroom home selling at 1.118 million so those combined median it moved from 860,000 to 1.118 million that's an increase of 30%

**[5:01]** largely just because that mix change comparable properties didn't rise by 30% together.

**[5:08]** So the two bedroom median it only increased by 18% while the three bedroom median that increased by 25% but the combined as was noted the combined rose faster because more properties in 2026

**[5:21]** sold that were larger and more expensive.

**[5:24]** Trick number one, when it comes to median house prices, you need to break them down by house categories.

**[5:30]** So they should be broken down between attached or detached homes and ideally by a number of bedrooms within those subcategories as well.


### 5:40 — Trap 2 — different cities, different mixes

**[5:40]** OK, so this brings us to trap number two, and that's different cities have different mixes.

**[5:45]** So we just learned how the mix of homes changes over time, whether that be larger or smaller homes over time.

**[5:53]** Well, different cities have different mixes within them.

**[5:57]** So for example, Melbourne has roughly twice the number of units in its population as capital cities in other states around Australia.

**[6:08]** So when we compare the median house price, which is typically shown as all dwellings of Melbourne to say Sydney or Brisbane it's not a like comparison because there's twice as many units in

**[6:22]** Melbourne as there are in those other cities and units are far cheaper.

**[6:27]** So this kind of phenomenon occurs locally as well.

**[6:31]** So right now in Robina there's roughly half attached to detached dwellings so roughly half are homes and other half are units.

**[6:41]** In Burleigh Waters there's two times as many homes for sale as there are units.

**[6:47]** So if we were to just look at the combined median house price of all dwellings across Robina and compare it to Burleigh Waters, it's saying as much about what type of homes are built there in those suburbs as it is about

**[7:01]** what properties are worth.

**[7:03]** When we're comparing one suburb to another or one city to another, We need to break it down by house type detached or unattached and also ideally by a number of bedrooms as well.

**[7:16]** But we do need to be careful drilling down too far and getting too specific because if the sample size gets too small then we can get unreliable numbers there as well because the variation starts to really go up.


### 7:28 — Trap 3 — small samples swing

**[7:28]** Which brings me to trap number three.

**[7:31]** Sample sizes too small can be unreliable.

**[7:33]** So when you hear a median number you should always be thinking how many samples is in that number and try and find that data because it needs to be disclosed.

**[7:44]** So that brings me to our next chart.

**[7:46]** So we just scroll down here we have a chart here a month long.

**[7:50]** So this chart goes right back to Q1 of 2025 up to Q2 of 2026.

**[7:57]** So you can see a nice smooth line there of 12 month median house prices.

**[8:02]** If I layer in the rolling three month median now we've got a much more erratic figure there and if we would only look at small periods of time there it would have looked like it was dramatically rising and other periods

**[8:15]** it was drastically or sharply declining.

**[8:19]** So what's happening here is that we've got different sample sizes in a 12 month versus a three month rolling median.

**[8:26]** So let's have a look at how this is played out in most recent data.

**[8:30]** Take a look at the the March quarter there of 2026.

**[8:35]** We had a median house price of 1.56 million that then declined sharply down to 1.4 million a single quarter later in the June quarter.

**[8:45]** So those two are based on 72 sales in March and 55 sales in June.

**[8:52]** Whereas the 12 rolling median it only declines subtly from 1.5 million down to 1.492 million but take a look how many samples are in it so the March quarter right the 12 month rolling median

**[9:05]** 274 samples in that in that median data set versus the three month quarterly of only 71 so that's why you get a much more gradual movement in a 12 months

**[9:18]** and a much more erratic movement in the month data set.

**[9:23]** So we have to be careful with small sample sizes bringing variation in.

**[9:28]** So it's not to say that three months data sets don't have any value at all and that there's no flaws in 12 rolling 12 month medians.

**[9:37]** Because if you think about it right now, so as I'm

**[9:41]** recording this video, this is now September 2026.

**[9:48]** If you think about the way that the changed over the last 12 months we've gone through a big boom period into the back half of 2025 where the market really peaked around December and then into the first few months of

**[10:01]** this year and now in the last three months we've had started to get declines in this market so a 12-month median is still holding those boom months of last year and only including a small number of

**[10:15]** months of the decline from this year whereas the three months is obviously the three month median to the current period, September, 2026, that's picking up that entire decline within it.

**[10:26]** So it's not to say that one doesn't have use and the other does.

**[10:31]** We can look at three months medians.

**[10:33]** We just have to be mindful.

**[10:34]** Is it noise or is it like the noise?

**[10:37]** So just the way the variation in the data naturally moves, or is it actually a true signal that we should be taking note of?

**[10:44]** And what I like to do is combine it with unrelated data sets.

**[10:48]** So see if I can find different data points from different areas.

**[10:52]** And if they're all pointing in the same direction,

**[10:55]** then we can start to say, well, that three month median might actually have some value.

**[11:00]** So other data sets you can use are things like days on market.

**[11:03]** Is that starting to shoot up higher?

**[11:05]** That would show weakening demand.

**[11:07]** Is the number of homes being withdrawn from market shooting up?

**[11:10]** Is the new house lending indicator declining?

**[11:14]** If we started to get those types of metrics all pointing in a similar way a softening or declining house market and the three-month median was also declining like it is there as of this time of

**[11:28]** making this film.

**[11:30]** Then we've got some signal there could be some signal in that noise but obviously we always recognise that three-month medians especially for single suburbs like

**[11:40]** Robina it's a lot of variation in those small sample sizes.

**[11:49]** You'd like to get up to higher sample sizes, anything over 100, 200 sort of better, then you've got something that you can sort of work with and longer timeframes are obviously more stable.


### 12:00 — Trap 4 — asking prices aren't sale prices

**[12:00]** So that brings us to trap number four, our last trap in this series.

**[12:04]** And this is about asking prices and how they're different to sale prices.

**[12:10]** So there's a data vendor out there, a company called QSM Research, and they publish a national asking price for every suburb around the country every month and it's quite a popular source of

**[12:23]** data it's used by David Koch on sunrise and Ross Greenwood the finance report on channel 9 but what we've got to recognise with these with this information is that asking price and selling price

**[12:37]** are really two different things and I'll show you that here in this chart so we just scroll down to this final chart Burleigh Waters houses.

**[12:46]** So what you're looking at here is on that copper line, that's the asking price of sellers.

**[12:53]** So that's vendors listing prices when they put their home on the market.

**[12:58]** That solid line underneath that solid green line, that's the actual selling price.

**[13:02]** That's the median selling price at the same time.

**[13:05]** And what's immediately obvious is that they're two different numbers moving in different trajectories at different time.

**[13:11]** So you can see the asking prices are more volatile than the median price that sometimes it shoots up and then it shoots down.

**[13:19]** Another thing that you might notice there just glancing is that times when the markets either flatlined or corrected or peaked so recently 2022

**[13:30]** and in December when it peaked you're getting the biggest gaps between asking price and median price.

**[13:38]** So that 22 was the market correction and look at that large gap that that persisted there.

**[13:45]** And then again in December of 2025 we have a really spike there when the market peaked of asking prices being really out of sync with median house prices.

**[13:57]** They've come back down now recently but the point I want to make on this chart is that they're two very different things.

**[14:05]** And so you've got to kind of ask yourself, what signal am I looking for out of a median price?

**[14:12]** What's the reason why I want to know what a median price is?

**[14:16]** Because if it's to get an idea of what your home might be worth or its value, then an asking price is going to be quite misleading.

**[14:24]** Take a look at that chart.

**[14:25]** At any point in time, it's most likely not being related and sometimes quite significantly not related to what the actual selling price of houses have been.

**[14:36]** Trick number four is to make sure that you're looking at median sale prices not median listing prices and then just given everything else that we've learned pay attention to the sample sizes.

**[14:51]** So ideally you want a larger sample size of rolling 12 month median gives you the best view of what's happening and just you can use three months medians but need to be cautious about variation those data sets and I and


### 14:51 — How to read a median

**[15:04]** you really have to be sure that you're comparing like for like so make sure that the categories are split out into attached or detached and ideally as I mentioned number of bedrooms to just making sure that your sample

**[15:16]** sizes are large enough to have some real underlying meaning
