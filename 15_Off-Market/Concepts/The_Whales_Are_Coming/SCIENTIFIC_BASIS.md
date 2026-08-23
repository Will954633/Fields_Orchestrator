# The science behind the swim

This animation is driven by measured biomechanics, not by keyframing. This
document records every piece of research it rests on, what each parameter is set
to and why, and — as importantly — where the published evidence runs out and a
choice had to be made instead.

Three things are worth stating at the top, because they shaped everything below:

1. **The obvious model was wrong three times.** The head moves *with* the flukes,
   not against them; the amplitude minimum sits at the flippers, not at the nose;
   and a cetacean blink is a corner-anchored purse, not an upper-lid shutter.
   Each is counter-intuitive, each is measured, and each is built in.

2. **The detailed kinematic dataset is for dolphins, not humpbacks.** The
   per-body-point amplitude and phase numbers that make the whole animal move
   correctly were measured on odontocetes (dolphins, orca, beluga). For
   humpbacks there is exactly *one* direct fluke-amplitude measurement in the
   literature. Everything humpback-specific below is frequency, speed and body
   shape. Where an odontocete number is used for a humpback, it is flagged.

3. **Nothing here is invented to look scientific.** Two numbers in the whole
   build are unsourced — the blink interval and duration — because no
   measurement of them exists for any cetacean. They are labelled as artistic
   choices wherever they appear.

---

## 1. Body length, speed and tail-beat frequency

These three set the fundamental scale and timing of the animation. All are from
tag data on live baleen whales.

**Body length — 13.5 m.**
> Woodward, B. L., Winn, J. P. & Fish, F. E. (2006). "Morphological
> specializations of baleen whales associated with hydrodynamic performance and
> ecological niche." *Journal of Morphology* 267: 1284–1294.
> doi:10.1002/jmor.10474

Adult humpback mean length 13.50 m (n = 128, whaling and stranding records;
range 11.58–15.85 m). The same paper places the humpback at fineness ratio 4.21
against the blue whale's 6.37 — i.e. a fast, manoeuvrable body, not a slender
stiff cruiser. That matters for §3.

**Cruising speed — 2.0 m/s.**
> Gough, W. T., Segre, P. S., Bierlich, K. C., Cade, D. E., Potvin, J., Fish,
> F. E., et al. & Goldbogen, J. A. (2019). "Scaling of swimming performance in
> baleen whales." *Journal of Experimental Biology* 222: jeb204172.
> doi:10.1242/jeb.204172

Humpback tag data (n = 97 deployments): mean speed 1.77 m/s; a photogrammetry
subset gives 1.99 ± 0.45 m/s, with a modelled optimal speed of 1.95 ± 0.04 m/s.
A companion paper (Gough et al. 2021, *JEB* 224: jeb237586) gives routine
swimming at 2.09 ± 0.066 m/s. **2.0 m/s sits in the centre of all of these.**

Locally relevant cross-check, migrating humpbacks off the Gold Coast:
> Kela, H., de Bie, J., Paas, K. H. W., Stack, S., Franklin, W., Franklin, T. &
> Meynecke, J.-O. (2024). "Assessment of humpback whale swimming speeds in two
> eastern Australian bays." *Marine and Freshwater Research*. doi:10.1071/MF24116

Mean 1.15 m/s in the Gold Coast bay (a minimum-speed method, so it under-reads).
The animation's 2.0 m/s is the open-water cruising figure, not the in-bay one.

**Tail-beat frequency — ~0.23 Hz, i.e. one beat every ~4.3 seconds.** From Gough
et al. 2019: humpback mean 0.229 ± 0.039 Hz (n = 97). This is *the* number that
separates a whale from a fish on screen — almost every hand-animated whale beats
its tail roughly ten times too fast. In the animation the frequency is not set
directly; it falls out of the Strouhal relation (§2).

**Frequency scales with body length as L^−0.53** (Gough et al. 2019, log-log
regression, R² = 0.635), which is far shallower than the L^−1.0 an
optimal-Strouhal or resonant-beam oscillator predicts. The authors' explicit
conclusion is that whales are **not** operating as simple Strouhal machines. This
is why the Strouhal lock below is described as an animation control rather than a
law the animal obeys.

---

## 2. Strouhal number and fluke amplitude

**Fluke-beat amplitude — 0.20 of body length, peak-to-peak.**

The field-standard assumption is A = L/5:
> Bainbridge, R. (1958). "The speed of swimming of fish as related to size and
> to the frequency and amplitude of the tail beat." *Journal of Experimental
> Biology* 35: 109–133. ("This maximum amplitude is the same for all fish tested
> and is about one-fifth of the body length.")

For cetaceans specifically it is validated by the one direct humpback
measurement, from a tag that slipped onto a fluke blade (Gough et al. 2019):
peak-to-peak amplitude **2.63 ± 0.79 m**, which on an ~11–13 m animal is
A/L ≈ 0.20–0.24. Odontocete measurements agree:
> Rohr, J. J. & Fish, F. E. (2004). "Strouhal numbers and optimization of
> swimming by odontocete cetaceans." *Journal of Experimental Biology* 207:
> 1633–1642. (n = 248 measurements, 6 species; peak-to-peak fluke amplitude /
> body length "occurred predominantly between 0.15 and 0.25".)

Amplitude is **independent of swimming speed** across all these studies — speed
is modulated by *frequency*, not by how hard the tail swings. The animation
respects this: the amplitude parameter is fixed and speed changes drive
frequency.

**The Strouhal relation — St = fA/U.** The animation's default St = 0.31 is
chosen so the lock reproduces the *measured frequency* (0.23 Hz) at the measured
speed and amplitude. The efficient band is usually quoted as 0.25–0.35, but the
cetacean data is broader and lower:

- The one directly measured humpback Strouhal was **0.24 ± 0.04** (Gough et al.
  2019), at a faster 2.61 m/s.
- Rohr & Fish 2004 (n = 248): "most cetaceans prefer swimming at St values
  between 0.20 and 0.40"; 74% fall in 0.20–0.30; only 55% fall inside the
  theoretical 0.25–0.35 band.

The animation's on-screen readout warns below St 0.20 or above 0.35, using the
wider cetacean-measured range rather than the textbook one.

**An honest tension.** A/L = 0.20 *and* U = 2.0 m/s *and* f = 0.23 Hz together
imply St ≈ 0.31, which is inside the efficient band but above the single
measured humpback value of 0.24 (which came at 2.61 m/s). These cannot all be
honoured at one speed. The frequency is the better-evidenced number (n = 97
deployments versus n = 1 animal for St), so the lock is tuned to reproduce it.

---

## 3. The whole animal moves — the amplitude envelope and phase

This is the core of the realism, and where the intuitive model fails hardest.

### The load-bearing source

> Fish, F. E., Peacock, J. E. & Rohr, J. J. (2003). "Stabilization mechanism in
> swimming odontocete cetaceans by phased movements." *Marine Mammal Science*
> 19(3): 515–528.

They digitised four points — rostrum, flipper tip, peduncle, fluke tip — across
seven species at 1.4–7.3 m/s. The results, and how each is built in:

| Point | Measured amplitude | Measured phase vs fluke | In the animation |
|---|---|---|---|
| Rostrum (nose) | 0.02–0.06 L (fluke is 4.34–6.76× larger) | **−9.4° to +33.0°** | 19% of fluke amplitude, +20° |
| Flipper tip | **smallest of the four** | trails by 60.9–123.4° | smallest excursion; trails 90° |
| Peduncle | between | **leads** by 18.9–48.7° | leads ~38° |
| Fluke tip | 0.17–0.25 L | (reference) | reference |

**Verified output of the animation, measured off the live page:**

| | model | measured target |
|---|---|---|
| Rostrum amplitude | 19% of fluke, 3.8% L | 15–23%, 2–6% L |
| Rostrum phase | +20° | −9.4° to +33.0° |
| Peduncle phase | leads 38° | leads 18.9–48.7° |
| Flipper excursion | smallest of four | smallest of four |

### The two counter-intuitive findings

**(a) The head moves nearly IN phase with the flukes, not against them.** A rigid
beam pivoting about its centre of mass would put rostrum and fluke 180° apart.
Real animals do not: in two of the seven species the phase difference was
statistically indistinguishable from zero. Fish et al. verbatim:

> "By synchronously moving the rostrum in the same direction as flukes by
> muscular control, there is a reduction in the natural tendency of the rostrum
> to swing through a wide arc opposite the motion of the flukes."

So the animation models the body in **two zones meeting at a node**: a travelling
wave behind the node, and an anterior section whose phase is *prescribed against
the fluke* rather than inherited from the wave. A single travelling wave cannot
produce a near-synchronous rostrum and a peduncle that leads by only ~38° at the
same time; the split is what the measured muscular stabilisation actually does.

**(b) The amplitude minimum is at the flippers, not the nose.** The flipper tip
has the smallest excursion of the four points, because it sits nearest the
centre of mass. So the envelope is not a monotonic ramp from a still nose to a
big tail — it dips in the middle. In this sprite the measured node lands between
the two flipper hinges (u = 0.25 and u = 0.37), an independent check on the
earlier segmentation.

### Independent corroboration across 44 species

> Di Santo, V., Goerig, E., Wainwright, D. K., Akanyeti, O., Liao, J. C.,
> Castro-Santos, T. & Lauder, G. V. (2021). "Convergence of undulatory swimming
> kinematics across a diversity of fishes." *PNAS* 118(49): e2113206118.

Global fit across 44 species (peak-to-peak, proportion of body length):
**y = 0.05 − 0.13x + 0.28x²** — head 0.05 L, tail 0.20 L, so head:tail = 25%,
with a minimum at x = 0.232 L. Their across-species medians give head:tail ≈ 17%.
The animation sits at **19%** with the node at 0.28 — between their fit and their
medians, arrived at from an entirely separate (cetacean) literature. Two
independent lines converging is the strongest single piece of evidence here.

Di Santo et al. also demolish the textbook ordering: "there was **no decrease in
head:tail amplitude from the anguilliform to thunniform mode** of locomotion as
we expected from the traditional classification," and the ratio "was only
statistically higher in the tuna." The supposedly stiffest swimmer has the *most*
head yaw. A locked head is not conservative realism — it is a myth.

The same quadratic envelope traces back to fish kinematics measured by:
> Videler, J. J. & Hess, H. (1984), on steadily swimming saithe and mackerel;
> as fitted in Borazjani, I. & Sotiropoulos, F. (2010), "On the role of form and
> kinematics on the hydrodynamics of self-propelled body/caudal fin swimming,"
> *Journal of Experimental Biology* 213: 89–107 — envelope
> a(z) = 0.02 − 0.08z + 0.16z², giving nose = 20% of tail and a node at
> z = 0.25. A third independent arrival at the same ~20% / node-at-0.25 answer.

### Lighthill recoil — implemented, but off by default

> Lighthill, M. J. (1960). "Note on the swimming of slender fish." *Journal of
> Fluid Mechanics* 9(2): 305–317.
> Lighthill, M. J. (1970). "Aquatic animal propulsion of high hydromechanical
> efficiency." *Journal of Fluid Mechanics* 44(2): 265–301.

A prescribed body wave carries net lateral momentum and net angular momentum,
which a free-swimming body cannot. Requiring both to be zero leaves a rigid-body
heave and pitch — the "recoil" — that get subtracted from the wave. Lighthill
1970 (abstract): the recoil movements are "minimized with the right distribution
of total inertia (the sum of fish mass and the water's virtual mass)," which is
why the animation weights the momentum balance by the measured thickness profile
squared (a slender body's mass and added mass both scale with cross-section).

The recoil solver is implemented and, when enabled, roughly doubles the head's
throw and swings it into anti-phase. **It defaults to zero**, for two reasons:

1. The measured phases (§3a) say a live cetacean muscularly *suppresses* that
   anti-phase swing.
2. More decisively, measured envelopes already contain whatever recoil was not
   cancelled, so adding a recoil term on top double-counts it. This is made
   explicit in the modelling literature:
   > Maertens, A. P., Gao, A. & Triantafyllou, M. S. (2017). "Optimal undulatory
   > swimming for a single fish-like body and for a pair of interacting swimmers."
   > *Journal of Fluid Mechanics* 813: 301–345.

   who set their recoil term B(x,t) = 0 for the canonical carangiform gait
   *precisely because* the envelope came from Videler's measurements.

The slider is kept so the anti-phase recoil the animal works to suppress can be
seen; it is not meant to be used for the finished look.

---

## 4. The pectoral flippers

> Fish, F. E. & Battle, J. M. (1995). "Hydrodynamic design of the humpback whale
> flipper." *Journal of Morphology* 225(1): 51–60.

Humpback flippers are exceptionally long (0.28–0.33 of body length), aspect
ratio ~6, with 19° sweepback and tubercled leading edges. In this build they are
cut as separate layers with hinges measured at their roots — the near flipper
composited in front of the body, the far flipper behind.

**What flippers do during steady swimming — the governing paradigm:**
> Segre, P. S., Seakamela, S. M., Meÿer, M. A., Findlay, K. P. & Goldbogen, J. A.
> (2017). "A hydrodynamically active flipper-stroke in humpback whales."
> *Current Biology* 27(13): R636–R637.

> "A central paradigm of aquatic locomotion is that cetaceans use fluke strokes
> to power their swimming while relying on lift and torque generated by the
> flippers to perform maneuvers such as rolls, pitch changes and turns."

Segre et al. document an *active* flapping flipper-stroke — but only immediately
before mouth-opening during lunge feeding, observed twice in hundreds of hours of
video. In cruising, the flippers are control surfaces, not propulsors. The only
descriptive study of live humpback flipper motion agrees:
> Edel, R. K. & Winn, H. E. (1978). "Observations on underwater locomotion and
> flipper movement of the humpback whale *Megaptera novaeangliae*." *Marine
> Biology* 48: 279–287.

which reports large flipper movements reserved for banked turns above ~4 knots,
not for straight cruising.

**How the flippers move here.** Fish et al. 2003 (§3) measured the flipper tip
trailing the flukes by 60.9–123.4° with the smallest excursion of the four
points. The animation drives them off that measured phase lag (default 90°) with
deliberately small amplitude, opposing pitch. This is the honest position,
because:

> **No one has published a flipper motion time series for steady straight-line
> cruising, for any cetacean.** Sweep, feathering angle and dihedral over a
> cruise cycle are simply not in the literature.

So the flipper motion is a physically-motivated extrapolation from the one
measured quantity (phase lag), not a reproduction of measured kinematics. It is
kept subtle for exactly that reason.

---

## 5. Burst-and-coast, and duty-compensated thrust

Large whales rarely beat continuously; they stroke a few times and then glide
while drag bleeds the speed off. This is standard cetacean swimming behaviour
(described throughout Fish & Rohr's work). The animation defaults to 2 beats then
a 3-second glide — about two full cycles per 24-second crossing, beating 41% of
the time.

The one subtlety worth recording: thrust is scaled by **1/duty** so the
burst/glide sliders change the *rhythm* without changing the *speed*. Calibrating
thrust for continuous beating (thrust = drag·U²) undershoots at any duty below 1;
because frequency is Strouhal-locked to instantaneous speed, that shortfall would
otherwise drag the beat rate out of the measured band as a side effect of a
purely rhythmic control. Mean thrust must equal mean drag, so the instantaneous
value during a burst is drag·U²/duty. Verified on the live page: speed oscillates
1.72–2.28 m/s and the beat 0.198–0.262 Hz across every rhythm setting, every
sample inside the measured 0.229 ± 0.039 Hz band.

---

## 6. The blink

> Nishimaniwa, K., Yamada, T. K., Sekiya, S. I., Amano, M. & Tajima, Y. (2026).
> "Morphological features of the orbicularis oculi muscle and facial nerve in
> four odontocete families, with comparisons within Cetartiodactyla."
> *Journal of Veterinary Medical Science* 88(1): 1–12.

A cetacean blink is **a purse, not a shutter**. The orbicularis oculi closes the
palpebral fissure "using the medial and lateral canthi as fulcrums" — a sphincter
contraction anchored at the corners, with the retractor bulbi pulling the globe
inward at the same time. In the animation both margins converge on a mid-line,
the travel tapers to zero at the corners, and the closing line bows.

**Humpbacks are the awkward case, and the animation handles it deliberately.** In
dolphins and porpoises the upper palpebral region has degenerated into an
aponeurotic sheet with almost no facial-nerve supply, so the lower lid does most
of the moving. Mysticetes did not degenerate:
> Rodrigues, F. M. et al. (2015). "Morphology of accessory structures of the
> humpback whale eye (*Megaptera novaeangliae*)." *Acta Zoologica* 96: 328–334.
> Zhu, Q., Hillmann, D. J. & Henk, W. G. (2000). On the bowhead whale eye,
> *Anatomical Record* 259: 189–204.

In humpback and bowhead the muscle is "entirely composed of muscular fibers,"
the ancestral mammalian arrangement — so a humpback blink is *more* symmetric
than a dolphin's. Both lids therefore move by equal measure here.

**No nictitating membrane.** Cetaceans lack one:
> Meshida, K., Lin, S., Domning, D. P., Reidenberg, J. S., Wang, P. & Gilland, E.
> (2020). "Cetacean Orbital Muscles: Anatomy and Function of the Circular
> Layers." *Anatomical Record*.

which lists the nictitating membrane among features "absent in cetaceans but
present in other closely related terrestrial mammals." Most popular sources claim
whales have a third eyelid; they are wrong, and none is animated.

**Closure is faster than reopening** — this asymmetry *is* sourced:
> Aiello, B. R. et al. (2023). "The origin of blinking in both mudskippers and
> tetrapods is linked to life on land." *PNAS* 120(18): e2220404120.

Peak eye velocity and acceleration significantly higher during closure than
reopening (P < 10⁻¹⁹), and the asymmetry "is observed in all tetrapods for which
data is available." The animation's blink stroke is fast-down, brief-hold,
slower-up accordingly.

### The two unsourced numbers

**There is no published measurement of blink rate or blink duration for any
cetacean species.** This was checked systematically against Europe PMC across
species and term variants; every cetacean hit is either anatomy with no
kinematics, or sleep work that scores eye state as a sustained condition in
5-second epochs rather than counting blinks (e.g. Lyamin, Mukhametov & Siegel
2004, *Archives Italiennes de Biologie* 142: 557–568).

So the mean interval (11 s) and stroke duration (0.55 s) are **artistic
choices** — the only two numbers in the entire build not backed by a
measurement. The literature licenses "infrequent and slow": the 5-second
sleep-scoring methodology only works if frequent blinks are not happening, and
cetaceans have well-developed Harderian glands, so blinking "seems unnecessary
for maintaining the moisture of the corneal surface" (Nishimaniwa et al.). That
is an argument for a slow, rare blink, not a measurement of one.

Widely-repeated web claims that whales "blink once every couple of hours" have no
citation and no traceable origin. They are not used.

---

## 7. Body flexibility — why this is modelled as more than a stiff tail

The choice to move the whole animal, rather than confining motion to the rear
third, is grounded in the humpback being genuinely more flexible than the
dolphins the §3 kinematics come from.

> Buchholtz, E. A. (2001). "Vertebral osteology and swimming style in living and
> fossil whales (Order: Cetacea)." *Journal of Zoology* 253(2): 175–190.

Mysticetes retain the archaeocete pattern of near-constant vertebral shape along
the torso, which acts as a single undulatory unit. As quoted in Kot et al. (2022,
*Integrative Organismal Biology* 4(1): obab036), dorsoventral displacement
"began at the chest in a swimming humpback whale," versus being "largely
restricted to the caudal peduncle" in porpoises and white-sided dolphins.

The consequence for this animation is important and honest: because humpbacks are
*more* flexible than the odontocetes measured in §3, the anterior share of the
motion here is plausibly **under**-stated, not over-stated. There is no published
humpback per-body-point number to correct it with, so the odontocete value is
used as-is rather than invented upward.

---

## 8. Summary of parameters and their provenance

| Parameter | Value | Source | Confidence |
|---|---|---|---|
| Body length | 13.5 m | Woodward et al. 2006 (n=128) | Humpback, measured |
| Cruising speed | 2.0 m/s | Gough et al. 2019/2021 | Humpback, measured |
| Tail-beat frequency | ~0.23 Hz | Gough et al. 2019 (n=97) | Humpback, measured |
| Fluke amplitude | 0.20 L p-p | Gough et al. 2019; Bainbridge 1958 | Humpback (n=1) + convention |
| Strouhal number | 0.31 (tuned to f) | Rohr & Fish 2004; Gough 2019 | Reproduces measured f |
| Rostrum amplitude | 19% of fluke | Fish, Peacock & Rohr 2003 | Odontocete, measured |
| Rostrum phase | +20° vs fluke | Fish, Peacock & Rohr 2003 | Odontocete, measured |
| Peduncle phase | leads ~38° | Fish, Peacock & Rohr 2003 | Odontocete, measured |
| Node position | u = 0.28 | Fish 2003; Di Santo 2021; Videler 1984 | Three independent lines |
| Flipper phase lag | 90° trailing | Fish, Peacock & Rohr 2003 | Odontocete, measured |
| Flipper amplitude | small | Segre 2017; Edel & Winn 1978 | Descriptive only |
| Blink mechanism | corner-anchored purse, both lids | Nishimaniwa 2026; Rodrigues 2015 | Anatomy, measured |
| Blink close vs open | faster close | Aiello et al. 2023 | Measured (all tetrapods) |
| Blink interval | 11 s | — | **Artistic choice — no data exists** |
| Blink duration | 0.55 s | — | **Artistic choice — no data exists** |

---

## 9. Where the animation is honestly limited

- **Most per-body-point kinematics are odontocete, not humpback.** The head and
  peduncle phase relations were measured on dolphins, orca and beluga. They are
  the best available and are almost certainly conservative for a humpback (§7),
  but they are not humpback measurements.
- **Flipper cruise motion is extrapolated, not reproduced.** No time series
  exists for any cetacean; only the phase lag is measured (§4).
- **The blink timing is unsourced** because no cetacean measurement exists (§6).
- **A flat sprite cannot rotate in depth.** The source is a three-quarter view,
  so the fluke's angle of attack is faked by the phase lag rather than being a
  real pitch. It holds at the default amplitude and reads as rubber if pushed far
  past it.
- **The Strouhal lock is a control, not a law.** Real whales scale frequency as
  L^−0.53, not the L^−1.0 the lock implies (§1). It is kept because it retimes
  the tail correctly when speed changes, not because the animal obeys it.

---

## Full reference list

1. Aiello, B. R. et al. (2023). "The origin of blinking in both mudskippers and
   tetrapods is linked to life on land." *PNAS* 120(18): e2220404120.
2. Bainbridge, R. (1958). "The speed of swimming of fish as related to size and
   to the frequency and amplitude of the tail beat." *J. Exp. Biol.* 35: 109–133.
3. Borazjani, I. & Sotiropoulos, F. (2010). "On the role of form and kinematics
   on the hydrodynamics of self-propelled body/caudal fin swimming."
   *J. Exp. Biol.* 213: 89–107.
4. Buchholtz, E. A. (2001). "Vertebral osteology and swimming style in living and
   fossil whales (Order: Cetacea)." *J. Zool.* 253(2): 175–190.
   doi:10.1017/S0952836901000164
5. Di Santo, V., Goerig, E., Wainwright, D. K., Akanyeti, O., Liao, J. C.,
   Castro-Santos, T. & Lauder, G. V. (2021). "Convergence of undulatory swimming
   kinematics across a diversity of fishes." *PNAS* 118(49): e2113206118.
6. Edel, R. K. & Winn, H. E. (1978). "Observations on underwater locomotion and
   flipper movement of the humpback whale *Megaptera novaeangliae*."
   *Marine Biology* 48: 279–287.
7. Fish, F. E. (1998). "Comparative kinematics and hydrodynamics of odontocete
   cetaceans: morphological and ecological correlates with swimming performance."
   *J. Exp. Biol.* 201(20): 2867–2877.
8. Fish, F. E. (2002). "Balancing requirements for stability and maneuverability
   in cetaceans." *Integr. Comp. Biol.* 42: 85–93.
9. Fish, F. E. & Battle, J. M. (1995). "Hydrodynamic design of the humpback whale
   flipper." *J. Morphol.* 225(1): 51–60.
10. Fish, F. E., Peacock, J. E. & Rohr, J. J. (2003). "Stabilization mechanism in
    swimming odontocete cetaceans by phased movements." *Marine Mammal Science*
    19(3): 515–528.
11. Gough, W. T., Segre, P. S., Bierlich, K. C., Cade, D. E., Potvin, J., Fish,
    F. E., et al. & Goldbogen, J. A. (2019). "Scaling of swimming performance in
    baleen whales." *J. Exp. Biol.* 222: jeb204172. doi:10.1242/jeb.204172
12. Gough, W. T., Smith, H. J., Savoca, M. S., et al. & Goldbogen, J. A. (2021).
    "Scaling of oscillatory kinematics and Froude efficiency in baleen whales."
    *J. Exp. Biol.* 224(13): jeb237586.
13. Kela, H., de Bie, J., Paas, K. H. W., Stack, S., Franklin, W., Franklin, T. &
    Meynecke, J.-O. (2024). "Assessment of humpback whale swimming speeds in two
    eastern Australian bays." *Marine and Freshwater Research*. doi:10.1071/MF24116
14. Lighthill, M. J. (1960). "Note on the swimming of slender fish." *J. Fluid
    Mech.* 9(2): 305–317.
15. Lighthill, M. J. (1970). "Aquatic animal propulsion of high hydromechanical
    efficiency." *J. Fluid Mech.* 44(2): 265–301.
16. Lyamin, O. I., Mukhametov, L. M. & Siegel, J. M. (2004). Eye-state and
    unihemispheric sleep in the bottlenose dolphin and beluga. *Arch. Ital. Biol.*
    142: 557–568.
17. Maertens, A. P., Gao, A. & Triantafyllou, M. S. (2017). "Optimal undulatory
    swimming for a single fish-like body and for a pair of interacting swimmers."
    *J. Fluid Mech.* 813: 301–345.
18. Meshida, K., Lin, S., Domning, D. P., Reidenberg, J. S., Wang, P. & Gilland,
    E. (2020). "Cetacean Orbital Muscles: Anatomy and Function of the Circular
    Layers." *Anatomical Record*.
19. Nishimaniwa, K., Yamada, T. K., Sekiya, S. I., Amano, M. & Tajima, Y. (2026).
    "Morphological features of the orbicularis oculi muscle and facial nerve in
    four odontocete families, with comparisons within Cetartiodactyla."
    *J. Vet. Med. Sci.* 88(1): 1–12.
20. Rodrigues, F. M. et al. (2015). "Morphology of accessory structures of the
    humpback whale eye (*Megaptera novaeangliae*)." *Acta Zoologica* 96: 328–334.
21. Rohr, J. J. & Fish, F. E. (2004). "Strouhal numbers and optimization of
    swimming by odontocete cetaceans." *J. Exp. Biol.* 207(10): 1633–1642.
22. Videler, J. J. & Hess, H. (1984). "Fast continuous swimming of two pelagic
    predators, saithe and mackerel: a kinematic analysis." *J. Exp. Biol.* 109:
    209–228.
23. Woodward, B. L., Winn, J. P. & Fish, F. E. (2006). "Morphological
    specializations of baleen whales associated with hydrodynamic performance and
    ecological niche." *J. Morphol.* 267: 1284–1294. doi:10.1002/jmor.10474
24. Zhu, Q., Hillmann, D. J. & Henk, W. G. (2000). On the bowhead whale eye.
    *Anatomical Record* 259: 189–204.

---

*Compiled from three literature reviews conducted during the build. Every value
above was traced to the cited work; where a source could only be reached through
a secondary citation (e.g. Videler & Hess 1984, whose fits are quoted via
Borazjani & Sotiropoulos 2010), that is stated inline. The distinction between
measured humpback data, measured odontocete data used for a humpback, and
unsourced artistic choices is maintained throughout — it is the difference
between "true to life" and "looks about right," and this animation tries to be
honest about which is which.*
