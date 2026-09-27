"""Draw the research-note figures from saved results and derived geometry."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MultipleLocator, StrMethodFormatter
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
INK = '#213547'
MUTED = '#64717d'
ROSE = '#a53d59'
TEAL = '#397c77'
BLUE = '#527f9d'
GOLD = '#b28a39'

STYLE = {
    'font.family': 'DejaVu Serif',
    'font.size': 9,
    'mathtext.fontset': 'cm',
    'pdf.fonttype': 42,
    'axes.labelsize': 10,
    'axes.labelcolor': INK,
    'axes.edgecolor': '#9ba5ad',
    'axes.linewidth': .65,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'xtick.color': MUTED,
    'ytick.color': MUTED,
    'xtick.labelsize': 8.5,
    'ytick.labelsize': 8.5,
    'text.color': INK,
    'savefig.facecolor': 'white',
}


def risk_turnover(rows):
    fig, ax = plt.subplots(figsize=(7, 3.85))
    fig.subplots_adjust(left=.115, right=.985, bottom=.27, top=.96)
    groups = [
        ('equal_weight', 'Equal weight', '#89929a', 'D'),
        ('minimum_variance', 'Calendar MV', BLUE, 's'),
        ('weight_band', 'Weight band', GOLD, '^'),
        ('variance_penalty', 'Variance penalty', TEAL, 'v'),
        ('risk_tolerant', 'Risk tolerance', ROSE, 'o'),
    ]
    for prefix, label, color, marker in groups:
        values = [row for row in rows if row['id'].startswith(prefix)]
        ax.scatter(
            [r['annualized_full_notional_turnover'] for r in values],
            [100*r['annualized_gross_volatility'] for r in values],
            s=36, marker=marker, facecolors='white' if prefix == 'risk_tolerant' else color,
            edgecolors=color, linewidths=1.15, alpha=.95, zorder=3,
        )
    for policy, label, color, marker, label_position in [
        ('risk_tolerant_0.02', r'$A:\varepsilon=0.02$', ROSE, 'o', (1.02, 18.02)),
        ('variance_penalty_0.3', r'$B:\lambda=0.3$', TEAL, 'v', (2.06, 17.62)),
    ]:
        row = next(r for r in rows if r['id'] == policy)
        point = (row['annualized_full_notional_turnover'], 100*row['annualized_gross_volatility'])
        ax.scatter(*point, s=90, facecolors='white', edgecolors=color, linewidths=1.45, zorder=5)
        ax.scatter(*point, s=32, marker=marker, color=color, zorder=6)
        ax.annotate(label, point, xytext=label_position, fontsize=12, color=color,
                    arrowprops={'arrowstyle': '-', 'color': color, 'lw': .85,
                                'shrinkA': 5, 'shrinkB': 7},
                    bbox={'facecolor': 'white', 'edgecolor': 'none', 'pad': 1.5}, zorder=7)
    ax.set(xlim=(-.13, 4.55), ylim=(16.96, 19.95),
           xlabel=r'Annual routine turnover, $T$ (NAV/year)',
           ylabel=r'Annual gross volatility, $\sigma$ (%)')
    ax.xaxis.set_major_locator(MultipleLocator(1))
    ax.yaxis.set_major_locator(MultipleLocator(.5))
    ax.yaxis.set_major_formatter(StrMethodFormatter('{x:.1f}'))
    ax.grid(axis='y', color='#e5e9ec', linewidth=.6, zorder=0)
    ax.tick_params(length=3, width=.65)
    handles = [Line2D([], [], marker=m, linestyle='none', markersize=5,
                      markerfacecolor='white' if prefix == 'risk_tolerant' else c,
                      markeredgecolor=c, label=label)
               for prefix, label, c, m in groups]
    fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.54, .005),
               ncol=3, frameon=False, fontsize=8.2, columnspacing=1.7, handletextpad=.5)
    return fig


def allocation_plane(data):
    current = np.asarray(data['current_weights'])
    mv = np.asarray(data['minimum_variance_weights'])
    chosen = np.asarray(data['chosen_weights'])
    gram = np.asarray(data['normalized_variance_gram'])
    u, v = np.meshgrid(np.linspace(-.15, 1.25, 401), np.linspace(-.15, 1.25, 401))
    weights = current + u[..., None]*(mv-current) + v[..., None]*(chosen-current)
    feasible = (weights.min(axis=2) >= -1e-10) & (weights.max(axis=2) <= data['position_cap']+1e-10)
    z = np.stack([np.ones_like(u), u, v], axis=-1)
    ratio = np.sqrt(np.maximum(0, np.einsum('...i,ij,...j->...', z, gram, z)))
    inside_risk = feasible & (ratio <= data['forecast_volatility_limit'])
    inside_band = feasible & (np.max(np.abs(weights-mv), axis=2) <= data['weight_band'])

    fig = plt.figure(figsize=(7, 4.25))
    ax = fig.add_axes([.095, .14, .575, .67])
    fig.text(.095, .963, 'First partial rebalance  |  2 January 2020', fontsize=9, color=MUTED)
    fig.text(.095, .89, r'$w(u,v)=w^{-}+u\,(w^{\star}-w^{-})+v\,(w^{A}-w^{-})$', fontsize=14)
    ax.contourf(u, v, feasible.astype(int), levels=[-.5, .5, 1.5], colors=['#f0f2f3', 'white'])
    ax.contourf(u, v, inside_band.astype(int), levels=[.5, 1.5], colors=['#d8e7ef'])
    ax.contourf(u, v, inside_risk.astype(int), levels=[.5, 1.5], colors=['#ddb5c1'])
    contours = ax.contour(u, v, np.where(feasible, ratio, np.nan),
                          levels=[1.02, 1.05, 1.10, 1.20],
                          colors=[ROSE, '#83909a', '#83909a', '#83909a'], linewidths=[1, .65, .65, .65])
    ax.clabel(contours, manual=[(.12, .88), (.20, .66), (.07, .50), (-.07, .15)],
              fmt='%.2f', fontsize=7.5, inline_spacing=4)
    for x, y, label, color, offset in [
        (0, 0, r'Current $w^{-}$', BLUE, (6, 10)),
        (1, 0, r'Minimum risk $w^{\star}$', INK, (-80, -18)),
        (0, 1, r'Chosen $w^{A}$', ROSE, (8, 10)),
    ]:
        ax.scatter(x, y, s=50, color=color, edgecolors='white', linewidths=.9, zorder=5)
        ax.annotate(label, (x, y), xytext=offset, textcoords='offset points', fontsize=8.5,
                    color=color, zorder=6)
    ax.set(xlim=(-.15, 1.25), ylim=(-.15, 1.25), xlabel=r'$u$', ylabel=r'$v$')
    ax.xaxis.set_major_locator(MultipleLocator(.2))
    ax.yaxis.set_major_locator(MultipleLocator(.2))
    ax.tick_params(length=3, width=.65)
    ax.xaxis.labelpad = 5
    ax.yaxis.labelpad = 4
    legend_ax = fig.add_axes([.715, .14, .28, .67])
    legend_ax.axis('off')
    legend_ax.legend(handles=[
        Patch(facecolor='#ddb5c1', edgecolor='none',
              label='Forecast-risk region\n'+r'$\sigma(w)/\sigma^{\star}\leq 1.02$'),
        Patch(facecolor='#d8e7ef', edgecolor='none',
              label='Weight band\n'+r'$\|w-w^{\star}\|_{\infty}\leq 0.08$'),
        Patch(facecolor='#f0f2f3', edgecolor='#bac2c8', linewidth=.5,
              label='Outside position\nconstraints'),
    ], loc='upper left', borderaxespad=0, frameon=False, fontsize=8.2,
       handlelength=1, handletextpad=.65, labelspacing=1.6)
    legend_ax.text(0, .20, 'Contour labels', fontsize=8, color=MUTED)
    legend_ax.text(0, .11, r'$\sigma(w)/\sigma^{\star}$', fontsize=13, color=INK)
    return fig


def build_figures(work_dir):
    """Refresh the repository PNGs and return vector PDFs for document assembly."""
    rows = json.loads((ROOT/'reports/results/all_policy_metrics.json').read_text(encoding='utf-8'))
    baseline = [r for r in rows if r['scenario'] == 'baseline']
    if len(baseline) != 21:
        raise ValueError('Expected 21 frozen baseline policy rows')
    geometry = json.loads((ROOT/'reports/results/note_figure_inputs.json').read_text(encoding='utf-8'))
    vector_dir = Path(work_dir)/'PDF'
    vector_dir.mkdir(parents=True, exist_ok=True)
    outputs = {}
    with plt.rc_context(STYLE):
        for name, figure in [('publication_risk_turnover', risk_turnover(baseline)),
                             ('allocation_plane', allocation_plane(geometry))]:
            png = ROOT/'reports/figures'/f'{name}.png'
            pdf = vector_dir/f'{name}.pdf'
            figure.savefig(png, dpi=320)
            figure.savefig(pdf, metadata={'CreationDate': None, 'ModDate': None})
            plt.close(figure)
            outputs[png.name] = pdf
    return outputs
