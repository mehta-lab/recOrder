import numpy as np
import matplotlib.pyplot as plt

def gather_empty_fov(data: AICSImageio, thresh=0.1, approx_focus = 0, plot=False):
    """ This function will loop through all positions times for given data object
    and compute the normalized log variance score at each FOV.  Function will then return
    an array of indices corresponding to the score less than the defined threshold.  This
    array is equivalent to the "empty" FOV

    :param data: Data Object
    :param thresh: (float) threshold for empty FOV.  Fraction of normalized log variance
    :param approx_focus: (int) Z-Slice to use.  Should be close to true focal plane for best results
    :param plot: (bool) plot normalized log variance

    :return: [array] of empty position or position+time indices
    """

    score = []
    pt_index = []
    # Loop through all positions, times, at specified z-plane
    for pos in range(data.size_p):
        if data.size_t != 1:
            for time in range(data.size_t):

                # If time dimension, append variance score for every p,t
                img = data.get_image_data('YX', S=pos, T=time, Z = approx_focus)
                score.append(np.var(img))
                pt_index.append((pos,time))

        else:

            # if no time dimension, append variance score for every p
            img = data.get_image_data('YX', S=pos, T=0, Z=approx_focus)
            score.append(np.var(img))

    # Compute normalized log of variance
    log_score = np.log(score)
    min = np.min(log_score)
    max = np.max(log_score)
    norm_log_score = (log_score - min) / (max-min)

    # Plot normalized-log variance score if desired
    if plot:
        plt.title('Normalized log(Variance)')
        plt.xlabel('Position Index')
        plt.ylabel('score')
        plt.plot(norm_log_score)
        plt.show()

    # if time dimension, gather empty pos,time indices
    if pt_index != None:
        empty_pt_index = []
        empty_fov_idx = np.where(norm_log_score < thresh)[0]

        for idx in empty_fov_idx:
            empty_pt_index.append(pt_index[idx])

        return np.asarray(empty_pt_index)

    # if no time dimension, gather empty pos indices
    else:
        empty_pos_idx = np.where(norm_log_score < thresh)[0]

        return np.as_array(empty_pos_idx)









