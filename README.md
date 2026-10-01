# 🧬 Q-VIRA: Quantum Bio-Threat & Drug Discovery Pipeline
> **Team BioQubit Labs | Quantum Biotech & Chemistry Track | Quantum Week Hackathon**

**Q-VIRA** is a hybrid Quantum-Classical Bio-Quant platform that transforms raw viral RNA sequences into mutation threat scores, real-time SEIR epidemic forecasts, and targeted molecular inhibitor designs.

🔗 **[Live Prototype Demo (Netlify) ->](#)** *(Add your Netlify link here)*  
🎥 **[3-Minute Pitch Video (YouTube/Loom) ->](#)** *(Add your video link here)*

---

## ⚠️ The Problem: Public Health Latency & Classical Limits
When viral pathogens mutate, public health agencies face a **14 to 21-day reporting lag**. By the time CDC data drops, outbreaks have already spread. Furthermore, classical computers (like standard SVMs or classical molecular simulators) struggle to map the massive combinatorial search space of viral mutations and exact fermionic binding energies in real-time.

## 💡 The Solution: Q-VIRA Architecture
We solve this using a pipeline that bridges **Quantum Computing, Computational Biology, and Quantitative Finance**:

1. **Feature Reduction (Classical):** We use Meta's pre-trained ESM-2 protein language model to vectorize raw viral FASTA sequences, using PCA to compress the 1280-dimensional hidden states into a 4-feature tensor.
2. **Threat Predictor (PennyLane VQC):** The tensor is mapped via Angle Encoding into a 4-qubit Variational Quantum Circuit (VQC), which evaluates mutational L2 drift to output a normalized Quantum Threat Score ($S_{threat}$).
3. **Epidemiological Bridge (SEIR):** $S_{threat}$ instantly updates the transmission ($\beta$) parameters of an SEIR differential equation, projecting the Outbreak Velocity ($R_0$) weeks ahead of clinical data.
4. **Vulnerability Discovery (Qiskit VQE):** A Variational Quantum Eigensolver (VQE) simulates the fermionic Hamiltonian of the viral binding pocket, computing the ground state electronic energy ($E_0$) to identify stable small-molecule drug inhibitors.

## 🛠️ Technology Stack
* **Quantum Backend:** PennyLane (VQC), Qiskit Nature (VQE)
* **Biological Embeddings:** Hugging Face `esm2_t33_650M_UR50D`
* **API / Middleware:** FastAPI, Python, SciPy (ODE solver)
* **Frontend UI:** React, Vite, Tailwind CSS, Recharts, py3Dmol
