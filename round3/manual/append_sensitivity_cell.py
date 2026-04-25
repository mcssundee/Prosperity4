"""Appends the sensitivity curve cell to bid_optimization.ipynb."""
import json, pathlib

NB = pathlib.Path(__file__).parent / "bid_optimization.ipynb"
nb = json.loads(NB.read_text())

# Remove any previously appended sensitivity cells to stay idempotent
nb["cells"] = [c for c in nb["cells"] if "sensitivity" not in "".join(c.get("source", [])).lower()
               or c["cell_type"] == "markdown" and "Sensitivity" not in "".join(c.get("source", []))]

md_cell = {
    "cell_type": "markdown",
    "id": "sens-md-01",
    "metadata": {},
    "source": [
        "## 3 · Profit vs Bid 2 — Sensitivity to Competitor Distributions\n",
        "\n",
        "Fixed **bid1 = 755**. X axis = your bid2. Each curve assumes competitors draw bid2 from\n",
        "a different **N(μ, σ)** distribution.\n",
        "\n",
        "- **Colour** = competitor mean μ (blue = conservative ≈ 750 → red = aggressive ≈ 875)\n",
        "- **Line style** = σ: solid = tight (σ=20), dashed = spread (σ=40)\n",
        "- Grey dotted = Uniform U[670, 920] reference\n",
        "\n",
        "This makes the optimal bid2 choice and penalty cliff visible at a glance.",
    ],
}

code_lines = [
    "# ── Sensitivity: E[profit] vs bid2 for different competitor N(μ,σ) ──────\n",
    "FIXED_B1     = 755\n",
    "j_fixed      = int((FIXED_B1 - 670) / 5)   # = 17\n",
    "b1_p_fixed   = (SELL - FIXED_B1) * j_fixed  # deterministic bid1 profit\n",
    "b2_sweep     = bid_grid[bid_grid > FIXED_B1] # 760 … 920\n",
    "\n",
    "comp_means  = [750, 775, 800, 825, 850, 875]\n",
    "comp_sigmas = [20, 40]\n",
    "cmap        = plt.colormaps['RdYlBu_r']\n",
    "colors      = [cmap(i / (len(comp_means) - 1)) for i in range(len(comp_means))]\n",
    "linestyles  = ['-', '--']\n",
    "\n",
    "\n",
    "def curve_for(draws):\n",
    "    \"\"\"E[profit] for each bid2 in b2_sweep given competitor draws (N_SIMS, N_COMP).\"\"\"\n",
    "    comp_sum = draws.sum(axis=1)\n",
    "    out = []\n",
    "    for b2 in b2_sweep:\n",
    "        k      = int((b2 - 670) / 5)\n",
    "        n2     = k - j_fixed\n",
    "        margin = float(SELL - b2)\n",
    "        if n2 <= 0 or margin <= 0:\n",
    "            out.append(float(b1_p_fixed))\n",
    "            continue\n",
    "        avg_b2 = (comp_sum + b2) / (N_COMP + 1)\n",
    "        no_pen = b2 >= avg_b2\n",
    "        pen    = ((SELL - avg_b2) / (SELL - b2)) ** 3\n",
    "        b2_p   = np.where(no_pen, margin * n2, margin * n2 * pen)\n",
    "        out.append(float((b1_p_fixed + b2_p).mean()))\n",
    "    return out\n",
    "\n",
    "\n",
    "fig, ax = plt.subplots(figsize=(12, 6))\n",
    "\n",
    "# Uniform reference\n",
    "draws_u = RNG.uniform(670, 920, (N_SIMS, N_COMP))\n",
    "ax.plot(b2_sweep, curve_for(draws_u),\n",
    "        color='grey', lw=2, ls=':', label='Uniform U[670, 920]', zorder=10)\n",
    "\n",
    "# Normal-distribution curves\n",
    "for si, sigma in enumerate(comp_sigmas):\n",
    "    for mi, mu in enumerate(comp_means):\n",
    "        draws = RNG.normal(mu, sigma, (N_SIMS, N_COMP)).clip(670, 919)\n",
    "        ax.plot(b2_sweep, curve_for(draws),\n",
    "                color=colors[mi], ls=linestyles[si],\n",
    "                lw=2.2 if si == 0 else 1.4,\n",
    "                label=f'N(μ={mu}, σ={sigma})')\n",
    "\n",
    "# Reference lines\n",
    "ax.axvline(840, color='black', ls='--', lw=1.3, alpha=0.7, label='bid2=840 (recommended)')\n",
    "ax.axhline(4165, color='black', ls=':', lw=1.0, alpha=0.4, label='Theoretical max = 4165')\n",
    "\n",
    "ax.set_xlabel('Your Bid 2', fontsize=12)\n",
    "ax.set_ylabel('Expected Profit', fontsize=12)\n",
    "ax.set_title(\n",
    "    'E[Profit] vs Bid 2  (bid1=755 fixed)\\n'\n",
    "    'Solid = σ=20 (tight competitors)   Dashed = σ=40 (spread competitors)\\n'\n",
    "    'Colour: blue = conservative (μ=750) → red = aggressive (μ=875)',\n",
    "    fontsize=11,\n",
    ")\n",
    "ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))\n",
    "ax.legend(fontsize=8, ncol=2, loc='lower left')\n",
    "plt.tight_layout()\n",
    "plt.show()\n",
]

code_cell = {
    "cell_type": "code",
    "execution_count": None,
    "id": "sens-code-01",
    "metadata": {},
    "outputs": [],
    "source": code_lines,
}

nb["cells"].append(md_cell)
nb["cells"].append(code_cell)
NB.write_text(json.dumps(nb, indent=1))
print(f"Notebook now has {len(nb['cells'])} cells.")
