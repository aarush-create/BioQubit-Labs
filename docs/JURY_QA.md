# Jury Q&A prep — Q-Hack India 2026

Finale 30–31 Oct, MSRIT Bengaluru. Day 2 is the top-7 pitch plus jury Q&A.

Judging weights: **Technical Implementation 30% · Quantum Relevance 20% ·
Originality 20% · Problem Significance 10% · Potential Impact 10% ·
Presentation 10%.** Half the marks sit in the two columns the jury probes hardest.

**The one rule:** if you don't know, say "we didn't measure that." Naming your own
limits reads as competent. Being caught overclaiming is very hard to recover from
in a live Q&A.

**Your numbers, memorised:**
- Surveillance: ~40 deposits → ~14 distinct variants · ~11 mutations shared by all
  (the feed refreshes itself, so read the live counts off the panel, not from memory)
- Top distinguishing: L441I 0.871 · K444R 0.868 · K417N 0.849
- VQE: max error 1.9e-7 Ha across the H₂ curve (chemical accuracy = 1.6e-3)
- VQC held-out **AUC 0.747** · 4 qubits · 6 layers · 74 parameters
- Baselines on identical features: **SVM 0.750 (we are within 0.004)** · MLP 0.766 · logistic 0.780
- Biggest single gain: ACE2 interface distance from PDB 6M0J, +0.065 AUC (0.682 → 0.747)
- Chance = 0.500 · majority-class accuracy = 0.684
- Train 2,856 rows / 151 sites · Test 946 rows / 50 sites · site-grouped split

---

## Quantum Relevance (20%)

**"Where is the quantum advantage?"**
> There isn't one, and we don't claim one. Our VQC reaches 0.747 AUC; on the same
> features the SVM gets 0.750, the MLP 0.766 and logistic regression 0.780. We
> place fourth of five, and it's on our results slide. At 4 qubits the state is 16-dimensional and classically simulable. This
> is a feasibility study, and the value is in what the ablations taught us about
> the circuit, not in beating sklearn.

*Never say "quantum explores all possibilities in parallel."* That one phrase can
cost you the room.

**"Then why use a quantum circuit at all?"**
> Because the question we can answer at this scale is whether the model structure
> behaves sensibly, and that has to be settled at simulable size before anything
> larger is worth attempting. We got three measured answers that generalise:
> width should match feature count, depth hurts before it helps, and data
> width should match feature count, structure beats more chemistry, and depth
> and width interact rather than acting independently.

**"Walk me through your circuit."**
> 4 qubits, one per feature. Each descriptor is angle-encoded as an RY rotation,
> then `StronglyEntanglingLayers` applies parameterised rotations plus a ring of
> CNOTs. The input is re-encoded before every layer — data re-uploading. We
> measure ⟨Z⟩ on wire 0 and pass it through a trained sigmoid calibration.
> 6 layers, 74 parameters total.

**"Why data re-uploading?"** *(say what you measured and what you didn't)*
> We took it from the literature, not from our own ablation. A single encoding
> followed by entangling layers is limited in the functions it can express;
> re-uploading makes the circuit a universal approximator (Pérez-Salinas et al.
> 2020). We have **not** run a controlled single-encoding comparison on this
> dataset, so we don't quote a number for what it bought us. That ablation is on
> the Round 2 list.

*An earlier draft of our repo did quote a figure here. It wasn't reproducible
from any committed script, so we withdrew it rather than defend it. If anyone
has seen that number in an old version, say exactly this — it is a better
answer than the number was.*

**"Why not more qubits?"** ⭐ *your strongest answer*
> We tested it. Angle encoding puts one feature per qubit, so qubits only help if
> there's more information to carry. At the time our 4-feature model scored 0.672;
> going to 8 features on 8 qubits DROPPED it to 0.640. We also doubled the depth
> at 8 qubits — 6 layers scored 0.558 against 0.640 for 3 layers, and the deeper
> circuit never trained below 0.556 loss. That's consistent with barren plateaus.
> Note the interaction, because it's the interesting part: those same 6 layers
> HELPED at 4 qubits, 0.672 to 0.682. Depth isn't good or bad on its own — a
> wider circuit hits trainability problems at a depth a narrower one tolerates.
> Bigger made it worse, twice, but only once we were already too wide.

**"Does this run on real hardware?"**
> Not yet — PennyLane `default.qubit`, with a `QVIRA_BACKEND` switch for Qiskit
> Aer. We report shot noise at 2048 shots, so the score carries an error bar.
> Hardware is next, and the question there is transpilation depth and readout
> error, not qubit count.

---

## Technical Implementation (30%)

**"What data, and what's your held-out result?"**
> Starr et al. 2020 deep mutational scanning of the SARS-CoV-2 RBD — 4,221 single
> mutants, each measured for ACE2 binding. Label is `bind_avg >= -1.0`. Held-out
> AUC 0.747 for the VQC, against 0.750 SVM / 0.766 MLP / 0.780 logistic on
> identical features and the identical split.

**"How did you split?"** *(they're checking for leakage)*
> Grouped by site, not by row. Mutations at one position are highly correlated,
> so a random row split leaks and inflates the metric. 151 train sites, 50 test
> sites, no overlap.

**"Why report AUC and not accuracy?"**
> The dataset is 68% positive, so a model that always answers "yes" scores 0.684
> accuracy. Every model we trained lands near 0.70 accuracy, which tells you
> nothing. AUC separates them. That's also why `majority_class` is in our table.

**"What are your features?"**
> BLOSUM62 substitution score, wild-type residue volume, change in volume, and
> relative position in the chain. We compute eight and use four — selected by
> ablation, not intuition.

**"How did you choose those four?"** ⭐
> We measured every subset. BLOSUM62 alone gives 0.655. Adding wild-type volume
> takes it to 0.705, relative position to 0.754, delta volume to 0.757. Adding
> the remaining four descriptors made it *worse* — 0.714. The ones we dropped —
> delta hydropathy at 0.504 AUC alone, delta charge at 0.518 — are close to noise,
> and each costs a qubit.

**"Isn't BLOSUM62 doing all the work?"**
> It's the strongest single feature, but no. Alone it's 0.655; the full set is
> 0.757. And the clearest counterexample is relative position: it scores only
> 0.602 on its own, yet removing it from the full set costs more AUC than
> removing anything else. Univariate importance misled us, and we have the
> drop-one-out table.

**"Did anything fail?"** ⭐ *answer this one enthusiastically*
> Yes, and it's the most useful thing we did. Our first run plateaued at 0.5866
> loss and never moved. That value is exactly the entropy of the class prior,
> 0.5862 — the model had collapsed to predicting the base rate. The cause was our
> featuriser: it used whole-sequence averages, and a single substitution in a
> 201-residue protein shifts those by under 0.05 radians out of a π range. Every
> variant was the same input. We switched to substitution-level descriptors.

**"Is your R₀ predicted?"**
> No. It's a stated linear map from the score onto 0.8–4.0, and we show the
> mapping. It makes the SEIR panel interactive. Calling it a prediction would
> need a backtest we haven't run.

**"Your SEIR assumptions?"**
> Deterministic, homogeneous mixing, constant R₀, no interventions, no waning
> immunity. β = R₀γ, σ = 1/5 d, γ = 1/7 d, integrated with RK45. A scenario.

**"The VQE — what did you compute?"**
> H₂ in STO-3G, 4 qubits, UCCSD-style ansatz, scanned across the dissociation
> curve and benchmarked against exact diagonalisation at every point. Max error
> 1.45e-7 Hartree, four orders inside chemical accuracy.

**"Why not a binding pocket?"**
> ~10⁵ qubits in a minimal basis, before error correction. Any demo claiming a
> quantum-computed protein-ligand binding energy is doing something else.

**"What happens if your AI copilot hits its rate limit while I'm watching?"** ⭐
> It falls through. The copilot runs a provider chain — Gemini first, Grok second
> — and any failure moves to the next one: a 429, a quota reset, a timeout, even
> a model being renamed under us. Both providers get the identical system prompt
> and the identical grounding context, so the answer doesn't change character
> when it falls through, and the reply tells you which one served it. Either key
> alone is enough to run.
>
> It's the one part of the app that depends on someone else's server, which is
> exactly why it has a fallback and the rest of the app doesn't need one.

**"Isn't an LLM in the loop just a way to fabricate numbers?"**
> It would be, if it computed anything. It doesn't. Every figure it can quote is
> passed in as context from the endpoints that computed it, and the system prompt
> forbids inventing figures and tells it to say so when the answer isn't in the
> context. Ask it something the run didn't measure and it will tell you it
> doesn't have it — that's worth demonstrating live.

**"What breaks if NCBI is down during your demo?"**
> Nothing visible. The feed is served from memory and the refresh runs on a
> worker thread, so a failed fetch leaves the previous payload on screen and
> reports the error rather than blanking the panel. Same principle everywhere in
> the demo path: the copilot has a second provider, the feed has its committed
> cache, and `/predict` returns a 503 with an explanation rather than a
> plausible-looking number.

---

## Originality (20%) and Impact (10%)

**"Why not just use Nextstrain or the CDC?"**
> Complementary. Nextstrain tells you what *has* spread, from assembled genomes.
> We score a substitution the moment it's deposited. We'd consume Nextstrain, not
> replace it.

**"What's genuinely novel?"**
> Not the VQC — variational classifiers are well explored. What's ours is the
> end-to-end path from substitution to scenario with the uncertainty, the
> classical baseline and the failed configurations all visible. Most pipelines
> hide the baseline. The honest framing is engineering integration and
> experimental discipline, not a new algorithm.

**"Who would use this?"**
> Surveillance labs triaging which deposited variants deserve wet-lab
> characterisation first. That's a prioritisation problem, and it tolerates an
> imperfect score far better than any clinical use would.

---

## The dangerous questions

**"Your model is worse than logistic regression. Why should we care?"**
> Because we measured it and reported it. The project is a controlled study of
> whether a variational circuit is viable on this task at a scale where every
> claim is verifiable. The answer is "not yet, and here is exactly how much not
> yet." A team that reported only a quantum number would be hiding this.

**"This looks AI-generated."**
> We used Gemini 3.1 Pro and Claude for code generation and review, credited in
> the README. Every modelling decision — the site-grouped split, the feature
> ablation, the depth ablation, the re-uploading ansatz — we made and measured.
> Happy to walk through any file, or re-run any ablation right now.

*Rehearse calmly. It's only damaging if you look caught.*

**"What if I give it a different virus?"** ⭐
> It will return a score, because the features are generic residue chemistry —
> but that score is out of distribution and unvalidated. We trained only on
> SARS-CoV-2 RBD binding to human ACE2. Influenza binds sialic acid, Ebola binds
> NPC1 — different locks entirely. And our `ace2_distance` feature is a literal
> measurement from the SARS-CoV-2 RBD/ACE2 crystal structure, 6M0J — there is no
> such distance in another protein.
> The model cannot detect this itself: we verified it returns an *identical*
> score for the same substitution on a SARS reference and an Ebola reference.
> So the interface flags it instead. Pick Ebola in the dropdown and you'll see
> the warning. Validating on a second virus needs that virus's own DMS dataset.

**"Your reference is the full 1,273-residue spike but you trained on 201 residues. How do the coordinates line up?"** ⭐
> Good question — we hit exactly that bug. The DMS data is indexed by spike site
> 331–531, so every per-site feature is defined *within* that 201-residue window.
> Our NCBI reference is the full-length spike, so a naive index would read site
> 501 as 0.393 of the way through instead of 0.846 — same mutation, completely
> different feature value, silently wrong scores. The API now maps spike
> coordinates back into the trained window, and flags any substitution outside
> 331–531 as extrapolation. The same frame is what lets `ace2_distance` look up
> the right residue in 6M0J.

**"Is the surveillance feed live?"** ⭐
> It refreshes itself, but a page load never waits on NCBI. The committed cache
> is a seed; once the feed passes twelve hours old a background thread re-queries
> NCBI and swaps the fresh result in, so the timestamp moves on its own. The
> panel shows the real fetch time and how old it is — never a page-load time
> dressed up as live. There's also a button that fires the fetch on demand.
>
> We built it that way because NCBI is rate-limited and our host's filesystem is
> ephemeral: a synchronous fetch on page load is a demo that hangs in front of
> you. The pipeline behind it is real — deposited SARS-CoV-2 spikes, aligned
> against Wuhan-Hu-1, substitutions extracted, the ones inside sites 331–531
> scored by the trained VQC. Sequences we can't align past 80% coverage are
> skipped and the count is *reported*, not quietly dropped.

**"How do you rank the surveillance feed?"** ⭐
> Not by the highest-scoring mutation — we tried that and it ranked nothing.
> In the batch where we found this, 22 RBD mutations were present in every single
> deposit — the Omicron-era inheritance — so all 11 distinct variants tied at
> exactly 0.910 on R403K. The exact counts move as the feed refreshes; the
> confounder doesn't. We now
> set aside the shared background and rank by each deposit's *distinguishing*
> mutations. That produces real separation: L441I at 0.871, K444R at 0.868,
> K417N at 0.849. The shared background is the signal's biggest confounder and
> it only appears when you run real data.

**"Is the VQE computed live?"**
> No, and the panel says so. It is a real VQE — same optimiser, same circuit —
> but run ahead of time by `build_vqe_data.py` and served from JSON. We had it
> optimising inside the request and it blocked the server, making the tab
> unusable. Max error across the dissociation curve is 1.9e-7 Hartree, four
> orders inside chemical accuracy. Every point is reproducible with the notebook,
> and the API still accepts `live: true` if you want to watch it run.

**"Should you just add more residue descriptors?"** ⭐
> We measured that, and more chemistry made it worse: 8 descriptors scored 0.640
> against 0.682 for the best 4. The missing information was not chemical but
> spatial — none of our features knew where in the FOLDED protein a mutation
> sits, and for ACE2 binding that dominates. So we computed each residue's
> distance to ACE2 from the experimental complex 6M0J. It validated cleanly: our
> <4.5 A set reproduces all 17 literature ACE2-contact residues. Alone it scores
> 0.714, our strongest single feature, and it took the VQC from 0.682 to 0.747 —
> within 0.004 of the SVM. One number per site, zero runtime cost, and it REPLACED a
> feature rather than being added, so we stayed at 4 qubits.

**"Why doesn't your quantum model match the classical ones?"** ⭐
> We tested whether it was under-training. Doubling depth (3→6 layers) and
> tripling epochs took us from 0.672 to 0.682 — only +0.010 — while the training
> loss fell much further, 0.499 to 0.464. Fitting the training set better without generalising
> better means we are near the ceiling of the representation, not short of
> optimisation. With only four residue descriptors there is a cap around 0.74 —
> where the MLP sits — and a 4-qubit circuit read out through a single Pauli-Z
> does not reach it. The fix is a richer representation, ESM-2 embeddings, not a
> bigger circuit. We also found depth interacts with width: 6 layers helped at
> 4 qubits and badly hurt at 8 (0.558), which is the barren-plateau behaviour.

**"What happens at residues your crystal structure does not cover?"** ⭐
> They get a far-field fallback distance, and we caught that biasing a real run.
> 6M0J covers RBD 333-526, so sites 331-332 and 527-531 have no measurement. The
> fallback reads as "far from the interface", which the model scores highly — and
> on one NCBI batch the top-ranked drivers were exactly those unresolved sites.
> We now flag them, mark them with an asterisk, and exclude them from ranking
> while still displaying them. Promoting missing data to the top of a triage list
> is the specific failure mode a surveillance tool must not have.

**"Could it generalise at all?"**
> Possibly, partially. BLOSUM62 carries general signal about destabilising
> substitutions in any protein. But we have zero measurements outside
> SARS-CoV-2, so we don't claim it. That's a roadmap item, not a result.

**"Show me it working on a mutation I pick."**
> Have this ready. Warm Render first. If they name a mutation that doesn't match
> the reference, the API says so and names the actual residue — demo that, it
> looks good. The ablation flags also let you re-run a losing config live.

---

## Showing the model card live

The masthead shows the held-out AUC and opens a **model card** served from
`/metrics` — the same JSON the training run wrote, not typed by hand. It draws
every model as a ranked bar, with ours sitting fourth of five and a note saying
so.

Open it yourself, early, before anyone asks. Leading with "here is where our
quantum model loses" buys more credibility than any number you could show, and
it pre-empts the single most dangerous question in the room.

## Demo failure drill

1. Pre-warm Render ~10 min before. Free instances sleep.
2. Keep local `npm run dev` + `uvicorn` running as the fallback.
3. Keep the 3-min video downloaded, not streamed.
4. If the backend dies the UI shows a red banner and **no numbers**. Point at it:
   "it refuses to show fabricated output" is a better moment than a smooth demo.
5. Have `RESULTS.md` and `metrics.json` open in tabs — that's your evidence.

## Slide checklist (max 10; FAQ says 8 — confirm in the portal)

1. Problem — surveillance triage latency
2. Architecture diagram
3. **Why quantum** — expressivity per parameter, no advantage claimed
4. The circuit — 4 qubits, 6 layers, re-uploading ansatz (no number claimed for it)
5. **Results** — VQC 0.747 beside all baselines, chance line marked
6. **Ablations** — structure vs chemistry, features 4 vs 8, depth x width, the flat-loss failure
7. VQE — H₂ vs exact diagonalisation, plus the scaling table
8. Limitations and roadmap ← **do not cut this slide**

## Two days before

- [ ] `metrics.json` says `"is_synthetic": false`
- [ ] `python build_panel.py` run; `reference_panel.json` committed
- [ ] Every accession and PDB ID checked against its label
- [ ] Deck numbers match `RESULTS.md` exactly — zero placeholders
- [ ] Each member can explain one component end to end
- [ ] Deployed frontend talks to deployed backend (check CORS)
