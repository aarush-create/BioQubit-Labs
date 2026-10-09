/* ===========================================================================
   Plain-English glossary
   ---------------------------------------------------------------------------
   This project cannot avoid technical vocabulary — it scores protein mutations
   with a quantum circuit, and both halves of that sentence are jargon. What it
   can avoid is making a reader go and find out what the words mean before any
   of the page makes sense.

   Every entry here is a term that appears on the page. `plain` is what it means
   in one or two sentences with no other jargon in them, written for someone who
   has no biology and no quantum mechanics. `href` is where to read more, chosen
   to be stable and authoritative rather than merely first in a search: a
   Wikipedia article for an established concept, the primary paper for a method,
   the database record itself for a specific entry.

   Links were checked when this file was written. If one dies, the `plain` text
   is still the definition — the link is extra, not the answer.
   ========================================================================= */

export const GROUPS = {
  biology: 'Biology',
  method: 'How the data is prepared',
  learning: 'Machine learning',
  quantum: 'Quantum computing',
  epi: 'Epidemiology',
};

export const GLOSSARY = {
  /* ------------------------------------------------------------- biology */
  ace2: {
    term: 'ACE2',
    group: 'biology',
    plain: 'A protein on the outside of human cells, mostly in the lungs, gut and blood vessels. SARS-CoV-2 has to grab hold of it to get inside a cell — so it works like a door handle. How tightly a mutated virus can still grab it is the single thing this model predicts.',
    href: 'https://en.wikipedia.org/wiki/Angiotensin-converting_enzyme_2',
    source: 'Wikipedia',
  },
  spike: {
    term: 'spike protein',
    group: 'biology',
    plain: 'The knobbly protein sticking out of the coronavirus surface — the spikes in every picture of the virus. It is the part that touches a human cell, and the part vaccines train your immune system to recognise.',
    href: 'https://en.wikipedia.org/wiki/Coronavirus_spike_protein',
    source: 'Wikipedia',
  },
  rbd: {
    term: 'receptor-binding domain',
    group: 'biology',
    plain: 'The small section at the tip of the spike protein that actually touches ACE2 — about 201 building blocks long, spike positions 331 to 531. It is the only part this model was trained on, because it is the part that does the grabbing.',
    href: 'https://en.wikipedia.org/wiki/Coronavirus_spike_protein',
    source: 'Wikipedia',
  },
  residue: {
    term: 'amino acid',
    group: 'biology',
    plain: 'The building blocks proteins are made of — twenty of them, each written as one letter. A protein is a long chain of them, and a mutation usually means one link in the chain has been swapped for a different one. "Residue" is what one link in the chain is called.',
    href: 'https://en.wikipedia.org/wiki/Amino_acid',
    source: 'Wikipedia',
  },
  substitution: {
    term: 'substitution',
    group: 'biology',
    plain: 'One amino acid in a protein swapped for another. Written as N501Y: the original letter (N), the position along the chain (501), and what it became (Y).',
    href: 'https://en.wikipedia.org/wiki/Point_mutation',
    source: 'Wikipedia',
  },
  wildtype: {
    term: 'wild-type',
    group: 'biology',
    plain: 'The original, unmutated version — here, the virus first sequenced in Wuhan in 2019. Everything else is described as a list of changes away from it.',
    href: 'https://en.wikipedia.org/wiki/Wild_type',
    source: 'Wikipedia',
  },
  epistasis: {
    term: 'epistasis',
    group: 'biology',
    plain: 'When two mutations together do something different from what each does alone — one can rescue, cancel or amplify the other. It is the main reason scoring mutations one at a time is an approximation, and it is known to be a large effect in this protein.',
    href: 'https://en.wikipedia.org/wiki/Epistasis',
    source: 'Wikipedia',
  },
  structure: {
    term: 'crystal structure',
    group: 'biology',
    plain: 'A map of where every atom in a protein actually sits, measured in a laboratory rather than predicted by software. 6M0J is the one used here: the virus spike tip caught in the act of holding on to human ACE2.',
    href: 'https://www.rcsb.org/structure/6M0J',
    source: 'RCSB Protein Data Bank',
  },
  pdb: {
    term: 'Protein Data Bank',
    group: 'biology',
    plain: 'The free public archive where solved protein structures are deposited. Every entry has a four-character code — 6M0J is the spike–ACE2 pair this project measures distances from.',
    href: 'https://en.wikipedia.org/wiki/Protein_Data_Bank',
    source: 'Wikipedia',
  },

  /* -------------------------------------------------------------- method */
  dms: {
    term: 'deep mutational scanning',
    group: 'method',
    plain: 'A laboratory technique that builds thousands of mutant versions of a protein at once and measures what each one does. It is where this project’s 4,221 training measurements come from — every one of them a real experiment, not a prediction.',
    href: 'https://pubmed.ncbi.nlm.nih.gov/25075907/',
    source: 'Fowler & Fields, Nature Methods 2014',
  },
  starr: {
    term: 'Starr et al. 2020',
    group: 'method',
    plain: 'The published study this model learned from. It measured, for thousands of single mutations in the spike tip, how well each one still bound ACE2. Those measurements are the ground truth here.',
    href: 'https://doi.org/10.1016/j.cell.2020.08.012',
    source: 'Cell, 2020',
  },
  ncbi: {
    term: 'NCBI',
    group: 'method',
    plain: 'The US National Center for Biotechnology Information — the public database labs upload new virus sequences to. The surveillance feed on this site reads from it directly.',
    href: 'https://www.ncbi.nlm.nih.gov/',
    source: 'ncbi.nlm.nih.gov',
  },
  accession: {
    term: 'accession',
    group: 'method',
    plain: 'The permanent ID a sequence gets when it is deposited in a public database, like a catalogue number. It is how you find that exact record again.',
    href: 'https://en.wikipedia.org/wiki/Accession_number_(bioinformatics)',
    source: 'Wikipedia',
  },
  alignment: {
    term: 'sequence alignment',
    group: 'method',
    plain: 'Lining two protein sequences up side by side so you can see where they differ. It is how we work out which positions a newly uploaded virus has changed, rather than assuming the two chains start at the same place.',
    href: 'https://en.wikipedia.org/wiki/Sequence_alignment',
    source: 'Wikipedia',
  },
  smithwaterman: {
    term: 'Smith–Waterman',
    group: 'method',
    plain: 'The standard algorithm for lining up the best-matching stretch of two sequences. It is slower than the shortcuts most tools use, and it is guaranteed to find the best alignment rather than a good guess.',
    href: 'https://en.wikipedia.org/wiki/Smith%E2%80%93Waterman_algorithm',
    source: 'Wikipedia',
  },
  blosum: {
    term: 'BLOSUM62',
    group: 'method',
    plain: 'A scoring table that says how surprising each amino-acid swap is, based on how often it shows up in related real proteins. It stops the alignment treating a common, harmless swap the same as a drastic one.',
    href: 'https://en.wikipedia.org/wiki/BLOSUM',
    source: 'Wikipedia',
  },
  fasta: {
    term: 'FASTA',
    group: 'method',
    plain: 'The plain-text format protein and DNA sequences are normally shared in: a title line, then the sequence as a run of letters.',
    href: 'https://en.wikipedia.org/wiki/FASTA_format',
    source: 'Wikipedia',
  },

  /* ------------------------------------------------------------ learning */
  rocauc: {
    term: 'ROC-AUC',
    group: 'learning',
    plain: 'A score for how well a model sorts things into the right order. Pick one binder and one non-binder at random: ROC-AUC is the probability the model ranks the binder higher. 0.5 means it is guessing; 1.0 means it is never wrong. Unlike accuracy, it cannot be faked by always giving the same answer.',
    href: 'https://en.wikipedia.org/wiki/Receiver_operating_characteristic',
    source: 'Wikipedia',
  },
  heldout: {
    term: 'held-out',
    group: 'learning',
    plain: 'Data deliberately kept back during training and only used at the end, to check the model learned something general instead of memorising its examples. Every score quoted here is on held-out data.',
    href: 'https://en.wikipedia.org/wiki/Training,_validation,_and_test_data_sets',
    source: 'Wikipedia',
  },
  ablation: {
    term: 'ablation',
    group: 'learning',
    plain: 'Removing one piece of a model and re-measuring, to find out whether that piece was doing any work. It is how the four inputs here were chosen: we started with eight and took away the ones that did not help.',
    href: 'https://en.wikipedia.org/wiki/Ablation_(artificial_intelligence)',
    source: 'Wikipedia',
  },
  baseline: {
    term: 'classical baseline',
    group: 'learning',
    plain: 'An ordinary, non-quantum method run on exactly the same data, so there is something to compare the quantum model against. Without one, a quantum result is just a number with nothing to measure it by.',
    href: 'https://en.wikipedia.org/wiki/Logistic_regression',
    source: 'Wikipedia',
  },
  logistic: {
    term: 'logistic regression',
    group: 'learning',
    plain: 'One of the simplest and oldest prediction methods there is: weigh up each input, add them together, turn the total into a probability. It is the strongest performer on this dataset.',
    href: 'https://en.wikipedia.org/wiki/Logistic_regression',
    source: 'Wikipedia',
  },
  mlp: {
    term: 'neural network',
    group: 'learning',
    plain: 'A model that stacks layers of simple units so it can learn curved, non-obvious relationships. The small one used here is called a multilayer perceptron.',
    href: 'https://en.wikipedia.org/wiki/Multilayer_perceptron',
    source: 'Wikipedia',
  },
  svm: {
    term: 'support vector machine',
    group: 'learning',
    plain: 'A method that looks for the dividing line that leaves the widest possible margin between the two groups it is separating.',
    href: 'https://en.wikipedia.org/wiki/Support_vector_machine',
    source: 'Wikipedia',
  },

  /* ------------------------------------------------------------- quantum */
  qubit: {
    term: 'qubit',
    group: 'quantum',
    plain: 'The quantum version of a bit. A bit is 0 or 1; a qubit can hold a blend of both at once, and several qubits can be linked so their blends depend on each other. Four of them is a very small quantum computer — it is simulated here, not run on quantum hardware.',
    href: 'https://en.wikipedia.org/wiki/Qubit',
    source: 'Wikipedia',
  },
  vqc: {
    term: 'variational circuit',
    group: 'quantum',
    plain: 'A quantum circuit with adjustable dials. You run it, see how wrong the answer is, nudge the dials, and repeat — the same training loop ordinary machine learning uses, with a quantum circuit in the middle. This one has 74 dials.',
    href: 'https://pennylane.ai/qml/glossary/variational_circuit',
    source: 'PennyLane',
  },
  reupload: {
    term: 'data re-uploading',
    group: 'quantum',
    plain: 'Feeding the same input into the circuit again at every layer instead of only once at the start. It lets a circuit with very few qubits represent more complicated patterns than it otherwise could.',
    href: 'https://arxiv.org/abs/1907.02085',
    source: 'Pérez-Salinas et al., 2020',
  },
  pauliz: {
    term: 'Pauli-Z',
    group: 'quantum',
    plain: 'One of the standard measurements you can make on a qubit: it asks, in effect, "how much of this qubit is pointing towards 0 rather than 1?" and answers with a number between +1 and −1. This model’s score is that number, read off the first qubit.',
    href: 'https://en.wikipedia.org/wiki/Pauli_matrices',
    source: 'Wikipedia',
  },
  expval: {
    term: 'expectation value',
    group: 'quantum',
    plain: 'The average answer you would get if you measured the same quantum state over and over. A single measurement is random; the average is not, and it is what the model actually uses.',
    href: 'https://en.wikipedia.org/wiki/Expectation_value_(quantum_mechanics)',
    source: 'Wikipedia',
  },
  basisstate: {
    term: 'basis state',
    group: 'quantum',
    plain: 'One of the plain, definite settings the qubits could be found in — 0000, 0001, and so on. Four qubits have 16 of them, and the quantum state is a blend of all 16 at once. The chart shows how much of the blend sits in each.',
    href: 'https://en.wikipedia.org/wiki/Qubit',
    source: 'Wikipedia',
  },
  vqe: {
    term: 'VQE',
    group: 'quantum',
    plain: 'Variational quantum eigensolver — a quantum algorithm for finding the lowest energy a molecule can have. It is the most realistic near-term use of quantum computers in chemistry, and it is what the chemistry panel runs.',
    href: 'https://en.wikipedia.org/wiki/Variational_quantum_eigensolver',
    source: 'Wikipedia',
  },
  hamiltonian: {
    term: 'Hamiltonian',
    group: 'quantum',
    plain: 'The mathematical description of all the energy in a system — here, the push and pull between a molecule’s electrons and nuclei. Finding its lowest value is finding the molecule’s resting state.',
    href: 'https://en.wikipedia.org/wiki/Molecular_Hamiltonian',
    source: 'Wikipedia',
  },
  diagonalization: {
    term: 'exact diagonalization',
    group: 'quantum',
    plain: 'Solving the energy problem by brute force, with no approximation. It only works for tiny systems, which is exactly why a two-atom molecule is useful: we can get the true answer and check the quantum one against it.',
    href: 'https://en.wikipedia.org/wiki/Exact_diagonalization',
    source: 'Wikipedia',
  },
  sto3g: {
    term: 'STO-3G',
    group: 'quantum',
    plain: 'The simplest standard way of describing where a molecule’s electrons can be — the smallest set of shapes that still gives sensible chemistry. Choosing it keeps this calculation small enough to check exactly.',
    href: 'https://en.wikipedia.org/wiki/STO-nG_basis_sets',
    source: 'Wikipedia',
  },
  jordanwigner: {
    term: 'Jordan–Wigner',
    group: 'quantum',
    plain: 'The standard recipe for turning a chemistry problem about electrons into something a set of qubits can represent. It is the translation step between the molecule and the quantum computer.',
    href: 'https://en.wikipedia.org/wiki/Jordan%E2%80%93Wigner_transformation',
    source: 'Wikipedia',
  },
  hartreefock: {
    term: 'Hartree–Fock',
    group: 'quantum',
    plain: 'The standard first approximation in quantum chemistry: pretend each electron feels only the average of all the others, rather than dodging them individually. It is close, but it misses real energy — and that missing part is what VQE is trying to recover.',
    href: 'https://en.wikipedia.org/wiki/Hartree%E2%80%93Fock_method',
    source: 'Wikipedia',
  },
  correlation: {
    term: 'correlation energy',
    group: 'quantum',
    plain: 'The energy Hartree–Fock misses because electrons really do avoid each other rather than feeling an average. It is small, but it is the part that decides most interesting chemistry.',
    href: 'https://en.wikipedia.org/wiki/Electronic_correlation',
    source: 'Wikipedia',
  },
  hartree: {
    term: 'hartree (Ha)',
    group: 'quantum',
    plain: 'The natural unit of energy in atomic physics. One hartree is about 27.2 electronvolts — roughly the energy holding an electron onto a hydrogen atom.',
    href: 'https://en.wikipedia.org/wiki/Hartree',
    source: 'Wikipedia',
  },
  chemacc: {
    term: 'chemical accuracy',
    group: 'quantum',
    plain: 'The agreed threshold for a computed energy being good enough to predict real chemistry: within 1.6×10⁻³ hartree of the true value, about 1 kcal/mol. Below it, the calculation can be trusted to say which reaction wins.',
    href: 'https://en.wikipedia.org/wiki/Hartree',
    source: 'Wikipedia',
  },
  angstrom: {
    term: 'ångström (Å)',
    group: 'quantum',
    plain: 'A length unit used for atoms: one ten-billionth of a metre. Two bonded hydrogen atoms sit about 0.74 Å apart.',
    href: 'https://en.wikipedia.org/wiki/Angstrom',
    source: 'Wikipedia',
  },
  activespace: {
    term: 'active space',
    group: 'quantum',
    plain: 'Picking the handful of electrons that matter for the chemistry you care about and treating only those carefully, while handling the rest cheaply. It is how quantum chemistry gets anything useful out of a molecule too big to solve whole.',
    href: 'https://en.wikipedia.org/wiki/Complete_active_space',
    source: 'Wikipedia',
  },
  qmmm: {
    term: 'QM/MM',
    group: 'quantum',
    plain: 'Treating the small, chemically interesting part of a large molecule with full quantum mechanics and the rest with cheap classical physics. The standard way to study a reaction inside a protein.',
    href: 'https://en.wikipedia.org/wiki/QM/MM',
    source: 'Wikipedia',
  },

  /* ----------------------------------------------------------------- epi */
  seir: {
    term: 'SEIR model',
    group: 'epi',
    plain: 'A textbook outbreak model that sorts everyone into four buckets — Susceptible, Exposed, Infected, Recovered — and describes how fast people move between them. It is a teaching tool, deliberately simple: it assumes everyone mixes with everyone evenly and that nothing is ever done to stop the spread.',
    href: 'https://en.wikipedia.org/wiki/Compartmental_models_in_epidemiology',
    source: 'Wikipedia',
  },
  r0: {
    term: 'R₀',
    group: 'epi',
    plain: 'How many people one infected person passes the disease to on average, when nobody is immune and nothing is being done about it. Below 1 the outbreak dies out; above 1 it grows.',
    href: 'https://en.wikipedia.org/wiki/Basic_reproduction_number',
    source: 'Wikipedia',
  },
  attackrate: {
    term: 'attack rate',
    group: 'epi',
    plain: 'The share of the population that catches the disease over the whole outbreak.',
    href: 'https://en.wikipedia.org/wiki/Attack_rate',
    source: 'Wikipedia',
  },
  herd: {
    term: 'herd immunity threshold',
    group: 'epi',
    plain: 'The fraction of a population that has to be immune before each infection stops causing more than one more, and the outbreak starts shrinking on its own.',
    href: 'https://en.wikipedia.org/wiki/Herd_immunity',
    source: 'Wikipedia',
  },
};

/** Entries grouped for the glossary list, in the order GROUPS declares. */
export function glossaryByGroup() {
  return Object.entries(GROUPS).map(([key, label]) => [
    label,
    Object.entries(GLOSSARY)
      .filter(([, v]) => v.group === key)
      .sort((a, b) => a[1].term.localeCompare(b[1].term)),
  ]);
}
