import numpy as np
from scipy import optimize
import os, sys
from recOrder.calib.CoreFunctions import set_lc, get_lc, snap_image

class BrentOptimizer:

    def __init__(self, calib):

        self.calib = calib


    def _check_bounds(self, lca_bound, lcb_bound):

        current_lca = get_lc(self.calib.mmc, self.calib.PROPERTIES['LCA'])
        current_lcb = get_lc(self.calib.mmc, self.calib.PROPERTIES['LCB'])

        # check that bounds don't exceed range of LC
        lca_lower_bound = 0.01 if (current_lca - lca_bound) <= 0.01 else current_lca - lca_bound
        lca_upper_bound = 1.6 if (current_lca + lca_bound) >= 1.6 else current_lca + lca_bound

        lcb_lower_bound = 0.01 if current_lcb - lcb_bound <= 0.01 else current_lcb - lcb_bound
        lcb_upper_bound = 1.6 if current_lcb + lcb_bound >= 1.6 else current_lcb + lcb_bound

        return lca_lower_bound, lca_upper_bound, lcb_lower_bound, lcb_upper_bound

    def opt_lca(self, cost_function, lower_bound, upper_bound, reference, cost_function_args):

        xopt, fval, ierr, numfunc = optimize.fminbound(cost_function,
                                                       x1=lower_bound,
                                                       x2=upper_bound,
                                                       disp=0,
                                                       args=cost_function_args,
                                                       full_output=True)

        lca = xopt
        lcb = get_lc(self.calib.mmc, self.calib.PROPERTIES['LCA'])
        abs_intensity = fval + reference
        difference = fval / reference * 100

        if self.calib.print_details:
            print('\tOptimize lca ...')
            print(f"\tlca = {lca:.5f}")
            print(f"\tlcb = {lcb:.5f}")
            print(f'\tIntensity = {abs_intensity}')
            print(f'\tIntensity Difference = {difference:.4f}%')

        return [lca, lcb, abs_intensity, difference]

    def opt_lcb(self, cost_function, lower_bound, upper_bound, reference, cost_function_args):

        xopt, fval, ierr, numfunc = optimize.fminbound(cost_function,
                                                       x1=lower_bound,
                                                       x2=upper_bound,
                                                       disp=0,
                                                       args=cost_function_args,
                                                       full_output=True)

        lca = get_lc(self.calib.mmc, self.calib.PROPERTIES['LCA'])
        lcb = xopt
        abs_intensity = fval + reference
        difference = fval / reference * 100

        if self.calib.print_details:
            print('\tOptimize lcb ...')
            print(f"\tlca = {lca:.5f}")
            print(f"\tlcb = {lcb:.5f}")
            print(f'\tIntensity = {abs_intensity}')
            print(f'\tIntensity Difference = {difference:.4f}%')

        return [lca, lcb, abs_intensity, difference]

    def optimize(self, state, lca_bound, lcb_bound, reference, thresh, n_iter):

        converged = False
        iteration = 1
        self.calib.inten = []
        optimal = []

        while not converged:
            if self.calib.print_details:
                print(f'iteration: {iteration}')

            lca_lower_bound, lca_upper_bound,\
            lcb_lower_bound, lcb_upper_bound = self._check_bounds(lca_bound, lcb_bound)

            if state == 'ext':

                results_lca = self.opt_lca(self.calib.opt_lc, lca_lower_bound, lca_upper_bound,
                                            reference, (self.calib.PROPERTIES['LCA'], reference))

                set_lc(self.calib.mmc, results_lca[0], self.calib.PROPERTIES['LCA'])

                optimal.append(results_lca)

                results_lcb = self.opt_lcb(self.calib.opt_lc, lcb_lower_bound, lcb_upper_bound,
                                            reference, (self.calib.PROPERTIES['LCB'], reference))

                set_lc(self.calib.mmc, results_lca[1], self.calib.PROPERTIES['LCB'])

                optimal.append(results_lcb)

            if state == '45' or state == '135':

                results = self.opt_lcb(self.calib.opt_lc, lca_lower_bound, lca_upper_bound,
                                        reference, (self.calib.PROPERTIES['LCB'], reference))

                optimal.append(results)

            if state == '60':

                results = self.opt_lca(self.calib.opt_lc_cons, lca_lower_bound, lca_upper_bound,
                                        reference, (reference, '60'))

                swing = (self.calib.lca_ext - results[0]) * self.calib.ratio
                lca = results[0]
                lcb = self.calib.lcb_ext + swing

                optimal.append([lca, lcb, results[2], results[3]])

            if state == '90':

                results = self.opt_lca(self.calib.opt_lc, lca_lower_bound, lca_upper_bound,
                                           reference, (self.calib.PROPERTIES['LCA'], reference))

                optimal.append(results)

            if state == '120':
                results = self.opt_lca(self.calib.opt_lc_cons, lca_lower_bound, lca_upper_bound,
                                       reference, (reference, '120'))

                swing = (self.calib.lca_ext - results[0]) * self.calib.ratio
                lca = results[0]
                lcb = self.calib.lcb_ext - swing

                optimal.append([lca, lcb, results[2], results[3]])

            # if both LCA and LCB meet threshold, stop
            if results[3] <= thresh:
                converged = True
                optimal = np.asarray(optimal)

                return optimal[-1, 0], optimal[-1, 1], optimal[-1, 2]

            # if loop preforms more than n_iter iterations, stop
            elif iteration >= n_iter:
                if self.calib.print_details:
                    print(f'Exceeded {n_iter} Iterations: Search discontinuing')

                converged = True
                optimal = np.asarray(optimal)
                opt = np.where(optimal == np.min(np.abs(optimal[:, 0])))[0]

                if self.calib.print_details:
                    print(f'Lowest Inten: {optimal[opt, 0]}, lca = {optimal[opt, 1]}, lcb = {optimal[opt, 2]}')

                return optimal[-1, 0], optimal[-1, 1], optimal[-1, 2]

            iteration += 1


class MinScalarOptimizer:

    def __init__(self, calib):

        self.calib = calib

    def _check_bounds(self, lca_bound, lcb_bound):

        current_lca = get_lc(self.calib.mmc, self.calib.PROPERTIES['LCA'])
        current_lcb = get_lc(self.calib.mmc, self.calib.PROPERTIES['LCB'])

        # check that bounds don't exceed range of LC
        lca_lower_bound = 0.01 if (current_lca - lca_bound) <= 0.01 else current_lca - lca_bound
        lca_upper_bound = 1.6 if (current_lca + lca_bound) >= 1.6 else current_lca + lca_bound

        lcb_lower_bound = 0.01 if current_lcb - lcb_bound <= 0.01 else current_lcb - lcb_bound
        lcb_upper_bound = 1.6 if current_lcb + lcb_bound >= 1.6 else current_lcb + lcb_bound

        return lca_lower_bound, lca_upper_bound, lcb_lower_bound, lcb_upper_bound

    def opt_lca(self, cost_function, lower_bound, upper_bound, reference, cost_function_args):

        res = optimize.minimize_scalar(cost_function, bounds=(lower_bound, upper_bound),
                                       method='bounded', args=cost_function_args)

        lca = res.x
        lcb = get_lc(self.calib.mmc, self.calib.PROPERTIES['LCB'])
        abs_intensity = res.fun + reference
        difference = res.fun / reference * 100

        if self.calib.print_details:
            print('\tOptimize lca ...')
            print(f"\tlca = {lca:.5f}")
            print(f"\tlcb = {lcb:.5f}")
            print(f'\tIntensity = {abs_intensity}')
            print(f'\tIntensity Difference = {difference:.4f}%')

        return [lca, lcb, abs_intensity, difference]

    def opt_lcb(self, cost_function, lower_bound, upper_bound, reference, cost_function_args):

        res = optimize.minimize_scalar(cost_function, bounds=(lower_bound, upper_bound),
                                       method='bounded', args=cost_function_args)

        lca = get_lc(self.calib.mmc, self.calib.PROPERTIES['LCA'])
        lcb = res.x
        abs_intensity = res.fun + reference
        difference = res.fun / reference * 100

        if self.calib.print_details:
            print('\tOptimize lcb ...')
            print(f"\tlca = {lca:.5f}")
            print(f"\tlcb = {lcb:.5f}")
            print(f'\tIntensity = {abs_intensity}')
            print(f'\tIntensity Difference = {difference:.4f}%')

        return [lca, lcb, abs_intensity, difference]

    def optimize(self, state, lca_bound, lcb_bound, reference, thresh=None, n_iter=None):

        lca_lower_bound, lca_upper_bound, lcb_lower_bound, lcb_upper_bound = self._check_bounds(lca_bound, lcb_bound)

        if state == 'ext':
            optimal = []

            results_lca = self.opt_lca(self.calib.opt_lc, lca_lower_bound, lca_upper_bound,
                                       reference, (self.calib.PROPERTIES['LCA'], reference))

            set_lc(self.calib.mmc, results_lca[0], self.calib.PROPERTIES['LCA'])

            optimal.append(results_lca)

            results_lcb = self.opt_lcb(self.calib.opt_lc, lcb_lower_bound, lcb_upper_bound,
                                       reference, (self.calib.PROPERTIES['LCB'], reference))

            set_lc(self.calib.mmc, results_lcb[1], self.calib.PROPERTIES['LCB'])

            optimal.append(results_lcb)

            # ============BEGIN FINE SEARCH=================

            if self.calib.print_details:
                print(f'\n\tBeginning Finer Search\n')
            lca_lower_bound = results_lcb[0] - .01
            lca_upper_bound = results_lcb[0] + .01
            lcb_lower_bound = results_lcb[1] - .01
            lcb_upper_bound = results_lcb[1] + .01

            results_lca = self.opt_lca(self.calib.opt_lc, lca_lower_bound, lca_upper_bound,
                                       reference, (self.calib.PROPERTIES['LCA'], reference))

            set_lc(self.calib.mmc, results_lca[0], self.calib.PROPERTIES['LCA'])

            optimal.append(results_lca)

            results_lcb = self.opt_lcb(self.calib.opt_lc, lcb_lower_bound, lcb_upper_bound,
                                       reference, (self.calib.PROPERTIES['LCB'], reference))

            set_lc(self.calib.mmc, results_lcb[1], self.calib.PROPERTIES['LCB'])

            optimal.append(results_lcb)

            # Sometimes this optimization can drift away from the minimum,
            # this makes sure we use the lowest iteration
            optimal = np.asarray(optimal)
            #todo: figure out where the extra optimal[opt][0] indexing comes from
            opt = np.where(optimal == np.min(optimal[:][2]))[0]

            lca = float(optimal[opt][0][0])
            lcb = float(optimal[opt][0][1])
            results = optimal[opt][0]

        if state == '45' or state == '135':
            results = self.opt_lcb(self.calib.opt_lc, lcb_lower_bound, lcb_upper_bound,
                                   reference, (self.calib.PROPERTIES['LCB'], reference))

            lca = results[0]
            lcb = results[1]

        if state == '60':
            results = self.opt_lca(self.calib.opt_lc_cons, lca_lower_bound, lca_upper_bound,
                                   reference, (reference, '60'))

            swing = (self.calib.lca_ext - results[0]) * self.calib.ratio
            lca = results[0]
            lcb = self.calib.lcb_ext + swing

        if state == '90':
            results = self.opt_lca(self.calib.opt_lc, lca_lower_bound, lca_upper_bound,
                                       reference, (self.calib.PROPERTIES['LCA'], reference))
            lca = results[0]
            lcb = results[1]

        if state == '120':
            results = self.opt_lca(self.calib.opt_lc_cons, lca_lower_bound, lca_upper_bound,
                                   reference, (reference, '120'))

            swing = (self.calib.lca_ext - results[0]) * self.calib.ratio
            lca = results[0]
            lcb = self.calib.lcb_ext - swing

        return lca, lcb, results[2]

def optimize_grid(calib, a_min, a_max, b_min, b_max, step):
    """
    Exhaustive Search method

    Finds the minimum intensity value for a given
    grid of LCA,LCB values

    :param a_min: float
        Minimum value of LCA
    :param a_max: float
        Maximum value of LCA
    :param b_min: float
        Minimum value of LCB
    :param b_max: float
        Maximum value of LCB
    :param step: float
        step size of the grid between max/min values


    :return best_lca: float
        LCA value corresponding to lowest mean Intensity
    :return best_lcb: float
        LCB value corresponding to lowest mean Intensity
    :return min_int: float
        Lowest value of mean Intensity
    """

    min_int = 65536
    better_lca = -1
    better_lcb = -1

    # coarse search
    for lca in np.arange(a_min, a_max, step):
        for lcb in np.arange(b_min, b_max, step):

            set_lc(calib.mmc, lca, calib.PROPERTIES['LCA'])
            set_lc(calib.mmc, lcb, calib.PROPERTIES['LCB'])

            current_int = np.mean(snap_image(calib.mmc))

            if current_int < min_int:
                better_lca = lca
                better_lcb = lcb
                min_int = current_int
                if calib.print_details:
                    print("update (%f, %f, %f)" % (min_int, better_lca, better_lcb))

    if calib.print_details:
        print("coarse search done")
        print("better lca = " + str(better_lca))
        print("better lcb = " + str(better_lcb))
        print("better int = " + str(min_int))

    best_lca = better_lca
    best_lcb = better_lcb

    return best_lca, best_lcb, min_int