# Jury Q&A prep — Q-Hack India 2026

Finale 30–31 Oct, MSRIT Bengaluru. Day 2 is the top-7 pitch plus jury Q&A.

Judging weights: **Technical Implementation 30% · Quantum Relevance 20% ·
Originality 20% · Problem Significance 10% · Potential Impact 10% ·
Presentation 10%.** Half the marks sit in the two columns the jury probes hardest.

**The one rule:** if you don't know, say "we didn't measure that." Naming your own
limits reads as competent. Being caught overclaiming is very hard to recover from
in a live Q&A.

**We now ship TWO models. Keep them straight — a judge will test whether you do:**

- **SARS-CoV-2 specialist** — RBD → ACE2 binding. **2 qubits · 6 layers · 41 params ·
  AUC 0.742 ± 0.002.** Baselines on identical features/split: SVM 0.758 · MLP 0.771 ·
  logistic 0.780.
- **Cross-virus generalist** — 17 proteins, 12 organisms, held out **by protein**.
  **3 qubits · 6 layers · 63 params · AUC 0.681 ± 0.002.** Baselines: logistic 0.676 ·
  SVM 0.683 · MLP 0.684 — we are **level** with all three.

**Other numbers, memorised:**
- Every headline is a **3-seed mean ± sd**, not one seed. Seed spread is ±0.002 on the
  panel (112k rows) and up to ±0.02 on SARS-CoV-2 (2,856 rows) — more data, tighter number.
- Biggest SARS-CoV-2 gain: ACE2 interface distance from PDB 6M0J, +0.065 AUC.
- Biggest cross-virus gain: **burial** (structure-derived), **+0.027 AUC, all 4 held-out
  proteins improved**, restart ranges disjoint.
- Database grew 3,802 → 146,161 rows; 1 → 12 viral organisms; ~28× distinct feature vectors.
- VQE: max error ~1.9e-7 Ha across the H₂ curve (chemical accuracy = 1.6e-3).
- Surveillance: ~40 deposits → ~14 distinct variants; read live counts off the panel.

**If you take one framing in: we did not raise the headline AUC — we halved the qubits
at the same accuracy, and we built a second model that generalises across 12 viruses.
The story is resource efficiency and generalisation, measured honestly.**

---

## Quantum Relevance (20%)

**"Where is the quantum advantage?"**
> There isn't one, and we don't claim one. On raw AUC both models trail the best
> classical baseline on identical features — it's on our results slide. What we
> defend is efficiency: the SARS-CoV-2 model reaches the same accuracy as our
> Round 1 four-qubit version on **two qubits and 41 parameters**, and the
> cross-virus model is level with every classical baseline on three qubits. At
> this width the state is 4–8 dimensional and classically simulable — that's the
> point, every claim is verifiable by hand.

*Never say "quantum explores all possibilities in parallel."* That one phrase can
cost you the room.

**"Walk me through your circuit."**
> Take the SARS-CoV-2 model: four residue features on **two** qubits, using dense
> encoding — two features per qubit, one on the RY axis and one on RZ. Then
> `StronglyEntanglingLayers` applies parameterised rotations and a CNOT ring, and
> the input is re-encoded before every layer (data re-uploading). Six layers. The
> readout is a **trained linear map over the full computational-basis
> distribution** — all four basis probabilities — not a single qubit. The
> cross-virus model is the same recipe with six features on three qubits.

**"Why dense encoding — and why the full-distribution readout?"** ⭐
> Two measured decisions. Angle encoding puts one feature per qubit; six features
> would need six qubits, and we measured that eight qubits hits a barren plateau
> (0.558 AUC, loss stuck). Dense encoding carries two features per qubit, so six
> ride on three — narrower *and* more informative. And we were originally reading
> one qubit through a single Pauli-Z, which throws away the entangled state the
> layers built; a trained linear readout over the whole basis distribution uses
> it. Both changes are why the new model matches the old on half the width.

**"Why data re-uploading?"** *(say what you measured and what you didn't)*
> We took it from the literature (Pérez-Salinas et al. 2020): a single encoding
> followed by entangling layers is limited in what it can express; re-uploading
> makes the circuit a universal approximator. We have **not** run a controlled
> single-encoding comparison on this dataset, so we quote no number for it. That
> ablation is still on the list.

**"Why not more qubits?"** ⭐
> We tested it. More qubits only help if there's more information to carry, and
> we measured eight qubits dropping to 0.640 and eight-qubits-six-layers
> collapsing to 0.558 with the loss stuck — a barren-plateau signature. The
> interesting part is the interaction: those same six layers *helped* at the
> narrow width. So we went the other way — dense encoding to stay narrow, and the
> shipped models are 2 and 3 qubits. Bigger made it worse; smaller-and-smarter
> made it efficient.

**"Does this run on real hardware?"** ⭐ *(stronger answer than Round 1)*
> Not yet, but the circuits are now 2–3 qubits — trivially small for a real
> backend — so it's our immediate next step, not a distant one. We run on
> PennyLane `default.qubit` with a `QVIRA_BACKEND` switch for Qiskit, and we
> report shot noise at 2048 shots so the score carries an error bar. The open
> question on hardware is readout error and transpilation, not qubit count.

---

## Technical Implementation (30%)

**"What are your two models, and your held-out results?"**
> The SARS-CoV-2 specialist: Starr et al. 2020 deep mutational scanning of the
> RBD, label `bind_avg ≥ −1.0`, held-out AUC 0.742 ± 0.002 against 0.758 SVM /
> 0.771 MLP / 0.780 logistic on identical features and split. The cross-virus
> generalist: 17 viral proteins from the ProteinGym benchmark, 146k mutants
> across 12 organisms, held out by protein, AUC 0.681 ± 0.002 — level with all
> three classical baselines.

**"How did you split?"** *(they're checking for leakage)*
> SARS-CoV-2: grouped by **site**, so correlated mutations at one position can't
> leak across the split. Cross-virus: grouped by **protein**, so each test score
> is the model generalising to a virus it never saw in training. Both are the
> harder, honest choice — a random row split would have inflated both numbers by
> ~0.2 AUC, which we measured.

**"Why report AUC and not accuracy?"**
> The SARS-CoV-2 set is 68% positive, so "always yes" scores 0.684 accuracy and
> tells you nothing; AUC separates the models. The panel is balanced at 50%, so
> there majority-class is 0.500 and our 0.63 accuracy is a genuine 0.13 above
> chance — a stronger result than it looks next to the old imbalanced numbers.

**"What's the burial feature, and why does it matter?"** ⭐ *(the Round 2 centrepiece)*
> The SARS-CoV-2 model's strongest feature was ACE2 interface distance — but it's
> measured from one crystal structure and is meaningless for any other virus. Its
> generalisable cousin is **residue burial**: how packed a residue is in its own
> fold, computed from AlphaFold structures. Adding it to the cross-virus model
> gained **+0.027 AUC and improved all four held-out proteins**, with
> non-overlapping restart ranges. And we verified the structure-to-assay join
> residue-by-residue against the wildtype — two proteins whose AlphaFold numbering
> disagreed were detected and dropped rather than trained on as noise.

**"How did you choose features — and does the same set work for both models?"** ⭐
> No, and that's a measured result. Four features are best for SARS-CoV-2;
> adding two made it *overfit* — AUC fell 0.07 while training loss improved, the
> textbook signature. The same two features *help* on the 112k-row panel. The
> optimal feature count scales with the data, so a set chosen on a small dataset
> can't be assumed to transfer. We were briefly fooled by a logistic-regression
> test that favoured six features — logistic regression has seven parameters and
> can't overfit at that scale; our circuit can.

**"Did anything fail, or surprise you?"** ⭐ *answer enthusiastically*
> Several things, and they're the most useful part. One: our first-ever run
> collapsed to the class prior — diagnosed from the loss equalling the prior
> entropy exactly — because whole-sequence-average features made every variant
> look identical. Two: more data didn't raise AUC until it was more *proteins*,
> not more genetic backgrounds — a background panel was 90% feature-vector
> duplicates. Three: narrowing the BLOSUM encoding range, which we were sure
> would help, changed nothing (0.6812 vs 0.6796). We report the nulls because a
> null is a result.

**"Why should I trust a single number from you?"** ⭐
> You shouldn't, which is why we stopped quoting single seeds. Every headline is
> a mean over three random restarts with its spread. On the panel that spread is
> ±0.002; on the smaller SARS-CoV-2 set it's up to ±0.02 — big enough that one
> lucky seed could have "beaten" a baseline, which is exactly why we don't report
> one. More data made the measurement itself trustworthy, tenfold.

**"Is your R₀ predicted?"**
> No. It's a stated linear map from the score onto 0.8–4.0 that makes the SEIR
> panel interactive; we show the mapping. Calling it a prediction would need a
> backtest we haven't run. On the cross-virus tab it's flagged even more
> strongly — SEIR fits a respiratory epidemic, so for an HIV or dengue protein
> it's a generic what-if, shown for comparison only.

**"The VQE — what did you compute, and why is it on both tabs?"**
> H₂ in a minimal basis, 4 qubits, scanned across the dissociation curve and
> benchmarked against exact diagonalisation at every point — max error ~1.9e-7
> Hartree, four orders inside chemical accuracy. It's the same benchmark on both
> model tabs because H₂ is H₂ regardless of virus: it validates the quantum stack
> and marks the honest rung of what runs exactly today. A protein binding pocket
> is ~10⁵ qubits away; any demo claiming a quantum-computed binding energy is
> doing something else.

**"What if your AI copilot hits its rate limit mid-demo?"**
> It falls through — Gemini first, Grok second, any failure moves to the next,
> both with the identical grounding context. It *explains*, it never computes:
> every figure it can quote is passed in from the endpoints, and the prompt
> forbids inventing numbers. Ask it something the run didn't measure and it says
> so — worth demonstrating live.

---

## Originality (20%) and Impact (10%)

**"What's genuinely novel?"**
> Not the VQC — variational classifiers are well explored. What's ours is the
> end-to-end discipline: two models with every baseline, every ablation and every
> *null* result visible; a structural feature verified residue-by-residue; and a
> cross-virus generalist held out by protein. Most pipelines hide the baseline and
> the failures. The honest framing is engineering integration and experimental
> rigour, not a new algorithm.

**"Who would use this?"**
> Surveillance labs triaging which deposited variants deserve wet-lab
> characterisation first — a prioritisation problem that tolerates an imperfect
> score far better than any clinical use would. The cross-virus model widens that
> from SARS-CoV-2 to a dozen organisms.

---

## The dangerous questions

**"Your SARS-CoV-2 model is still worse than logistic regression. Why should we care?"**
> Because we measured it and lead with it. And the Round 2 point isn't the AUC —
> it's that we reached the same accuracy as our four-qubit model on **two qubits
> and 45% fewer parameters**. For near-term quantum, qubit count and depth are the
> scarce resources; halving them at equal accuracy is the engineering result. On
> calibration and top-of-list precision — what a triage tool actually needs — the
> circuit is level with logistic regression.

**"Then why is the cross-virus model's number even lower, at 0.68?"** ⭐
> Different, harder task — don't let the numbers be compared directly. 0.74 is
> within-SARS-CoV-2; 0.68 is predicting a virus the model never saw in training,
> which is strictly harder. On *that* task the circuit is level with every
> classical baseline, and it spans 12 organisms. The honest statement is two
> models answering two questions, each measured properly.

**"This looks AI-generated."**
> We used AI for code generation and review, credited in the README. Every
> modelling decision — both grouped splits, the feature ablations, the burial
> feature and its verification, the dense encoding, the measured nulls — we made
> and measured. Happy to walk any file or re-run any ablation right now. The giveaway
> that it isn't slop: we report three null results and a model that loses on AUC.

**"What if I give it a different virus?"** ⭐ *(answer changed — we built for this)*
> That's exactly what the **Cross-virus** tab is for. We trained a second model
> across 17 proteins from 12 organisms — influenza, HIV-1, dengue, coxsackievirus
> and more — held out by protein, so it's generalising to an unseen virus by
> design. Pick one from the dropdown and score a substitution. The honest limit:
> it only offers those 17 proteins, because its structural feature needs a solved
> structure — it is not a universal scorer for an arbitrary protein, and we say so.

**"Full-length spike but you trained on 201 residues — how do the coordinates line up?"** ⭐
> We hit exactly that bug. The DMS data is indexed by spike site 331–531, so every
> per-site feature is defined within that window; our NCBI reference is
> full-length. A naive index would read site 501 as 39% of the way through instead
> of 85% — same mutation, different feature, silently wrong. The API maps spike
> coordinates into the trained window and flags anything outside 331–531. The
> cross-virus model enforces the same discipline: its burial join is verified
> against each protein's wildtype, and mismatches are dropped, not scored.

**"How do you rank the surveillance feed?"** ⭐
> Not by the highest-scoring mutation — we tried that and it tied everything,
> because a shared Omicron-era background sat in every deposit. We set the shared
> background aside and rank by each deposit's *distinguishing* mutations, which
> produces real separation. The confounder only shows up on real NCBI data.

**"Is the VQE computed live?"**
> No, and the panel says so. It's a real VQE run ahead of time and served from
> JSON — optimising inside the request blocked the server. Max error ~1.9e-7 Ha,
> reproducible from the notebook.

**"You lose on AUC — isn't the resource-efficiency story just spin?"** ⭐
> Test it: our 2-qubit model's `/metrics` reports 41 parameters and AUC 0.742
> against the Round 1 4-qubit/74-param model at 0.747 — same accuracy within the
> ±0.002 seed noise, half the qubits. That's not a framing, it's in the committed
> metrics. For NISQ hardware, where every qubit and gate costs fidelity, that is
> the quantity that matters.

**"Could burial be a fluke of one split?"**
> No — three seeds, and the restart ranges don't overlap: 0.653–0.656 without
> burial, 0.679–0.683 with it. All four held-out proteins improved, and the
> training loss fell too. If it were a lucky split we'd see overlap and a flat
> training loss; we see neither.

**"Can I just open this on my phone?"**
> Yes — hand them the phone. Verified across ten viewports, 44px touch targets,
> 16px form fields so iOS doesn't zoom. Both model tabs work the same.

---

## Showing the model cards live

The masthead opens a **model card** served from `/metrics` — the same JSON the
training run wrote. Open it yourself, early: leading with "here's where our
quantum model loses on AUC, and here's the two-qubit efficiency win beside it"
buys more credibility than any number, and pre-empts the most dangerous question.
Then open the **Cross-virus** tab and score an influenza or HIV mutation live —
that's the Round 2 story in one click.

## Demo failure drill

1. Pre-warm Render ~10 min before (free instances sleep ~50 s).
2. Keep local `npm run dev` + `uvicorn` running as fallback.
3. Keep the 3-min video downloaded, not streamed.
4. If the backend dies the UI shows a banner and **no numbers** — point at it:
   "it refuses to show fabricated output" beats a smooth demo.
5. Have `RESULTS.md`, `metrics.json` and `metrics_panel.json` open as evidence.
6. Check `GET /` and `GET /panel/status` before you start: panel should read
   `available: true`, `n_proteins: 17`.

## Slide checklist (max 10; confirm the cap in the portal)

1. Problem — surveillance triage latency
2. Architecture — two models, one shared circuit definition
3. **Why quantum** — expressivity per parameter, no advantage claimed
4. The circuits — 2 and 3 qubits, dense encoding, re-uploading ansatz
5. **Results** — both models beside their baselines, 3-seed spreads, chance line
6. **The burial feature** — +0.027, all 4 proteins, verified join
7. **What we measured** — feature count scales with data; three null results
8. VQE — H₂ vs exact diagonalisation + the scaling ladder
9. Limitations and roadmap (hardware run next) ← **do not cut**

## Two days before

- [ ] `metrics.json` and `metrics_panel.json` both say `"is_synthetic": false`
- [ ] `GET /panel/status` → `available: true`, 17 proteins
- [ ] Deck numbers match `RESULTS.md` exactly — zero placeholders
- [ ] `bootstrap_gap.py` re-run against the shipped 2-qubit weights (the committed
      JSON is from the old model)
- [ ] Each member can explain one component end to end — and can state which model
      is which
- [ ] Deployed frontend talks to deployed backend; both model tabs load
