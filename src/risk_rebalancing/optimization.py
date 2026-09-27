"""Convex decision-time targets. No orders, returns, costs or portfolio ledger.

Optimization errors are explicit. Only a verified feasible current allocation
can produce KEEP. All turnover here is full L1 weight turnover (buys + sells).
"""
from dataclasses import dataclass, asdict
from typing import Callable
import warnings
import cvxpy as cp
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Numerics:
    weight_tolerance: float = 1e-8
    risk_relative_tolerance: float = 1e-7
    reference_relative_gap: float = 1e-7
    objective_gap_tolerance: float = 2e-7
    tie_turnover_slack: float = 1e-7
    spectral_relative_tolerance: float = 1e-12
    zero_variance_relative_floor: float = 1e-12
    solver_tolerances: tuple[float, ...] = (1e-9, 1e-11)
    solver_iterations: tuple[int, ...] = (300, 600)
    static_regularizations: tuple[float, ...] = (1e-8, 1e-12)


class NumericalError(RuntimeError):
    pass


class OptimizationError(RuntimeError):
    def __init__(self, stage, attempts):
        super().__init__(f"No certified solution for {stage}; inspect attempts, never substitute KEEP")
        self.stage = stage
        self.attempts = tuple(attempts)


@dataclass(frozen=True)
class MinimumVariance:
    tickers: tuple[str, ...]
    weights: tuple[float, ...]
    variance_daily: float
    lower_bound_daily: float
    relative_gap: float
    diagnostics: dict


@dataclass(frozen=True)
class Decision:
    policy: str
    action: str
    tickers: tuple[str, ...]
    target_weights: tuple[float, ...] | None
    current_weights: tuple[float, ...]
    expected_weight_turnover: float
    forecast_variance_daily: float
    reference_variance_daily: float
    risk_limit_daily: float | None
    diagnostics: dict

    def to_dict(self):
        return asdict(self)


def capped_simplex_linear_minimum(gradient, cap):
    """Exact greedy LP over sum(w)=1, 0<=w<=cap; stable ties by asset order."""
    weights = np.zeros(len(gradient))
    remaining = 1.
    for i in np.argsort(gradient, kind="stable"):
        amount = min(cap, remaining)
        weights[i] = amount
        remaining -= amount
        if remaining <= 0:
            break
    if remaining > 1e-12:
        raise ValueError("Infeasible position cap")
    return weights


class PortfolioOptimizer:
    def __init__(self, covariance: pd.DataFrame, cap=0.25, numerics=None):
        self.settings = numerics or Numerics()
        ncfg = self.settings
        numeric_values = [ncfg.weight_tolerance, ncfg.risk_relative_tolerance,
                          ncfg.reference_relative_gap, ncfg.objective_gap_tolerance,
                          ncfg.tie_turnover_slack, ncfg.spectral_relative_tolerance,
                          ncfg.zero_variance_relative_floor, *ncfg.solver_tolerances,*ncfg.static_regularizations]
        if not all(np.isfinite(x) and x>0 for x in numeric_values) or not (len(ncfg.solver_tolerances)==len(ncfg.solver_iterations)==len(ncfg.static_regularizations)) or not ncfg.solver_tolerances or any(not isinstance(x,int) or x<=0 for x in ncfg.solver_iterations):
            raise ValueError("Invalid numerical settings")
        if not isinstance(covariance,pd.DataFrame) or covariance.shape[0]!=covariance.shape[1] or len(covariance)<2:
            raise ValueError("covariance must be a square labeled DataFrame")
        self.tickers = tuple(covariance.columns)
        if tuple(covariance.index)!=self.tickers or len(set(self.tickers))!=len(self.tickers) or not all(isinstance(x,str) and x for x in self.tickers):
            raise ValueError("Covariance row/column labels must match and be unique strings")
        self.n = len(self.tickers)
        if not np.isfinite(cap) or cap<=0 or cap>1 or self.n*cap<1:
            raise ValueError("Infeasible position cap")
        self.cap = float(cap)
        matrix = covariance.to_numpy(dtype=float, copy=True)
        if not np.isfinite(matrix).all():
            raise ValueError("Nonfinite covariance")
        scale = float(np.max(np.abs(matrix)))
        if scale<=0:
            raise ValueError("Zero covariance cannot define a relative risk tolerance")
        symmetry_error = float(np.max(np.abs(matrix-matrix.T))/scale)
        if symmetry_error>ncfg.spectral_relative_tolerance:
            raise ValueError("Materially asymmetric covariance")
        symmetric = (matrix+matrix.T)/(2*scale)
        eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
        cutoff = ncfg.spectral_relative_tolerance*max(1.,float(np.max(eigenvalues)))
        if float(eigenvalues.min()) < -cutoff:
            raise ValueError("Covariance is not positive semidefinite")
        clean = np.where(eigenvalues>cutoff,eigenvalues,0.)
        self.scale = scale
        self.factor = (np.sqrt(clean[clean>0])[:,None]*eigenvectors[:,clean>0].T)
        self.q = self.factor.T@self.factor
        positive_vectors = eigenvectors[:,clean>0]
        self.q_inverse = (positive_vectors/clean[clean>0])@positive_vectors.T
        self.range_projector = positive_vectors@positive_vectors.T
        self.rank = int((clean>0).sum())
        self.covariance_diagnostics = {
            "scale":scale,"numerical_rank":self.rank,
            "relative_symmetry_error":symmetry_error,
            "spectral_adjustment_daily":float(np.max(np.abs(clean-eigenvalues))*scale),
            "positive_eigenvalue_condition_number":float(clean.max()/clean[clean>0].min()) if self.rank else None,
        }
        if not self.rank:
            raise ValueError("No positive covariance eigenvalues")
        self.q.setflags(write=False)
        self.factor.setflags(write=False)
        self._reference = None

    def _current(self, weights):
        if not isinstance(weights,pd.Series) or weights.index.has_duplicates or set(weights.index)!=set(self.tickers):
            raise ValueError("Current weights must be a Series with exactly the covariance labels")
        current = weights.reindex(self.tickers).to_numpy(dtype=float,copy=True)
        tol = self.settings.weight_tolerance
        if not np.isfinite(current).all() or np.min(current)<-tol or abs(current.sum()-1)>tol:
            raise ValueError("Current weights must be long-only and sum to one; cash needs an explicit ledger convention")
        return current

    def _q(self, weights):
        return float(np.square(self.factor@weights).sum())

    def _base_constraints(self, weights):
        return [cp.sum(weights)==1, weights>=0, weights<=self.cap]

    def _feasible(self, weights):
        return max(abs(float(weights.sum())-1), max(0.,-float(weights.min())), max(0.,float(weights.max())-self.cap)) <= self.settings.weight_tolerance

    def _quadratic_lower_bound(self,coefficient,linear,constant,base_constraints):
        """Dual quadratic bound, retaining a bounded-domain nullspace term.

        For PSD Q, complete the square on its range. A linear nullspace term
        is bounded over C with the exact greedy LP instead of being discarded.
        """
        budget = float(base_constraints[0].dual_value)
        low = np.maximum(np.asarray(base_constraints[1].dual_value),0.)
        high = np.maximum(np.asarray(base_constraints[2].dual_value),0.)
        g = linear+budget-low+high
        in_range = self.range_projector@g
        null = g-in_range
        return float(constant-budget-self.cap*high.sum()
                     -(in_range@self.q_inverse@in_range)/(4*coefficient)
                     +null@capped_simplex_linear_minimum(null,self.cap))

    def _clean_target(self, raw):
        raw = np.asarray(raw,dtype=float).reshape(-1)
        if len(raw)!=self.n or not np.isfinite(raw).all() or not self._feasible(raw):
            raise NumericalError("Raw solver weights fail budget/position constraints")
        # Only a numerically feasible target is projected. The change is logged
        # and all economic constraints/objectives are checked again afterwards.
        lo, hi = float(np.min(raw-self.cap)), float(np.max(raw))
        for _ in range(80):
            mid = (lo+hi)/2
            if np.clip(raw-mid,0,self.cap).sum()>1:
                lo = mid
            else:
                hi = mid
        target = np.clip(raw-(lo+hi)/2,0,self.cap)
        residual = 1-float(target.sum())
        for i in range(self.n):
            change = min(residual,self.cap-target[i]) if residual>=0 else max(residual,-target[i])
            target[i] += change
            residual -= change
        repair = float(np.max(np.abs(raw-target)))
        if repair>2*self.settings.weight_tolerance or not self._feasible(target):
            raise NumericalError("Target requires a material numerical repair")
        return target, repair

    def _solve(self, stage, problem, variable, validate: Callable, allow_certified_inaccurate=False, restore=None):
        attempts = []
        for tol, max_iter, regularization in zip(self.settings.solver_tolerances,self.settings.solver_iterations,self.settings.static_regularizations):
            record = {"stage":stage,"solver":"CLARABEL","solver_tolerance":tol,"max_iter":max_iter,"static_regularization":regularization}
            try:
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    problem.solve(solver="CLARABEL",warm_start=False,verbose=False,
                                  tol_gap_abs=tol,tol_gap_rel=tol,tol_feas=tol,max_iter=max_iter,
                                  static_regularization_constant=regularization)
                record.update(status=problem.status,warnings=[str(w.message) for w in caught],
                              iterations=problem.solver_stats.num_iters)
                status_allowed = problem.status==cp.OPTIMAL or (allow_certified_inaccurate and problem.status==cp.OPTIMAL_INACCURATE)
                if not status_allowed or variable.value is None:
                    raise NumericalError("Solver did not return OPTIMAL")
                target, repair = self._clean_target(variable.value)
                if restore is not None:
                    target, restoration = restore(target)
                    record["restoration"] = restoration
                    if not self._feasible(target):
                        raise NumericalError("Restored target fails position constraints")
                checks = validate(target)
                record.update(checks=checks,projection_linf=repair,accepted=True,
                              qualified_inaccurate_status=problem.status==cp.OPTIMAL_INACCURATE)
                attempts.append(record)
                return target, {"attempts":attempts,**checks}
            except (cp.error.SolverError,NumericalError) as exc:
                record.update(accepted=False,error=f"{type(exc).__name__}: {exc}")
                attempts.append(record)
        raise OptimizationError(stage,attempts)

    def minimum_variance(self):
        if self._reference is not None:
            return self._reference
        w = cp.Variable(self.n)
        problem = cp.Problem(cp.Minimize(cp.sum_squares(self.factor@w)),self._base_constraints(w))
        def validate(x):
            value = self._q(x)
            gradient = 2*self.q@x
            lp = capped_simplex_linear_minimum(gradient,self.cap)
            gap = max(0.,float(gradient@(x-lp)))
            lower = value-gap
            if lower<=self.settings.zero_variance_relative_floor:
                raise NumericalError("Minimum variance has no certified positive lower bound")
            relative_gap = gap/lower
            if relative_gap>self.settings.reference_relative_gap:
                raise NumericalError(f"Minimum-variance relative optimality gap {relative_gap:g}")
            return {"normalized_variance":value,"normalized_lower_bound":lower,"relative_gap":relative_gap}
        target, diagnostic = self._solve("minimum_variance",problem,w,validate)
        self._reference = MinimumVariance(self.tickers,tuple(target),self._q(target)*self.scale,
                                         diagnostic["normalized_lower_bound"]*self.scale,
                                         diagnostic["relative_gap"],diagnostic)
        return self._reference

    def _decision(self, policy,current,target,reference,limit,diagnostics):
        kept = target is None
        actual = current if kept else target
        return Decision(policy,"KEEP" if kept else "TARGET",self.tickers,
                        None if kept else tuple(float(x) for x in target),tuple(float(x) for x in current),
                        0. if kept else float(np.abs(target-current).sum()),self._q(actual)*self.scale,
                        reference.variance_daily,limit,
                        {"covariance":self.covariance_diagnostics,"numerics":asdict(self.settings),
                         "forecast_volatility_ratio_to_reference":float(np.sqrt(self._q(actual)*self.scale/reference.variance_daily)),
                         "forecast_volatility_ratio_upper_bound":float(np.sqrt(self._q(actual)*self.scale/reference.lower_bound_daily)),
                         **diagnostics})

    def minimum_variance_target(self,current_weights):
        current = self._current(current_weights)
        reference = self.minimum_variance()
        return self._decision("minimum_variance",current,np.asarray(reference.weights),reference,None,
                              {"reference":reference.diagnostics})

    def _minimum_turnover(self,policy,current,reference,limit=None,band=None,face=False):
        """L1 epigraph + quadratic risk/linear band/optimal-face constraints."""
        w,u = cp.Variable(self.n),cp.Variable(self.n)
        positive,negative = w-current<=u,current-w<=u
        constraints = self._base_constraints(w)+[positive,negative]
        risk_constraint = face_constraint = lower_band = upper_band = None
        ref = np.asarray(reference.weights)
        if face:
            face_constraint = self.factor@w==self.factor@ref
            constraints.append(face_constraint)
        elif limit is not None:
            risk_factor = self.factor/np.sqrt(limit/self.scale)
            risk_constraint = cp.SOC(1.,risk_factor@w)
            constraints.append(risk_constraint)
        if band is not None:
            lower_band,upper_band = w>=ref-band,w<=ref+band
            constraints += [lower_band,upper_band]
        def economic_checks(x):
            if limit is not None and self._q(x)>limit/self.scale*(1+self.settings.risk_relative_tolerance):
                raise NumericalError("Target violates the forecast-risk ceiling")
            if face and np.max(np.abs(self.factor@(x-ref)))>self.settings.weight_tolerance:
                raise NumericalError("Target leaves the zero-tolerance optimal face")
            if band is not None and np.max(np.abs(x-ref))>band+self.settings.weight_tolerance:
                raise NumericalError("Target violates the absolute weight band")
        def extra_affine_bound():
            gradient = np.zeros(self.n)
            constant = 0.
            if risk_constraint is not None:
                cone_scalar = max(0.,float(np.asarray(risk_constraint.dual_value[0]).item()))
                cone_vector = np.asarray(risk_constraint.dual_value[1]).reshape(-1)
                norm = float(np.linalg.norm(cone_vector))
                if norm>cone_scalar:
                    cone_vector = cone_vector*(cone_scalar/norm)
                gradient -= risk_factor.T@cone_vector
                constant -= cone_scalar
            if face_constraint is not None:
                dual = np.asarray(face_constraint.dual_value)
                gradient += self.factor.T@dual
                constant -= float(dual@(self.factor@ref))
            if band is not None:
                low = np.maximum(np.asarray(lower_band.dual_value),0)
                high = np.maximum(np.asarray(upper_band.dual_value),0)
                gradient += high-low
                constant += float(low@(ref-band)-high@(ref+band))
            return gradient,constant
        def lower_bound(x):
            # A dual-feasible affine minorant gives a solver-independent lower
            # bound after minimizing a linear function over the capped simplex.
            s = np.clip(np.asarray(positive.dual_value)-np.asarray(negative.dual_value),-1.,1.)
            gradient,constant = extra_affine_bound()
            gradient += s
            constant -= float(s@current)
            return float(gradient@capped_simplex_linear_minimum(gradient,self.cap)+constant)
        def validate_primary(x):
            economic_checks(x)
            value = float(np.abs(x-current).sum())
            bound = lower_bound(x)
            gap = value-bound
            if not np.isfinite(bound) or gap < -self.settings.objective_gap_tolerance or gap>self.settings.objective_gap_tolerance:
                raise NumericalError(f"Turnover optimality gap {gap:g}")
            return {"turnover":value,"lower_bound":bound,"absolute_gap":max(0.,gap)}
        primary = cp.Problem(cp.Minimize(cp.sum(u)),constraints)
        first, primary_diagnostic = self._solve(
            policy+"_primary",primary,w,validate_primary,
            allow_certified_inaccurate=(risk_constraint is not None))
        limit_l1 = float(np.abs(first-current).sum())+self.settings.tie_turnover_slack
        turnover_constraint = cp.sum(u)<=limit_l1
        tie_problem = cp.Problem(cp.Minimize(cp.sum_squares(w-current)),constraints+[turnover_constraint])
        def restore_turnover(x):
            actual = float(np.abs(x-current).sum())
            alpha = 0.
            if actual>limit_l1:
                # The primary solution is a known feasible anchor with strictly
                # less L1 turnover than the tie budget. Convex interpolation
                # restores that budget without relaxing risk/cap constraints.
                safe_limit = float(np.nextafter(limit_l1,-np.inf))
                alpha = min(1.,max(0.,(actual-safe_limit)/(actual-float(np.abs(first-current).sum()))))
            restored = (1-alpha)*x+alpha*first
            return restored,{"primary_anchor_fraction":alpha,"linf_change":float(np.max(np.abs(restored-x)))}
        def validate_tie(x):
            economic_checks(x)
            turnover = float(np.abs(x-current).sum())
            if turnover>limit_l1+self.settings.weight_tolerance:
                raise NumericalError("Tie-break exceeds its turnover budget")
            theta = max(0.,float(turnover_constraint.dual_value))
            s = np.clip(np.asarray(positive.dual_value)-np.asarray(negative.dual_value),-theta,theta)
            extra_gradient,extra_constant = extra_affine_bound()
            budget_dual = float(constraints[0].dual_value)
            low = np.maximum(np.asarray(constraints[1].dual_value),0.)
            high = np.maximum(np.asarray(constraints[2].dual_value),0.)
            gradient = -2*current+s+extra_gradient+budget_dual-low+high
            constant = float(current@current-s@current+extra_constant-theta*limit_l1-budget_dual-self.cap*high.sum())
            lower = constant-float(gradient@gradient)/4
            squared_distance = float(np.square(x-current).sum())
            gap = squared_distance-lower
            if not np.isfinite(lower) or abs(gap)>self.settings.objective_gap_tolerance:
                raise NumericalError(f"Distance tie-break optimality gap {gap:g}")
            return {"turnover":turnover,"turnover_budget":limit_l1,
                    "squared_distance":squared_distance,"distance_lower_bound":lower,
                    "distance_absolute_gap":max(0.,gap),
                    "primary_gap_upper_bound":max(0.,turnover-primary_diagnostic["lower_bound"])}
        target, tie_diagnostic = self._solve(policy+"_tie_break",tie_problem,w,validate_tie,
                                            allow_certified_inaccurate=True,restore=restore_turnover)
        return self._decision(policy,current,target,reference,limit,
                              {"reference":reference.diagnostics,"primary":primary_diagnostic,"tie_break":tie_diagnostic})

    def risk_tolerant(self,current_weights,epsilon=0.02):
        if not np.isfinite(epsilon) or epsilon<0 or not np.isfinite((1+epsilon)**2):
            raise ValueError("epsilon must be a finite nonnegative relative volatility tolerance")
        current = self._current(current_weights)
        reference = self.minimum_variance()
        limit = (1+epsilon)**2*reference.variance_daily
        if self._feasible(current) and self._q(current)*self.scale<=limit*(1+self.settings.risk_relative_tolerance):
            return self._decision("risk_tolerant",current,None,reference,limit,{"epsilon":epsilon,"reason":"current_holdings_feasible","reference":reference.diagnostics})
        if epsilon==0 and self.rank==self.n:
            # The positive-definite minimum is unique: avoid a degenerate cone.
            return self._decision("risk_tolerant",current,np.asarray(reference.weights),reference,limit,
                                  {"epsilon":epsilon,"reason":"unique_zero_tolerance_minimum","reference":reference.diagnostics})
        result = self._minimum_turnover("risk_tolerant",current,reference,limit,face=epsilon==0)
        result.diagnostics["epsilon"] = epsilon
        return result

    def weight_band(self,current_weights,band):
        if not np.isfinite(band) or band<0:
            raise ValueError("band must be a nonnegative absolute weight deviation")
        current = self._current(current_weights)
        reference = self.minimum_variance()
        if self._feasible(current) and np.max(np.abs(current-np.asarray(reference.weights)))<=band+self.settings.weight_tolerance:
            return self._decision("weight_band",current,None,reference,None,{"band":band,"reason":"inside_weight_band"})
        result = self._minimum_turnover("weight_band",current,reference,band=band)
        result.diagnostics["band"] = band
        return result

    def repair_caps(self,current_weights):
        current = self._current(current_weights)
        reference = self.minimum_variance()
        if self._feasible(current):
            return self._decision("cap_repair",current,None,reference,None,{"reason":"caps_satisfied"})
        return self._minimum_turnover("cap_repair",current,reference)

    def variance_penalty(self,current_weights,penalty):
        if not np.isfinite(penalty) or penalty<0:
            raise ValueError("penalty must be finite and nonnegative")
        if penalty==0:
            return self.minimum_variance_target(current_weights)
        current = self._current(current_weights)
        reference = self.minimum_variance()
        qref = reference.variance_daily/self.scale
        # At the current portfolio the L1 subgradient is a box. If it can
        # satisfy the capped-simplex first-order conditions, KEEP is globally
        # optimal. This is a certificate, not a small-trade threshold.
        gradient = 2*self.q@current/qref
        lower = float(np.max((gradient-penalty)[current>0]))
        upper = float(np.min((gradient+penalty)[current<self.cap])) if np.any(current<self.cap) else float("inf")
        if self._feasible(current) and lower<=upper:
            center = lower if not np.isfinite(upper) else (lower+upper)/2
            subgradient = np.clip(center-gradient,-penalty,penalty)
            g = gradient+subgradient
            gap = max(0.,float(g@(current-capped_simplex_linear_minimum(g,self.cap))))
            if gap<=self.settings.objective_gap_tolerance:
                return self._decision("variance_penalty",current,None,reference,None,
                    {"penalty":penalty,"reason":"current_subgradient_certificate","absolute_gap":gap,"reference":reference.diagnostics})
        w,u = cp.Variable(self.n),cp.Variable(self.n)
        positive,negative = w-current<=u,current-w<=u
        base_constraints = self._base_constraints(w)
        problem = cp.Problem(cp.Minimize(cp.sum_squares(self.factor@w)/qref+penalty*cp.sum(u)),
                             base_constraints+[positive,negative])
        def validate(x):
            s = np.clip(np.asarray(positive.dual_value)-np.asarray(negative.dual_value),-penalty,penalty)
            gq = 2*self.q@x/qref
            g = gq+s
            bound = float(g@capped_simplex_linear_minimum(g,self.cap)+self._q(x)/qref-gq@x-s@current)
            bound = max(bound,self._quadratic_lower_bound(1/qref,s,-float(s@current),base_constraints))
            value = self._q(x)/qref+penalty*float(np.abs(x-current).sum())
            gap = value-bound
            if not np.isfinite(bound) or abs(gap)>self.settings.objective_gap_tolerance:
                raise NumericalError(f"Penalty objective gap {gap:g}")
            return {"objective":value,"lower_bound":bound,"absolute_gap":max(0.,gap)}
        target,diagnostics = self._solve("variance_penalty",problem,w,validate)
        # Do not convert a merely small computed trade to KEEP. That would alter
        # the declared policy and hide numerical issues without a certificate.
        return self._decision("variance_penalty",current,target,reference,None,
                              {"penalty":penalty,"primary":diagnostics,"reference":reference.diagnostics})
