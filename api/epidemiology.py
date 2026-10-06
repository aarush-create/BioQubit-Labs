"""
SEIR compartmental model.

The original dashboard drew `100 * R0^(day/8)` and called it SEIR. That is a
bare exponential: no compartments, no susceptible depletion, so it never
peaks and never turns over. This module integrates the actual ODE system.

    dS/dt = -beta * S * I / N
    dE/dt =  beta * S * I / N - sigma * E
    dI/dt =  sigma * E - gamma * I
    dR/dt =  gamma * I

with beta = R0 * gamma, sigma = 1/incubation_period, gamma = 1/infectious_period.

IMPORTANT FRAMING: this is a scenario projection under a fixed R0, not a
forecast. It assumes a homogeneous well-mixed population and no interventions.
Say that out loud in the pitch -- a judge who does epidemiology will ask, and
"it's a scenario under stated assumptions" is a much stronger answer than
claiming prediction.
"""

from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp


def _deriv(t, y, beta, sigma, gamma, N):
    S, E, I, R = y
    new_infections = beta * S * I / N
    return [
        -new_infections,
        new_infections - sigma * E,
        sigma * E - gamma * I,
        gamma * I,
    ]


def simulate(
    r0: float,
    population: int = 1_000_000,
    incubation_days: float = 5.0,
    infectious_days: float = 7.0,
    initial_infected: int = 10,
    days: int = 180,
    hospitalisation_rate: float = 0.04,
    hospital_capacity: int = 2500,
) -> dict:
    """Integrate the SEIR system and return curves plus derived indicators."""
    if r0 <= 0:
        raise ValueError("r0 must be positive")
    if incubation_days <= 0 or infectious_days <= 0:
        raise ValueError("incubation_days and infectious_days must be positive")
    if initial_infected >= population:
        raise ValueError("initial_infected must be smaller than population")

    sigma = 1.0 / incubation_days
    gamma = 1.0 / infectious_days
    beta = r0 * gamma
    N = float(population)

    y0 = [N - initial_infected, 0.0, float(initial_infected), 0.0]
    t_eval = np.arange(0, days + 1, dtype=float)

    sol = solve_ivp(
        _deriv,
        (0.0, float(days)),
        y0,
        args=(beta, sigma, gamma, N),
        t_eval=t_eval,
        method="RK45",
        rtol=1e-6,
        atol=1e-3,
    )
    if not sol.success:
        raise RuntimeError(f"SEIR integration failed: {sol.message}")

    S, E, I, R = sol.y
    hospitalised = I * hospitalisation_rate

    peak_idx = int(np.argmax(I))
    over = np.where(hospitalised > hospital_capacity)[0]

    curve = [
        {
            "day": int(t),
            "susceptible": int(S[i]),
            "exposed": int(E[i]),
            "infected": int(I[i]),
            "recovered": int(R[i]),
            "hospitalised": int(hospitalised[i]),
            "capacity": hospital_capacity,
        }
        for i, t in enumerate(sol.t)
    ]

    return {
        "curve": curve,
        "parameters": {
            "r0": r0,
            "beta": round(beta, 5),
            "sigma": round(sigma, 5),
            "gamma": round(gamma, 5),
            "population": population,
            "incubation_days": incubation_days,
            "infectious_days": infectious_days,
            "hospitalisation_rate": hospitalisation_rate,
        },
        "indicators": {
            "peak_day": int(sol.t[peak_idx]),
            "peak_infected": int(I[peak_idx]),
            "attack_rate_percent": round(float(R[-1]) / N * 100, 2),
            "capacity_breach_day": int(sol.t[over[0]]) if over.size else None,
            # Final-size / herd-immunity threshold, both standard results.
            "herd_immunity_threshold_percent": round((1 - 1 / r0) * 100, 2)
            if r0 > 1
            else 0.0,
        },
        "assumptions": (
            "Deterministic, homogeneously-mixed SEIR under a constant R0. "
            "No interventions, no waning immunity, no age structure, no "
            "importation. This is a scenario projection, not a forecast."
        ),
    }
